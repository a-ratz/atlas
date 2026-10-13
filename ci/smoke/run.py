#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "PyYAML==6.0.3",
# ]
# ///
"""Prepare and tear down an isolated Atlas for a smoke run (ci/smoke/README.md).

    uv run ci/smoke/run.py prepare <scenario> [--ref <git ref>] [--id <agent id>]
    uv run ci/smoke/run.py stop <run dir> [--clean]

`prepare` makes a run folder with its own HOME, installs this checkout's skill the way a user does
(`npx skills add … -g -s atlas`), runs the installer, loads the demo if the scenario asks for it,
starts `atlas.py serve --operator` on a free port and writes the two briefs: `operator.md` for the
agent that answers in Atlas, `user.md` for the agent that drives the browser. It prints the run as
JSON. With `--ref`, the first install comes from that ref (the upgrade scenario) and `upgrade` brings
it to this checkout afterwards. Nothing outside the run folder is touched.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SMOKE = Path(__file__).resolve().parent


def scenario(name: str) -> dict:
    path = SMOKE / "scenarios" / f"{name}.md"
    if not path.exists():
        sys.exit(f"no scenario `{name}`: {', '.join(p.stem for p in sorted((SMOKE / 'scenarios').glob('*.md')))}")
    text = path.read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---")[1]) if text.startswith("---") else {}
    return {"name": name, "path": str(path), "text": text, **(meta or {})}


def sh(cmd: list[str], env: dict, cwd: Path | None = None) -> str:
    r = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(f"`{' '.join(cmd)}` failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def install_skill(source: Path, env: dict) -> Path:
    npx = shutil.which("npx") or sys.exit("npx is missing: install Node.js 22+")
    sh([npx, "--yes", "skills", "add", str(source), "-g", "-s", "atlas", "-a", "claude-code", "-a", "codex",
        "--copy", "-y"], env)
    skill = Path(env["HOME"]) / ".claude" / "skills" / "atlas"
    if not (skill / "scripts" / "atlas_install.py").exists():
        sys.exit(f"the skill did not land in {skill}")
    return skill


def prepare(args) -> None:
    sc = scenario(args.scenario)
    run = Path(tempfile.mkdtemp(prefix=f"atlas-smoke-{sc['name']}-"))
    home = run / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "APPDATA": str(home / "AppData" / "Roaming"), "LOCALAPPDATA": str(home / "AppData" / "Local"),
           # agent CLIs install into these when set; the real ones must never be touched
           "CLAUDE_CONFIG_DIR": str(home / ".claude"), "CODEX_HOME": str(home / ".codex"),
           "DO_NOT_TRACK": "1", "DISABLE_TELEMETRY": "1",
           # a user's machine has a git identity; the isolated HOME does not, and the install's first commit needs one
           "GIT_AUTHOR_NAME": "Smoke Test", "GIT_AUTHOR_EMAIL": "smoke@example.com",
           "GIT_COMMITTER_NAME": "Smoke Test", "GIT_COMMITTER_EMAIL": "smoke@example.com"}
    uv = [shutil.which("uv") or "uv", "run", "--no-project", "--quiet"]
    atlas_dir = run / "Atlas"

    first = ROOT
    if args.ref:  # the upgrade scenario installs an older Atlas first
        first = run / "previous"
        sh(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(first), args.ref], env)
    skill = install_skill(first, env)
    sh([*uv, str(skill / "scripts" / "atlas_install.py"), "install", str(atlas_dir)], env)
    if sc.get("demo"):
        sh([*uv, str(atlas_dir / "engine" / "atlas.py"), "demo", "--vault", str(atlas_dir / "vault")], env)
    if args.ref:  # content made with the old version stays; then the skill and the app move to this checkout
        for setup in sc.get("before_upgrade", []):
            sh([*uv, str(atlas_dir / "engine" / "atlas.py"), "--vault", str(atlas_dir / "vault"), *setup.split()], env)
        skill = install_skill(ROOT, env)
        sh([*uv, str(skill / "scripts" / "atlas_install.py"), "upgrade"], env)
        sh(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(first)], env)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = open(run / "server.log", "w", encoding="utf-8")
    server = subprocess.Popen([*uv, str(atlas_dir / "engine" / "atlas.py"), "--vault", str(atlas_dir / "vault"),
                               "serve", "--operator", "--port", str(port)], env=env, stdout=log, stderr=subprocess.STDOUT,
                              start_new_session=True)
    url = f"http://127.0.0.1:{port}"
    (run / "run.json").write_text(json.dumps({"run": str(run), "url": url, "pid": server.pid}), encoding="utf-8")
    for _ in range(300):
        try:
            urllib.request.urlopen(url + "/api/meta", timeout=2).read()
            break
        except OSError:
            time.sleep(0.2)
    else:
        end(server.pid)
        sys.exit(f"the engine did not start; see {run / 'server.log'} (the run folder stays for a look: {run})")

    agent = args.id
    facts = {"run": str(run), "home": str(home), "atlas": str(atlas_dir), "vault": str(atlas_dir / "vault"),
             "url": url, "port": port, "pid": server.pid, "agent": agent, "scenario": sc["name"],
             "version": (atlas_dir / "VERSION").read_text(encoding="utf-8").strip(),
             "started": dt.datetime.now().isoformat(timespec="seconds")}
    (run / "run.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
    (run / "operator.md").write_text(OPERATOR.format(**facts, timebox=sc.get("timebox", 15)), encoding="utf-8")
    (run / "user.md").write_text(USER.format(**facts, timebox=sc.get("timebox", 15), steps=sc.get("max_steps", 25),
                                             scenario_text=sc["text"], template=SMOKE / "report-template.md"),
                                 encoding="utf-8")
    print(json.dumps(facts, indent=1))


def end(pid: int) -> None:
    """End the server and the Python process `uv run` started for it."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)  # the server runs in its own session: end the group
        except (ProcessLookupError, PermissionError):
            pass


def stop(args) -> None:
    run = Path(args.run)
    facts = json.loads((run / "run.json").read_text(encoding="utf-8"))
    end(facts["pid"])
    if args.clean:
        shutil.rmtree(run, ignore_errors=True)
    print(f"stopped {facts['url']}{' and removed ' + str(run) if args.clean else ''}")


OPERATOR = """# Smoke run: operator

You are the agent connected to a fresh Atlas install, the way a user's agent would be.

- Atlas folder: `{atlas}` (its `AGENTS.md` and `.agents/skills/` are your instructions; read them first)
- Your agent id: `{agent}`. Use `--agent {agent}` with `wait`, `say`, `boot` and `commit`.
- Atlas runs at {url}; it is already started.
- Isolation: work only inside `{run}`. Run every command with `HOME="{home}"` and the git identity
  `GIT_AUTHOR_NAME="Smoke Test" GIT_AUTHOR_EMAIL=smoke@example.com GIT_COMMITTER_NAME="Smoke Test"
  GIT_COMMITTER_EMAIL=smoke@example.com`, so nothing touches the real user's configuration.
  Do not install anything outside this folder.

Loop: `uv run --no-project engine/atlas.py --vault "{vault}" wait --agent {agent}` (from `{atlas}`), do
what the message asks with the skills, answer with `say`, and wait again. Stop after {timebox} minutes
or when a message says "smoke run over". Keep a short log of what you did in `{run}/operator-log.md`:
each request, the skill you used, what you wrote, anything that went wrong or was unclear in the
instructions.
"""

USER = """# Smoke run: user

You play a person using Atlas for the first time. Atlas runs at {url} and an agent answers in its
chat. You only know what the screen shows and what the scenario below says; you have not seen the
code or the pull request's diff. Missing or confusing guidance on screen is a finding, not your fault.

- Drive the browser (Playwright): open pages, press buttons, write in the chat, wait for answers.
- Timebox: {timebox} minutes, at most {steps} steps. Stop there and report what you reached.
- Screenshots: each "screenshot" in the scenario, in dark and in light (switch with the theme button).
  Save them under `{run}/shots/`.
- When you are done, write "smoke run over" in the chat.
- Report: fill in `{template}` and save it as `{run}/report.md`. Sort every finding into bug,
  papercut or idea; give each bug the steps to reproduce.

## The scenario

{scenario_text}
"""


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("scenario")
    p.add_argument("--ref", help="install this git ref first, then upgrade to the checkout (upgrade scenario)")
    p.add_argument("--id", default="smoke", help="the operator's agent id")
    s = sub.add_parser("stop")
    s.add_argument("run")
    s.add_argument("--clean", action="store_true")
    args = ap.parse_args()
    {"prepare": prepare, "stop": stop}[args.cmd](args)


if __name__ == "__main__":
    main()
