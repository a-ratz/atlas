#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "PyYAML==6.0.3",
# ]
# ///
"""The pull request gate. Each check protects a claim Atlas makes, can fail, and costs seconds.

    uv run ci/gate.py static       # Python compiles, JavaScript parses, YAML loads, skills name themselves
    uv run ci/gate.py operator     # a chat message reaches `wait`, `say` reaches the chat
    uv run ci/gate.py upgrade      # this engine runs on a vault whose atlas.yaml came from the base branch
    uv run ci/gate.py installer    # install, upgrade and restore keep the user's files and the factory's
    uv run ci/gate.py docs         # every `engine/atlas.py <command>` the docs name exists
    uv run ci/gate.py hygiene      # no absolute home paths in tracked files
    uv run ci/gate.py tests        # tests/ with the engine's own dependencies
    uv run ci/gate.py pr           # pull requests: VERSION raised for app changes, screenshots for UI changes

`--base <ref>` (default origin/main) names the branch a pull request goes into.
"""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "atlas"
APP = SKILL / "app"
ENGINE = APP / "engine" / "atlas.py"
UV = [shutil.which("uv") or "uv", "run", "--no-project", "--quiet"]  # each script brings its own dependencies
failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL {msg}")


def ok(msg: str) -> None:
    print(f"ok   {msg}")


def tracked(*patterns: str) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", *patterns], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.split("\0") if p]


def atlas(vault: Path, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run([*UV, str(ENGINE), "--vault", str(vault), *args],
                          capture_output=True, text=True, timeout=timeout)


def demo_vault(tmp: Path) -> Path:
    vault = tmp / "vault"
    shutil.copytree(APP / "vault", vault, ignore=shutil.ignore_patterns(".atlas"))
    r = atlas(vault, "demo")
    if r.returncode:
        sys.exit(f"the demo did not load:\n{r.stdout}{r.stderr}")
    return vault


class Server:
    """`atlas.py serve` on a free port, for as long as the `with` block runs."""

    def __init__(self, vault: Path, operator: bool = False):
        self.vault, self.operator = vault, operator

    def __enter__(self) -> "Server":
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        args = [*UV, str(ENGINE), "--vault", str(self.vault), "serve", "--port", str(port)]
        self.proc = subprocess.Popen(args + (["--operator"] if self.operator else []),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.base = f"http://127.0.0.1:{port}"
        for _ in range(300):  # the first run may resolve the engine's dependencies
            try:
                self.get("/api/meta")
                return self
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.2)
        self.proc.terminate()
        sys.exit(f"the engine did not start:\n{self.proc.stdout.read() if self.proc.stdout else ''}")

    def __exit__(self, *exc) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def get(self, path: str):
        req = urllib.request.Request(self.base + path, headers={"x-atlas": "1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def post(self, path: str, body: dict):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"x-atlas": "1", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())


# --------------------------------------------------------------------------- checks

def check_static(args) -> None:
    for py in tracked("*.py"):
        try:
            py_compile.compile(str(py), doraise=True)
        except py_compile.PyCompileError as exc:
            fail(f"{py.relative_to(ROOT)} does not compile: {exc.msg}")
    ok("Python compiles")

    for path in tracked("*.yml", "*.yaml"):
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            fail(f"{path.relative_to(ROOT)} is not valid YAML: {exc}")
    ok("YAML loads")

    for skill in tracked("*SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n", text, re.S)
        meta = yaml.safe_load(m.group(1)) if m else None
        rel = skill.relative_to(ROOT)
        if not isinstance(meta, dict):
            fail(f"{rel} has no frontmatter")
        elif meta.get("name") != skill.parent.name:
            fail(f"{rel} is named `{meta.get('name')}`, its folder `{skill.parent.name}`")
        elif not str(meta.get("description") or "").strip():
            fail(f"{rel} has no description")
    ok("skills name themselves and say what they do")

    node = shutil.which("node")
    if not node:
        fail("node is not installed, so the JavaScript could not be checked")
        return
    with tempfile.TemporaryDirectory() as tmp:
        for js in tracked("*.js"):
            if "vendor" in js.parts:
                continue
            copy = Path(tmp) / (js.stem + ".mjs")  # the app's scripts are ES modules
            shutil.copy(js, copy)
            r = subprocess.run([node, "--check", str(copy)], capture_output=True, text=True)
            if r.returncode:
                fail(f"{js.relative_to(ROOT)} does not parse:\n{r.stderr}")
    ok("JavaScript parses")


def check_operator(args) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        vault = demo_vault(Path(tmp))
        with Server(vault, operator=True) as srv:
            wait = subprocess.Popen([*UV, str(ENGINE), "--vault", str(vault), "wait", "--timeout", "90"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            heartbeat = vault / ".atlas" / "heartbeat"
            for _ in range(100):  # `wait` beats once it listens
                if heartbeat.exists() and time.time() - heartbeat.stat().st_mtime < 5:
                    break
                time.sleep(0.2)
            srv.post("/api/chat", {"text": "ping from the gate"})
            try:
                out, _ = wait.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                wait.kill()
                fail("`wait` did not return after a chat message")
                return
            if "ping from the gate" not in out:
                fail(f"`wait` returned without the message:\n{out}")
            for say in (("--progress", "Reading the gate's sources", "--title", "Checking the gate"), ("pong from the gate",)):
                r = atlas(vault, "say", *say)
                if r.returncode:
                    fail(f"`say` failed: {r.stderr}")
            msgs = srv.get("/api/chat")["messages"]
            if not any(m.get("role") == "agent" and m.get("text") == "pong from the gate" for m in msgs):
                fail("the answer from `say` is not in the chat")
            if not any(m.get("title") == "Checking the gate" for m in msgs):
                fail("`say --title` left no title in the chat")
    ok("operator round trip: chat → wait → say → chat, with a title")


def check_upgrade(args) -> None:
    rel = "skills/atlas/app/vault/atlas.yaml"
    old = subprocess.run(["git", "show", f"{args.base}:{rel}"], cwd=ROOT, capture_output=True, text=True)
    if old.returncode:
        print(f"skip upgrade: {args.base} has no {rel}")
        return
    with tempfile.TemporaryDirectory() as tmp:
        vault = demo_vault(Path(tmp))
        (vault / "atlas.yaml").write_text(old.stdout, encoding="utf-8")
        r = atlas(vault, "check")
        if r.returncode:
            fail(f"`check` fails on a vault with the registry from {args.base}:\n{r.stdout}{r.stderr}")
        with Server(vault) as srv:
            meta = srv.get("/api/meta")
            srv.get("/api/home")
            for t in meta["types"]:
                for item in srv.get(f"/api/list?type={t['id']}").get("items", [])[:3]:
                    srv.get(f"/api/entity?id={urllib.parse.quote(item['id'])}")
    ok(f"this engine reads a vault whose atlas.yaml came from {args.base}")


def check_installer(args) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        skill = tmp / "skill"  # a copy, so the pointer the installer writes never lands in this checkout
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("config.json", ".atlas", "__pycache__"))
        user = tmp / "user"  # every place the installer may keep its pointer, so the real one is never touched
        env = {**os.environ, "HOME": str(user), "USERPROFILE": str(user), "XDG_CONFIG_HOME": str(user / ".config"),
               "APPDATA": str(user / "AppData" / "Roaming"), "LOCALAPPDATA": str(user / "AppData" / "Local")}
        home = tmp / "Atlas"

        def run(*cmd: str) -> str:
            r = subprocess.run([*UV, str(skill / "scripts" / "atlas_install.py"), *cmd],
                               capture_output=True, text=True, env=env)
            if r.returncode:
                fail(f"`atlas_install.py {' '.join(cmd)}` failed:\n{r.stdout}{r.stderr}")
            return r.stdout

        run("install", str(home))
        note, css, graph = home / "vault" / "insights" / "A note the user wrote.md", home / "engine" / "static" / "style.css", home / "engine" / "static" / "graph.js"
        note.write_text("# A note the user wrote\n", encoding="utf-8")
        factory_css = css.read_text(encoding="utf-8")
        css.write_text(factory_css + "\n/* the user's change */\n", encoding="utf-8")
        graph.unlink()
        run("upgrade")
        if not note.exists():
            fail("upgrade removed a note from the vault")
        if "the user's change" not in css.read_text(encoding="utf-8"):
            fail("upgrade overwrote an app file the user changed")
        if not graph.exists():
            fail("upgrade did not bring back a missing app file")
        run("restore", "engine")
        if css.read_text(encoding="utf-8") != factory_css:
            fail("restore did not put the factory copy back")
        if not note.exists():
            fail("restore touched the vault")
    ok("install → upgrade keeps the user's files → restore brings the factory copy back")


def check_docs(args) -> None:
    help_text = subprocess.run([*UV, str(ENGINE), "--help"], capture_output=True, text=True).stdout
    m = re.search(r"\{([a-z,-]+)\}", help_text)
    commands = set(m.group(1).split(",")) if m else set()
    fence = re.compile(r"^(`{3,})(\w*)[^\n]*\n(.*?)^\1[ \t]*$", re.S | re.M)
    call = re.compile(r"engine/atlas\.py(?:\s+--vault\s+\S+)?\s+([a-z][a-z-]*)")
    for md in tracked("*.md"):
        text = md.read_text(encoding="utf-8")
        spans = []  # (offset, code): fenced blocks except ```text (diagrams), then inline code outside them
        for m in fence.finditer(text):
            if m.group(2) != "text":
                spans.append((m.start(3), m.group(3)))
        prose = fence.sub(lambda m: " " * len(m.group(0)), text)
        spans += [(m.start(), m.group(0)) for m in re.finditer(r"`[^`\n]+`", prose)]
        for start, code in spans:
            for c in call.finditer(code):
                if c.group(1) not in commands:
                    line = text.count("\n", 0, start + c.start()) + 1
                    fail(f"{md.relative_to(ROOT)}:{line} names `engine/atlas.py {c.group(1)}`, which does not exist")
    ok(f"the docs name only commands the engine has ({len(commands)} known)")


def check_hygiene(args) -> None:
    home = re.compile(r"(?<![\w.])(/home/|/Users/)[A-Za-z][\w.-]*")
    for path in tracked():
        if not path.is_file() or path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in home.finditer(text):
            fail(f"{path.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1} names a home folder: {m.group(0)}")
    ok("no absolute home paths in tracked files")


def check_tests(args) -> None:
    header = re.search(r"# /// script\n(.*?)# ///", ENGINE.read_text(encoding="utf-8"), re.S).group(1)
    deps = re.findall(r'#\s+"([^"]+)"', header)
    cmd = ["uv", "run", "--no-project", "--with", "pytest", "--with", "httpx"]
    for d in deps:
        cmd += ["--with", d]
    r = subprocess.run([*cmd, "python", "-m", "pytest", "tests", "-q"], cwd=ROOT)
    if r.returncode:
        fail("tests failed")
    else:
        ok("tests pass")


def check_pr(args) -> None:
    version = (APP / "VERSION").read_text(encoding="utf-8").strip()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"Atlas (\S+) is the current release", readme)
    if not m or m.group(1) != version:
        fail(f"README says Atlas {m.group(1) if m else '?'} is the current release, VERSION says {version}")
    diff = subprocess.run(["git", "diff", "--name-only", f"{args.base}...HEAD"], cwd=ROOT, capture_output=True, text=True)
    if diff.returncode:
        fail(f"cannot compare with `{args.base}` (fetch it, or pass --base): {diff.stderr.strip()}")
        return
    changed = diff.stdout.split()
    if any(p.startswith("skills/atlas/app/") for p in changed):
        old = subprocess.run(["git", "show", f"{args.base}:skills/atlas/app/VERSION"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
        as_tuple = lambda v: tuple(int(x) for x in re.findall(r"\d+", v))
        if old and as_tuple(version) <= as_tuple(old):
            fail(f"the app changed but VERSION stays {version} (base: {old}); raise it and the README line")
    ok(f"release: VERSION {version} and the README agree")

    event = os.environ.get("GITHUB_EVENT_PATH")
    pr = json.loads(Path(event).read_text(encoding="utf-8")).get("pull_request") if event and Path(event).exists() else None
    if pr is None:
        print("skip screenshots: not a pull request")
        return
    if any(p.startswith("skills/atlas/app/engine/static/") for p in changed):
        body = pr.get("body") or ""
        section = re.search(r"^##\s+Screenshots\b(.*?)(?=^##\s|\Z)", body, re.S | re.M)
        if not section or not re.search(r"!\[|<img\b", section.group(1)):
            fail("this pull request changes the UI (engine/static/): its description needs a `## Screenshots` "
                 "section with images of the final state, in both themes")
        else:
            ok("UI change with screenshots")


CHECKS = {"static": check_static, "operator": check_operator, "upgrade": check_upgrade, "installer": check_installer,
          "docs": check_docs, "hygiene": check_hygiene, "tests": check_tests, "pr": check_pr}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checks", nargs="+", choices=sorted(CHECKS))
    ap.add_argument("--base", default="origin/main", help="the branch a pull request goes into")
    args = ap.parse_args()
    for name in args.checks:
        CHECKS[name](args)
    if failures:
        sys.exit(f"\n{len(failures)} check(s) failed")


if __name__ == "__main__":
    main()
