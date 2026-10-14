#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "playwright==1.55.0",
# ]
# ///
"""Re-take the README screenshots in docs/assets/ from this checkout.

Stages a temporary Atlas with the demo vault the way the README shows it: the user Ada, a chat with
Claude and Codex, both listening, Codex on the Nightlight project with its spec open in the
workbench. Then it serves it and takes each picture in its frame. Nothing outside the temporary
folder is written except the pictures; the server and the listeners are stopped at the end.

    uv run site/readme_shots.py [--out docs/assets] [--keep] [name ...]

Names: home reader operator tour project cabinet palette paper phone (default: all of them).
Playwright's Chromium is needed once: `uvx playwright@1.55.0 install chromium`.
replay.gif and banner.png are not made here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "skills" / "atlas" / "app"
UV = [shutil.which("uv") or "uv", "run", "--no-project", "--quiet"]
NAMES = ["home", "reader", "operator", "tour", "project", "cabinet", "palette", "paper", "phone"]

CLAUDE = """Three things, in order of how much I'd lean on them:

```atlas:notes
- insights/tmr-effect-is-smaller-than-first-reports.md
- insights/tmr-cues-reactivate-memories.md
- insights/cueing-at-home-needs-eeg.md
```

Cueing works in **NREM**, with a smaller effect than the early studies. Your vault, by map:

```atlas:chart
title: Insights by map
type: bar
unit: notes
data: {Learning techniques: 9, Sleep and memory: 8, Memory interventions: 6}
```

```atlas:choices
title: What next?
options:
  - Does Nightlight's cue timing hold up against that?
  - Dig into home EEG headbands
```"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stage(home: Path, now: dt.datetime) -> Path:
    """The README's vault: install, Ada, the demo, Codex on Nightlight, and the chat the pictures show."""
    shutil.copytree(APP, home, ignore=shutil.ignore_patterns(".atlas", "__pycache__"))
    # Today's demo steps keep their order and gaps but end 30 minutes before now: the demo puts a
    # step that lies in the future at "now", and the home feed would show them all at one minute.
    demo = home / "demo" / "demo.yaml"
    text = demo.read_text(encoding="utf-8")
    step = re.compile(r"(- day: 0\n  time: ')(\d\d:\d\d)(')")
    times = [dt.datetime.combine(now.date(), dt.time.fromisoformat(m.group(2))) for m in step.finditer(text)]
    if times:
        shift = max(dt.timedelta(0), max(times) - (now.replace(tzinfo=None) - dt.timedelta(minutes=30)))
        if (min(times) - shift).date() != now.date():
            sys.exit(f"today's demo steps do not fit before {now:%H:%M}; run this later in the day")
        text = step.sub(lambda m: m.group(1) + (dt.datetime.combine(now.date(), dt.time.fromisoformat(m.group(2))) - shift).strftime("%H:%M") + m.group(3), text)
        demo.write_text(text, encoding="utf-8")

    git = lambda *a: subprocess.run(["git", "-C", str(home), *a], check=True, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")  # Git speaks UTF-8 whatever the locale
    git("init", "-q")
    git("config", "user.name", "Ada")
    git("config", "user.email", "ada@example.org")
    reg = home / "vault" / "atlas.yaml"
    reg.write_text(reg.read_text(encoding="utf-8").replace('  name: ""', '  name: "Ada"', 1), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", f"atlas: install {(APP / 'VERSION').read_text(encoding='utf-8').strip()}")
    vault = home / "vault"
    engine = lambda *a: subprocess.run([*UV, str(home / "engine" / "atlas.py"), "--vault", str(vault), *a],
                                       check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    engine("demo")
    engine("boot", "nightlight", "--agent", "codex")

    ts = lambda minutes: (now + dt.timedelta(minutes=minutes)).isoformat()
    inbox = [
        {"ts": ts(-16), "role": "user", "kind": "message", "text": "What does my vault say about cueing memories during sleep?", "context": None, "to": "claude"},
        {"ts": ts(-6), "role": "user", "kind": "message", "text": "Does Nightlight's cue timing hold up against that?", "context": None, "via": "choice", "to": "codex"},
    ]
    outbox = [
        {"ts": ts(-14), "role": "agent", "agent": "claude", "text": CLAUDE},
        {"ts": ts(-6), "role": "agent", "agent": "codex", "kind": "progress", "text": "Checking the cue-mode spec against the two cueing notes"},
        {"ts": ts(-5), "role": "agent", "agent": "codex", "open": "specs/nightlight-cue-mode.md",
         "text": "It holds: cues only in NREM, and only with the headband's EEG. One open point: the volume cap is still a **proposed** decision. I opened the spec next to the chat."},
    ]
    state = vault / ".atlas"
    state.mkdir(exist_ok=True)
    (state / "inbox.jsonl").write_text("".join(json.dumps(r) + "\n" for r in inbox), encoding="utf-8")
    (state / "outbox.jsonl").write_text("".join(json.dumps(r) + "\n" for r in outbox), encoding="utf-8")
    (state / "cursor").write_text(str(len(inbox)), encoding="utf-8")  # the listeners wait for what comes next
    return vault


def shoot(base: str, out: Path, names: list[str], now: dt.datetime) -> None:
    def page_for(browser, w, h, scale, theme="dark", mobile=False):
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale, color_scheme=theme,
                                  is_mobile=mobile, has_touch=mobile)
        ctx.clock.set_fixed_time(now)
        last_seen = json.dumps((now - dt.timedelta(days=2)).isoformat())
        ctx.add_init_script(f"localStorage.setItem('atlas.theme', '{theme}'); localStorage.setItem('atlas.lastSeen', JSON.stringify({last_seen}));")
        page = ctx.new_page()
        page.goto(base)
        page.wait_for_timeout(1500)
        if page.locator("body.chat-open").count():  # the pictures read without the chat column
            page.click("#chat-close")
            page.wait_for_timeout(400)
        return page

    def go(page, route, wait=1500):
        page.evaluate(f"location.hash = {route!r}")
        page.wait_for_timeout(wait)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in names:
            if name == "home":
                page = page_for(browser, 1440, 1640, 2)
            elif name == "reader":
                page = page_for(browser, 1440, 900, 2)
                go(page, "#/e/insights%2Ftmr-effect-is-smaller-than-first-reports.md")
                page.locator("#main li a", has_text="Cues played during slow-wave sleep").first.hover()
                page.wait_for_timeout(1200)
            elif name == "operator":
                page = page_for(browser, 1440, 900, 2)
                go(page, "#/chat", 2500)
            elif name == "tour":
                page = page_for(browser, 1440, 900, 2)
                go(page, "#/e/tours%2Fthis-week.md", 2000)
                page.locator(".tour-rail").get_by_text("Cap cue volume at 45 dB").click()
                page.wait_for_timeout(1000)
                page.mouse.move(5, 450)
            elif name == "project":
                page = page_for(browser, 1440, 900, 2)
                go(page, "#/e/projects%2Fprivate%2Fnightlight%2Fproject.md", 2000)
            elif name == "cabinet":
                page = page_for(browser, 1440, 1040, 2)
                go(page, "#/e/cabinet%2Fpeople%2Fsusanne-diekelmann.md", 2000)
            elif name == "palette":
                page = page_for(browser, 1440, 900, 2)
                go(page, "#/e/insights%2Fspacing-plus-sleep.md")
                page.keyboard.press("Control+k")
                page.wait_for_timeout(500)
                page.keyboard.type("sleep", delay=60)
                page.wait_for_timeout(1200)
            elif name == "paper":
                page = page_for(browser, 1440, 900, 2, theme="light")
            elif name == "phone":
                page = page_for(browser, 390, 844, 3, mobile=True)
            page.screenshot(path=out / f"{name}.png")
            page.context.close()
            print(out / f"{name}.png")
        browser.close()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # a Windows console or pipe would refuse a non-cp1252 path
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", metavar="name", help=f"any of: {' '.join(NAMES)}")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "assets")
    ap.add_argument("--keep", action="store_true", help="keep the staged Atlas and print where it is")
    args = ap.parse_args()
    if unknown := [n for n in args.names if n not in NAMES]:
        ap.error(f"unknown picture {', '.join(unknown)}; choose from {' '.join(NAMES)}")
    names = args.names or NAMES
    args.out.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().astimezone().replace(microsecond=0)
    tmp = Path(tempfile.mkdtemp(prefix="atlas-readme-shots-"))
    procs: list[subprocess.Popen] = []
    try:
        vault = stage(tmp / "Atlas", now)
        engine = [*UV, str(tmp / "Atlas" / "engine" / "atlas.py"), "--vault", str(vault)]
        env = {**os.environ, "ATLAS_MACHINE": "laptop"}  # project pages print the machine's name
        port = free_port()
        quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "env": env}
        procs.append(subprocess.Popen([*engine, "serve", "--operator", "--port", str(port)], **quiet))
        base = f"http://127.0.0.1:{port}/"
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "api/meta", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            sys.exit("the staged Atlas did not start")
        for agent in ("claude", "codex"):  # "listening" on Home and in the header
            procs.append(subprocess.Popen([*engine, "wait", "--agent", agent, "--timeout", "3600"], **quiet))
        time.sleep(3)
        shoot(base, args.out, names, now)
    finally:
        for proc in procs:
            if proc.poll() is None:
                if os.name == "nt":  # uv does not pass terminate() on to its child on Windows
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
                else:
                    proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if args.keep:
            print(f"kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
