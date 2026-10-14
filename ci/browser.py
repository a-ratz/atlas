#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "PyYAML==6.0.3",
#   "playwright==1.55.0",
# ]
# ///
"""Browser smoke: the app renders every page without a console error, in both themes.

Serves the demo vault in operator mode, opens Home, the operator page, the projects, the
constellation, Rediscover, every type's list and a sample of entities in a headless Chromium,
once with a dark and once with a light color scheme. Any console error or uncaught exception
fails the run. A few checks pin behavior that reviews found broken once.

    uv run ci/browser.py              # needs: uv run --with playwright==1.55.0 playwright install chromium
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import Server, atlas, demo_vault  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

failures: list[str] = []


def routes(srv: Server) -> list[str]:
    out = ["#/", "#/chat", "#/projects", "#/graph", "#/rediscover", "#/search?q=memory"]
    for t in srv.get("/api/meta")["types"]:
        if t.get("nav") is False:
            continue
        out.append(f"#/t/{urllib.parse.quote(t['id'])}")
        for item in srv.get(f"/api/list?type={urllib.parse.quote(t['id'])}").get("items", [])[:2]:
            out.append(f"#/e/{urllib.parse.quote(item['id'], safe='')}")
    return out


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # a Windows console or pipe would refuse "→" and "×" as cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    with tempfile.TemporaryDirectory() as tmp:
        vault = demo_vault(Path(tmp))
        with Server(vault, operator=True) as srv, sync_playwright() as pw:
            pages = routes(srv)
            browser = pw.chromium.launch()
            for scheme in ("dark", "light"):
                ctx = browser.new_context(color_scheme=scheme, viewport={"width": 1280, "height": 860})
                page = ctx.new_page()
                errors: list[str] = []
                page.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
                page.on("pageerror", lambda e: errors.append(f"exception: {e}"))
                for route in pages:
                    errors.clear()
                    page.goto(f"{srv.base}/{route}")
                    page.wait_for_function("document.querySelector('#main, main')?.children.length > 0", timeout=15000)
                    page.wait_for_timeout(300)  # late renders: cards, graph, streamed chat
                    if page.query_selector("text=Could not load this view"):  # the router's catch-all, no console error
                        errors.append("the view failed to render: " + page.inner_text("#main, main")[:200])
                    for e in errors:
                        failures.append(f"[{scheme}] {route}: {e}")
                checks(page, srv.base, scheme)
                if scheme == "light":  # the last pass: it edits and moves a demo note
                    follows_changes(ctx, srv, vault)
                    move_waits_for_its_own_answer(ctx, srv, vault)
                    move_ignores_late_history(ctx, srv, vault)
                    moves_release(ctx, srv, vault)
                ctx.close()
            empty_home_lists_notes(browser, Path(tmp))
            browser.close()
            print(f"{len(pages)} pages × 2 color schemes opened")
    for f in failures:
        print(f"FAIL {f}")
    if failures:
        sys.exit(f"\n{len(failures)} browser problem(s)")
    print("ok   every page renders without a console error, dark and light")


def checks(page, base: str, scheme: str) -> None:
    """Behavior a review found broken once (#4); each check names its finding."""
    page.goto(f"{base}/#/t/question?status=open")
    page.wait_for_selector("#list", timeout=15000)
    page.wait_for_timeout(300)
    on = page.eval_on_selector_all(".facet.on", "els => els.map(e => e.textContent)")
    if not any(t.startswith("open") for t in on):
        failures.append(f"[{scheme}] a status from the link shows no active chip (#4, round 2)")
    if not page.query_selector('.nav-link.active[data-t="question"]'):
        failures.append(f"[{scheme}] the sidebar does not mark a link with a query (#4, round 2)")
    deep_after_nothing(page, base, scheme)
    page.goto(f"{base}/#/chat")
    page.wait_for_selector(".op-bar", timeout=15000)
    if not page.query_selector("#op-title"):
        failures.append(f"[{scheme}] the operator bar has no title slot (#1)")
    if "starting" not in page.inner_text("#presence"):  # the browser smoke serves without an agent
        failures.append(f"[{scheme}] a session whose agent has not listened yet does not say starting (#10)")
    chip = page.query_selector(".chat-welcome [data-prefill]")  # same helper as Home's chips on an empty vault
    if not chip:
        failures.append(f"[{scheme}] the empty chat shows no suggestion chips to check (#10)")
        return
    chip.click()
    box = page.evaluate("(() => { const i = document.activeElement; return [i.value, i.value.slice(i.selectionStart, i.selectionEnd)]; })()")
    if "…" in box[0] or not box[1]:
        failures.append(f"[{scheme}] a Home chip put {box[0]!r} in the box, selecting {box[1]!r} (#10)")
    page.goto(f"{base}/#/e/{urllib.parse.quote('questions/can-tmr-work-without-eeg.md', safe='')}")
    page.wait_for_selector(".meta-row", timeout=15000)
    row = page.inner_text(".meta-row")
    if "[[" in row or "raised_count" in row or not page.query_selector(".meta-row a[href^='#/e/insights']"):
        failures.append(f"[{scheme}] the facts line shows {row!r} instead of a linked title (#10)")
    if scheme != "light":  # pressing a move writes to the chat, which the next pass expects empty
        return
    page.click(".moves-bar [data-via='move']:has-text('Later')")
    try:
        page.wait_for_selector(".moves-bar.sent .sent-note", timeout=5000)
        if page.eval_on_selector_all(".moves-bar button", "bs => bs.some((b) => !b.disabled)"):
            failures.append(f"[{scheme}] a pressed move leaves the other buttons on (#10)")
    except Exception:
        failures.append(f"[{scheme}] pressing Later shows nothing on the page, only a toast (#10)")


def follows_changes(ctx, srv: Server, vault: Path) -> None:
    """An open page shows the agent's edit and follows a move, keeping its scroll position (#13, #14).
    The index looks every 10 seconds."""
    ctx.add_init_script("""window.__keydown = { on: 0, added: 0 };  // key handlers on document: a re-render leaves none behind
      for (const [name, step] of [["addEventListener", 1], ["removeEventListener", -1]]) {
        const real = document[name].bind(document);
        document[name] = (type, fn, opts) => {
          if (type === "keydown") { window.__keydown.on += step; if (step > 0) window.__keydown.added++; }
          return real(type, fn, opts);
        };
      }""")
    page = ctx.new_page()
    item = srv.get("/api/list?type=capture")["items"][0]
    page.goto(f"{srv.base}/#/e/{urllib.parse.quote(item['id'], safe='')}")
    page.wait_for_selector(".reader", timeout=15000)
    path = vault / item["id"]
    filler = "".join(f"\n\nA paragraph the agent added, number {n}." for n in range(40))
    path.write_text(path.read_text(encoding="utf-8") + filler + "\n\nAn edit the agent made while the page was open.\n",
                    encoding="utf-8")
    try:
        page.wait_for_selector("text=An edit the agent made while the page was open.", timeout=25000)
    except Exception:
        failures.append("an open note did not show the agent's edit (#13)")
        return
    page.evaluate("scrollTo(0, 600)")
    path.write_text(path.read_text(encoding="utf-8") + "\n\nA second edit.\n", encoding="utf-8")
    try:
        page.wait_for_selector("text=A second edit.", timeout=25000)
        if abs(page.evaluate("scrollY") - 600) > 5:
            failures.append(f"an edit scrolled the open note to {page.evaluate('scrollY')} instead of 600 (#13)")
    except Exception:
        failures.append("an open note did not show the agent's second edit (#13)")
    moved = vault / "sources" / path.name
    moved.parent.mkdir(exist_ok=True)
    path.rename(moved)
    try:
        page.wait_for_function("decodeURIComponent(location.hash).startsWith('#/e/sources/')", timeout=25000)
        page.wait_for_selector(".reader[data-src^='sources/']", timeout=15000)
        if abs(page.evaluate("scrollY") - 600) > 5:
            failures.append(f"following a move scrolled to {page.evaluate('scrollY')} instead of 600 (#14, round 1)")
    except Exception:
        failures.append("an open note the agent moved did not follow it to its new folder (#13)")
    page.goto(f"{srv.base}/#/e/{urllib.parse.quote('tours/this-week.md', safe='')}")
    page.wait_for_timeout(800)
    before = page.evaluate("window.__keydown")
    tour = vault / "tours" / "this-week.md"
    tour.write_text(tour.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    try:
        page.wait_for_function(f"window.__keydown.added > {before['added']}", timeout=25000)  # the tour re-rendered
        if page.evaluate("window.__keydown.on") != before["on"]:
            failures.append("re-rendering a tour left its old key handlers on the page (#14, review round 1)")
    except Exception:
        failures.append("an open tour did not re-render after the agent changed it (#13)")
    page.close()
    left_refresh(ctx, srv, vault, moved.relative_to(vault).as_posix())


def left_refresh(ctx, srv: Server, vault: Path, rel: str) -> None:
    """A refresh the reader leaves (Home while the note reloads) must not scroll the note when it is opened
    again (#14, review round 2)."""
    page = ctx.new_page()
    url = f"{srv.base}/#/e/{urllib.parse.quote(rel, safe='')}"
    page.goto(url)
    page.wait_for_selector(".reader", timeout=15000)
    page.evaluate("scrollTo(0, 600)")
    held, seen = [], []
    def hold_second(route):  # the refresh's first request answers; its re-render's request waits
        seen.append(route)
        held.append(route) if len(seen) == 2 else route.continue_()
    page.route("**/api/entity?*", hold_second)
    (vault / rel).write_text((vault / rel).read_text(encoding="utf-8") + "\n\nA third edit.\n", encoding="utf-8")
    for _ in range(125):
        if held:
            break
        page.wait_for_timeout(200)
    else:
        failures.append("the left-refresh check never saw the re-render's request")
        page.close()
        return
    page.evaluate("location.hash = '#/'")
    page.wait_for_timeout(500)
    held[0].continue_()
    page.wait_for_timeout(500)
    page.unroute("**/api/entity?*")
    page.evaluate(f"location.hash = {json.dumps('#/e/' + urllib.parse.quote(rel, safe=''))}")
    page.wait_for_selector(".reader", timeout=15000)
    page.wait_for_timeout(300)
    if page.evaluate("scrollY") != 0:
        failures.append(f"a note opened at {page.evaluate('scrollY')}, the position of a refresh the reader left "
                        "(#14, review round 2)")
    page.close()


def empty_home_lists_notes(browser, tmp: Path) -> None:
    """A fresh vault keeps its welcome, and a reminder the agent wrote shows under it as "Needs you"
    (#18, smoke run first-run)."""
    import shutil
    from gate import APP
    vault = tmp / "fresh" / "vault"
    shutil.copytree(APP / "vault", vault, ignore=shutil.ignore_patterns(".atlas"))
    (vault / "you" / "notes").mkdir(parents=True, exist_ok=True)
    (vault / "you" / "notes" / "2026-10-14-000000-remind-spaced-repetition.md").write_text(
        "---\nfrom: user\naction: remind\ncreated: 2026-10-14T00:00:00+00:00\nstatus: new\n---\n\n"
        "Remember to look into spaced repetition\n", encoding="utf-8")
    with Server(vault, operator=True) as srv:
        page = browser.new_page()
        page.goto(f"{srv.base}/#/")
        try:
            page.wait_for_selector(".empty-hero .empty-needs", timeout=10000)
            if "spaced repetition" not in page.inner_text(".empty-needs"):
                failures.append("the empty Home's Needs you does not show the reminder (#18)")
        except Exception:
            failures.append("a fresh vault's Home does not show a new reminder under Needs you (#18)")
        page.close()


def move_waits_for_its_own_answer(ctx, srv: Server, vault: Path) -> None:
    """A sent move waits for an answer that came after it, from the agent it went to (#18, review round 2):
    not an answer that was already there (same second), and not the agent the user picks while it is sent."""
    import datetime as dt
    import json
    import os
    import time
    presence = vault / ".atlas" / "agents"
    presence.mkdir(parents=True, exist_ok=True)
    for name in ("claude", "codex"):  # both listen
        (presence / f"{name}.beat").touch()
        os.utime(presence / f"{name}.beat", (time.time() + 600, time.time() + 600))
    later = (dt.datetime.now().astimezone() + dt.timedelta(seconds=20)).isoformat(timespec="seconds")
    with open(vault / ".atlas" / "outbox.jsonl", "a", encoding="utf-8") as f:  # an answer stamped after the press
        f.write(json.dumps({"ts": later, "role": "agent", "agent": "claude", "text": "An answer from before"}) + "\n")
    page = ctx.new_page()
    page.goto(f"{srv.base}/#/e/{urllib.parse.quote('questions/can-tmr-work-without-eeg.md', safe='')}")
    page.wait_for_selector(".moves-bar", timeout=15000)
    page.evaluate("localStorage.setItem('atlas.to', JSON.stringify('claude'))")
    page.wait_for_timeout(2500)  # presence and chat loaded
    held = []
    page.route("**/api/chat", lambda r: held.append(r) if r.request.method == "POST" else r.continue_())
    page.click(".moves-bar [data-via='move']:has-text('Research this')")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    page.evaluate("localStorage.setItem('atlas.to', JSON.stringify('codex'))")  # the user picks codex meanwhile
    if held:
        held[0].continue_()
    page.unroute("**/api/chat")
    page.wait_for_selector(".moves-bar.sent", timeout=5000)
    atlas(vault, "say", "Something else entirely.", "--agent", "codex")
    page.wait_for_timeout(3500)
    if not page.query_selector(".moves-bar.sent"):
        failures.append("a sent move was freed by an earlier answer or another agent's (#18, review round 2)")
    atlas(vault, "say", "Researching it.", "--agent", "claude")
    try:
        page.wait_for_selector(".moves-bar.sent", state="detached", timeout=10000)
    except Exception:
        failures.append("a sent move stays locked after the answer of the agent it went to (#18, review round 2)")
    page.evaluate("localStorage.removeItem('atlas.to')")
    page.close()


def move_ignores_late_history(ctx, srv: Server, vault: Path) -> None:
    """An answer written before the move but loaded after it (a slow chat request) does not free the move
    (#18, review round 3)."""
    import os
    import time
    beat = vault / ".atlas" / "agents" / "claude.beat"
    beat.touch()
    os.utime(beat, (time.time() + 600, time.time() + 600))  # claude listens
    page = ctx.new_page()
    page.goto(f"{srv.base}/#/e/{urllib.parse.quote('questions/do-cues-disturb-sleep.md', safe='')}")
    page.wait_for_selector(".moves-bar", timeout=15000)
    page.evaluate("localStorage.setItem('atlas.to', JSON.stringify('claude'))")
    page.wait_for_timeout(2500)
    held, holding = [], [True]
    page.route("**/api/chat", lambda r: held.append(r) if holding[0] and r.request.method == "GET" else r.continue_())
    atlas(vault, "say", "An answer from before the move.", "--agent", "claude")
    page.wait_for_timeout(2200)  # the click lands in a later second than that answer
    page.click(".moves-bar [data-via='move']:has-text('Research this')")
    page.wait_for_selector(".moves-bar.sent", timeout=5000)
    holding[0] = False
    for r in held:  # the history arrives now, the earlier answer in it
        r.continue_()
    page.wait_for_timeout(3500)
    page.unroute("**/api/chat")
    if not held:
        failures.append("the late-history check held no chat request (#18, review round 3)")
    elif not page.query_selector(".moves-bar.sent"):
        failures.append("an answer from before the move, loaded late, freed it (#18, review round 3)")
    atlas(vault, "say", "On it.", "--agent", "claude")
    try:
        page.wait_for_selector(".moves-bar.sent", state="detached", timeout=10000)
    except Exception:
        failures.append("a sent move stays locked after its agent's answer (#18, review round 3)")
    page.evaluate("localStorage.removeItem('atlas.to')")
    page.close()


def moves_release(ctx, srv: Server, vault: Path) -> None:
    """A pressed move frees its bar when its agent answers, whatever another agent is doing; standalone Atlas
    locks nothing; a quoted passage stays as it is (#18, review round 1)."""
    import datetime as dt
    import json
    import os
    import time
    presence = vault / ".atlas" / "agents"
    presence.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for name, at in (("claude", now + 600), ("codex", now - 60)):  # claude listens; codex listened a minute ago
        (presence / f"{name}.beat").touch()
        os.utime(presence / f"{name}.beat", (at, at))
    with open(vault / ".atlas" / "inbox.jsonl", "a", encoding="utf-8") as f:  # ... and works on a request of its own
        f.write(json.dumps({"ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "role": "user",
                            "kind": "message", "text": "Research something else", "to": "codex"}) + "\n")
    question = f"#/e/{urllib.parse.quote('questions/do-cues-disturb-sleep.md', safe='')}"
    page = ctx.new_page()
    page.goto(f"{srv.base}/{question}")
    page.wait_for_selector(".moves-bar", timeout=15000)
    page.wait_for_timeout(2500)  # the presence stream names both agents
    page.click(".moves-bar [data-via='move']:has-text('Later')")
    page.wait_for_selector(".moves-bar.sent", timeout=5000)
    atlas(vault, "say", "Set to dormant.", "--agent", "claude")
    try:
        page.wait_for_selector(".moves-bar.sent", state="detached", timeout=10000)
    except Exception:
        failures.append("a move stays locked after its agent answered, while another agent works (#18, round 1)")
    page.evaluate("""document.body.insertAdjacentHTML('beforeend', '<button id="quote" data-prefill="A passage with ‹working› in it">q</button>');
                     document.getElementById('quote').click()""")
    page.wait_for_timeout(300)
    box = page.evaluate("(() => { const i = document.activeElement; return [i.value, i.selectionStart === i.value.length && i.selectionEnd === i.value.length]; })()")
    if box != ["A passage with ‹working› in it", True]:  # the text as it was, the cursor at its end
        failures.append(f"a quoted passage changed in the box: {box} (#18, review round 1)")
    page.close()
    with Server(vault) as alone:
        page = ctx.new_page()
        page.goto(f"{alone.base}/{question}")
        page.wait_for_selector(".moves-bar", timeout=15000)
        page.click(".moves-bar [data-via='move']:has-text('Later')")
        page.wait_for_timeout(800)
        if page.query_selector(".moves-bar.sent"):
            failures.append("standalone Atlas locks a move that only saved a note (#18, review round 1)")
        page.close()


def deep_after_nothing(page, base: str, scheme: str) -> None:
    """With QMD on, an instant search that finds nothing goes on by meaning (smoke run on #15), also when QMD
    was set up after the page loaded (review round 4). The browser smoke has no QMD: the meta and the deep
    answer are faked; the switch is the app's."""
    page.goto(f"{base}/#/search?q=memory")
    page.wait_for_selector("#results .card, #results .empty", timeout=15000)  # loaded with the real meta: no QMD
    if page.query_selector(".seg a:has-text('By meaning')"):
        failures.append(f"[{scheme}] the search offers 'By meaning' without QMD (#15, second smoke run)")

    def meta(route):
        route.fulfill(json={**route.fetch().json(), "qmd": True})
    page.route("**/api/meta", meta)
    page.route("**/api/search?*mode=deep*", lambda r: r.fulfill(json={"mode": "deep", "results": []}))
    page.goto(f"{base}/#/search?q=zzqxwv")
    try:
        page.wait_for_function("location.hash.includes('mode=deep')", timeout=10000)
    except Exception:
        failures.append(f"[{scheme}] an empty instant search does not go on by meaning once QMD is on (#15)")
    # a slow empty answer that arrives after the reader opened a note must not take them back (round 4)
    held = []
    page.route("**/api/search?*q=yyqxwv*", lambda r: held.append(r))
    page.goto(f"{base}/#/search?q=yyqxwv")
    for _ in range(150):  # the search waits for the meta first; a slow runner takes its time
        if held:
            break
        page.wait_for_timeout(100)
    page.goto(f"{base}/#/projects")
    page.wait_for_timeout(300)
    if not held:
        failures.append(f"[{scheme}] the late-answer check never saw its search request (#15)")
    for r in held:  # every held request gets its answer, so nothing hangs into the next check
        r.fulfill(json={"mode": "fast", "results": []})
    page.wait_for_timeout(800)
    if held and not page.evaluate("location.hash").startswith("#/projects"):
        failures.append(f"[{scheme}] a late search answer took the reader away from the page they opened (#15)")
    page.unroute("**/api/search?*q=yyqxwv*")
    page.unroute("**/api/meta")
    page.unroute("**/api/search?*mode=deep*")
    page.goto(f"{base}/#/")
    page.reload()  # the faked meta stays in the app until it loads again
    page.wait_for_selector("#main > *", timeout=15000)

if __name__ == "__main__":
    main()
