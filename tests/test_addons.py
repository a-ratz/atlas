"""Addons (#54): the loader (#55) and the Teams addon (#56-#59), over its demo data and fakes; no network."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import urllib.error
from argparse import Namespace

import pytest
from conftest import APP
from starlette.testclient import TestClient

HEADER = {"x-atlas": "1"}


def switch_on(vault, block: str) -> None:
    reg = vault / "atlas.yaml"
    reg.write_text(reg.read_text(encoding="utf-8") + "\naddons:\n" + block, encoding="utf-8")


def client(engine):
    return TestClient(engine.make_app(engine.Index()), base_url="http://127.0.0.1")


@pytest.fixture
def teams_module():
    spec = importlib.util.spec_from_file_location("teams_addon_under_test", APP / "addons" / "teams" / "addon.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def addon_data(engine, tmp_path, monkeypatch):
    path = tmp_path / "addon-data"
    monkeypatch.setattr(engine, "ADDON_DATA", path)
    return path


# ------------------------------------------------------------------ the loader

def test_a_vault_without_addons_mounts_none(engine, vault):
    c = client(engine)
    assert c.get("/api/meta").json()["addons"] == []
    assert c.get("/api/addons/teams/state").status_code == 404


def test_an_addon_the_vault_does_not_switch_on_is_never_imported(engine, vault, tmp_path, monkeypatch):
    root = tmp_path / "addons"
    (root / "probe").mkdir(parents=True)
    marker = tmp_path / "imported"
    (root / "probe" / "addon.yaml").write_text("title: Probe\n", encoding="utf-8")
    (root / "probe" / "addon.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n"
                                             "def register(ctx):\n    return []\n", encoding="utf-8")
    monkeypatch.setattr(engine, "ADDONS", root)
    switch_on(vault, "  probe:\n    enabled: false\n")
    assert engine.load_addons() == []
    assert not marker.exists()


def test_a_broken_addon_is_reported_and_atlas_keeps_running(engine, vault, tmp_path, monkeypatch, capsys):
    root = tmp_path / "addons"
    (root / "broken").mkdir(parents=True)
    (root / "broken" / "addon.yaml").write_text("title: Broken\n", encoding="utf-8")
    (root / "broken" / "addon.py").write_text("raise ImportError('no such library')\n", encoding="utf-8")
    monkeypatch.setattr(engine, "ADDONS", root)
    switch_on(vault, "  broken: {}\n  ../engine: {}\n")
    meta = client(engine).get("/api/meta")
    assert meta.status_code == 200
    rows = {a["name"]: a for a in meta.json()["addons"]}
    assert "no such library" in rows["broken"]["error"]
    assert "no addon called" in rows["../engine"]["error"]  # a name is never a path
    engine.cmd_status(Namespace())
    assert "no such library" in json.loads(capsys.readouterr().out)["addons"]["broken"]


def test_writes_to_an_addon_need_the_atlas_header(engine, vault, addon_data):
    switch_on(vault, "  teams:\n    demo: true\n")
    c = client(engine)
    url = "/api/addons/teams/chats/c-mara/messages"
    assert c.post(url, json={"text": "hello"}).status_code == 403
    sent = c.post(url, json={"text": "hello"}, headers=HEADER)
    assert sent.status_code == 200
    assert sent.json()["messages"][-1]["text"] == "hello"


# ------------------------------------------------------------------ Teams over the demo data

def test_teams_demo_shows_chats_and_channels_and_takes_posts(engine, vault, addon_data):
    switch_on(vault, "  teams:\n    demo: true\n")
    c = client(engine)
    meta = {a["name"]: a for a in c.get("/api/meta").json()["addons"]}
    assert meta["teams"]["title"] == "Teams" and meta["teams"]["view"].startswith("/addons/teams/view.js")
    assert c.get(meta["teams"]["view"]).status_code == 200
    assert c.get("/api/addons/teams/state").json()["signed_in"] is True
    chats = c.get("/api/addons/teams/chats").json()["chats"]
    assert [x["title"] for x in chats][0] == "Mara Lindqvist"  # the newest first
    teams = c.get("/api/addons/teams/teams").json()["teams"]
    channel = teams[0]["channels"][0]
    url = f"/api/addons/teams/channels/{teams[0]['id']}/{channel['id']}/messages"
    posts = c.get(url).json()["messages"]
    assert posts[0]["replies"] == 3
    after = c.post(url, json={"text": "on it"}, headers=HEADER).json()["messages"]
    assert after[-1]["text"] == "on it" and len(after) == len(posts) + 1
    assert c.post(url, json={"text": "   "}, headers=HEADER).status_code == 400


def test_message_html_is_shown_as_text(teams_module):
    text = teams_module.html_to_text('<p>Hi <at>Mara</at></p><script>alert("x")</script>'
                                     '<img src=x onerror="alert(1)">see&nbsp;<b>this</b>&lt;tag&gt;')
    assert "<" not in text.replace("<tag>", "") and "alert" not in text
    assert text == "Hi @Mara\nsee this<tag>"
    view = teams_module.message_view({"id": "1", "body": {"contentType": "html", "content": "<div>a<br>b</div>"},
                                      "from": {"user": {"displayName": "Lea"}}})
    assert view == {"id": "1", "from": "Lea", "at": "", "text": "a\nb", "system": False,
                    "attachments": 0, "replies": 0, "link": ""}


# ------------------------------------------------------------------ sign-in

def test_a_callback_with_a_wrong_state_is_refused(engine, vault, addon_data):
    switch_on(vault, "  teams:\n    client_id: 00000000-0000-0000-0000-000000000001\n    tenant: example\n")
    c = client(engine)
    start = c.get("/api/addons/teams/login", follow_redirects=False)
    assert start.status_code in (302, 307)
    target = start.headers["location"]
    assert target.startswith("https://login.microsoftonline.com/example/oauth2/v2.0/authorize?")
    assert "code_challenge_method=S256" in target and "redirect_uri=http%3A%2F%2Flocalhost" in target
    assert "ChannelMessage.Read.All" not in target  # only once an admin consented
    bad = c.get("/api/addons/teams/callback?state=forged&code=abc")
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_state"
    assert not (addon_data / "teams" / "token.json").exists()


def test_the_token_stays_outside_the_vault_refreshes_and_goes_on_sign_out(teams_module, vault, tmp_path, monkeypatch):
    calls = []

    def post_form(url, fields):
        calls.append(fields["grant_type"])
        return {"access_token": f"access-{len(calls)}", "refresh_token": "refresh", "expires_in": 3600}

    data = tmp_path / "addon-data" / "teams"
    account = teams_module.Account({"client_id": "id", "tenant": "t"}, data, post_form=post_form)
    url = account.login_url("http://localhost:8765/api/addons/teams/callback")
    state = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&"))["state"]
    account.finish_login(state, "the-code")
    token_file = data / "token.json"
    assert token_file.exists() and vault not in token_file.parents
    if os.name == "posix":
        assert token_file.stat().st_mode & 0o777 == 0o600
    with pytest.raises(teams_module.GraphError):
        account.finish_login(state, "the-code")  # a state works once
    saved = json.loads(token_file.read_text(encoding="utf-8"))
    saved["expires_at"] = 0
    token_file.write_text(json.dumps(saved), encoding="utf-8")
    assert account.access_token() == "access-2" and calls == ["authorization_code", "refresh_token"]
    account.sign_out()
    assert not token_file.exists() and account.access_token() is None


def test_a_missing_client_id_shows_the_setup_steps(engine, vault, addon_data):
    switch_on(vault, "  teams: {}\n")
    state = client(engine).get("/api/addons/teams/state").json()
    assert state["configured"] is False and state["signed_in"] is False


# ------------------------------------------------------------------ Graph

def test_throttling_slows_down_instead_of_failing(teams_module, tmp_path):
    opened = []

    def opener(req, timeout):
        opened.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "7"}, io.BytesIO(b""))

    account = teams_module.Account({"client_id": "id"}, tmp_path, opener=opener)
    account.store.save({"access_token": "a", "refresh_token": "r", "expires_at": 9e12})
    with pytest.raises(teams_module.Throttled) as first:
        account.graph("GET", "/me/chats")
    assert first.value.retry_after == 7
    with pytest.raises(teams_module.Throttled):
        account.graph("GET", "/me/chats")
    assert len(opened) == 1  # the second call waits instead of asking again
    answer = teams_module._error(first.value)
    assert answer.status_code == 429 and answer.headers["retry-after"] == "7"


def test_channels_without_consent_say_so_and_chats_keep_working(engine, vault, addon_data):
    switch_on(vault, "  teams:\n    client_id: id\n    tenant: example\n")
    c = client(engine)
    blocked = c.get("/api/addons/teams/channels/team/19%3Aabc%40thread.tacv2/messages")
    assert blocked.status_code == 403 and blocked.json() == {"error": "consent", "needs": "ChannelMessage.Read.All"}
    assert c.get("/api/addons/teams/chats").status_code == 401  # signed out, not broken


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_the_token_file_is_never_world_readable_even_when_replaced(teams_module, tmp_path):
    store = teams_module.TokenStore(tmp_path)
    store.save({"access_token": "a"})
    os.chmod(store.path, 0o644)
    store.save({"access_token": "b"})
    assert store.path.stat().st_mode & 0o777 == 0o600


# ------------------------------------------------------------------ review round 1 on #60, one test per finding

def fake_teams_app(teams_module, tmp_path, graph, settings=None):
    """The Teams routes over a fake Graph: `graph(method, path, body)` answers or raises."""
    from starlette.applications import Starlette
    from starlette.routing import Mount

    class Ctx:
        pass
    ctx = Ctx()
    ctx.name, ctx.data_dir = "teams", tmp_path / "data"
    ctx.settings = settings or {"client_id": "id", "tenant": "t", "channel_messages": True}
    teams_module.Account.graph = lambda self, method, path, body=None: graph(method, path, body)
    app = Starlette(routes=[Mount("/api/addons/teams", routes=teams_module.register(ctx))])
    return TestClient(app, base_url="http://127.0.0.1")


def test_the_registered_redirect_uri_is_the_one_sign_in_uses(engine, vault, addon_data):
    switch_on(vault, "  teams:\n    client_id: id\n    tenant: t\n")
    target = client(engine).get("/api/addons/teams/login", follow_redirects=False).headers["location"]
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A" in target and "%2Fapi%2Faddons%2Fteams%2Fcallback" in target
    registered = "http://localhost/api/addons/teams/callback"  # Entra ignores the port for localhost, not the path
    for doc in ("README.md", "static/view.js"):
        assert registered in (APP / "addons" / "teams" / doc).read_text(encoding="utf-8"), doc


def test_a_refused_channel_post_is_an_error_not_a_consent_notice(teams_module, tmp_path):
    def graph(method, path, body):
        if method == "POST":
            raise teams_module.GraphError(403, "Forbidden", "posting is limited to moderators")
        return {"value": []}
    c = fake_teams_app(teams_module, tmp_path, graph)
    r = c.post("/api/addons/teams/channels/t1/c1/messages", json={"text": "hello"})
    assert r.status_code == 403 and r.json()["error"] == "post_refused"


def test_an_accepted_message_stays_sent_when_the_refresh_after_it_fails(teams_module, tmp_path):
    def graph(method, path, body):
        if method == "POST":
            return {"id": "new"}
        raise teams_module.Throttled(5)
    c = fake_teams_app(teams_module, tmp_path, graph)
    for url in ("/api/addons/teams/chats/19%3Aa%40thread.v2/messages", "/api/addons/teams/channels/t1/c1/messages"):
        r = c.post(url, json={"text": "hello"})
        assert r.status_code == 200 and r.json() == {"sent": True, "messages": None}, url


def test_sign_out_waits_for_a_refresh_in_flight_and_wins(teams_module, tmp_path):
    import threading
    import time as clock
    started, go = threading.Event(), threading.Event()

    def post_form(url, fields):
        started.set()
        go.wait(5)
        return {"access_token": "fresh", "refresh_token": "r", "expires_in": 3600}

    account = teams_module.Account({"client_id": "id"}, tmp_path, post_form=post_form)
    account.store.save({"access_token": "old", "refresh_token": "r", "expires_at": 0})
    refresh = threading.Thread(target=account.access_token)
    refresh.start()
    started.wait(5)
    out = threading.Thread(target=account.sign_out)
    out.start()
    clock.sleep(0.1)
    go.set()
    refresh.join(5)
    out.join(5)
    assert not account.store.path.exists()  # signed out stays signed out


def test_saves_that_overlap_do_not_trip_over_one_temporary_file(teams_module, tmp_path):
    import threading
    store, errors = teams_module.TokenStore(tmp_path), []

    def save(i):
        try:
            for _ in range(50):
                store.save({"access_token": str(i)})
        except OSError as e:
            errors.append(e)
    threads = [threading.Thread(target=save, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and store.load()["access_token"] in {"0", "1", "2", "3"}


def test_a_busy_token_endpoint_keeps_the_refresh_token_a_revoked_one_does_not(teams_module, tmp_path):
    answers = [teams_module.GraphError(503, "temporarily_unavailable", ""), teams_module.GraphError(0, "network", ""),
               teams_module.GraphError(400, "invalid_grant", "")]

    def post_form(url, fields):
        raise answers.pop(0)

    account = teams_module.Account({"client_id": "id"}, tmp_path, post_form=post_form)
    account.store.save({"access_token": "old", "refresh_token": "r", "expires_at": 0})
    for _ in range(2):
        with pytest.raises(teams_module.Throttled):
            account.access_token()
        assert account.store.load()["refresh_token"] == "r"
    assert account.access_token() is None and account.store.load() is None


# ------------------------------------------------------------------ review round 2 on #60

def test_signing_out_never_blocks_other_requests(teams_module, tmp_path):
    import threading
    import time as clock

    def slow_sign_out(self):  # as if it waited for a refresh in flight that holds the lock
        clock.sleep(1.0)
        self.store.clear()

    teams_module.Account.sign_out = slow_sign_out
    with fake_teams_app(teams_module, tmp_path, lambda method, path, body: {"value": []}) as c:  # one event loop
        out = threading.Thread(target=lambda: c.post("/api/addons/teams/logout"))
        out.start()
        clock.sleep(0.1)
        started = clock.monotonic()
        assert c.get("/api/addons/teams/chats").status_code == 200
        waited = clock.monotonic() - started
        out.join(5)
    assert waited < 0.6, f"another request waited {waited:.2f}s for the sign-out"
