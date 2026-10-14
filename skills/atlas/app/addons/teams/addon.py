"""Teams: Microsoft Teams chats and channels inside Atlas (a proof of concept).

Signs in with Entra ID (authorization code with PKCE through the local Atlas, a public client with
delegated permissions, no secret) and talks to Microsoft Graph with the standard library. Teams
content stays out of the vault, git, the index and the agent chat: this module only passes it
from Graph to the view. The token lives in the addon's data directory, readable by the user only.

Settings in the vault's atlas.yaml:

    addons:
      teams:
        client_id: <the app registration's Application (client) ID>
        tenant: <the Directory (tenant) ID, or "organizations">
        channel_messages: true   # only once an admin consented to ChannelMessage.Read.All
        demo: true               # made-up people, chats and channels; no sign-in, no network
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"
# Reading channel posts needs ChannelMessage.Read.All, which only an admin can consent to; it is
# asked for only when the settings say the consent is there, so sign-in works without it.
SCOPES = ["openid", "profile", "offline_access", "User.Read", "Chat.Read", "ChatMessage.Send",
          "Team.ReadBasic.All", "Channel.ReadBasic.All", "ChannelMessage.Send"]
CHANNEL_READ = "ChannelMessage.Read.All"
PENDING_SECONDS = 600  # how long a started sign-in waits for its callback


class Throttled(Exception):
    """Graph answered 429 or 503: try again after `retry_after` seconds."""

    def __init__(self, retry_after: int):
        super().__init__(f"throttled for {retry_after}s")
        self.retry_after = retry_after


class GraphError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


# ---------------------------------------------------------------------------------------------
# Message text: Graph returns HTML. The view shows text only, so markup can never run.

class _Text(HTMLParser):
    BREAKS = {"br", "p", "div", "li", "tr", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BREAKS:
            self.parts.append("\n")
        elif tag == "at":  # Teams wraps @mentions in <at>
            self.parts.append("@")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(body: str) -> str:
    """The text of a message body, markup dropped; `<script>` and `<style>` dropped whole."""
    parser = _Text()
    parser.feed(body or "")
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def message_text(message: dict) -> str:
    body = message.get("body") or {}
    content = body.get("content") or ""
    return html_to_text(content) if body.get("contentType") == "html" else content.strip()


# ---------------------------------------------------------------------------------------------
# Sign-in: authorization code with PKCE.

def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


class TokenStore:
    """The signed-in account's tokens in one file, readable by the user only."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "token.json"

    def load(self) -> dict | None:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self, token: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(token, f)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:  # Windows keeps its own ACLs; the file sits in the user's profile
            pass

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def _post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except ValueError:
            err = {}
        # the error code and its description only: never the request, which holds the code
        raise GraphError(e.code, err.get("error", "sign_in_failed"), err.get("error_description", "").split("\r\n")[0])


class Account:
    """Entra ID sign-in and the Graph calls of one signed-in user."""

    def __init__(self, settings: dict, data_dir: Path, post_form=_post_form, opener=None):
        self.client_id = str(settings.get("client_id") or "")
        self.tenant = str(settings.get("tenant") or "organizations")
        self.scopes = SCOPES + ([CHANNEL_READ] if settings.get("channel_messages") else [])
        self.store = TokenStore(data_dir)
        self.post_form = post_form
        self.opener = opener or urllib.request.urlopen
        self.pending: dict[str, tuple[str, str, float]] = {}  # state -> (verifier, redirect_uri, started)
        self.blocked_until = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id)

    def login_url(self, redirect_uri: str) -> str:
        now = time.time()
        self.pending = {s: p for s, p in self.pending.items() if now - p[2] < PENDING_SECONDS}
        state = secrets.token_urlsafe(24)
        verifier, challenge = pkce_pair()
        self.pending[state] = (verifier, redirect_uri, now)
        query = urllib.parse.urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": redirect_uri,
            "response_mode": "query", "scope": " ".join(self.scopes), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account",
        })
        return f"{LOGIN}/{self.tenant}/oauth2/v2.0/authorize?{query}"

    def finish_login(self, state: str, code: str) -> None:
        pending = self.pending.pop(state, None)
        if not pending or time.time() - pending[2] >= PENDING_SECONDS:
            raise GraphError(400, "invalid_state", "This sign-in was not started here, or it expired. Start it again.")
        verifier, redirect_uri, _ = pending
        token = self.post_form(f"{LOGIN}/{self.tenant}/oauth2/v2.0/token", {
            "client_id": self.client_id, "grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri, "code_verifier": verifier, "scope": " ".join(self.scopes),
        })
        self._keep(token)

    def _keep(self, token: dict, previous: dict | None = None) -> None:
        self.store.save({
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token") or (previous or {}).get("refresh_token", ""),
            "expires_at": time.time() + int(token.get("expires_in", 3600)),
            "scope": token.get("scope", ""),
        })

    def sign_out(self) -> None:
        self.store.clear()

    def access_token(self) -> str | None:
        token = self.store.load()
        if not token:
            return None
        if token.get("expires_at", 0) - time.time() > 300:
            return token["access_token"]
        if not token.get("refresh_token"):
            return None
        try:
            fresh = self.post_form(f"{LOGIN}/{self.tenant}/oauth2/v2.0/token", {
                "client_id": self.client_id, "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"], "scope": " ".join(self.scopes),
            })
        except GraphError:
            self.store.clear()  # the refresh token was revoked or expired: sign in again
            return None
        self._keep(fresh, token)
        return fresh["access_token"]

    def signed_in(self) -> bool:
        return self.store.load() is not None

    def graph(self, method: str, path: str, body: dict | None = None) -> dict:
        """One Graph call. Raises Throttled on 429/503 (and refuses calls until it passes)."""
        wait = self.blocked_until - time.time()
        if wait > 0:
            raise Throttled(int(wait) + 1)
        token = self.access_token()
        if not token:
            raise GraphError(401, "signed_out", "Sign in to Microsoft first.")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(path if path.startswith("https://") else GRAPH + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with self.opener(req, timeout=20) as r:
                raw = r.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                retry = int(e.headers.get("Retry-After") or 10)
                self.blocked_until = time.time() + retry
                raise Throttled(retry)
            try:
                err = json.loads(e.read().decode("utf-8")).get("error", {})
            except ValueError:
                err = {}
            raise GraphError(e.code, err.get("code", "graph_error"), err.get("message", ""))


# ---------------------------------------------------------------------------------------------
# What the view gets: plain dicts with text, never Graph's HTML.

def _person(identity: dict | None) -> str:
    identity = identity or {}
    who = identity.get("user") or identity.get("application") or identity.get("device") or {}
    return who.get("displayName") or "Someone"


def chat_view(chat: dict, me: str) -> dict:
    members = [m.get("displayName") or "" for m in chat.get("members") or []]
    others = [m for m in members if m and m != me]
    preview = chat.get("lastMessagePreview") or {}
    return {
        "id": chat["id"],
        "title": chat.get("topic") or ", ".join(others) or "Chat",
        "kind": chat.get("chatType", "oneOnOne"),
        "members": members,
        "last": message_text(preview) if preview else "",
        "last_from": _person(preview.get("from")) if preview else "",
        "at": preview.get("createdDateTime") or chat.get("lastUpdatedDateTime") or "",
    }


def message_view(message: dict) -> dict:
    return {
        "id": message["id"],
        "from": _person(message.get("from")),
        "at": message.get("createdDateTime") or "",
        "text": message_text(message),
        "system": message.get("messageType") not in (None, "message"),
        "attachments": len(message.get("attachments") or []),
        "replies": len(message.get("replies") or []),
        "link": message.get("webUrl") or "",
    }


# ---------------------------------------------------------------------------------------------
# Demo: made-up people, chats and channels; no sign-in, no network.

class Demo:
    ME = "You"

    def __init__(self):
        t = "2026-10-14T"
        self.chats = {
            "c-mara": {"title": "Mara Lindqvist", "kind": "oneOnOne", "members": ["Mara Lindqvist", self.ME], "messages": [
                ("Mara Lindqvist", t + "09:40:00Z", "Lunch at 12:30? Then the deck review at 14:00."),
                (self.ME, t + "09:42:00Z", "Yes to both. I will bring the export fix.")]},
            "c-design": {"title": "Design review", "kind": "group", "members": ["Aiko Tanaka", "Lea Hoffmann", self.ME], "messages": [
                ("Aiko Tanaka", t + "08:02:00Z", "Onboarding v3 is in our library. Comments by Thursday, please."),
                ("Lea Hoffmann", t + "08:15:00Z", "I will go through it tomorrow morning.")]},
            "c-ben": {"title": "Ben Okafor", "kind": "oneOnOne", "members": ["Ben Okafor", self.ME], "messages": [
                ("Ben Okafor", "2026-10-13T16:05:00Z", "Thanks for the review, merged.")]},
        }
        self.teams = [
            {"id": "t-platform", "name": "Platform", "channels": [
                {"id": "ch-release", "name": "release-train", "posts": [
                    ("Jonas Petersen", t + "07:12:00Z", "Release 4.2 is cut. Smoke tests are green except the export job.", 3),
                    ("Mara Lindqvist", t + "07:20:00Z", "Can you check whether the export folder permissions changed?", 1)]},
                {"id": "ch-incidents", "name": "incidents", "posts": [
                    ("Ben Okafor", t + "06:52:00Z", "EU West shows degraded since 06:40. Backing off to 30 s.", 2)]}]},
            {"id": "t-design", "name": "Design", "channels": [
                {"id": "ch-reviews", "name": "reviews", "posts": [
                    ("Aiko Tanaka", t + "08:00:00Z", "The v3 flow is up for review.", 0)]}]},
        ]

    @staticmethod
    def _msg(i: int, who: str, at: str, text: str, replies: int = 0) -> dict:
        return {"id": f"m{i}", "from": who, "at": at, "text": text, "system": False,
                "attachments": 0, "replies": replies, "link": ""}

    def chat_list(self) -> list[dict]:
        out = []
        for cid, c in self.chats.items():
            who, at, text = c["messages"][-1]
            out.append({"id": cid, "title": c["title"], "kind": c["kind"], "members": c["members"],
                        "last": text, "last_from": who, "at": at})
        return sorted(out, key=lambda c: c["at"], reverse=True)

    def chat_messages(self, cid: str) -> list[dict]:
        return [self._msg(i, *m) for i, m in enumerate(self.chats[cid]["messages"])]

    def send_chat(self, cid: str, text: str) -> None:
        self.chats[cid]["messages"].append((self.ME, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), text))

    def team_list(self) -> list[dict]:
        return [{"id": t["id"], "name": t["name"], "channels": [{"id": c["id"], "name": c["name"]} for c in t["channels"]]}
                for t in self.teams]

    def _channel(self, tid: str, chid: str) -> dict:
        team = next(t for t in self.teams if t["id"] == tid)
        return next(c for c in team["channels"] if c["id"] == chid)

    def channel_posts(self, tid: str, chid: str) -> list[dict]:
        return [self._msg(i, *p) for i, p in enumerate(self._channel(tid, chid)["posts"])]

    def post_channel(self, tid: str, chid: str, text: str) -> None:
        self._channel(tid, chid)["posts"].append((self.ME, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), text, 0))


# ---------------------------------------------------------------------------------------------
# Routes, mounted by Atlas under /api/addons/teams/.

BACK = "/#/addon/teams"  # where the view lives in Atlas
MAX_TEXT = 20000


def _q(segment: str) -> str:
    return urllib.parse.quote(segment, safe=":@")


def _error(e: Exception) -> JSONResponse:
    if isinstance(e, Throttled):
        return JSONResponse({"error": "throttled", "retry_after": e.retry_after}, status_code=429,
                            headers={"Retry-After": str(e.retry_after)})
    if isinstance(e, GraphError):
        if e.code == "signed_out":
            return JSONResponse({"error": "signed_out"}, status_code=401)
        return JSONResponse({"error": e.code, "message": e.message}, status_code=e.status if e.status in (400, 403, 404) else 502)
    raise e


async def _text_of(request: Request) -> str | None:
    try:
        text = str((await request.json()).get("text") or "").strip()
    except ValueError:
        return None
    return text if 0 < len(text) <= MAX_TEXT else None


def register(ctx) -> list[Route]:
    settings = ctx.settings or {}
    demo = Demo() if settings.get("demo") else None
    account = Account(settings, ctx.data_dir)
    me: dict[str, str] = {}

    def my_name() -> str:
        if "name" not in me:
            me["name"] = account.graph("GET", "/me?$select=displayName,mail").get("displayName", "")
        return me["name"]

    async def state(request: Request):
        if demo:
            return JSONResponse({"configured": True, "demo": True, "signed_in": True, "user": Demo.ME, "channel_messages": True})
        signed_in = account.configured and account.signed_in()
        user = ""
        if signed_in:
            try:
                user = await run_in_threadpool(my_name)
            except (GraphError, Throttled):
                signed_in = account.signed_in()
        return JSONResponse({"configured": account.configured, "demo": False, "signed_in": signed_in, "user": user,
                             "channel_messages": CHANNEL_READ in account.scopes})

    async def login(request: Request):
        if demo or not account.configured:
            return RedirectResponse(BACK)
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        # Entra matches http://localhost on any port for a public client; 127.0.0.1 would need its own entry
        return RedirectResponse(account.login_url(f"http://localhost:{port}/api/addons/teams/callback"))

    async def callback(request: Request):
        params = request.query_params
        if params.get("error"):
            return RedirectResponse(BACK + "?error=" + urllib.parse.quote(params.get("error", "")))
        try:
            await run_in_threadpool(account.finish_login, params.get("state", ""), params.get("code", ""))
        except GraphError as e:
            return JSONResponse({"error": e.code, "message": e.message}, status_code=400)
        me.clear()
        return RedirectResponse(BACK)

    async def logout(request: Request):
        account.sign_out()
        me.clear()
        return JSONResponse({"ok": True})

    async def chats(request: Request):
        if demo:
            return JSONResponse({"chats": demo.chat_list()})

        def load():
            try:
                raw = account.graph("GET", "/me/chats?$expand=members,lastMessagePreview"
                                           "&$orderby=lastMessagePreview/createdDateTime%20desc&$top=50")
            except GraphError as e:
                if e.status != 400:
                    raise
                raw = account.graph("GET", "/me/chats?$expand=members&$top=50")  # a tenant that refuses the double expand
            name = my_name()
            return sorted((chat_view(c, name) for c in raw.get("value", [])), key=lambda c: c["at"], reverse=True)

        try:
            return JSONResponse({"chats": await run_in_threadpool(load)})
        except (GraphError, Throttled) as e:
            return _error(e)

    async def chat_messages(request: Request):
        cid = request.path_params["cid"]
        if demo:
            if cid not in demo.chats:
                return JSONResponse({"error": "not_found"}, status_code=404)
            if request.method == "POST":
                text = await _text_of(request)
                if text is None:
                    return JSONResponse({"error": "empty"}, status_code=400)
                demo.send_chat(cid, text)
            return JSONResponse({"messages": demo.chat_messages(cid)})
        try:
            if request.method == "POST":
                text = await _text_of(request)
                if text is None:
                    return JSONResponse({"error": "empty"}, status_code=400)
                await run_in_threadpool(account.graph, "POST", f"/chats/{_q(cid)}/messages",
                                        {"body": {"contentType": "text", "content": text}})
            raw = await run_in_threadpool(account.graph, "GET", f"/me/chats/{_q(cid)}/messages?$top=50")
            items = sorted((message_view(m) for m in raw.get("value", [])), key=lambda m: m["at"])
            return JSONResponse({"messages": items})
        except (GraphError, Throttled) as e:
            return _error(e)

    async def teams(request: Request):
        if demo:
            return JSONResponse({"teams": demo.team_list()})

        def load():
            out = []
            for team in account.graph("GET", "/me/joinedTeams?$select=id,displayName").get("value", []):
                channels = account.graph("GET", f"/teams/{_q(team['id'])}/channels?$select=id,displayName").get("value", [])
                out.append({"id": team["id"], "name": team.get("displayName", ""),
                            "channels": [{"id": c["id"], "name": c.get("displayName", "")} for c in channels]})
            return out

        try:
            return JSONResponse({"teams": await run_in_threadpool(load)})
        except (GraphError, Throttled) as e:
            return _error(e)

    async def channel_messages(request: Request):
        tid, chid = request.path_params["tid"], request.path_params["chid"]
        if demo:
            try:
                if request.method == "POST":
                    text = await _text_of(request)
                    if text is None:
                        return JSONResponse({"error": "empty"}, status_code=400)
                    demo.post_channel(tid, chid, text)
                return JSONResponse({"messages": demo.channel_posts(tid, chid)})
            except StopIteration:
                return JSONResponse({"error": "not_found"}, status_code=404)
        base = f"/teams/{_q(tid)}/channels/{_q(chid)}/messages"
        try:
            if request.method == "POST":
                text = await _text_of(request)
                if text is None:
                    return JSONResponse({"error": "empty"}, status_code=400)
                await run_in_threadpool(account.graph, "POST", base, {"body": {"contentType": "text", "content": text}})
            if CHANNEL_READ not in account.scopes:
                return JSONResponse({"error": "consent", "needs": CHANNEL_READ}, status_code=403)
            raw = await run_in_threadpool(account.graph, "GET", base + "?$top=20&$expand=replies")
            items = sorted((message_view(m) for m in raw.get("value", [])), key=lambda m: m["at"])
            return JSONResponse({"messages": items})
        except GraphError as e:
            if e.status == 403:
                return JSONResponse({"error": "consent", "needs": CHANNEL_READ}, status_code=403)
            return _error(e)
        except Throttled as e:
            return _error(e)

    return [
        Route("/state", state),
        Route("/login", login),
        Route("/callback", callback),
        Route("/logout", logout, methods=["POST"]),
        Route("/chats", chats),
        Route("/chats/{cid}/messages", chat_messages, methods=["GET", "POST"]),
        Route("/teams", teams),
        Route("/channels/{tid}/{chid}/messages", channel_messages, methods=["GET", "POST"]),
    ]
