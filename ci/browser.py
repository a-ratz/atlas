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
import os
import sys
import tempfile
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import Server, atlas, demo_vault  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

# the engines this starts must not note the agent session running it in ~/.atlas/sessions.json (#65)
for _name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID"):
    os.environ.pop(_name, None)

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
                light_follows(ctx, srv, vault, scheme)
                if scheme == "light":  # the last pass: it edits and moves a demo note
                    follows_changes(ctx, srv, vault)
                    move_waits_for_its_own_answer(ctx, srv, vault)
                    move_ignores_late_history(ctx, srv, vault)
                    move_survives_pickup(ctx, srv, vault)
                    moves_release(ctx, srv, vault)
                    light_catch_up_race(ctx, srv, vault)
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
    slow_view_stays_behind(page, base, scheme)
    project_pages(page, base, scheme)
    card_facts(page, base, scheme)
    log_links(page, base, scheme)
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
    try:
        page.wait_for_selector(".reader-main h1:has-text('Can cueing work')", timeout=15000)  # this page, not the last
        row = page.inner_text(".reader-main .meta-row", timeout=15000)
    except Exception as err:  # say what the page showed instead of stopping the run
        failures.append(f"[{scheme}] the question page did not settle ({type(err).__name__}): "
                        f"{page.evaluate('location.hash')} {page.inner_html('#main')[:600]!r}")
        return
    if "[[" in row or "raised_count" in row or not page.query_selector(".reader-main .meta-row a[href^='#/e/insights']"):
        failures.append(f"[{scheme}] the facts line shows {row!r} instead of a linked title (#10)")
    if scheme != "light":  # pressing a move writes to the chat, which the next pass expects empty
        return
    churn = page.evaluate("""new Promise((done) => { let n = 0;
      const o = new MutationObserver(() => n++); o.observe(document.querySelector('#main'), {childList: true});
      setTimeout(() => { o.disconnect(); done(n); }, 3000); })""")
    try:
        page.click(".moves-bar [data-via='move']:has-text('Later')", timeout=15000)
    except Exception as err:  # say what the page was doing instead of stopping the run
        state = page.evaluate("""[...document.querySelectorAll('.moves-bar button')].map((b) => b.textContent + (b.disabled ? ':off' : ''))""")
        failures.append(f"[{scheme}] could not press Later ({type(err).__name__}): main re-rendered {churn}x in 3 s; "
                        f"buttons {state}; presence {page.inner_text('#presence')!r}; {page.evaluate('location.hash')}; "
                        f"main: {page.inner_html('#main')[:700]!r}")
        return
    try:
        page.wait_for_selector(".moves-bar.sent .sent-note", timeout=5000)
        if page.eval_on_selector_all(".moves-bar button", "bs => bs.some((b) => !b.disabled)"):
            failures.append(f"[{scheme}] a pressed move leaves the other buttons on (#10)")
    except Exception:
        failures.append(f"[{scheme}] pressing Later shows nothing on the page, only a toast (#10)")


def log_links(page, base: str, scheme: str) -> None:
    """Thread log lines on a project page show links, not [[wiki]] syntax (#27)."""
    page.goto(f"{base}/#/e/{urllib.parse.quote('projects/private/nightlight/project.md', safe='')}")
    page.wait_for_selector(".side-col .path:has-text('projects/private/nightlight/project.md')", timeout=15000)
    head = page.inner_text(".left-off") if page.query_selector(".left-off") else ""
    if "[[" in head or not page.query_selector(".left-off a[href*='insights']"):
        failures.append(f"[{scheme}] 'Where we left off' shows {head[:120]!r} instead of a linked title (#27)")


def card_facts(page, base: str, scheme: str) -> None:
    """The facts line leaves out the type's status field, which the badge shows (#22: depth twice)."""
    page.goto(f"{base}/#/t/person")
    page.wait_for_selector("#list .card", timeout=15000)
    first = page.eval_on_selector("#list .card a, #list a.card", "a => a.getAttribute('href')")
    page.goto(f"{base}/{first}")
    page.wait_for_selector(".reader-main .meta-row", timeout=15000)
    if "depth:" in page.inner_text(".reader-main .meta-row"):
        failures.append(f"[{scheme}] a card's facts line repeats its depth next to the badge (#22)")


def project_pages(page, base: str, scheme: str) -> None:
    """A project shows the spec and sketch it came from (#16); one left-off line is not said twice."""
    page.goto(f"{base}/#/e/{urllib.parse.quote('projects/private/nightlight/project.md', safe='')}")
    page.wait_for_selector(".side-col .path:has-text('projects/private/nightlight/project.md')", timeout=15000)
    if not (page.query_selector(".side-col .chain a[href*='specs']") and page.query_selector(".side-col .chain a[href*='sketches']")):
        failures.append(f"[{scheme}] the project page does not show the spec and sketch it came from (#16)")
    for project in ("projects/private/nightlight/project.md", "projects/work/thesis/project.md"):
        page.goto(f"{base}/#/e/{urllib.parse.quote(project, safe='')}")
        page.wait_for_selector(f".side-col .path:has-text('{project}')", timeout=15000)  # this project, not the last
        if page.query_selector(".left-off"):
            head = page.inner_text(".left-off h2").strip()
            lines = page.eval_on_selector_all(".left-off .line", "ls => ls.map((l) => l.innerText)")
            if any(head in line for line in lines) and len(lines) == 1:
                failures.append(f"[{scheme}] {project}: 'Where we left off' says {head!r} twice (#16 smoke run)")

def slow_view_stays_behind(page, base: str, scheme: str) -> None:
    """A view whose data comes late does not paint over the page the reader opened meanwhile (CI on #18: Home,
    still loading after a reload, replaced an open question)."""
    held = []
    page.goto(f"{base}/#/projects")  # from another page: a goto to the hash the page is on loads nothing
    page.wait_for_timeout(300)
    page.route("**/api/home", lambda r: held.append(r))
    page.goto(f"{base}/#/")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(100)
    page.goto(f"{base}/#/e/{urllib.parse.quote('questions/can-tmr-work-without-eeg.md', safe='')}")
    page.wait_for_selector(".reader-main h1:has-text('Can cueing work')", timeout=15000)
    for r in held:
        r.continue_()
    page.wait_for_timeout(1500)
    page.unroute("**/api/home")
    if not held:
        failures.append(f"[{scheme}] the slow-view check held no Home request")
    elif not page.query_selector(".reader-main h1:has-text('Can cueing work')"):
        failures.append(f"[{scheme}] a late Home answer painted over the open question (#18, CI)")


def light_follows(ctx, srv: Server, vault: Path, scheme: str) -> None:
    """`atlas.py light` takes the user to the constellation with its notes lit; a hidden kind it needs is shown
    without changing the saved choice; a note written just before joins once the server's index catches up;
    the chip's x clears the highlight and repaints a settled graph (#63, review round 1 on #64). The chat and
    the vault are put back afterwards: the next pass expects them as they were."""
    outbox, extra = vault / ".atlas" / "outbox.jsonl", vault / "insights" / "light-joins-late.md"
    before = outbox.read_bytes() if outbox.exists() else b""
    page = ctx.new_page()
    try:
        _light_follows(page, srv, vault, scheme, extra)
    finally:
        page.close()
        extra.unlink(missing_ok=True)
        outbox.write_bytes(before)


def _light_follows(page, srv: Server, vault: Path, scheme: str, extra: Path) -> None:
    page.goto(f"{srv.base}/#/")
    page.wait_for_selector("#main > *", timeout=15000)
    page.wait_for_timeout(1500)  # the chat has loaded: a light from before the page opened is not followed
    extra.write_text("---\ndescription: written right before the light\n---\n\n# A note that joins late\n\n"
                     "[[spacing-plus-sleep]]\n", encoding="utf-8")  # the server's index has not seen it yet
    r = atlas(vault, "light", "Sleep and memory", "insights/spacing-plus-sleep.md", "replay-reruns-the-day", "light-joins-late")
    if r.returncode or "lit 3 notes" not in r.stdout:
        return failures.append(f"[{scheme}] atlas.py light failed (#63): {r.stdout}{r.stderr}")
    try:
        page.wait_for_function("location.hash === '#/graph?light=sleep-and-memory'", timeout=15000)
        page.wait_for_selector("#gx-lit:not([hidden])", timeout=15000)
    except Exception:
        return failures.append(f"[{scheme}] a light did not take the user to the lit constellation (#63): {page.evaluate('location.hash')}")
    try:
        page.wait_for_function("document.querySelector('#gx-lit .n')?.textContent === '3'", timeout=30000)
    except Exception:
        failures.append(f"[{scheme}] the chip says {page.inner_text('#gx-lit')!r}: the note written right before never joined (#64 r1)")
    page.evaluate("""() => { window.__draws = 0; const p = CanvasRenderingContext2D.prototype, real = p.clearRect;
      p.clearRect = function (...a) { if (this.canvas.closest("#gx-canvas")) window.__draws++; return real.apply(this, a); }; }""")
    last, still = -1, 0
    for _ in range(60):  # wait until the layout has settled: a second without a frame
        page.wait_for_timeout(500)
        n = page.evaluate("window.__draws")
        still, last = (still + 1 if n == last else 0), n
        if still >= 2:
            break
    page.click("#gx-lit .x")
    page.wait_for_timeout(600)
    if page.is_visible("#gx-lit") or page.evaluate("location.hash") != "#/graph":
        failures.append(f"[{scheme}] x left the light on: chip {page.is_visible('#gx-lit')}, {page.evaluate('location.hash')} (#63)")
    if page.evaluate("window.__draws") == last:
        failures.append(f"[{scheme}] x on a settled graph left the lit picture on the canvas (#64 r1)")
    # a hidden kind the highlight needs: shown for this view, the saved choice untouched
    sketch = srv.get("/api/list?type=sketch")["items"][0]["id"]
    r = atlas(vault, "light", "An idea", sketch, "spacing-plus-sleep")
    try:
        page.wait_for_function("location.hash === '#/graph?light=an-idea'", timeout=15000)
        page.wait_for_selector("#gx-lit:not([hidden])", timeout=15000)
    except Exception:
        return failures.append(f"[{scheme}] a second light did not take the user along (#63): {r.stdout}{r.stderr} {page.evaluate('location.hash')}")
    box = page.eval_on_selector(".gx-extra input[value=sketch]", "i => [i.checked, i.disabled]")
    if box != [True, True]:
        failures.append(f"[{scheme}] a lit sketch did not show the sketches for this view: checked, disabled = {box} (#63)")
    page.click("#gx-lit .x")
    page.wait_for_timeout(800)
    box = page.eval_on_selector(".gx-extra input[value=sketch]", "i => [i.checked, i.disabled]")
    if box != [False, False]:
        failures.append(f"[{scheme}] x kept the sketches shown for the light: checked, disabled = {box} (#63)")


def light_catch_up_race(ctx, srv: Server, vault: Path) -> None:
    """A note written right before `light` is missing from the first graph answers (the server re-reads the
    vault at most every 10 s); the index event that brings it must not get lost on the way (#64):
    - round 3: the event arrives while the first answer is still on its way;
    - round 4: a newer load (an "Also show" toggle) has landed while the first one is still pending;
    - round 5: as round 4, but the user has opened another highlight since: the old view must stay quiet.
    Answers are fetched at once, while stale, and delivered in the order the case needs."""
    outbox = vault / ".atlas" / "outbox.jsonl"
    before = outbox.read_bytes() if outbox.exists() else b""
    page = ctx.new_page()
    written: list[Path] = []
    try:
        for case in ("first-load", "superseded", "replaced"):
            for attempt in range(3):  # the server may re-read the vault at the wrong moment: stage it again
                note = vault / "insights" / f"light-race-{case}-{attempt}.md"
                written.append(note)
                staged = _light_race(page, srv, vault, note, case)
                if staged is not None:
                    break
            else:
                print(f"note: the light race ({case}) could not be staged in three tries; not checked")
    finally:
        page.close()
        for note in written:
            note.unlink(missing_ok=True)
        outbox.write_bytes(before)


def _light_race(page, srv: Server, vault: Path, note: Path, case: str):
    """None when the race could not be staged (an answer was already fresh), else True."""
    page.goto(f"{srv.base}/#/")
    page.wait_for_selector("#main > *", timeout=15000)
    page.wait_for_timeout(1500)
    page.evaluate("window.__idx = 0; addEventListener('atlas:index', () => window.__idx++)")
    answers: list = []  # (route, response, stale) per graph request, in order

    def hold(route):
        if len(answers) >= 2 or (case == "first-load" and answers):
            return route.continue_()
        resp = route.fetch()
        answers.append((route, resp, note.stem not in resp.text()))
        if len(answers) == 2:  # the newer load lands at once
            route.fulfill(response=resp)
    page.route("**/api/graph?*", hold)
    note.write_text(f"---\ndescription: written right before the light\n---\n\n# {note.stem}\n\n[[spacing-plus-sleep]]\n",
                    encoding="utf-8")
    name = note.stem
    try:
        r = atlas(vault, "light", name, "insights/spacing-plus-sleep.md", note.stem)
        if r.returncode:
            failures.append(f"atlas.py light failed (#64): {r.stdout}{r.stderr}")
            return True
        page.wait_for_function(f"location.hash === '#/graph?light={name}'", timeout=15000)
        for _ in range(150):
            if answers:
                break
            page.wait_for_timeout(100)
        if not answers[0][2]:
            return None
        if case in ("superseded", "replaced"):
            page.click(".gx-extra input[value=capture]")  # a newer load while the first is still held
            page.wait_for_selector("#gx-lit:not([hidden])", timeout=15000)
            if len(answers) < 2 or not answers[1][2] or page.evaluate("window.__idx") > 0:
                answers[0][0].fulfill(response=answers[0][1])
                return None  # the newer answer was fresh, or the event came before it landed
            if case == "replaced":  # another highlight replaces the view whose first load is still held
                page.wait_for_timeout(1100)  # chat times have whole seconds: the follow needs a later one (r6)
                r = atlas(vault, "light", "New light", "insights/spacing-plus-sleep.md")
                page.wait_for_function("location.hash === '#/graph?light=new-light'", timeout=15000)
                page.wait_for_function("document.querySelector('#gx-lit')?.innerText.includes('New light')", timeout=15000)
                if page.evaluate("window.__idx") > 0:
                    answers[0][0].fulfill(response=answers[0][1])
                    return None
            page.wait_for_function("window.__idx > 0", timeout=30000)  # the event, after the newer load landed
            if case == "replaced":
                page.wait_for_timeout(2500)  # time for an old view to catch up and paint over the new one
                chip = page.inner_text("#gx-lit") if page.is_visible("#gx-lit") else ""
                answers[0][0].fulfill(response=answers[0][1])  # the old view's first answer, last of all
                page.wait_for_timeout(1500)
                after = page.inner_text("#gx-lit") if page.is_visible("#gx-lit") else ""
                if "New light" not in chip or "New light" not in after:
                    failures.append(f"light race replaced: an old graph view painted over the new highlight: {chip!r}, then {after!r} (#64 r5)")
                return True
            answers[0][0].fulfill(response=answers[0][1])  # the superseded answer comes in last
        else:
            page.wait_for_function("window.__idx > 0", timeout=30000)  # the event, before the first answer lands
            answers[0][0].fulfill(response=answers[0][1])
    except Exception as err:
        failures.append(f"could not stage the light race {case} ({type(err).__name__}): {page.evaluate('location.hash')} (#64)")
        return True
    finally:
        page.unroute("**/api/graph?*")
    try:
        page.wait_for_function("document.querySelector('#gx-lit .n')?.textContent === '2'", timeout=15000)
    except Exception:
        round_ = "r4" if case == "superseded" else "r3"
        failures.append(f"light race {case}: the note never joined, chip {page.inner_text('#gx-lit')!r} (#64 {round_})")
    return True


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
    page.click(".moves-bar [data-via='move']:has-text('Research this')")  # often in the same second (round 5)
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


def move_survives_pickup(ctx, srv: Server, vault: Path) -> None:
    """An agent that picks a move up (working, then listening again) has not answered it (#18, review round 5)."""
    import os
    import time
    beat = vault / ".atlas" / "agents" / "claude.beat"
    beat.touch()
    os.utime(beat, (time.time() - 60, time.time() - 60))  # claude listened a minute ago: a message makes it work
    page = ctx.new_page()
    page.goto(f"{srv.base}/#/e/{urllib.parse.quote('questions/do-cues-disturb-sleep.md', safe='')}")
    page.wait_for_selector(".moves-bar", timeout=15000)
    page.evaluate("localStorage.setItem('atlas.to', JSON.stringify('claude'))")
    page.wait_for_timeout(2500)
    page.click(".moves-bar [data-via='move']:has-text('Research this')")
    page.wait_for_selector(".moves-bar.sent", timeout=5000)
    page.wait_for_timeout(3000)  # working
    os.utime(beat, (time.time() + 600, time.time() + 600))  # `wait` again: listening, nothing answered
    page.wait_for_timeout(4000)
    if not page.query_selector(".moves-bar.sent"):
        failures.append("picking a move up freed it before any answer (#18, review round 5)")
    atlas(vault, "say", "Done.", "--agent", "claude")
    try:
        page.wait_for_selector(".moves-bar.sent", state="detached", timeout=10000)
    except Exception:
        failures.append("a picked-up move stays locked after its answer (#18, review round 5)")
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
    import shutil
    alone_vault = vault.parent / "alone" / "vault"  # one Atlas per vault (#24): the standalone one gets a copy
    shutil.copytree(vault, alone_vault, ignore=shutil.ignore_patterns(".atlas"))
    with Server(alone_vault) as alone:
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
