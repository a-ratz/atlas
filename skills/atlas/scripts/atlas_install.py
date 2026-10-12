#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Install Atlas from this skill into a folder the user picks, and keep the skill pointing at it.

    uv run --no-project scripts/atlas_install.py status [--json]
    uv run --no-project scripts/atlas_install.py install <dir>
    uv run --no-project scripts/atlas_install.py locate <dir>          # use an existing Atlas folder (e.g. a clone)
    uv run --no-project scripts/atlas_install.py upgrade [--dry-run]   # app files -> this skill's version
    uv run --no-project scripts/atlas_install.py restore <what> [--dry-run]   # factory copy: a skill, engine, ...

The app ships in ../app. The user's Atlas is a copy of it in its own folder ("home"); the
user's knowledge lives in home/vault and is never overwritten. The pointer to home lives in
this skill folder (config.json) and, because `npx skills add/update` replaces the skill
folder, also in the user's config dir (~/.config/atlas/config.json). Each restores the other.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
APP = SKILL / "app"
CFG = SKILL / "config.json"
MANIFEST = ".atlas-install.json"   # in home: version + the factory hash of every file it got from the skill
SKIP_DIRS = {"__pycache__", ".git", ".atlas", "node_modules"}
SKIP_FILES = {".DS_Store", "config.json"}


def mirror_path() -> Path:
    base = os.environ.get("APPDATA") if os.name == "nt" else None
    base = Path(base) if base else Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "atlas" / "config.json"


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def version() -> str:
    return (APP / "VERSION").read_text(encoding="utf-8").strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle() -> dict[str, Path]:
    """Every file the skill would install, keyed by its path inside home."""
    out = {}
    for root, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name in SKIP_FILES:
                continue
            path = Path(root) / name
            out[path.relative_to(APP).as_posix()] = path
    return out


def app_owned(rel: str) -> bool:
    """Files the app owns and upgrades. Everything under vault/ belongs to the user."""
    return not rel.startswith("vault/")


# ------------------------------------------------------------------ pointer

def load_cfg() -> dict | None:
    for src in (CFG, mirror_path()):
        try:
            cfg = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if src != CFG:  # the skill folder was replaced (npx skills update): put the pointer back
            save_cfg(cfg)
        return cfg
    return None


def save_cfg(cfg: dict) -> None:
    for dst in (CFG, mirror_path()):
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"note: could not write {dst}: {exc}", file=sys.stderr)


def is_home(path: Path) -> bool:
    return (path / "engine" / "atlas.py").is_file() and (path / "AGENTS.md").is_file()


def read_manifest(home: Path) -> dict:
    try:
        return json.loads((home / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": None, "files": {}}


def write_manifest(home: Path, manifest: dict) -> None:
    (home / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def git(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=home, capture_output=True, text=True)


def link_claude_skills(home: Path) -> str:
    """Claude Code reads .claude/skills; the skills live in .agents/skills (every other harness)."""
    link = home / ".claude" / "skills"
    if link.exists() or link.is_symlink():
        return "exists"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(Path("..") / ".agents" / "skills", link, target_is_directory=True)
        return "symlink"
    except OSError:  # Windows without symlink rights: a copy works, it just needs `restore skills` after edits
        shutil.copytree(home / ".agents" / "skills", link)
        return "copy"


# ------------------------------------------------------------------ commands

def status(as_json: bool) -> dict:
    cfg = load_cfg()
    info: dict = {"skill": str(SKILL), "bundled_version": version()}
    if not cfg:
        info["state"] = "not installed"
    else:
        home = Path(cfg["home"])
        info["home"] = str(home)
        if not is_home(home):
            info["state"] = "home missing"
        else:
            info["state"] = "ok"
            man = read_manifest(home)
            info["installed_version"] = man.get("version")
            modified, upgradable, new = [], [], []
            for rel, src in bundle().items():
                if not app_owned(rel):
                    continue
                dst, factory = home / rel, man["files"].get(rel)
                if not dst.exists():
                    new.append(rel)
                    continue
                current, bundled = sha(dst), sha(src)
                if factory and current != factory:
                    modified.append(rel)
                elif current != bundled:
                    upgradable.append(rel)
            info.update(modified=sorted(modified), upgradable=sorted(upgradable), new=sorted(new))
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        print(f"state: {info['state']}" + (f" · home: {info['home']}" if "home" in info else ""))
        if info["state"] == "ok":
            print(f"version: installed {info['installed_version']} · this skill {info['bundled_version']}")
            if info["upgradable"] or info["new"]:
                print(f"upgrade available: {len(info['upgradable'])} changed, {len(info['new'])} new app file(s)"
                      " (`atlas_install.py upgrade --dry-run`)")
            if info["modified"]:
                print(f"changed in home since install (kept on upgrade): {', '.join(info['modified'])}")
        elif info["state"] == "home missing":
            print("the folder moved or is gone: `locate <dir>`, or install again")
        else:
            print("first run: install Atlas (see references/onboarding.md)")
    return info


def install(target: str) -> None:
    home = Path(target).expanduser().resolve()
    if home.exists() and any(p.name != ".git" for p in home.iterdir()):
        sys.exit(f"{home} is not empty. Pick an empty or new folder, e.g. {home / 'atlas'}")
    files = bundle()
    for rel, src in files.items():
        dst = home / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    linked = link_claude_skills(home)
    write_manifest(home, {"version": version(), "installed_at": now(), "files": {rel: sha(p) for rel, p in files.items()}})
    notes = [f"installed Atlas {version()} into {home} ({len(files)} files; .claude/skills: {linked})"]
    inside = git(home, "rev-parse", "--show-toplevel")
    if inside.returncode == 0 and Path(inside.stdout.strip()).resolve() != home:
        notes.append(f"inside the git repository {inside.stdout.strip()}: no git init, no commit")
    else:
        if inside.returncode != 0:
            git(home, "init", "-q")
        git(home, "add", "-A")
        done = git(home, "commit", "-q", "-m", f"atlas: install {version()}")
        notes.append("git: initialized and committed" if done.returncode == 0
                     else "git: initialized; commit skipped (set git user.name and user.email, then commit)")
    save_cfg({"home": str(home), "installed_at": now(), "version": version()})
    notes.append(f"pointer saved: {CFG} and {mirror_path()}")
    print("\n".join(notes))


def locate(target: str) -> None:
    home = Path(target).expanduser().resolve()
    if not is_home(home):
        sys.exit(f"{home} is not an Atlas folder (no engine/atlas.py and AGENTS.md)")
    linked = link_claude_skills(home)
    man = read_manifest(home)
    save_cfg({"home": str(home), "located_at": now(), "version": man.get("version")})
    print(f"pointing at {home} (Atlas {man.get('version') or 'unknown version'}; .claude/skills: {linked})")


def _home_or_exit() -> Path:
    cfg = load_cfg()
    if not cfg or not is_home(Path(cfg["home"])):
        sys.exit("no Atlas installed or found: run `status`")
    return Path(cfg["home"])


def upgrade(dry: bool) -> None:
    """Replace app files the user has not changed; add new ones; never touch changed files or the vault."""
    home = _home_or_exit()
    man = read_manifest(home)
    files = bundle()
    replaced, added, kept, removed = [], [], [], []
    for rel, src in files.items():
        dst, factory = home / rel, man["files"].get(rel)
        if not app_owned(rel):
            if not dst.exists() and rel not in man["files"]:
                added.append(rel)  # a new template file in the vault, never one the user deleted
            continue
        if not dst.exists():
            added.append(rel)
        elif sha(dst) == sha(src):
            continue
        elif factory is None or sha(dst) == factory:
            replaced.append(rel)
        else:
            kept.append(rel)
    for rel, factory in man["files"].items():
        if app_owned(rel) and rel not in files and (home / rel).exists():
            (removed if sha(home / rel) == factory else kept).append(rel)
    print(f"Atlas {man.get('version')} -> {version()} in {home}")
    for label, items in (("replace", replaced), ("add", added), ("remove", removed),
                         ("keep (changed by you; `restore` to reset)", kept)):
        for rel in items:
            print(f"  {label}: {rel}")
    if dry or not (replaced or added or removed):
        print("dry run: nothing changed" if dry else "already up to date")
        return
    for rel in replaced + added:
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files[rel], home / rel)
        man["files"][rel] = sha(files[rel])
    for rel in removed:
        (home / rel).unlink()
        man["files"].pop(rel, None)
    man.update(version=version(), upgraded_at=now())
    write_manifest(home, man)
    save_cfg({**(load_cfg() or {}), "home": str(home), "version": version()})
    print("done; commit it in home: git add -A && git commit -m 'atlas: upgrade to " + version() + "'")


RESTORE_GROUPS = {
    "all": lambda rel: app_owned(rel) or rel == "vault/atlas.yaml",
    "skills": lambda rel: rel.startswith(".agents/skills/"),
    "engine": lambda rel: rel.startswith("engine/"),
    "agents-md": lambda rel: rel in ("AGENTS.md", "CLAUDE.md"),
    "registry": lambda rel: rel == "vault/atlas.yaml",
}


def restore(what: str, dry: bool) -> None:
    """Put the factory copy back. The current file goes to .atlas-backup/<time>/ first."""
    home = _home_or_exit()
    man = read_manifest(home)
    files = bundle()
    match = RESTORE_GROUPS.get(what) or (lambda rel: rel.startswith(f".agents/skills/{what}/") or rel == what)
    chosen = [rel for rel in files if match(rel) and (not (home / rel).exists() or sha(home / rel) != sha(files[rel]))]
    if not any(match(rel) for rel in files):
        sys.exit(f"nothing called `{what}`: use all, skills, engine, agents-md, registry, a skill name or a path")
    if not chosen:
        print(f"{what}: already the factory version")
        return
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for rel in chosen:
        print(f"  restore: {rel}")
        if dry:
            continue
        dst = home / rel
        if dst.exists():
            backup = home / ".atlas-backup" / stamp / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files[rel], dst)
        man["files"][rel] = sha(files[rel])
    if dry:
        print("dry run: nothing changed")
        return
    write_manifest(home, man)
    print(f"restored {len(chosen)} file(s); your previous versions are in .atlas-backup/{stamp}/")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    sub.add_parser("install").add_argument("dir")
    sub.add_parser("locate").add_argument("dir")
    u = sub.add_parser("upgrade")
    u.add_argument("--dry-run", action="store_true")
    r = sub.add_parser("restore")
    r.add_argument("what")
    r.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "status":
        status(a.json)
    elif a.cmd == "install":
        install(a.dir)
    elif a.cmd == "locate":
        locate(a.dir)
    elif a.cmd == "upgrade":
        upgrade(a.dry_run)
    else:
        restore(a.what, a.dry_run)


if __name__ == "__main__":
    main()
