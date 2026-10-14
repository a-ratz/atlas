#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "starlette==0.46.2",
#   "uvicorn==0.34.3",
#   "markdown-it-py==3.0.0",
#   "PyYAML==6.0.3",
# ]
# ///
"""Build the recorded Atlas demo for GitHub Pages.

Installs Atlas into a temporary folder with the demo vault, starts the real engine in operator mode
and records every answer the front end can ask for. Then it plays the scene in scene.yaml for real
(a chat message, progress lines, notes written and committed through the engine, `check`) and
records the chat and the vault after each step. demo.js replays the recording: no server, no agent.

    uv run site/build.py [--out site/dist]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import itertools
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "skills" / "atlas" / "app"
SITE = Path(__file__).resolve().parent
GRAPH_EXTRA = ["sketch", "spec", "capture", "project", "question"]  # the constellation's "Also show"


class Recorder:
    def __init__(self, home: Path):
        self.home, self.vault = home, home / "vault"
        self.engine_py = home / "engine" / "atlas.py"
        self.state = self.vault / ".atlas"
        self.bodies: list = []
        self.seen: dict[str, int] = {}
        self.ids: set[str] = set()  # every note any recorded state had, to record where the moved ones went
        self.server = None
        self.base = ""

    # ------------------------------------------------------------ engine and server
    def atlas(self, *args: str, stdin: str | None = None) -> str:
        r = subprocess.run([sys.executable, str(self.engine_py), *args, "--vault", str(self.vault)],
                           input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=self.home)
        if r.returncode:
            sys.exit(f"atlas.py {args[0]} failed:\n{r.stdout}\n{r.stderr}")
        return r.stdout

    def start(self) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.server = subprocess.Popen([sys.executable, str(self.engine_py), "serve", "--operator", "--port", str(port),
                                        "--vault", str(self.vault)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                self.get("/api/meta")
                return
            except OSError:
                time.sleep(0.2)
        sys.exit("the engine did not start")

    def stop(self) -> None:
        if self.server:
            self.server.terminate()
            self.server.wait(timeout=10)

    def get(self, path: str):
        req = urllib.request.Request(self.base + path, headers={"x-atlas": "1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def post(self, path: str, body: dict):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"x-atlas": "1", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def reindexed(self, version, timeout: float = 30) -> None:
        """The engine re-reads the vault at most every ten seconds; record only once it has."""
        end = time.time() + timeout
        while time.time() < end:
            if self.get("/api/meta")["version"] != version:
                return
            time.sleep(0.5)
        sys.exit("the engine did not pick up the scene's notes")

    # ------------------------------------------------------------ presence
    def beat(self, **ages: float) -> None:
        """Set how long ago each agent (and the operator session) last listened: < 15 s reads as listening."""
        agents = self.state / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for name, age in ages.items():
            path = self.state / "heartbeat" if name == "operator" else agents / f"{name}.beat"
            path.touch()
            os.utime(path, (now - age, now - age))

    # ------------------------------------------------------------ recording
    def keep(self, value) -> int:
        """Identical answers are stored once; states point at them by number."""
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        key = hashlib.sha1(text.encode()).hexdigest()
        if key not in self.seen:
            self.seen[key] = len(self.bodies)
            self.bodies.append(value)
        return self.seen[key]

    def vault_state(self) -> dict:
        q = lambda **kw: "?" + urllib.parse.urlencode(kw)
        out = {"meta": self.keep(self.get("/api/meta")), "home": self.keep(self.get("/api/home")),
               "projects": self.keep(self.get("/api/projects"))}
        meta = self.bodies[out["meta"]]
        ids: set[str] = set()
        for t in meta["types"]:
            listing = self.get("/api/list" + q(type=t["id"]))
            out[f"list:{t['id']}"] = self.keep(listing)
            for item in listing.get("items", []):
                ids.add(item["id"])
            for group in listing.get("groups", []):
                ids.update(d["id"] for d in group["docs"])
        for n in range(len(GRAPH_EXTRA) + 1):
            for extra in itertools.combinations(GRAPH_EXTRA, n):
                types = sorted(["insight", "map", *extra])
                graph = self.get("/api/graph" + q(types=",".join(types)))
                out["graph:" + ",".join(types)] = self.keep(graph)
                ids.update(node["id"] for node in graph["nodes"])
        for i in sorted(ids):
            out[f"entity:{i}"] = self.keep(self.get("/api/entity" + q(id=i)))
            out[f"card:{i}"] = self.keep(self.get("/api/card" + q(id=i)))
        for gone in sorted(self.ids - ids):  # an open page follows a moved note (#13)
            try:
                self.get("/api/entity" + q(id=gone))
            except urllib.error.HTTPError as err:
                body = json.loads(err.read() or b"{}")
                if body.get("moved_to"):
                    out[f"moved:{gone}"] = self.keep(body)
        self.ids |= ids
        out["search"] = self.keep(self.search_table())
        return out

    def search_table(self) -> list:
        """What fast_search reads, so the browser can answer any query the way the engine would."""
        spec = importlib.util.spec_from_file_location("atlas_engine", self.engine_py)
        eng = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = eng  # dataclasses look their module up while the class is built
        spec.loader.exec_module(eng)
        eng.set_vault(self.vault)
        index = eng.Index()
        return [{"type": e.type, "t": e.title.lower(), "d": e.description.lower(), "b": e.body.lower(),
                 "touched": index.touched.get(e.id) or "", "card": e.card(index)} for e in index.entities.values()]

    def chat(self) -> int:
        return self.keep(self.get("/api/chat"))


def epoch_ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp() * 1000)


def second() -> int:
    """Now, cut to the second the engine's timestamps have: a step's messages are never older than its start."""
    return int(time.time()) * 1000


def write_chat(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def record(scene: dict, work: Path) -> dict:
    home = work / "atlas"
    shutil.copytree(APP, home)
    git = lambda *a: subprocess.run(["git", "-C", str(home), *a], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    git("init", "-q")
    git("config", "user.name", scene["user"])
    git("config", "user.email", "demo@example.org")
    reg = home / "vault" / "atlas.yaml"
    text = reg.read_text(encoding="utf-8")
    named = text.replace('  name: ""', f'  name: "{scene["user"]}"', 1)
    if named == text:
        sys.exit("vault/atlas.yaml has no empty user name to fill in")
    reg.write_text(named, encoding="utf-8")
    version = (APP / "VERSION").read_text(encoding="utf-8").strip()
    git("add", "-A")
    git("commit", "-q", "-m", f"atlas: install {version}")

    rec = Recorder(home)
    rec.atlas("demo")
    rec.atlas("boot", "nightlight", "--agent", "codex")  # Atlas shows Codex on the Nightlight project
    rec.start()
    try:
        inbox, outbox = rec.state / "inbox.jsonl", rec.state / "outbox.jsonl"
        now = dt.datetime.now().astimezone().replace(microsecond=0)

        # the canned replies, rendered by the engine, then out of the chat again
        for text in scene["canned"].values():
            write_chat(outbox, {"ts": now.isoformat(), "role": "agent", "agent": "claude", "text": text})
        rendered = rec.get("/api/chat")["messages"]
        canned = {key: next(m for m in rendered if m["text"] == text) for key, text in scene["canned"].items()}
        outbox.write_text("")

        for m in scene["earlier"]:
            ts = (now + dt.timedelta(minutes=m["minutes"])).isoformat()
            if m["role"] == "user":
                write_chat(inbox, {"ts": ts, "role": "user", "kind": "message", "text": m["text"], "context": None,
                                   **({"to": m["to"]} if m.get("to") else {})})
            else:
                write_chat(outbox, {"ts": ts, "role": "agent", "agent": m["agent"], "text": m["text"]})
        rec.atlas("say", "-", "--agent", "claude", stdin=scene["welcome"])
        rec.beat(operator=0, claude=0, codex=0)
        idle = rec.chat()
        before = rec.vault_state()
        recorded_at = epoch_ms(rec.bodies[idle]["messages"][-1]["ts"])

        steps = []
        time.sleep(1.1)  # every step gets its own second, so the browser can retime it
        started = second()
        rec.beat(operator=30, claude=30, codex=0)
        rec.post("/api/chat", {"text": scene["trigger"], "via": "choice", "to": "claude"})
        steps.append({"pause": 400, "at": started, "chat": rec.chat()})  # after the toast that names the recipient
        after = None
        for step in scene["steps"]:
            time.sleep(1.1)
            started = second()
            if "write" in step or "move" in step:
                paths = []
                for rel, body in (step.get("write") or {}).items():
                    (rec.vault / rel).parent.mkdir(parents=True, exist_ok=True)  # a scene may start a folder
                    (rec.vault / rel).write_text(body, encoding="utf-8")
                    paths.append(rec.vault / rel)
                for rel, swaps in (step.get("edit") or {}).items():
                    path = rec.vault / rel
                    text = path.read_text(encoding="utf-8")
                    for old, new in swaps:
                        if old not in text:
                            sys.exit(f"scene edit: {old!r} not in {rel}")
                        text = text.replace(old, new, 1)
                    path.write_text(text, encoding="utf-8")
                    paths.append(path)
                for src, dst in (step.get("move") or {}).items():
                    git("mv", f"vault/{src}", f"vault/{dst}")
                    paths += [rec.vault / src, rec.vault / dst]
                indexed = rec.get("/api/meta")["version"]
                rec.atlas("commit", "--agent", "claude", "-m", step["commit"], *map(str, paths))
                rec.reindexed(indexed)
            if step.get("check"):
                rec.atlas("check")
            if "progress" in step:
                rec.atlas("say", step["progress"], "--progress", "--agent", "claude")
            if "say" in step:
                rec.atlas("say", "-", "--agent", "claude", *(["--open", step["open"]] if step.get("open") else []),
                          stdin=step["say"])
                rec.beat(operator=0, claude=0, codex=0)
            else:
                rec.beat(operator=30, claude=30, codex=0)
            row = {"pause": step.get("pause", 1000), "at": started, "chat": rec.chat()}
            if "write" in step or "move" in step:
                after = rec.vault_state()
                row["vault"] = "after"
            steps.append(row)
        if after is None:
            sys.exit("the scene changes no notes")
        for step in scene["steps"]:  # an open page follows a moved note in the demo too (#14, review round 1)
            for src, dst in (step.get("move") or {}).items():
                if f"moved:{src}" not in after or rec.bodies[after[f"moved:{src}"]].get("moved_to") != dst:
                    sys.exit(f"the scene moves {src} to {dst}, but the recording does not say so")
        return {
            "version": version, "recorded_at": recorded_at, "record_day": dt.date.today().isoformat(),
            "user": scene["user"], "bodies": rec.bodies, "states": {"before": before, "after": after},
            "chat": idle, "canned": canned,
            "scene": {"trigger": scene["trigger"], "steps": steps},
        }
    finally:
        rec.stop()


def patch(path: Path, swaps: list[tuple[str, str]]) -> None:
    """The engine's absolute /static/ paths become relative, so the site works under any Pages prefix."""
    text = path.read_text(encoding="utf-8")
    for old, new in swaps:
        if old not in text:
            sys.exit(f"{path.name}: expected {old!r}; the front end changed, update site/build.py")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def bundle(data: dict, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(APP / "engine" / "static", out / "static")
    version = str(int(time.time()))
    patch(out / "static" / "index.html", [("/static/", "static/"), ("__ATLAS_V__", version),
                                          ('<script type="module"', '<script src="demo.js"></script>\n  <script type="module"')])
    (out / "static" / "index.html").rename(out / "index.html")
    patch(out / "static" / "style.css", [("/static/vendor/", "vendor/")])
    patch(out / "static" / "graph.js", [('"/static/vendor/', '"static/vendor/')])
    patch(out / "static" / "app.js", [("import(`/static/graph.js", "import(`./graph.js")])
    shutil.copy2(SITE / "demo.js", out / "demo.js")
    (out / "demo-data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    game = ROOT / "docs" / "guided-run" / "game"
    if game.is_dir():  # the game the guided run built (docs/guided-run.md), playable next to the demo
        shutil.copytree(game, out / "guided-run")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(SITE / "dist"))
    args = ap.parse_args()
    scene = yaml.safe_load((SITE / "scene.yaml").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="atlas-site-") as work:
        data = record(scene, Path(work))
    bundle(data, Path(args.out))
    size = (Path(args.out) / "demo-data.json").stat().st_size
    print(f"demo site: {args.out} ({len(data['bodies'])} recorded answers, {size // 1024} KB, "
          f"{len(data['scene']['steps'])} scene steps)")


if __name__ == "__main__":
    main()
