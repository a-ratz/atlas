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
"""Atlas: a knowledge vault you grow by talking to your agent, and read in the browser.

Run from the repo root (or anywhere; paths resolve from this file):

    uv run --no-project engine/atlas.py serve              # standalone: chat becomes notes in vault/you/notes/
    uv run --no-project engine/atlas.py serve --operator   # an agent session answers in the chat
    uv run --no-project engine/atlas.py wait [--agent <id>]           # operator: block until the user writes, print it
    uv run --no-project engine/atlas.py say "text" [--open <path>] [--agent <id>]   # operator: reply in the chat
    uv run --no-project engine/atlas.py next               # what the vault suggests doing next
    uv run --no-project engine/atlas.py check              # notes that need a fix (exit 1 if any)
    uv run --no-project engine/atlas.py boot <project> --agent <id>   # an agent's context for a project
    uv run --no-project engine/atlas.py commit --agent <id> -m "msg" <paths>   # stamp authorship, commit
    uv run --no-project engine/atlas.py close --agent <id> [--checkpoint]   # /close covered this session
    uv run --no-project engine/atlas.py sessions [digest <id> | skip <id> --reason "…"]   # sessions without /close
    uv run --no-project engine/atlas.py hook session-start   # SessionStart hook (payload on stdin)
    uv run --no-project engine/atlas.py tour --since 2026-10-04 --agent <id>   # scaffold a tour of what changed (tours/)
    uv run --no-project engine/atlas.py demo [--remove]    # load the demo notes, or take them out again
    uv run --no-project engine/atlas.py machine            # this machine's id (keys of project paths)
    uv run --no-project engine/atlas.py map-path <project> <dir>   # record where a project's checkout lives here
    uv run --no-project engine/atlas.py status
    uv run --no-project engine/atlas.py expose             # print the Tailscale command for the tailnet

Every command takes --vault <dir> (default: ./vault next to engine/, or $ATLAS_VAULT).
The vault files are the truth. Atlas reads them live through <vault>/atlas.yaml
(or engine/registry.default.yaml); its index and chat state (<vault>/.atlas/) are disposable.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import fnmatch
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

APP = Path(__file__).resolve().parent
STATIC = APP / "static"
DEFAULT_PORT = 8765
VAULT = STATE = NOTES = REGISTRY = INBOX = OUTBOX = CURSOR = HEARTBEAT = SESSION = PRESENCE = SNOOZE = TOURS = Path()
DROP_MAX = 50 * 1024 * 1024
AGENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def ensure_state() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ignore = STATE / ".gitignore"
    if not ignore.exists():  # chat logs never get committed with the vault
        ignore.write_text("*\n", encoding="utf-8")


def set_vault(path: str | Path | None) -> None:
    """Point every module path at one vault. Called once before any command runs."""
    global VAULT, STATE, NOTES, REGISTRY, INBOX, OUTBOX, CURSOR, HEARTBEAT, SESSION, PRESENCE, SNOOZE, TOURS
    VAULT = Path(path or os.environ.get("ATLAS_VAULT") or APP.parent / "vault").expanduser().resolve()
    STATE = VAULT / ".atlas"
    NOTES = VAULT / "you" / "notes"  # the user's own notes and actions, read by agents
    REGISTRY = VAULT / "atlas.yaml" if (VAULT / "atlas.yaml").exists() else APP / "registry.default.yaml"
    INBOX, OUTBOX, CURSOR, HEARTBEAT, SESSION = (STATE / n for n in
                                                 ("inbox.jsonl", "outbox.jsonl", "cursor", "heartbeat", "session.json"))
    PRESENCE = STATE / "agents"  # <id>.beat (touched by `wait --agent`), <id>.json (project from `boot`)
    SNOOZE = STATE / "snooze.json"  # rows of Needs you the user put off
    TOURS = VAULT / "tours"  # guided tours through what changed, written by agents
    old, new = VAULT / "brain", VAULT / "cabinet"
    if old.is_dir() and not new.exists():  # 0.6.1: the Brain is now the Cabinet; move the folder once
        try:
            old.rename(new)
            print("Atlas: moved brain/ to cabinet/ (the Brain is now the Cabinet).", file=sys.stderr)
        except OSError:
            pass  # another Atlas process moved it first


def agent_id(value: str | None) -> str | None:
    """A named agent (`--agent claude`), or None for the single unnamed operator of earlier versions."""
    if not value:
        return None
    a = value.strip().lower()
    if not AGENT_ID.match(a):
        sys.exit(f"`{value}` is not an agent id: use the file name in agents/ (letters, digits, - and _)")
    return a

FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)
H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.M)
WIKI = re.compile(r"\[\[([^\]|#\n]+)(?:#[^\]|\n]*)?(?:\|([^\]\n]+))?\]\]")
MDLINK = re.compile(r"\]\(([^)\s#]+\.md)(#[^)]*)?\)")
DATEISH = re.compile(r"(\d{4}-\d{2}(?:-\d{2})?)")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- index

@dataclass
class Entity:
    id: str
    type: str
    title: str
    description: str
    meta: dict
    body: str
    date: str | None = None
    status: str | None = None
    group: str | None = None
    agent: str | None = None
    project: str | None = None
    mtime: float = 0.0
    links: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # frontmatter checks (registry `checks:`)
    unresolved: list[str] = field(default_factory=list)  # [[links]] that match no note
    unresolved_fields: list[str] = field(default_factory=list)  # frontmatter fields (checks.resolve) naming no note

    def card(self, index: "Index") -> dict:
        return {
            "id": self.id, "type": self.type, "title": self.title, "description": self.description,
            "date": self.date, "status": self.status, "group": self.group, "agent": self.agent,
            "project": self.project, "touched": index.touched.get(self.id),
            "by": _plain(self.meta.get("created_by")), "edited_by": _plain(self.meta.get("updated_by")),
            "facts": {k: _plain(self.meta.get(k)) for k in index.types[self.type].get("fields", [])
                      if self.meta.get(k) not in (None, "", [])},
        }


def _plain(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    if isinstance(value, (set, frozenset, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(_plain(k)): _plain(v) for k, v in value.items()}
    if isinstance(value, int) and abs(value) > 2 ** 53:
        return str(value)
    return value


def _date(value) -> str | None:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()[:10]
    if isinstance(value, str):
        m = DATEISH.search(value)
        return m.group(1) if m else None
    return None


def parse_file(path: Path) -> tuple[dict, str, str | None]:
    """(frontmatter, body, problem): a broken frontmatter still yields what can be read, plus the problem."""
    import yaml
    text = path.read_text(encoding="utf-8", errors="replace")
    m = FRONT.match(text)
    if not m:
        return {}, text, None
    problem = None
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except Exception as exc:  # YAMLError, but also ValueError for impossible dates like 2026-02-30
        problem = f"frontmatter is not valid YAML ({type(exc).__name__})"
        try:
            meta = yaml.load(m.group(1), Loader=yaml.BaseLoader) or {}  # everything as strings
        except Exception:
            meta = {}
    return (meta if isinstance(meta, dict) else {}), text[m.end():], problem


def first_paragraph(body: str) -> str:
    for block in re.split(r"\n\s*\n", body):
        line = " ".join(block.split())
        if line and not line.startswith(("#", "|", "```", "---", "<!--", "- [[", "Topics:")):
            line = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), line)
            line = re.sub(r"[*_`]", "", line)
            return line[:240] + ("…" if len(line) > 240 else "")
    return ""


# ---------------------------------------------------------------- cabinet: people and organizations
# Types with `recall: true` in the registry are cards: `name`, `aliases`, the current state under the
# heading and an append-only `## Timeline`. Their names are matched in chat messages (`wait`, `recall`)
# and in every other note ("mentioned in"); a note's `authors:` naming a card counts as "written by".

AUTHOR_FIELDS = ("authors", "author")
TAG_FIELDS = ("people", "orgs")


def registry_types() -> dict[str, dict]:
    """The registry's types, plus default types a vault registry copied before they existed."""
    import yaml
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    types = {t["id"]: t for t in reg.get("types", [])}
    if REGISTRY != APP / "registry.default.yaml":
        for t in (yaml.safe_load((APP / "registry.default.yaml").read_text(encoding="utf-8")) or {}).get("types", []):
            if t["id"] in ("tour", "person", "org") and t["id"] not in types:
                types[t["id"]] = t
    return cabinet_renamed(types)


def aside_label(t: dict) -> str:
    """The word after the sidebar's "+N". 0.6 vaults wrote "resting" for questions whose files say "dormant"."""
    label = (t.get("count") or {}).get("aside_label", "")
    return "dormant" if label == "resting" and (t.get("count") or {}).get("aside") == ["dormant"] else label


def cabinet_renamed(types: dict[str, dict]) -> dict[str, dict]:
    """A registry copied before 0.6.1 still says Brain and brain/: read both as the Cabinet."""
    for spec in types.values():
        spec["globs"] = [re.sub(r"^brain/", "cabinet/", g) for g in spec.get("globs") or []]
        if spec.get("section") == "Brain":
            spec["section"] = "Cabinet"
    return types


def card_terms(meta: dict) -> set[str]:
    """The names a card answers to: its `name` and `aliases`."""
    aliases = meta.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    return {str(t).strip() for t in [meta.get("name"), *aliases] if t and len(str(t).strip()) >= 2}


def term_regex(term: str) -> "re.Pattern":
    """Whole words (a hyphen counts as a boundary, so "Nightlight-Projekt" matches); a short term (three characters or fewer, like "MS") only with exact case."""
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", 0 if len(term) <= 3 else re.I)


def unique_terms(cards: dict[str, dict]) -> dict[str, str]:
    """term -> card id, for terms that name exactly one card: an alias two cards share matches neither."""
    owners: dict[str, tuple[str, set]] = {}
    for cid, meta in cards.items():
        for term in card_terms(meta):
            owners.setdefault(term if len(term) <= 3 else term.lower(), (term, set()))[1].add(cid)
    return {term: next(iter(cids)) for term, cids in owners.values() if len(cids) == 1}


def card_state(body: str, n: int = 500) -> str:
    """A card's current state: the text between its heading and its first `##` section."""
    body = re.sub(r"^\s*# .*\n", "", body, count=1)
    head = re.split(r"\n## ", body, maxsplit=1)[0]
    head = " ".join(re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), head).split())
    return head if len(head) <= n else head[:n].rsplit(" ", 1)[0] + " …"


def recall_cards(text: str, limit: int = 3) -> list[dict]:
    """The cards whose name or alias appears in the text, in order of appearance (at most `limit`)."""
    cards, bodies = {}, {}
    for spec in registry_types().values():
        if not spec.get("recall"):
            continue
        for pattern in spec["globs"]:
            for path in sorted(VAULT.glob(pattern)):
                if path.is_file() and path.suffix == ".md":
                    meta, body, _ = parse_file(path)
                    if meta.get("name"):
                        rel = path.relative_to(VAULT).as_posix()
                        cards[rel], bodies[rel] = meta, body
    hits: dict[str, int] = {}
    for term, cid in unique_terms(cards).items():
        m = term_regex(term).search(text or "")
        if m:
            hits[cid] = min(hits.get(cid, m.start()), m.start())
    out = []
    for cid in sorted(hits, key=hits.get)[:limit]:
        meta = cards[cid]
        facts = " · ".join(str(_plain(meta[k])) for k in ("role", "kind", "relation", "email") if meta.get(k))
        out.append({"id": cid, "name": str(meta["name"]), "facts": facts, "state": card_state(bodies[cid])})
    return out


def _field_text(meta: dict, keys) -> list[str]:
    out = []
    for k in keys:
        v = meta.get(k)
        out += [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
    return out


def mentions(index: "Index", card: "Entity") -> dict:
    """The notes that name this card: `written` (their `authors:`) and `mentioned` (text, `people:`, `orgs:`)."""
    key = (index.version, card.id)
    cached = index._mentions.get(key)
    if cached is not None:
        return cached
    cards = {e.id: e.meta for e in index.entities.values() if index.types[e.type].get("recall")}
    rx = [term_regex(t) for t, cid in unique_terms(cards).items() if cid == card.id]
    written, mentioned = [], []
    for e in index.entities.values():
        if e.id == card.id or not rx:
            continue
        authors = _field_text(e.meta, AUTHOR_FIELDS)
        if any(r.search(a) for a in authors for r in rx):
            written.append(e)
        elif any(r.search(t) for t in [e.title, e.description, e.body, *_field_text(e.meta, TAG_FIELDS)] for r in rx):
            mentioned.append(e)
    order = {tid: i for i, tid in enumerate(index.order)}
    sort = lambda xs: [x.card(index) for x in sorted(xs, key=lambda x: (order.get(x.type, 99), x.title.lower()))][:600]
    out = {"written": sort(written), "mentioned": sort(mentioned),
           "total": {"written": len(written), "mentioned": len(mentioned)}}
    index._mentions = {key: out, **{k: v for k, v in index._mentions.items() if k[0] == index.version}}
    return out


class Index:
    def __init__(self) -> None:
        import yaml
        reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
        self.types = {t["id"]: t for t in reg.get("types", [])}
        self.commands = reg.get("commands")
        if REGISTRY != APP / "registry.default.yaml":  # a vault registry without moves/checks/commands gets the defaults
            default_reg = yaml.safe_load((APP / "registry.default.yaml").read_text(encoding="utf-8")) or {}
            defaults = {t["id"]: t for t in default_reg.get("types", [])}
            for tid, spec in self.types.items():
                for key in ("moves", "checks", "count"):
                    if key not in spec and defaults.get(tid, {}).get(key):
                        spec[key] = defaults[tid][key]
            legacy = {  # what 0.6.x shipped; only a type still in that shape is migrated, customizations stay
                "person": (["role", "org", "relation", "email", "phone", "updated"], [["🔄 Update"]]),
                "org": (["kind", "relation", "website", "updated"], [["🔄 Update", "🧭 What's next?"]]),
            }
            for tid, (old_fields, old_moves) in legacy.items():  # cards copied before 0.7 learn depth and Expand
                spec, default = self.types.get(tid), defaults.get(tid, {})
                if not spec or not default or "status" in spec:
                    continue
                if spec.get("fields") == old_fields:
                    spec["fields"] = [*old_fields[:-1], "depth", "checked", old_fields[-1]]
                    spec["status"] = default.get("status")
                    spec.setdefault("checks", default.get("checks"))
                if [m.get("label") for m in spec.get("moves") or []] in old_moves:
                    spec["moves"] = [*(m for m in default.get("moves", []) if m.get("label") == "🔎 Expand"), *spec["moves"]]
            old_commands = {"learn", "distill", "map", "sketch", "project", "close", "remember", "check", "next", "tour"}
            if self.commands is not None and {c.get("name") for c in self.commands} == old_commands:
                self.commands = [*self.commands, *(c for c in default_reg.get("commands") or [] if c.get("name") == "expand-cards")]
            ideas_07 = {  # what 0.7 shipped for ideas and projects: only that exact shape learns the spec step
                "sketch": (["status", "date"], ["🔎 Research prior art", "⚔️ Find the weak spots"], ["origin", "spec"]),
                "spec": (None, ["⚔️ Review it"], []),
                "project": (["status", "repo", "paths"], None, ["source"]),
            }
            for tid, (old_fields, old_moves, new_fields) in ideas_07.items():
                spec, default = self.types.get(tid), defaults.get(tid, {})
                if not spec or not default:
                    continue
                if old_fields and spec.get("fields") == old_fields:
                    spec["fields"] = [*old_fields, *new_fields]
                if old_moves and [m.get("label") for m in spec.get("moves") or []] == old_moves:
                    spec["moves"] = [*spec["moves"], *default.get("moves", [])[len(old_moves):]]
            if self.commands is not None and {c.get("name") for c in self.commands} == old_commands | {"expand-cards"}:
                at = next(i for i, c in enumerate(self.commands) if c.get("name") == "sketch") + 1
                self.commands = [*self.commands[:at], *(c for c in default_reg.get("commands") or [] if c.get("name") == "spec"),
                                 *self.commands[at:]]
            if self.commands is not None and {c.get("name") for c in self.commands} == old_commands | {"expand-cards", "spec"}:
                at = next(i for i, c in enumerate(self.commands) if c.get("name") == "map") + 1  # 0.9 learns /revisit (#52)
                self.commands = [*self.commands[:at], *(c for c in default_reg.get("commands") or [] if c.get("name") == "revisit"),
                                 *self.commands[at:]]
            ins = self.types.get("insight")
            if ins and [m.get("label") for m in ins.get("moves") or []] == ["🔗 Find connections", "⚔️ Challenge it", "🧭 Next research avenues"]:
                ins["moves"] = [*ins["moves"], *(m for m in defaults.get("insight", {}).get("moves", [])
                                                 if m.get("label") == "🔁 Revisit its source")]
            q = self.types.get("question")
            if q and [m.get("label") for m in q.get("moves") or []] == ["🔎 Research this"]:  # copied before 0.6.4
                q["moves"] = [*q["moves"], *(m for m in defaults.get("question", {}).get("moves", [])
                                            if m.get("label") != "🔎 Research this")]  # its own send text stays
            if self.commands is None:
                self.commands = default_reg.get("commands")
            if "tour" not in self.types and "tour" in defaults:  # tours came after this registry was copied
                self.types["tour"] = defaults["tour"]
                if not any(c.get("name") == "tour" for c in self.commands or []):
                    self.commands = [*(self.commands or []), *(c for c in default_reg.get("commands") or [] if c.get("name") == "tour")]
            for tid in ("person", "org"):  # the cabinet came after this registry was copied, too
                if tid not in self.types and tid in defaults:
                    self.types[tid] = defaults[tid]
            cabinet_renamed(self.types)
        self.commands = self.commands or []
        self.user = reg.get("user") or {}
        self.drop = {"dir": "captures", "file": "Read {path} and land what matters as a capture",
                     "url": "Read {url} and land what matters as a capture", **(reg.get("drop") or {})}
        self.order = list(self.types)
        self.entities: dict[str, Entity] = {}
        self.by_stem: dict[str, str] = {}
        self.backlinks: dict[str, list[str]] = {}
        self.touched: dict[str, str] = {}
        self.moved: dict[str, str] = {}  # old path -> new path, for notes seen leaving one and arriving at the other
        self.version = 0
        self.built_at = ""
        self._cache: dict[str, tuple[float, Entity]] = {}
        self._mentions: dict[tuple, dict] = {}
        self._lock = threading.Lock()
        self._last_check = 0.0
        self.refresh(force=True)

    # -- discovery
    def _paths(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for tid, spec in self.types.items():
            for pattern in spec["globs"]:
                for path in VAULT.glob(pattern):
                    if not path.is_file() or path.suffix != ".md":
                        continue
                    rel = path.relative_to(VAULT).as_posix()
                    if rel in found or any(fnmatch.fnmatch(rel, ex) for ex in spec.get("exclude", [])):
                        continue
                    if "/raw/" in rel or "/node_modules/" in rel or "/tmp/" in "/" + rel:
                        continue
                    if any(part.startswith(".") for part in rel.split("/")[:-1]):
                        continue  # .claude/.agents skill copies, .state, etc.
                    if spec.get("capture_stub_rule") and rel.startswith("ops/queue/archive/"):
                        folder, stem = path.parent.name, path.stem
                        if not folder.endswith(stem):
                            continue
                    found[rel] = tid
        return found

    def _build(self, rel: str, tid: str, mtime: float) -> Entity:
        spec = self.types[tid]
        meta, body, yaml_problem = parse_file(VAULT / rel)
        h1 = H1.search(body)
        title = str(meta.get("title") or (h1.group(1) if h1 else Path(rel).stem)).strip()
        description = str(meta.get("description") or meta.get("short") or first_paragraph(body)).strip()
        date = _date(meta.get(spec.get("date", ""))) or _date(meta.get("date")) or _date(meta.get("created"))
        parts = rel.split("/")
        group = agent = project = None
        if spec.get("group") == "frame" and len(parts) >= 3:
            group = "/".join(parts[1:-1])
            date = date or _date(parts[-2])
        if parts[0] == "projects" and len(parts) >= 3:  # projects/<group>/_group.md, projects/<group>/<slug>/...
            group = parts[1]
            project = parts[2] if len(parts) >= 4 else None
        if parts[0] == "memory" and len(parts) > 1:
            agent = parts[1]
            if len(parts) > 3 and parts[2] == "projects":
                project = parts[3]
            group = agent
        if tid == "social":
            date = date or _date(Path(rel).stem)
        status_field = spec.get("status")
        status = meta.get(status_field) if status_field else None
        ent = Entity(rel, tid, title, description, meta, body, date,
                     str(status) if status not in (None, "") else None, group, agent, project, mtime)
        ent.problems = [yaml_problem] if yaml_problem else frontmatter_problems(meta, spec.get("checks") or {})  # fix YAML first
        return ent

    def refresh(self, force: bool = False) -> bool:
        """Re-scan if files changed. Cheap enough to call on every request (rate-limited)."""
        if not force and time.time() - self._last_check < 10:
            return False
        with self._lock:
            self._last_check = time.time()
            paths = self._paths()
            changed = force or set(paths) != set(self.entities)
            entities: dict[str, Entity] = {}
            for rel, tid in paths.items():
                try:  # one odd or vanishing file must not stop the whole index
                    mtime = (VAULT / rel).stat().st_mtime
                    cached = self._cache.get(rel)
                    if cached and cached[0] == mtime and cached[1].type == tid:
                        entities[rel] = cached[1]
                    else:
                        entities[rel] = self._build(rel, tid, mtime)
                        self._cache[rel] = (mtime, entities[rel])
                        changed = True
                except (OSError, ValueError, TypeError) as exc:
                    print(f"atlas: skipped {rel}: {exc}", file=sys.stderr)
            if not changed:
                return False
            self._track_moves(entities)
            self.entities = entities
            self._link()
            self.touched = git_last_touched()
            self.version += 1
            self.built_at = now_iso()
            return True

    def _track_moves(self, entities: dict) -> None:
        """A move is a note that left one path and arrived at another with the same file name in the same scan
        (a capture distilled into sources/). A note that only vanished is no move, even if its name lives on."""
        new = [n for n in entities if n not in self.entities]
        for old in self.entities.keys() - entities.keys():
            same = [n for n in new if Path(n).name == Path(old).name]
            if len(same) > 1:  # two project.md moved at once: the project folder decides
                same = [n for n in same if Path(n).parent.name == Path(old).parent.name]
            if len(same) == 1:
                self.moved[old] = same[0]
        for rel in entities.keys() & self.moved.keys():  # a path in use again is no longer a move
            del self.moved[rel]

    def moved_to(self, rel: str) -> str | None:
        """Where a note that moved (maybe more than once) lives now."""
        seen = set()
        while rel in self.moved and rel not in seen:
            seen.add(rel)
            rel = self.moved[rel]
        return rel if seen and rel in self.entities else None

    def _link(self) -> None:
        rank = {t: i for i, t in enumerate(self.order)}
        by_stem: dict[str, str] = {}
        for e in sorted(self.entities.values(), key=lambda e: rank[e.type], reverse=True):
            by_stem[Path(e.id).stem] = e.id
            by_stem[Path(e.id).stem.lower()] = e.id
            by_stem.setdefault(e.title.lower(), e.id)
        self.by_stem = by_stem
        backlinks: dict[str, list[str]] = {}
        for e in self.entities.values():
            targets, unresolved = [], []
            for target, _ in WIKI.findall(e.body):
                hit = self.resolve(target)
                if hit and hit != e.id and hit not in targets:
                    targets.append(hit)
                elif not hit and target.strip() not in unresolved:
                    unresolved.append(target.strip())
            e.unresolved = unresolved
            e.unresolved_fields = []
            for fld in (self.types[e.type].get("checks") or {}).get("resolve", []):  # frontmatter fields naming a note
                vals = e.meta.get(fld)
                for val in vals if isinstance(vals, list) else [vals]:
                    if isinstance(val, str) and val.strip() and not self.resolve(val.strip().strip("[]")):
                        e.unresolved_fields.append(f"`{fld}: {val.strip()}` matches no note")
            for href, _ in MDLINK.findall(e.body):
                hit = self.resolve_path(e.id, href)
                if hit and hit != e.id and hit not in targets:
                    targets.append(hit)
            e.links = targets
            for t in targets:
                backlinks.setdefault(t, []).append(e.id)
        self.backlinks = backlinks

    def resolve(self, target: str) -> str | None:
        target = target.strip()
        return self.by_stem.get(target) or self.by_stem.get(target.lower())

    def resolve_path(self, src: str, href: str) -> str | None:
        if href.startswith(("http://", "https://")):
            return None
        for base in (Path(src).parent, Path(".")):
            rel = os.path.normpath((base / href).as_posix()).replace("\\", "/")
            if rel in self.entities:
                return rel
        return self.resolve(Path(href).stem)


def git_env(**extra: str) -> dict:
    """The environment for every git call: a path is a name, not a pattern, so a note titled
    "Results [2026].md" matches only itself and never "Results 2.md" (#48)."""
    return {**os.environ, "GIT_LITERAL_PATHSPECS": "1", **extra}


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(VAULT), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=git_env()).stdout
    except OSError:  # no git installed: Atlas still works, just without history
        return ""


def vault_rel(path: str, prefix: str) -> str | None:
    """git paths are relative to the repo root; entity ids are relative to the vault."""
    if not prefix:
        return path
    return path[len(prefix):] if path.startswith(prefix) else None


def git_last_touched() -> dict[str, str]:
    touched: dict[str, str] = {}
    current, prefix = "", git("rev-parse", "--show-prefix").strip()
    for line in git("-c", "core.quotepath=off", "log", "--format=@@%aI", "--name-only", "-n", "3000", "--", ".").splitlines():
        if line.startswith("@@"):
            current = line[2:12]
        elif line:
            rel = vault_rel(line, prefix)
            if rel and rel not in touched:
                touched[rel] = current
    return touched


# `atlas.py commit` adds an "Atlas-Agent: <id>" trailer; the feed shows who did it from there.
LOG_FORMAT = "--format=@@%H|%aI|%an|%(trailers:key=Atlas-Agent,valueonly,separator=%x2C)|%s"


def _log_head(line: str) -> dict:
    sha, when, author, agent, subject = line[2:].split("|", 4)
    return {"sha": sha[:8], "when": when, "author": author, "agent": agent.strip().lower() or None, "subject": subject}


def git_feed(index: Index, limit: int = 250) -> list[dict]:
    events = []
    cur, prefix = None, git("rev-parse", "--show-prefix").strip()
    for line in git("-c", "core.quotepath=off", "log", f"-n{limit}", LOG_FORMAT, "--name-only", "--", ".").splitlines():
        if line.startswith("@@"):
            cur = {**_log_head(line), "entities": [], "other": 0}
            events.append(cur)
        elif line and cur is not None:
            e = index.entities.get(vault_rel(line, prefix) or "")
            if e and len(cur["entities"]) < 200:  # a folded run counts its notes from these
                cur["entities"].append({"id": e.id, "type": e.type, "title": e.title})
            else:
                cur["other"] += 1
    events.sort(key=lambda ev: dt.datetime.fromisoformat(ev["when"]), reverse=True)  # back-dated commits too
    return [ev for ev in events if ev["entities"]]


_ADDED: dict[str, object] = {"head": None, "map": {}}


def git_added() -> dict[str, str]:
    """When each file first appeared in the vault (a move counts as a new arrival). Cached per HEAD."""
    head = git("rev-parse", "HEAD").strip()
    if head and head == _ADDED["head"]:
        return _ADDED["map"]  # type: ignore[return-value]
    added: dict[str, str] = {}
    current, prefix = "", git("rev-parse", "--show-prefix").strip()
    for line in git("-c", "core.quotepath=off", "log", "--no-renames", "--diff-filter=A", "--format=@@%aI",
                    "--name-only", "--", ".").splitlines():
        if line.startswith("@@"):
            current = line[2:12]
        elif line:
            rel = vault_rel(line, prefix)
            if rel:
                added[rel] = current  # newest first: the last write is the earliest arrival
    _ADDED.update(head=head, map=added)
    return added


def added_on(index: Index, e: "Entity") -> str | None:
    """The day a note arrived (YYYY-MM-DD): git first, then its content date, then its last touch."""
    for day in (git_added().get(e.id), e.date, index.touched.get(e.id)):
        if day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)[:10]):
            try:
                dt.date.fromisoformat(str(day)[:10])  # a month-only or impossible date is not a day
                return str(day)[:10]
            except ValueError:
                continue
    return None


def git_file_history(rel: str, n: int = 8) -> list[dict]:
    out = []
    for line in git("-c", "core.quotepath=off", "log", f"-n{n}", "--follow", LOG_FORMAT, "--", rel).splitlines():
        if line.startswith("@@"):
            out.append(_log_head(line))
    return out


def git_activity(folder: str, days: int = 14) -> dict[str, list[int]]:
    """Commits per day for each sub-folder two levels below `folder` (projects/<group>/<slug>), last `days` days."""
    today = dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    out: dict[str, list[int]] = {}
    current, prefix, seen = None, git("rev-parse", "--show-prefix").strip(), set()
    for line in git("-c", "core.quotepath=off", "log", "-n2000", "--format=@@%aI",  # no --since: it stops at the
                    "--name-only", "--", folder).splitlines():                         # first older (back-dated) commit
        if line.startswith("@@"):
            current, seen = dt.date.fromisoformat(line[2:12]), set()
        elif line and current and start <= current <= today:  # a commit dated ahead of the clock has no slot
            parts = (vault_rel(line, prefix) or "").split("/")
            if len(parts) >= 4:
                key = "/".join(parts[:3])
                if key not in seen:  # one commit counts once per project
                    seen.add(key)
                    out.setdefault(key, [0] * days)[(current - start).days] += 1
    return out


# --------------------------------------------------------------------------- views

def is_operational(e: "Entity") -> bool:
    return e.type == "capture" and str(e.meta.get("kind", "")) == "operational"


def needs_you(index: Index) -> dict:
    today = dt.date.today().isoformat()
    ents = index.entities.values()
    revisits = sorted((e for e in ents if e.type == "insight" and not e.meta.get("superseded_by") and _date(e.meta.get("revisit_after"))
                       and _date(e.meta.get("revisit_after")) <= today), key=lambda e: e.title)
    pending_q = [e for e in ents if e.type == "question" and str(e.meta.get("status", "")).lower() in ("pending", "open")]
    dialogs: list = []
    captures = sorted((e for e in ents if e.type == "capture" and not is_operational(e)), key=lambda e: e.date or "")  # oldest first
    operational = sorted((e for e in ents if is_operational(e)), key=lambda e: e.date or "")
    proposed = sorted((e for e in ents if e.type == "decision" and str(e.status) == "proposed"), key=lambda e: e.date or "", reverse=True)
    notes = sorted((e for e in ents if e.type == "note" and str(e.meta.get("status")) == "new"), key=lambda e: e.id, reverse=True)
    migrations: list = []
    card = lambda e: e.card(index)
    return {
        "captures": [card(e) for e in captures[:8]], "captures_total": len(captures),
        "revisits": [card(e) for e in revisits[:8]], "revisits_total": len(revisits),
        "questions": [card(e) for e in pending_q[:8]], "questions_total": len(pending_q),
        "decisions": [card(e) for e in proposed[:8]], "decisions_total": len(proposed),
        "operational": [card(e) for e in operational[:8]], "operational_total": len(operational),
        "notes": [card(e) for e in notes[:8]], "notes_total": len(notes),
        "dialogs": [card(e) for e in dialogs], "migrations": migrations,
        # what a snoozed row counts: it wakes when this changes, not only when the count does
        "sigs": {"captures": fingerprint(e.id for e in captures), "revisits": fingerprint(e.id for e in revisits),
                 "questions": fingerprint(e.id for e in pending_q), "operational": fingerprint(e.id for e in operational),
                 "notes": fingerprint(e.id for e in notes)},
    }


def fingerprint(items) -> str:
    return hashlib.sha1("\n".join(sorted(map(str, items))).encode()).hexdigest()[:12]


def metabolism(index: Index, days: int = 7) -> dict:
    """How research turns into knowledge: counts per stage and what arrived on each of the last `days` days."""
    today = dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    stages = {t: {"count": 0, "days": [0] * days} for t in ("capture", "insight", "map", "sketch", "spec")}
    for e in index.entities.values():
        if e.type not in stages or is_operational(e):
            continue
        stages[e.type]["count"] += 1
        when = added_on(index, e)
        if when:
            d = dt.date.fromisoformat(when)
            if start <= d <= today:  # a note dated in the future counts, but has no day in the past week
                stages[e.type]["days"][(d - start).days] += 1
    mapped = {i for e in index.entities.values() if e.type == "map" for i in e.links}
    unmapped = sum(1 for e in index.entities.values() if e.type == "insight" and e.id not in mapped)
    return {"stages": stages, "unmapped": unmapped, "start": start.isoformat()}


def rediscover(index: Index) -> dict:
    ents = list(index.entities.values())
    sketches = [e for e in ents if e.type == "sketch"]
    sketches.sort(key=lambda e: index.touched.get(e.id) or e.date or "")
    insights = [e for e in ents if e.type == "insight"]
    seed = int(hashlib.sha256(dt.date.today().isoformat().encode()).hexdigest(), 16)
    rng = random.Random(seed)
    daily = rng.sample(insights, min(3, len(insights)))
    speculative = [e for e in insights if e.status == "speculative"]
    return {
        "forgotten_sketches": [e.card(index) for e in sketches[:6]],
        "insights_of_the_day": [e.card(index) for e in daily],
        "speculative_pick": [e.card(index) for e in rng.sample(speculative, min(3, len(speculative)))],
    }


QUESTION_CAP = 7  # open questions a vault keeps; more reads like a backlog nobody works through


def open_questions(index: Index) -> list[Entity]:
    """Open questions, hottest first: raised most often, then most recently."""
    qs = [e for e in index.entities.values() if e.type == "question" and str(e.status) == "open"]
    return sorted(qs, key=lambda e: (_raised(e), e.date or ""), reverse=True)


def _raised(e: Entity) -> int:
    try:
        return max(1, int(e.meta.get("raised_count") or 1))
    except (TypeError, ValueError, OverflowError):  # OverflowError: `.inf` is valid YAML
        return 1


def question_of_the_day(index: Index) -> Entity | None:
    """One open question for Home, from the three hottest, changing once a day."""
    qs = open_questions(index)[:3]
    if not qs:
        return None
    seed = int(hashlib.sha256(("q" + dt.date.today().isoformat()).encode()).hexdigest(), 16)
    return random.Random(seed).choice(qs)


def recent_of(index: Index, tid: str, n: int = 6) -> list[dict]:
    items = [e for e in index.entities.values() if e.type == tid]
    if tid == "frame":  # one card per research run: its brief
        items = [e for e in items if e.id.endswith("/brief.md")]
    items.sort(key=lambda e: (index.touched.get(e.id) or "", e.date or ""), reverse=True)
    return [e.card(index) for e in items[:n]]


def render_markdown(index: Index, ent: Entity) -> str:
    return render_md(index, ent.body, ent.id)


def render_md(index: Index, text: str, base: str = "") -> str:
    """Markdown with resolved wiki links, repo-relative links and images. No raw HTML."""
    from markdown_it import MarkdownIt

    def wiki(m: re.Match) -> str:
        target, alias = m.group(1), m.group(2)
        hit = index.resolve(target)
        label = alias or (index.entities[hit].title if hit else target)  # a source's title, not its file name
        label = re.sub(r"([\\\[\]*_`<|])", r"\\\1", label)  # | too: a link in a table cell
        return f"[{label}](#/e/{quote(hit)})" if hit else f"[{label}](#/missing/{quote(target.strip())})"

    md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable(["table", "strikethrough"])
    default_link = md.renderer.rules.get("link_open")
    default_image = md.renderer.rules.get("image")

    def link_open(tokens, idx, options, env):
        href = tokens[idx].attrGet("href") or ""
        if href.endswith(".md") or ".md#" in href:
            hit = index.resolve_path(base, href.split("#")[0])
            if hit:
                tokens[idx].attrSet("href", f"#/e/{quote(hit)}")
        elif href.startswith(("http://", "https://")):
            tokens[idx].attrSet("target", "_blank")
            tokens[idx].attrSet("rel", "noopener")
        return default_link(tokens, idx, options, env) if default_link else md.renderer.renderToken(tokens, idx, options, env)

    def image(tokens, idx, options, env):
        src = tokens[idx].attrGet("src") or ""
        if not src.startswith(("http://", "https://", "data:")):
            rel = os.path.normpath((Path(base).parent / src).as_posix())
            tokens[idx].attrSet("src", f"/raw/{quote(rel)}")
        return default_image(tokens, idx, options, env)

    md.renderer.rules["link_open"] = link_open
    md.renderer.rules["image"] = image
    return md.render(WIKI.sub(wiki, text))


# --------------------------------------------------------------------------- generative chat blocks
#
# An agent message is Markdown that may contain fenced blocks ```atlas:<kind> … ```.
# They become native components in the chat (Intelligent-UI style): the agent picks
# from a small vocabulary, and `html` is a sandboxed escape hatch for mockups and tools.

BLOCK = re.compile(r"```atlas:([a-z]+)[^\n]*\n(.*?)^```[ \t]*$", re.S | re.M)
BLOCK_KINDS = {"note", "notes", "choices", "checklist", "chart", "graph", "html"}


def _yaml(text: str):
    import yaml
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def _find(index: Index, ref) -> Entity | None:
    ref = str(ref or "").strip().strip("[]").strip()
    if not ref:
        return None
    return index.entities.get(ref) or index.entities.get(index.resolve(ref) or "") or \
        index.entities.get(index.resolve(Path(ref).stem) or "")


def _block(index: Index, kind: str, body: str) -> dict:
    """A malformed block becomes an error block; it must never break the chat."""
    try:
        return _plain(_block_unsafe(index, kind, body))
    except Exception as exc:  # noqa: BLE001 - agent-authored input, anything goes
        return {"kind": "error", "text": f"atlas:{kind}: could not render ({type(exc).__name__}: {str(exc)[:120]})"}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _finite(value) -> float | None:
    import math
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def _block_unsafe(index: Index, kind: str, body: str) -> dict:
    data = _yaml(body) if kind != "html" else None
    if kind in ("note", "graph"):
        ref = data.get("path") if isinstance(data, dict) else (data if isinstance(data, str) else body)
        ent = _find(index, ref)
        if not ent:
            return {"kind": "error", "text": f"atlas:{kind}: no note found for {str(ref).strip()[:120]!r}"}
        if kind == "note":
            return {"kind": "note", "card": ent.card(index)}
        view = entity_view(index, ent.id)
        return {"kind": "graph", "card": ent.card(index), "neighbors": view["neighbors"] if view else []}
    if kind == "notes":
        refs = data if isinstance(data, list) else (_list(data.get("paths")) if isinstance(data, dict) else [])
        cards = [e.card(index) for e in (_find(index, r) for r in refs) if e]
        return {"kind": "notes", "cards": cards, "missing": len(refs) - len(cards)}
    if kind in ("choices", "checklist"):
        items = data if isinstance(data, list) else (_list(data.get("options") or data.get("items")) if isinstance(data, dict) else [])
        opts = []
        for it in items[:24]:
            if isinstance(it, dict):
                opts.append({"label": str(it.get("label", "")), "send": str(it.get("send") or it.get("label", ""))})
            else:
                opts.append({"label": str(it), "send": str(it)})
        title = data.get("title") if isinstance(data, dict) else None
        return {"kind": kind, "title": str(title) if title is not None else None, "options": opts}
    if kind == "chart":
        if not isinstance(data, dict):
            return {"kind": "error", "text": "atlas:chart needs YAML with title, type (bar|line) and data"}
        raw = data.get("data") or {}
        pairs = list(raw.items()) if isinstance(raw, dict) else [(r.get("label"), r.get("value")) for r in _list(raw) if isinstance(r, dict)]
        pairs = [(str(k), _finite(v)) for k, v in pairs]
        pairs = [(k, v) for k, v in pairs if v is not None][:40]
        opt = lambda key: str(data[key]) if data.get(key) is not None else None
        return {"kind": "chart", "type": "line" if str(data.get("type")) == "line" else "bar", "title": opt("title"),
                "unit": opt("unit"), "data": [{"label": k, "value": v} for k, v in pairs]}
    if kind == "html":
        return {"kind": "html", "html": body[:400_000]}
    return {"kind": "error", "text": f"unknown block atlas:{kind}"}


FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")


def atlas_block_open_at_end(text: str) -> bool:
    """Whether the message ends inside an `atlas:` block that was never closed. Fences are followed line by
    line the Markdown way: a fence opens with three or more backticks or tildes (up to three spaces in; a
    backtick fence's info string has no backticks) and closes only with the same character, at least as
    many, and nothing after them. A quoted line (`> `) or indented code is no fence."""
    fence, opened = None, None  # (character, length, is it an atlas: block), and where it opened
    lines = text.split("\n")
    for n, line in enumerate(lines):
        m = FENCE.match(line)
        if not m:
            continue
        mark, info = m.group(2), m.group(3)
        if fence is None:
            if not (mark[0] == "`" and "`" in info):
                fence, opened = (mark[0], len(mark), mark == "```" and info.startswith("atlas:")), n
        elif mark[0] == fence[0] and len(mark) >= fence[1] and not info.strip():
            fence = None
    if fence is None or not fence[2]:
        return False
    # Close it only where nothing else can pair with the added fence: every earlier `atlas:` opener belongs
    # to a complete block (BLOCK does not follow other fences), and in a list item every line after the
    # opener is indented at least as far, so it is the block's payload and not prose after the list.
    # Otherwise the answer stays as it was.
    start = sum(len(x) + 1 for x in lines[:opened]) + len(lines[opened]) - len(lines[opened].lstrip())
    done = [(m.start(), m.end()) for m in BLOCK.finditer(text)]
    if any(not any(a <= o < b for a, b in done) for o in (m.start() for m in re.finditer(r"```atlas:", text[:start]))):
        return False
    indent = len(lines[opened]) - len(lines[opened].lstrip())
    above = next((x for x in reversed(lines[:opened]) if x.strip()), "")
    if indent and re.match(r"\s*([-*+]|\d+[.)])\s", above):  # inside a list item: unindented lines leave it
        return all(len(x) - len(x.lstrip()) >= indent for x in lines[opened + 1:] if x.strip())
    return True


def render_agent_message(index: Index, text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # CRLF from Windows, or a stray CR: fences match per line
    if atlas_block_open_at_end(text):  # an agent left its last block open: the end of the message closes it
        text = text.rstrip("\n") + "\n```"
    blocks, pos = [], 0
    for m in BLOCK.finditer(text):
        before = text[pos:m.start()].strip()
        if before:
            blocks.append({"kind": "md", "html": render_md(index, before)})
        kind = m.group(1)
        blocks.append(_block(index, kind, m.group(2)) if kind in BLOCK_KINDS
                      else {"kind": "error", "text": f"unknown block atlas:{kind}"})
        pos = m.end()
    rest = text[pos:].strip()
    if rest:
        blocks.append({"kind": "md", "html": render_md(index, rest)})
    return blocks


def fact_links(index: Index, ent: Entity) -> dict:
    """Where the wiki links in a note's facts point (`affects: [[…]]`), so the reader shows them as links."""
    out = {}
    for k in index.types[ent.type].get("fields", []):
        val = _plain(ent.meta.get(k))
        for item in val if isinstance(val, list) else [val]:  # the values as written: JSON would escape quotes
            for target, _ in WIKI.findall(item) if isinstance(item, str) else []:
                hit = index.resolve(target)
                if hit:
                    out[target] = {"id": hit, "title": index.entities[hit].title}
    return out


def entity_view(index: Index, eid: str) -> dict | None:
    ent = index.entities.get(eid)
    if not ent:
        return None
    out = [index.entities[i] for i in ent.links if i in index.entities]
    back = [index.entities[i] for i in index.backlinks.get(eid, []) if i in index.entities]
    maps = [e for e in back if e.type == "map"]
    siblings = []
    if ent.group and ent.type == "frame":
        siblings = sorted((e for e in index.entities.values() if e.group == ent.group and e.id != eid), key=lambda e: e.id)
    members: list = []
    if ent.type == "project":  # its memory, in reading order: open threads, decisions in force, lessons
        members = sorted((e for e in index.entities.values() if e.group == ent.group and e.project == ent.project
                          and e.type in ("thread", "decision", "lesson")), key=member_order)
    elif ent.type == "group":
        members = sorted((e for e in index.entities.values() if e.type == "project" and e.group == ent.group), key=lambda e: e.title)
    group_note = index.entities.get(f"projects/{ent.group}/_group.md") if ent.group and ent.type in PROJECT_TYPES else None
    neighbors, seen = [], set()
    for e, rel in [(e, "out") for e in out] + [(e, "in") for e in back]:
        if e.id not in seen and len(neighbors) < 28:
            seen.add(e.id)
            neighbors.append({"id": e.id, "type": e.type, "title": e.title, "rel": rel})
    spec = index.types[ent.type]
    allowed = (spec.get("checks") or {}).get("allowed") or {}
    view = {
        **ent.card(index),
        "meta": _plain(ent.meta),
        "html": render_markdown(index, ent),
        "outlinks": [e.card(index) for e in out],
        "backlinks": [e.card(index) for e in back if e.type != "map"],
        "maps": [e.card(index) for e in maps],
        "siblings": [e.card(index) for e in siblings],
        "neighbors": neighbors,
        "fact_links": fact_links(index, ent),
        "path": ent.id,
        "issues": next((n["issues"] for n in health(index)["notes"] if n["id"] == eid), []),
        "members": [e.card(index) for e in members],
        "group_note": group_note.card(index) if group_note else None,
        "modified": dt.datetime.fromtimestamp(ent.mtime).astimezone().isoformat(timespec="seconds") if ent.mtime else None,
        "rev": ent.mtime,  # the index's own precision: an open page compares it to know its note changed
        "scale": [str(v) for v in allowed.get(spec.get("status") or "", [])],  # e.g. speculative → working → proven
        "provenance": [e.card(index) for e in provenance(index, ent)],
        "map_nav": map_nav(index, ent, maps),
        "history": git_file_history(ent.id),
        "log": thread_log(ent, index) if ent.type == "thread" else [],
    }
    if ent.type == "project":
        view["project_view"] = project_view(index, ent)
    if ent.type == "tour":
        view["tour_view"] = tour_view(index, ent)
    if spec.get("recall"):
        view["mentions"] = mentions(index, ent)
    return view


SOURCE_FIELDS = ("source", "source_sketch", "sources")


def provenance(index: Index, ent: "Entity", depth: int = 4) -> list["Entity"]:
    """Where a note came from, oldest first: follow `source`-like frontmatter fields that name a note."""
    chain, cur, seen = [], ent, {ent.id}
    for _ in range(depth):
        nxt = None
        for fld in SOURCE_FIELDS:
            val = cur.meta.get(fld)
            for ref in (val if isinstance(val, list) else [val]):
                hit = _find(index, ref) if isinstance(ref, str) and ref.strip() else None
                if hit and hit.id not in seen:
                    nxt = hit
                    break
            if nxt:
                break
        if not nxt:
            break
        seen.add(nxt.id)
        chain.insert(0, nxt)
        cur = nxt
    return chain


def map_nav(index: Index, ent: "Entity", maps: list["Entity"]) -> dict | None:
    """Previous and next note of the same kind in the first map that lists this one."""
    for m in maps:
        order = [i for i in m.links if index.entities.get(i) and index.entities[i].type == ent.type]
        if ent.id in order:
            k = order.index(ent.id)
            return {"map": m.id, "title": m.title, "pos": k + 1, "total": len(order),
                    "prev": order[k - 1] if k > 0 else None, "next": order[k + 1] if k + 1 < len(order) else None}
    return None


LOG_LINE = re.compile(r"^\s*[-*]\s+(\d{4}-\d{2}-\d{2})\s*\(([^)]+)\)\s*:\s*(.+?)\s*$", re.M)


def wiki_links(index: "Index | None", *texts) -> dict:
    """Where the wiki links in short texts (log lines, a thread's next) point, for the front end's inline()."""
    out = {}
    for text in texts if index else ():
        for target, _ in WIKI.findall(str(text or "")):
            hit = index.resolve(target)
            if hit:
                out[target] = {"id": hit, "title": index.entities[hit].title}
    return out


def thread_log(e: "Entity", index: "Index | None" = None) -> list[dict]:
    """A thread's `## Log`: `- 2026-10-10 (claude): what happened`, oldest first as written."""
    return [{"date": d, "agent": a.strip().lower(), "text": t, "thread": e.id, "title": e.title,
             "links": wiki_links(index, t)} for d, a, t in LOG_LINE.findall(e.body)]


def group_rules(group: "Entity | None") -> list[str]:
    """The bullets under `## Rules` in a group's _group.md (empty while it has none)."""
    if not group:
        return []
    m = re.search(r"^##\s+Rules\s*$(.*?)(?=^##\s|\Z)", group.body, re.M | re.S)
    if not m:
        return []
    return [re.sub(r"\s+", " ", b).strip() for b in re.findall(r"^\s*[-*]\s+(.+(?:\n(?![ \t]*[-*#]|\s*$).+)*)", m.group(1), re.M)]


def project_summary(index: Index, p: "Entity", activity: dict[str, list[int]] | None = None,
                    live: list[dict] | None = None) -> dict:
    mine = [e for e in index.entities.values() if e.group == p.group and e.project == p.project and e.id != p.id]
    threads = [e for e in mine if e.type == "thread"]
    open_threads = sorted((e for e in threads if str(e.status) == "open"),
                          key=lambda e: (index.touched.get(e.id) or "", e.mtime), reverse=True)
    logs = sorted((line for t in threads for line in thread_log(t, index)), key=lambda l: l["date"])
    last = logs[-1] if logs else None
    ops = [e for e in index.entities.values() if is_operational(e) and str(e.meta.get("project", "")) == p.project]
    co = resolve_checkout(p)
    here = [a for a in (live or []) if a.get("project") == p.project and a["state"] != "offline"]
    return {
        **p.card(index),
        "aliases": [str(a) for a in (p.meta.get("aliases") or [])],
        "repo": _plain(p.meta.get("repo")),
        "open": len(open_threads),
        "blocked": sum(1 for e in open_threads if e.meta.get("blocked")),
        "proposed": sum(1 for e in mine if e.type == "decision" and str(e.status) == "proposed"),
        "accepted": sum(1 for e in mine if e.type == "decision" and str(e.status) == "accepted"),
        "provisional": sum(1 for e in mine if e.type == "lesson" and str(e.status) == "provisional"),
        "next": ({"text": _plain(open_threads[0].meta.get("next")), "thread": open_threads[0].id, "title": open_threads[0].title,
                  "links": wiki_links(index, open_threads[0].meta.get("next"))}
                 if open_threads and open_threads[0].meta.get("next") else None),
        "last": last,
        "operational": len(ops),
        "checkout": co,
        "activity": (activity or {}).get(f"projects/{p.group}/{p.project}", [0] * 14),
        "here": here,
    }


def projects_overview(index: Index) -> dict:
    live = agents_state()
    activity = git_activity("projects")
    projects = sorted((e for e in index.entities.values() if e.type == "project"), key=lambda e: e.title.lower())
    groups: dict[str, dict] = {}
    for g in sorted({e.group for e in projects} | {e.group for e in index.entities.values() if e.type == "group"}):
        note = index.entities.get(f"projects/{g}/_group.md")
        groups[g] = {"group": g, "note": note.card(index) if note else None, "rules": group_rules(note), "projects": []}
    for p in projects:
        groups[p.group]["projects"].append(project_summary(index, p, activity, live))
    ents = index.entities.values()
    in_projects = lambda e: e.group and e.project
    blocked = [e for e in ents if e.type == "thread" and str(e.status) == "open" and e.meta.get("blocked") and in_projects(e)]
    return {
        "groups": [g for g in groups.values() if g["projects"] or g["note"]],
        "decisions": [e.card(index) for e in ents if e.type == "decision" and str(e.status) == "proposed" and in_projects(e)],
        "blocked": [{**e.card(index), "blocked": _plain(e.meta.get("blocked"))} for e in blocked],
        "lessons": [e.card(index) for e in ents if e.type == "lesson" and str(e.status) == "provisional" and in_projects(e)],
        "operational": [e.card(index) for e in ents if is_operational(e)],
        "machine": machine_id(),
    }


def project_view(index: Index, p: "Entity") -> dict:
    """Everything the project page shows, read from its threads, decisions, lessons and git."""
    live = agents_state()
    summary = project_summary(index, p, git_activity("projects"), live)
    mine = sorted((e for e in index.entities.values() if e.group == p.group and e.project == p.project and e.id != p.id),
                  key=member_order)
    logs = sorted((line for e in mine if e.type == "thread" for line in thread_log(e, index)), key=lambda l: l["date"])
    by_date: dict[str, list[dict]] = {}
    for line in logs:
        by_date.setdefault(line["date"], []).append(line)
    last_day = max(by_date) if by_date else None
    folder = f"projects/{p.group}/{p.project}"
    commits = []
    if last_day:  # the commits of the last session's day that touched this project
        for line in git("log", "-n300", LOG_FORMAT, "--", folder).splitlines():
            if line.startswith("@@") and line.split("|", 2)[1][:10] == last_day:
                commits.append(_log_head(line))
    who: dict[str, int] = {}
    for line in logs:
        who[line["agent"]] = who.get(line["agent"], 0) + 1
    for e in mine + [p]:
        for k in ("created_by", "updated_by"):
            if e.meta.get(k):
                who.setdefault(str(e.meta[k]).lower(), 0)
    agents = known_agents(index) - {"user"}
    boot_agent = next((l["agent"] for l in reversed(logs) if l["agent"] in agents), None) or (sorted(agents)[0] if agents else "agent")
    stats: dict = {}
    boot_packet(index, p, boot_agent, 12000, None, stats)
    paths = p.meta.get("paths") if isinstance(p.meta.get("paths"), dict) else {}
    member = lambda e, **extra: {**e.card(index), **extra}
    return {
        **summary,
        "threads": [member(e, next=_plain(e.meta.get("next")), blocked=_plain(e.meta.get("blocked")),
                           branch=_plain(e.meta.get("branch")), log=thread_log(e, index)) for e in mine if e.type == "thread"],
        "decisions": [member(e, superseded_by=(lambda h: h.card(index) if h else _plain(e.meta.get("superseded_by")))(
                          _find(index, e.meta.get("superseded_by")) if e.meta.get("superseded_by") else None))
                      for e in mine if e.type == "decision"],
        "lessons": [member(e, applies_to=_plain(e.meta.get("applies_to")), evidence=_plain(e.meta.get("evidence")),
                           promoted_to=_plain(e.meta.get("promoted_to"))) for e in mine if e.type == "lesson"],
        "last_session": {"date": last_day, "lines": by_date.get(last_day, []), "commits": commits} if last_day else None,
        "sessions": [{"date": d, "lines": by_date[d]} for d in sorted(by_date, reverse=True)[:12]],
        "who": sorted(({"agent": a, "lines": n} for a, n in who.items()), key=lambda x: -x["lines"]),
        "boot": {"agent": boot_agent, **stats},
        "paths": {str(k): str(v) for k, v in paths.items()},
        "group_rules": group_rules(index.entities.get(f"projects/{p.group}/_group.md")),
        "outlinks": [e.card(index) for e in (index.entities[i] for i in p.links if i in index.entities) if e.project != p.project],
        "backlinks": [e.card(index) for e in (index.entities[i] for i in index.backlinks.get(p.id, []) if i in index.entities)
                      if e.project != p.project],
    }


PROJECT_TYPES = {"project", "thread", "decision", "lesson"}
SCAFFOLD_TYPES = {"group", "agent", "you", "note"}  # present from the start or set up by agents; not the user's content


def content_count(index: "Index") -> int:
    """How much the user has grown: an install with only group templates and agent files is still empty."""
    return sum(1 for e in index.entities.values() if e.type not in SCAFFOLD_TYPES)
_MEMBER_RANK = {"thread": 0, "decision": 1, "lesson": 2}
_STATUS_RANK = {"open": 0, "accepted": 0, "validated": 0, "proposed": 1, "provisional": 1, "closed": 2, "superseded": 3}


def member_order(e: "Entity"):
    return (_MEMBER_RANK.get(e.type, 9), _STATUS_RANK.get(str(e.status or ""), 1), e.title.lower())


GRAPH_TYPES = {"insight", "map", "sketch", "spec", "capture", "project", "question"}


def graph_data(index: Index, types: set[str]) -> dict:
    """Compact graph for the explorer: nodes plus links as index pairs (undirected, deduped)."""
    ents = [e for e in index.entities.values() if e.type in types]
    pos = {e.id: i for i, e in enumerate(ents)}
    pairs, degree = set(), [0] * len(ents)
    for e in ents:
        for t in e.links:
            j = pos.get(t)
            if j is not None and j != pos[e.id]:
                pairs.add((min(pos[e.id], j), max(pos[e.id], j)))
    for a, b in pairs:
        degree[a] += 1
        degree[b] += 1
    listed: dict[str, str] = {}  # a note's home map when it names none in `topics`: the biggest map that links to it
    for m in sorted((e for e in index.entities.values() if e.type == "map"), key=lambda e: -len(e.links)):
        for t in m.links:
            listed.setdefault(t, m.id)
    nodes = []
    for i, e in enumerate(ents):
        home = e.id if e.type == "map" else listed.get(e.id)
        for topic in e.meta.get("topics") or []:
            hit = index.resolve(str(topic).strip("[]\" "))
            if hit and index.entities[hit].type == "map":
                home = hit
                break
        node = {"id": e.id, "k": e.type, "d": degree[i], "c": str(e.meta.get("category") or ""), "m": home, "s": e.status,
                "a": added_on(index, e), "w": str(e.meta.get("created_by") or "").lower() or None}  # arrival day, author
        if e.title != Path(e.id).stem:  # most insight titles equal the file name; the client derives them
            node["t"] = e.title
        nodes.append(node)
    return {"nodes": nodes, "links": sorted(pairs), "types": sorted(types)}


def fast_search(index: Index, q: str, tid: str | None, limit: int = 60) -> list[dict]:
    words = [w.lower() for w in q.split() if w.strip()]
    if not words:
        return []
    scored = []
    for e in index.entities.values():
        if tid and e.type != tid:
            continue
        title, desc = e.title.lower(), e.description.lower()
        if not all(w in title or w in desc or w in e.body.lower() for w in words):
            continue
        score = sum(5 * (w in title) + 3 * (w in desc) + 1 for w in words)
        scored.append((score, index.touched.get(e.id) or "", e))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [e.card(index) for _, _, e in scored[:limit]]


def deep_collections() -> tuple[str | None, dict]:
    """Where deep search looks: the vault's own index; before `qmd setup`, collections of QMD's default index
    that a user pointed at the vault by hand (how Atlas searched before 0.8). Off means nowhere."""
    if qmd_state() == "off" or not qmd_bin():
        return None, {}
    name = qmd_index()
    return name, qmd_collections(name) if name else {n: c for n, c in qmd_collections().items()
                                                     if c["path"].resolve() == VAULT or VAULT in c["path"].resolve().parents}


FRONT_LINE = re.compile(r"^\s*([\w-]+:|- |---$|$)")  # what a frontmatter line looks like


def frontmatter_end(rel: str) -> int:
    """The line number (from 1) of a note's closing `---`; 0 without frontmatter."""
    try:
        lines = (VAULT / rel).read_text(encoding="utf-8", errors="replace").splitlines()  # as parse_file reads it
    except OSError:
        return 0
    if not lines or lines[0].rstrip() != "---":
        return 0
    # unindented only: an indented --- belongs to a block scalar (description: |)
    return next((n + 1 for n, line in enumerate(lines[1:], 1) if line.rstrip() == "---"), 0)


def snippet_links(snippet: str, index: "Index") -> str:
    """[[links]] in a search snippet as the names a reader sees: the alias, else the linked note's title, else the
    target. The result card is a link itself, so the snippet carries no links of its own (#50)."""
    masked = WIKI.sub(lambda m: "\0" * len(m.group(0)), snippet)  # backticks inside a link do not start a code span
    quoted = [(m.start(), m.end()) for m in re.finditer(r"`[^`]+`", masked)]

    def name(m: re.Match) -> str:
        if any(a < m.start() and m.end() <= b for a, b in quoted):  # `[[note]]` quoted in code stays as written
            return m.group(0)
        if m.group(2):
            return m.group(2).strip()
        hit = index.entities.get(index.resolve(m.group(1)) or "")
        return hit.title if hit else m.group(1).strip()
    return WIKI.sub(name, snippet)


def snippet_text(snippet: str, title: str = "", keys: frozenset = frozenset(), front_end: int = 0) -> str:
    """QMD's snippet as the body text it found: without its diff header, without the frontmatter a hit near
    the top of a note starts in (opened or closed inside the snippet, or both), and without the title heading,
    which the result card shows already. Nothing left: empty, and the card shows its description."""
    head = re.match(r"@@ -(\d+)", snippet or "")  # QMD's hunk header: the line the excerpt starts on
    lines = re.sub(r"^@@.*?\n", "", snippet or "", flags=re.S).splitlines()
    dashes = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if lines and lines[0].strip() == "---":  # opens in the snippet: up to its end, or all of it that is there
        end = dashes[1] if len(dashes) > 1 else next((i for i, ln in enumerate(lines) if not FRONT_LINE.match(ln)), len(lines)) - 1
        lines = lines[end + 1:]
    elif dashes and all(FRONT_LINE.match(line) for line in lines[:dashes[0]]):  # starts inside it
        lines = lines[dashes[0] + 1:]
    elif lines and keys and head and int(head.group(1)) <= front_end \
            and lines[0].split(":", 1)[0].strip() in keys:  # inside it (by line), and its end is not in the snippet
        while lines and (lines[0].split(":", 1)[0].strip() in keys or lines[0].startswith((" ", "- ")) or not lines[0].strip()):
            lines = lines[1:]
    norm = lambda s: " ".join(s.split()).lower()
    while lines and (not lines[0].strip() or (title and lines[0].lstrip().startswith("# ")
                                               and norm(lines[0].lstrip()[2:]) == norm(title))):
        lines = lines[1:]  # the title's own heading; a section heading the hit is about stays
    return "\n".join(lines).strip()[:300]


def deep_search(index: Index, q: str) -> list[dict]:
    """QMD's hits for a query, each note once (see deep_collections for where it looks)."""
    q = q.strip().lstrip("-").strip()
    name, cols = deep_collections()
    if not q or not cols:
        return []  # this vault is not indexed in QMD; the caller falls back to instant search
    try:
        r = qmd("query", q, "--format", "json", "-n", "15", *[a for n in cols for a in ("-c", n)], index=name,
                timeout=180)
        hits = json.loads(r.stdout or "[]")
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    out, seen = [], set()
    for h in hits:
        m = re.match(r"qmd://([^/]+)/([^?]+)", h.get("file", ""))  # a named index adds ?index=<name>
        if not m or m.group(1) not in cols:
            continue
        try:
            rel = (cols[m.group(1)]["path"] / m.group(2)).resolve().relative_to(VAULT.resolve()).as_posix()
        except ValueError:
            rel = None
        if rel and rel in seen:  # two collections a user made by hand can both hold a note
            continue
        seen.add(rel)
        e = index.entities.get(rel) if rel else None
        snippet = snippet_links(snippet_text(h.get("snippet", ""), e.title if e else h.get("title") or "",
                                             frozenset(e.meta) if e else frozenset(), frontmatter_end(rel) if e else 0), index)
        if e:
            out.append({**e.card(index), "snippet": snippet, "score": h.get("score")})
        else:
            out.append({"id": None, "type": "external", "title": h.get("title"), "description": snippet,
                        "path": h.get("file"), "score": h.get("score")})
    return out


# --------------------------------------------------------------------------- chat + notes

def hover_card(index: Index, eid: str) -> dict | None:
    """What a link's hover card shows: the note's card, how connected it is, and its maps."""
    e = index.entities.get(eid)
    if not e:
        return None
    back = index.backlinks.get(eid, [])
    maps = [index.entities[i] for i in back if i in index.entities and index.entities[i].type == "map"]
    return {**e.card(index), "degree": len(set(e.links) | set(back)),
            "maps": [{"id": m.id, "title": m.title} for m in maps[:3]]}


# --------------------------------------------------------------------------- snooze (Needs you)
#
# A snoozed row of Needs you stays hidden until its day, or until what it counts changes (its `sig`):
# a new capture wakes "captures waiting". Atlas state only (<vault>/.atlas/); the notes are not touched.

_SNOOZE_LOCK = threading.Lock()


def snoozed() -> dict:
    try:
        data = json.loads(SNOOZE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    today = dt.date.today().isoformat()
    return {k: v for k, v in data.items() if isinstance(v, dict) and str(v.get("until", "")) > today}


def set_snooze(key: str, value: dict | None) -> dict:
    with _SNOOZE_LOCK:
        data = snoozed()  # expired entries fall away here
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
        ensure_state()
        tmp = SNOOZE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, SNOOZE)
        return data


# --------------------------------------------------------------------------- tours
#
# A tour (tours/*.md) walks the user through what changed in a period: stops in reading order, each with
# why it matters and the passage that carries it; `look_closely` marks a call only the user can make. An
# agent writes it (`atlas.py tour --since …` scaffolds the file). Atlas holds it to the record: a quoted
# excerpt must stand in its note, and every note that changed in the period appears somewhere in the tour.

TOUR_ORDER = ["insight", "map", "sketch", "spec", "project", "decision", "thread", "lesson", "question", "frame", "source", "capture"]  # the rest by kind


def _moment(value) -> str | None:
    """A frontmatter date or timestamp as something `git log --since` reads exactly."""
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return f"{value.isoformat()}T00:00:00"
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text}T00:00:00"
    return text or None


def changes_between(index: Index, since: str, until: str | None = None) -> dict:
    """{path: "A" (arrived) | "M" (changed)} for every note Atlas shows (tours aside) that changed in the
    period and still exists, and how many captures left captures/ (distilled). A renamed note changed;
    it did not arrive."""
    args = ["-c", "core.quotepath=off", "log", f"--since={since}", "-M", "--name-status", "--format=@@%h"]
    if until:
        args.append(f"--until={until}")
    prefix = git("rev-parse", "--show-prefix").strip()
    seen: dict[str, set[str]] = {}
    touches: dict[str, int] = {}
    renames: list[tuple[str, str]] = []
    left_captures: set[str] = set()
    for line in git(*args, "--", ".").splitlines():
        if not line or line.startswith("@@") or "\t" not in line:
            continue
        status, *paths = line.split("\t")
        rels = [vault_rel(x, prefix) for x in paths]
        if status.startswith("R") and len(rels) == 2:
            old, path = rels
            if old and path:
                renames.append((old, path))
            if old and old.startswith("captures/") and not (path or "").startswith("captures/"):
                left_captures.add(old)
            status = "M"
        else:
            path = rels[-1]
            if path and status.startswith("D") and path.startswith("captures/"):
                left_captures.add(path)
        if path:
            seen.setdefault(path, set()).add(status[:1])
            touches[path] = touches.get(path, 0) + 1
    for old, new in renames:  # arrived in the period and renamed later: still an arrival
        if "A" in seen.get(old, set()):
            seen[new].add("A")
    changed = {}
    for path, statuses in seen.items():
        e = index.entities.get(path)
        if e and e.type != "tour":
            changed[path] = "A" if "A" in statuses else "M"
    distilled = sum(1 for p in left_captures if p.endswith(".md") and not (VAULT / p).exists())
    return {"changed": changed, "touches": {p: touches[p] for p in changed}, "distilled": distilled}


def _plain_words(text: str) -> str:
    """Text as a reader sees it, for matching a quoted excerpt against the Markdown it came from."""
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", str(text))
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # [label](href) reads as its label
    text = re.sub(r"(?m)^\s*(?:[-+*]|\d+[.)])\s+", "", text).replace("\\", "")  # list markers, escapes
    text = re.sub(r"[*_`#>\[\]]", "", text).translate(str.maketrans("‘’“”", "''\"\""))
    return " ".join(text.split()).lower()


def tour_view(index: Index, ent: Entity) -> dict:
    m = ent.meta
    since, until = _moment(m.get("since")), _moment(m.get("until"))
    ch = changes_between(index, since, until) if since else {"changed": {}, "distilled": 0}
    changed, named, stops = ch["changed"], set(), []
    for raw in _list(m.get("stops")):
        if not isinstance(raw, dict):
            continue
        target = _find(index, raw.get("path"))
        if not target:
            stops.append({"missing": str(raw.get("path") or "")[:200]})
            continue
        named.add(target.id)
        excerpt = str(raw.get("excerpt") or "").strip()
        found = bool(excerpt) and _plain_words(excerpt) in _plain_words(target.body)
        look = str(raw.get("look_closely") or "").strip()
        stops.append({"card": target.card(index), "why": render_md(index, str(raw.get("why") or ""), ent.id),
                      "excerpt": excerpt if found else None, "unmatched": bool(excerpt) and not found,
                      "look_closely": render_md(index, look, ent.id) if look else None, "change": changed.get(target.id)})
    mechanical = [e for e in (_find(index, r) for r in _list(m.get("mechanical"))) if e]
    named |= {e.id for e in mechanical}
    rank = {t: i for i, t in enumerate(TOUR_ORDER)}
    rest = sorted((index.entities[p] for p in changed if p not in named),
                  key=lambda e: (rank.get(e.type, 99), changed[e.id] != "A", e.title.lower()))
    brief = lambda e: {"id": e.id, "type": e.type, "title": e.title, "change": changed.get(e.id)}  # a busy week: hundreds
    return {"since": since, "until": until, "by": str(m.get("written_by") or "") or None, "stops": stops,
            "mechanical": [brief(e) for e in mechanical], "uncovered": [brief(e) for e in rest],
            "distilled": ch["distilled"], "changed_total": len(changed)}


def latest_tour(index: Index) -> dict | None:
    tours = [e for e in index.entities.values()  # a scaffold without stops is still being written
             if e.type == "tour" and e.meta.get("until") and _list(e.meta.get("stops"))]
    if not tours:
        return None
    t = max(tours, key=lambda e: str(_moment(e.meta.get("until"))))
    return {"id": t.id, "title": t.title, "since": _moment(t.meta.get("since")), "until": _moment(t.meta.get("until")),
            "stops": len(_list(t.meta.get("stops"))), "by": str(t.meta.get("written_by") or "") or None}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def session() -> dict:
    try:
        return json.loads(SESSION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _presence(age: float, last_in: str, last_out: str, last_progress: str) -> str:
    if age < 15:
        return "listening"
    if ((last_in and last_in > last_out) or last_progress > last_out) and age < 3600:  # asked, or still reporting progress
        return "working"
    return "away" if age < 3600 else "offline"


def _plain_text(text: str, n: int = 180) -> str:
    text = BLOCK.sub(" ", str(text or ""))
    text = re.sub(r"[*_`#>\[\]]", "", " ".join(text.split()))
    return text[:n] + ("…" if len(text) > n else "")


def agents_state(inbox: list[dict] | None = None, out: list[dict] | None = None) -> list[dict]:
    """Every named agent that listened in the last two days (`wait --agent <id>`): state, project, current task, steps."""
    if not PRESENCE.is_dir():
        return []
    inbox = read_jsonl(INBOX) if inbox is None else inbox
    out = read_jsonl(OUTBOX) if out is None else out
    agents = []
    for beat in sorted(PRESENCE.glob("*.beat")):
        aid, age = beat.stem, time.time() - beat.stat().st_mtime
        if age > 2 * 86400:
            continue
        try:
            info = json.loads((PRESENCE / f"{aid}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            info = {}
        mine = [m for m in inbox if not m.get("to") or m.get("to") == aid]
        answers = [r for r in out if r.get("agent") == aid and r.get("kind") != "progress"]
        progress = [r for r in out if r.get("agent") == aid and r.get("kind") == "progress"]
        last_out = answers[-1]["ts"] if answers else ""
        state = _presence(age, mine[-1]["ts"] if mine else "", last_out, progress[-1]["ts"] if progress else "")
        pending = [m for m in mine if m.get("ts", "") >= last_out]  # >=: timestamps have one-second resolution
        task = pending[0] if state == "working" and pending else None
        since = task["ts"] if task else last_out
        agents.append({
            "id": aid, "state": state, "project": info.get("project"), "group": info.get("group"),
            "task": {"text": _plain_text(task.get("text", ""), 200), "ts": task["ts"], "via": task.get("via"),
                     "context": task.get("context")} if task else None,
            "steps": [{"text": r["text"], "ts": r["ts"]} for r in progress if r["ts"] > (since or "")][-6:] if state == "working" else [],
            "last": {"text": _plain_text(answers[-1].get("text", "")), "ts": last_out} if answers else None,
        })
    return agents


def operator_state() -> dict:
    s = session()
    if s.get("mode") != "operator":
        return {"mode": "standalone"}
    beat = HEARTBEAT.stat().st_mtime if HEARTBEAT.exists() else 0
    inbox, out = read_jsonl(INBOX), read_jsonl(OUTBOX)
    answers = [r for r in out if r.get("kind") != "progress"]  # a progress line is not an answer
    progress = [r for r in out if r.get("kind") == "progress"]
    state = _presence(time.time() - beat, inbox[-1]["ts"] if inbox else "", answers[-1]["ts"] if answers else "",
                      progress[-1]["ts"] if progress else "")
    try:
        started = dt.datetime.fromisoformat(s.get("started", "")).timestamp()
    except (TypeError, ValueError):
        started = 0
    if state == "offline" and beat < started and time.time() - started < 600:
        state = "starting"  # Atlas started for an agent that has not listened yet; for ten minutes, not forever
    return {"mode": "operator", "state": state, "since": s.get("started"), "agents": agents_state(inbox, out)}


def slug(text: str, n: int = 48) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n] or "note"


def write_note(action: str, target: str | None, text: str, index: Index) -> str:
    NOTES.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    ent = index.entities.get(target) if target else None
    name = f"{stamp}-{action}-{slug(ent.title if ent else text)}.md"
    lines = ["---", "from: user", f"action: {action}", f"target: {json.dumps(target) if target else 'null'}",
             f"created: {now_iso()}", "status: new", "via: atlas", "---", ""]
    if ent:
        lines += [f"On [[{Path(ent.id).stem}]]" if ent.type in ("insight", "map") else f"On `{ent.id}` ({ent.title})", ""]
    lines += [text.strip() or f"({action})", ""]
    path, n = NOTES / name, 2
    while path.exists():  # two quick clicks must not overwrite each other
        path, n = NOTES / f"{name[:-3]}-{n}.md", n + 1
    path.write_text("\n".join(lines), encoding="utf-8")
    return path.relative_to(VAULT).as_posix()


# --------------------------------------------------------------------------- web app

def make_app(index: Index):
    from starlette.applications import Starlette
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles

    def fresh():
        index.refresh()

    async def home(request):
        from starlette.responses import HTMLResponse
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for name in ("app.js", "style.css"):  # cache-bust: a changed file gets a new URL
            html = html.replace(f"/static/{name}", f"/static/{name}?v={int((STATIC / name).stat().st_mtime)}")
        html = html.replace("__ATLAS_V__", str(max(int(f.stat().st_mtime) for f in STATIC.glob("*.js"))))
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    async def meta(request):
        await run_in_threadpool(fresh)
        counts, runs, aside = {}, {}, {}
        for e in index.entities.values():
            rule = index.types.get(e.type, {}).get("count") or {}
            if rule.get("aside") and str(e.status) in [str(s) for s in rule["aside"]]:
                aside[e.type] = aside.get(e.type, 0) + 1
            if rule.get("only") and str(e.status) not in [str(s) for s in rule["only"]]:
                continue  # e.g. only open questions count; answered and dropped ones do not
            counts[e.type] = counts.get(e.type, 0) + 1
            runs.setdefault(e.type, set()).add(e.group)
        # a research run counts once however many documents it holds, the way its list shows it
        types = [{**{k: v for k, v in t.items() if k not in ("globs", "exclude", "count")},
                  "count": len(runs.get(t["id"], ())) if t.get("group") == "frame" else counts.get(t["id"], 0),
                  "aside": aside.get(t["id"], 0), "aside_label": aside_label(t),
                  "count_status": ",".join(map(str, (t.get("count") or {}).get("only") or [])),
                  "aside_status": ",".join(map(str, (t.get("count") or {}).get("aside") or []))}
                 for t in index.types.values()]
        ents = index.entities.values()
        projects = [{"id": e.id, "title": e.title, "group": e.group, "project": e.project, "status": e.status,
                     "open": sum(1 for x in ents if x.type == "thread" and x.group == e.group and x.project == e.project
                                 and str(x.status) == "open")}
                    for e in sorted((e for e in ents if e.type == "project"), key=lambda e: (e.group or "", e.title.lower()))]
        agents = [{"id": Path(e.id).stem, "title": e.title, "path": e.id} for e in sorted(ents, key=lambda e: e.id) if e.type == "agent"]
        return JSONResponse({"types": types, "version": index.version, "built_at": index.built_at,
                             "operator": operator_state(), "vault": VAULT.name, "vault_path": str(VAULT), "user": index.user,
                             "total": len(index.entities), "content": content_count(index),
                             "qmd": bool(deep_collections()[1]), "commands": index.commands, "drop": index.drop,
                             "projects": projects, "agents": agents})

    async def home_data(request):
        await run_in_threadpool(fresh)
        feed = await run_in_threadpool(git_feed, index)
        h = health(index)
        needs = {**needs_you(index), "fixes": [{**index.entities[n["id"]].card(index), "issues": n["issues"]} for n in h["notes"][:8]],
                 "fixes_total": h["total"]}
        needs["sigs"]["fixes"] = fingerprint(f"{n['id']}|{'|'.join(n['issues'])}" for n in h["notes"])
        q = question_of_the_day(index)
        return JSONResponse({"feed": feed, "needs": needs, "rediscover": rediscover(index), "snoozed": snoozed(),
                             "question": q.card(index) if q else None,
                             "tour": _plain(latest_tour(index)),
                             "metabolism": await run_in_threadpool(metabolism, index),
                             "recent": {t: recent_of(index, t) for t in ("sketch", "spec", "capture", "frame", "insight")}})

    async def projects_data(request):
        await run_in_threadpool(fresh)
        return JSONResponse(_plain(await run_in_threadpool(projects_overview, index)))

    async def listing(request):
        await run_in_threadpool(fresh)
        tid = request.query_params.get("type")
        items = [e for e in index.entities.values() if e.type == tid]
        items.sort(key=lambda e: (index.touched.get(e.id) or "", e.date or ""), reverse=True)
        cards = [e.card(index) for e in items]
        if index.types.get(tid, {}).get("group") == "frame":
            groups: dict[str, dict] = {}
            for c in cards:
                g = groups.setdefault(c["group"], {"group": c["group"], "docs": [], "touched": c["touched"]})
                g["docs"].append(c)
            for g in groups.values():
                brief = next((d for d in g["docs"] if d["id"].endswith("/brief.md")), g["docs"][0])
                g["title"], g["description"], g["lead"] = brief["title"], brief["description"], brief["id"]
                g["date"] = brief.get("date") or g["group"].split("/")[-1][:10]
            out = sorted(groups.values(), key=lambda g: (g["date"] or "", g["group"]), reverse=True)
            return JSONResponse({"type": tid, "groups": out})
        return JSONResponse({"type": tid, "items": cards})

    async def entity(request):
        await run_in_threadpool(fresh)
        eid = request.query_params.get("id", "")
        view = await run_in_threadpool(entity_view, index, eid)
        if view:
            return JSONResponse(view)
        moved = index.moved_to(eid)  # a note the agent moved (a capture to sources/): the open page follows it
        return JSONResponse({"error": "not found", **({"moved_to": moved} if moved else {})}, status_code=404)

    async def graph(request):
        await run_in_threadpool(fresh)
        wanted = {t for t in (request.query_params.get("types") or "insight,map").split(",") if t in GRAPH_TYPES}
        return JSONResponse(await run_in_threadpool(graph_data, index, wanted or {"insight", "map"}))

    async def search(request):
        q = request.query_params.get("q", "")
        tid = request.query_params.get("type") or None
        if request.query_params.get("mode") == "deep":
            if forbidden(request):  # the slow path only for Atlas itself
                return JSONResponse({"error": "forbidden"}, status_code=403)
            results = await run_in_threadpool(deep_search, index, q)
            if not results:
                note = ("Search by meaning is off for this vault; showing instant results." if qmd_state() == "off" else
                        "Search by meaning needs QMD (github.com/tobi/qmd) and its collections for this vault: "
                        "`engine/atlas.py qmd setup` (skill atlas-qmd); showing instant results.")
                return JSONResponse({"mode": "fast", "note": note, "results": fast_search(index, q, tid)})
            return JSONResponse({"mode": "deep", "results": results})
        try:
            limit = max(1, min(60, int(request.query_params.get("n") or 60)))
        except ValueError:
            limit = 60
        return JSONResponse({"mode": "fast", "results": fast_search(index, q, tid, limit)})

    async def card_data(request):
        view = hover_card(index, request.query_params.get("id", ""))
        return JSONResponse(view) if view else JSONResponse({"error": "not found"}, status_code=404)

    def forbidden(request) -> bool:
        """Writes need the app's own header: browsers cannot add it cross-origin without a
        CORS preflight this server never grants, so other sites (and sandboxed widgets)
        cannot write notes or message the agent."""
        return request.headers.get("x-atlas") != "1"

    async def body_of(request) -> dict:
        try:
            body = await request.json()
        except Exception:
            return {}
        return body if isinstance(body, dict) else {}

    def known(value) -> str | None:
        return value if isinstance(value, str) and value in index.entities else None

    async def action(request):
        if forbidden(request):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        body = await body_of(request)
        act = slug(str(body.get("action", "note")), 16)
        target = known(body.get("id"))
        text = str(body.get("text", ""))[:20000]
        path = write_note(act, target, text, index)
        if operator_state()["mode"] == "operator":
            append_jsonl(INBOX, {"ts": now_iso(), "role": "user", "kind": "action", "action": act,
                                 "context": target, "text": text, "note": path})
        index.refresh(force=True)
        return JSONResponse({"ok": True, "note": path})

    async def chat_post(request):
        if forbidden(request):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        body = await body_of(request)
        text = str(body.get("text", "")).strip()[:20000]
        context = known(body.get("context"))
        via = body.get("via") if body.get("via") in ("choice", "checklist", "widget", "move", "command") else None
        to = body.get("to") if isinstance(body.get("to"), str) and AGENT_ID.match(body.get("to")) else None
        if not text:
            return JSONResponse({"ok": False}, status_code=400)
        if operator_state()["mode"] == "operator":
            outbox_at = len(read_jsonl(OUTBOX))  # before the message exists: an answer to it cannot come earlier
            record = {"ts": now_iso(), "role": "user", "kind": "message", "text": text, "context": context}
            if via:
                record["via"] = via
            if to:  # for one named agent; without it, every listening agent receives the message
                record["to"] = to
            append_jsonl(INBOX, record)
            # outbox_at: how many answers there were before the message; one numbered from it on came after
            return JSONResponse({"ok": True, "delivered": "agent", "ts": record["ts"], "outbox_at": outbox_at})
        path = write_note("note", context, f"[via {via}] {text}" if via else text, index)
        return JSONResponse({"ok": True, "delivered": "note", "note": path})

    async def snooze(request):
        if forbidden(request):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        body = await body_of(request)
        key = str(body.get("key") or "")[:200]
        if not key:
            return JSONResponse({"ok": False}, status_code=400)
        if body.get("wake"):
            return JSONResponse({"ok": True, "snoozed": set_snooze(key, None)})
        until = _date(body.get("until"))
        if not until:
            return JSONResponse({"ok": False}, status_code=400)
        value = {"until": until, "sig": str(body.get("sig") or "")[:400], "label": str(body.get("label") or "")[:300]}
        return JSONResponse({"ok": True, "snoozed": set_snooze(key, value)})

    async def drop(request):
        """A file dropped on Atlas lands in the registry's `drop.dir` (captures/ by default), never outside the vault."""
        if forbidden(request):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        from urllib.parse import unquote
        raw = Path(unquote(request.headers.get("x-filename", ""))).name
        clean = lambda s: re.sub(r"[^\w.-]+", "-", s).strip("-.")
        name = (clean(Path(raw).stem)[:100] or "dropped") + (("." + clean(Path(raw).suffix)[:15]) if clean(Path(raw).suffix) else "")
        folder = (VAULT / str(index.drop.get("dir") or "captures")).resolve()
        if folder != VAULT.resolve() and VAULT.resolve() not in folder.parents:
            return JSONResponse({"error": "drop.dir must lie inside the vault"}, status_code=500)
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > DROP_MAX:
                return JSONResponse({"error": f"larger than {DROP_MAX // 2**20} MB"}, status_code=413)
        if not data:
            return JSONResponse({"error": "empty file"}, status_code=400)
        folder.mkdir(parents=True, exist_ok=True)
        path, n = folder / name, 2
        while path.exists() or path.is_symlink():  # never overwrite: report-3.pdf next to report.pdf
            path, n = folder / f"{Path(name).stem}-{n}{Path(name).suffix}", n + 1
        with open(path, "xb") as fh:  # exclusive: never write through a link
            fh.write(bytes(data))
        committed = path.suffix.lower() == ".md" and await run_in_threadpool(commit_drop, path, index.types)
        return JSONResponse({"ok": True, "path": path.relative_to(VAULT.resolve()).as_posix(), "committed": committed})

    def chat_payload() -> dict:
        outbox = [{**r, "n": i} for i, r in enumerate(read_jsonl(OUTBOX))]  # n: its place, to tell later from earlier
        items = read_jsonl(INBOX) + outbox
        items.sort(key=lambda r: r.get("ts", ""))
        items = items[-200:]
        for m in items:
            if m.get("role") == "agent" and m.get("kind") != "progress":
                try:
                    m["blocks"] = render_agent_message(index, str(m.get("text", "")))
                except Exception as exc:  # noqa: BLE001
                    m["blocks"] = [{"kind": "error", "text": f"could not render message: {type(exc).__name__}"}]
        return {"messages": items, "operator": operator_state()}

    async def chat_history(request):
        # off the event loop: a note or graph block reads git (history, project view) while it renders
        return JSONResponse(await run_in_threadpool(chat_payload))

    async def stream(request):
        async def events():
            sizes = (-1, -1)
            version, op, ping = index.version, None, time.time()
            yield "retry: 3000\n\nevent: chat\ndata: {}\n\n"  # (re)connected: client reloads the chat
            while True:
                if await request.is_disconnected():
                    break
                cur = (INBOX.stat().st_size if INBOX.exists() else 0, OUTBOX.stat().st_size if OUTBOX.exists() else 0)
                if cur != sizes:
                    if sizes != (-1, -1):
                        yield "event: chat\ndata: {}\n\n"
                    sizes = cur
                state = operator_state()
                if state != op:
                    op = state
                    yield f"event: operator\ndata: {json.dumps(state)}\n\n"
                await run_in_threadpool(fresh)
                if index.version != version:
                    version = index.version
                    yield f"event: index\ndata: {json.dumps({'version': version})}\n\n"
                if time.time() - ping > 15:
                    ping = time.time()
                    yield ": ping\n\n"
                await asyncio.sleep(1.5)
        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def raw(request):
        rel = request.path_params["path"]
        path = (VAULT / rel).resolve()
        if path.suffix.lower() not in IMAGE_EXT or not path.is_file() or VAULT.resolve() not in path.parents:
            return Response(status_code=404)
        return FileResponse(path, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
                                           "X-Content-Type-Options": "nosniff"})

    routes = [
        Route("/", home), Route("/api/meta", meta), Route("/api/home", home_data), Route("/api/list", listing),
        Route("/api/projects", projects_data),
        Route("/api/entity", entity), Route("/api/search", search), Route("/api/graph", graph), Route("/api/card", card_data),
        Route("/api/snooze", snooze, methods=["POST"]), Route("/api/drop", drop, methods=["POST"]),
        Route("/api/action", action, methods=["POST"]), Route("/api/chat", chat_post, methods=["POST"]),
        Route("/api/chat", chat_history, methods=["GET"]), Route("/api/stream", stream),
        Route("/raw/{path:path}", raw), Mount("/static", StaticFiles(directory=STATIC)),
    ]
    from starlette.middleware import Middleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    hosts = ["localhost", "127.0.0.1", "*.ts.net"] + [h for h in os.environ.get("ATLAS_HOSTS", "").split(",") if h]
    from starlette.middleware.gzip import GZipMiddleware
    return Starlette(routes=routes, middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=hosts),
                                                Middleware(GZipMiddleware, minimum_size=2048)])


# --------------------------------------------------------------------------- CLI

def port_free(host: str, port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def cmd_serve(args) -> None:
    import uvicorn
    if not port_free(args.host, args.port):
        sys.exit(f"port {args.port} is busy: another Atlas (or something else) runs there. "
                 f"Check `curl -s localhost:{args.port}/api/meta` (vault_path) or pass --port.")
    ensure_state()
    other = session()
    if other.get("port") and other.get("port") != args.port and serving(f"http://localhost:{other['port']}"):
        # one Atlas per vault: a second one would overwrite the session, and the first would turn standalone
        sys.exit(f"Atlas already runs for this vault at http://localhost:{other['port']} "
                 f"({other.get('mode', '?')}). Open that one, or stop it first.")
    mode = "operator" if args.operator else "standalone"
    SESSION.write_text(json.dumps({"mode": mode, "started": now_iso(), "port": args.port, "pid": os.getpid()}), encoding="utf-8")
    if args.operator and not CURSOR.exists():
        write_cursor(len(read_jsonl(INBOX)))  # first operator run: older history counts as read
    t0 = time.time()
    index = Index()
    print(json.dumps({"atlas": "started", "mode": mode, "url": f"http://localhost:{args.port}",
                      "entities": len(index.entities), "index_seconds": round(time.time() - t0, 1)}), flush=True)
    # Open live streams would otherwise keep the process alive forever on shutdown.
    uvicorn.run(make_app(index), host=args.host, port=args.port, log_level="warning", timeout_graceful_shutdown=2)


def read_cursor(path: Path | None = None) -> int:
    try:
        return int((path or CURSOR).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return len(read_jsonl(INBOX))  # unreadable cursor: never replay old history


def write_cursor(n: int, path: Path | None = None) -> None:
    path = path or CURSOR
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(n), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a concurrent reader never sees an empty file


def cmd_wait(args) -> None:
    """Block until the user writes in the chat, print the new messages, exit. Re-arm after replying.

    Only one waiter per agent: a second `wait` for the same agent exits at once instead of
    racing the first one for the user's message. With `--agent <id>`, several agents listen
    side by side: each gets the messages addressed to it and those addressed to nobody."""
    ensure_state()
    agent = agent_id(args.agent)
    note_session(agent)
    lock = open(STATE / (f"wait-{agent}.lock" if agent else "wait.lock"), "w", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:  # Windows
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print(f"(another `atlas.py wait{' --agent ' + agent if agent else ''}` is already listening; not starting a second one)")
        return
    cursor = STATE / f"cursor-{agent}" if agent else CURSOR
    if agent:
        PRESENCE.mkdir(parents=True, exist_ok=True)
        if not cursor.exists():  # a new agent starts where the shared cursor is: no replay of old history
            write_cursor(read_cursor() if CURSOR.exists() else len(read_jsonl(INBOX)), cursor)
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        HEARTBEAT.touch()
        if agent:
            (PRESENCE / f"{agent}.beat").touch()
        inbox = read_jsonl(INBOX)
        seen = read_cursor(cursor) if cursor.exists() else 0
        if len(inbox) > seen:
            write_cursor(len(inbox), cursor)
            mine = [m for m in inbox[seen:] if not agent or not m.get("to") or m.get("to") == agent]
            for msg in mine:
                ctx = f" [viewing: {msg['context']}]" if msg.get("context") else ""
                ctx += f" [via {msg['via']}]" if msg.get("via") else ""
                ctx += f" [to: {msg['to']}]" if msg.get("to") and not agent else ""  # an unnamed waiter sees everything
                if msg.get("kind") == "action":
                    print(f"USER ACTION {msg.get('action')}{ctx}: {msg.get('text') or ''} (note: {msg.get('note')})")
                else:
                    print(f"USER{ctx}: {msg.get('text')}")
                for c in recall_cards(msg.get("text") or ""):  # who the message names: their cards, briefly
                    print(f"  CABINET {c['name']} ({c['id']}): {c['facts']} | {c['state']}")
            if mine:
                return
        time.sleep(2)
    print(f"(no message from the user in {args.timeout // 60} min; re-arm with `engine/atlas.py wait"
          f"{' --agent ' + agent if agent else ''}`)")


def cmd_recall(args) -> None:
    """Print the cards named in a text. Without a text it reads stdin; a Claude Code
    UserPromptSubmit hook passes JSON with `prompt` there, and the output joins the prompt."""
    text = " ".join(args.text) if args.text else sys.stdin.read()
    try:
        text = json.loads(text).get("prompt", "") if text.lstrip().startswith("{") else text
    except (ValueError, AttributeError):
        pass
    cards = recall_cards(text)
    if cards:
        print("Cabinet cards for names in this message (vault/cabinet/):")
        for c in cards:
            print(f"- {c['name']} ({c['id']}): {c['facts']}\n  {c['state']}")


def cmd_mentions(args) -> None:
    """Which notes name a person or organization: written by them (`authors:`) and mentioning them."""
    index = Index()
    name = " ".join(args.name)
    cards = {e.id: e.meta for e in index.entities.values() if index.types[e.type].get("recall")}
    cid = unique_terms(cards).get(name) or next((c for t, c in unique_terms(cards).items() if t.lower() == name.lower()), None)
    if not cid:
        sys.exit(f"no card answers to {name!r}; cards live in cabinet/people/ and cabinet/orgs/")
    m = mentions(index, index.entities[cid])
    print(f"{index.entities[cid].title} ({cid})")
    for label, key in (("written by", "written"), ("mentioned in", "mentioned")):
        items = m[key]
        print(f"\n{label}: {m['total'][key]}" + (f" (first {len(items)} listed)" if len(items) < m["total"][key] else ""))
        for x in items:
            print(f"  {x['type']:9} {x['title']}  ({x['id']})")


def note_path(path: str) -> str:
    """A note path as Atlas names it, relative to the vault, however the agent wrote it: from the Atlas
    folder (`vault/captures/x.md`), from the vault (`captures/x.md`) or absolute."""
    p = Path(path)
    for cand in ([p] if p.is_absolute() else [Path.cwd() / p, VAULT / p]):
        try:
            return cand.resolve().relative_to(VAULT.resolve()).as_posix()
        except ValueError:
            continue
    return path.replace("\\", "/")


def cmd_say(args) -> None:
    note_session(agent_id(args.agent))
    text = args.text if args.text != "-" else sys.stdin.read()
    record = {"ts": now_iso(), "role": "agent", "text": text}
    if args.progress:  # a short status line while you work; the user still sees "agent is working"
        record = {**record, "kind": "progress", "text": " ".join(text.split())[:300]}
    if args.title:  # what you are doing now; Atlas shows it above the conversation
        record["title"] = " ".join(args.title.split())[:80]
    if args.open:
        record["open"] = note_path(args.open)
    agent = agent_id(args.agent)
    if agent:
        record["agent"] = agent
    append_jsonl(OUTBOX, record)
    print("sent")


def frontmatter_problems(meta: dict, checks: dict) -> list[str]:
    """What the registry's `checks:` for this type say is wrong with one note's frontmatter."""
    out = []
    for key in checks.get("require", []):
        if meta.get(key) in (None, "", []):
            out.append(f"missing `{key}`")
    limit = checks.get("description_max")
    desc = meta.get("description")
    if limit and isinstance(desc, str) and len(desc) > int(limit):
        out.append(f"description has {len(desc)} characters (max {limit})")
    for key, allowed in (checks.get("allowed") or {}).items():
        val = meta.get(key)
        if val not in (None, "") and str(val) not in [str(a) for a in allowed]:
            out.append(f"`{key}: {val}` is not one of {', '.join(map(str, allowed))}")
    return out


def health(index: Index) -> dict:
    """Checks that protect a claim, can fail and cost nothing: the index already holds every link."""
    ents = list(index.entities.values())
    knowledge = {"insight", "map"}
    insights = [e for e in ents if e.type == "insight"]
    orphans = []
    if len(insights) >= 2:  # the first insight of a vault has nothing to link to yet
        for e in insights:
            linked = [i for i in e.links + index.backlinks.get(e.id, []) if index.entities.get(i) and index.entities[i].type in knowledge]
            if not linked and not e.meta.get("unconnected"):  # `unconnected: "<why>"`: nothing related exists yet
                orphans.append(e)
    checked = {tid for tid, spec in index.types.items() if "checks" in spec}  # types that declare checks (even `checks: {}`)
    agents = known_agents(index)
    notes, attribution = [], 0
    qs = open_questions(index)
    over = {e.id for e in qs[QUESTION_CAP:]}  # the coldest ones past the cap
    for e in sorted(ents, key=lambda e: e.id):
        issues = []
        if e.type in checked:
            issues += e.problems + e.unresolved_fields + [f"links to [[{u}]], which matches no note" for u in e.unresolved]
        if e in orphans:
            issues.append("no link to or from any other insight or map")
        if e.id in over:
            issues.append(f"one of {len(qs)} open questions, the cap is {QUESTION_CAP}: answer it, merge it into "
                          "another, or set `status: dormant` (the coldest go first)")
        for key in ("created_by", "updated_by"):  # attribution is vault-wide, whatever the type
            who = e.meta.get(key)
            if who not in (None, "") and str(who) not in agents:
                issues.append(f"`{key}: {who}` is not an agent in agents/ (nor `user`)")
                attribution += 1
        if e.type == "agent" and e.meta.get("updated_by") not in (None, "", "user", Path(e.id).stem):
            issues.append(f"edited by `{e.meta.get('updated_by')}`: each agent owns its own identity file")
            attribution += 1
        if issues:
            notes.append({"id": e.id, "type": e.type, "title": e.title, "issues": issues})
    ents = [e for e in ents if e.type in checked]
    return {"notes": notes, "total": len(notes), "frontmatter": sum(1 for e in ents if e.problems),
            "unresolved": sum(len(e.unresolved) + len(e.unresolved_fields) for e in ents), "orphans": len(orphans),
            "attribution": attribution, "questions": len(over)}


def known_agents(index: Index) -> set[str]:
    """Agent ids are the file names in agents/; `user` is always known."""
    return {Path(e.id).stem for e in index.entities.values() if e.type == "agent"} | {"user"}


def suggestions(index: Index) -> list[str]:
    """What the vault suggests doing next, most useful first. The operator offers these as choices."""
    ents = list(index.entities.values())
    by = lambda t: [e for e in ents if e.type == t]
    insights, maps = by("insight"), by("map")
    captures = [e for e in by("capture") if str(e.meta.get("kind", "")) != "operational"]
    operational = [e for e in by("capture") if str(e.meta.get("kind", "")) == "operational"]
    mapped = {i for m in maps for i in m.links}
    unmapped = [e for e in insights if e.id not in mapped]
    today = dt.date.today().isoformat()
    due = [e for e in insights if not e.meta.get("superseded_by")  # a replaced claim is not re-checked (#53)
           and _date(e.meta.get("revisit_after")) and _date(e.meta.get("revisit_after")) <= today]
    notes = [e for e in ents if e.type == "note" and str(e.meta.get("status")) == "new"]
    out = []
    if notes:
        out.append(f"{len(notes)} new note(s) from the user in you/notes/: read and handle them, then set status: done")
    current = current_session()
    ended = open_sessions(current[1] if current else None)
    if ended:
        out.append(f"{len(ended)} earlier session(s) ended without /close: offer to catch them up "
                   "(`engine/atlas.py sessions`, skill atlas-project)")
    threads = sorted((e for e in ents if e.type == "thread" and str(e.status) == "open"),
                     key=lambda e: (index.touched.get(e.id) or "", e.mtime), reverse=True)
    for t in threads[:3]:  # project work first: what the user is most likely in the middle of
        where = f" ({t.project})" if t.project else ""
        if t.meta.get("blocked"):
            out.append(f"Thread \"{t.title}\"{where} is blocked: {_plain(t.meta['blocked'])}. Ask the user about it")
        else:
            step = f", next: {_plain(t.meta['next'])}" if t.meta.get("next") else ""
            out.append(f"Thread \"{t.title}\"{where} is open{step}. Offer to continue it (skill atlas-project)")
    if len(threads) > 3:
        out.append(f"{len(threads) - 3} more open thread(s): `engine/atlas.py boot <project>` lists a project's threads")
    if captures:
        out.append(f"{len(captures)} capture(s) waiting: offer to distill them into insights (skill atlas-distill)")
    if operational:
        today_d = dt.date.today()
        ages = [(today_d - dt.date.fromisoformat(e.date[:10])).days if e.date else 0 for e in operational]
        projects = sorted({str(e.meta.get("project")) for e in operational if e.meta.get("project")})
        out.append(f"{len(operational)} operational capture(s) waiting, oldest {max(ages)} day(s)"
                   f"{' (' + ', '.join(projects) + ')' if projects else ''}: resolve them into threads, decisions "
                   "or lessons (skill atlas-project)")
    if len(unmapped) >= 5:
        out.append(f"{len(unmapped)} insight(s) belong to no map: offer to build the first map(s) (skill atlas-map)")
    if due:
        out.append(f"{len(due)} insight(s) past revisit_after: offer /revisit (skill atlas-revisit)")
    h = health(index)
    if h["total"]:
        parts = [f"{n} {label}" for n, label in ((h["frontmatter"], "with frontmatter problems"),
                 (h["unresolved"], "unresolved link(s)"), (h["orphans"], "unconnected insight(s)"),
                 (h["attribution"], "attribution problem(s)"), (h["questions"], "open question(s) past the cap")) if n]
        out.append(f"{h['total']} note(s) need a fix ({', '.join(parts)}): run `engine/atlas.py check` and fix them; "
                   "a wrong link is usually a typo or a renamed title")
    minimal = [e for e in ents if e.type in ("person", "org") and str(e.meta.get("depth")) == "minimal"]
    if minimal:
        out.append(f"{len(minimal)} cabinet card(s) are minimal: offer \"Expand cards\" (/expand-cards, skill "
                   "atlas-cabinet), which completes them within the budget in atlas.yaml")
    qs = open_questions(index)
    if len(qs) >= QUESTION_CAP:
        out.append(f"{len(qs)} open questions, the cap is {QUESTION_CAP}: before filing more, answer one, merge two, "
                   "or rest the coldest as `status: dormant` (skill atlas-distill, step 5)")
    if not content_count(index):
        out.append("The vault is empty: ask what the user is curious about and research it (skill atlas-learn)")
    return out


def cmd_next(args) -> None:
    index = Index()
    tips = suggestions(index)
    counts: dict[str, int] = {}
    for e in index.entities.values():
        counts[e.type] = counts.get(e.type, 0) + 1
    print(json.dumps({"counts": counts, "next": tips}, ensure_ascii=False, indent=2))


def cmd_check(args) -> None:
    """List every note a check flags; exit 1 if there is any, so it can gate a commit."""
    h = health(Index())
    for n in h["notes"]:
        for issue in n["issues"]:
            print(f"{n['id']}: {issue}")
    print(f"{h['total']} note(s) need a fix" if h["total"] else "all checks pass")
    sys.exit(1 if h["total"] else 0)


# --------------------------------------------------------------------------- projects: machine, paths, boot

def machine_id() -> str:
    """Which machine this is, as the key of a project's `paths:`. $ATLAS_MACHINE overrides the host name."""
    import socket
    return (os.environ.get("ATLAS_MACHINE") or socket.gethostname().split(".")[0]).strip().lower()


def _norm_remote(url: str) -> str:
    u = url.strip().lower()
    u = re.sub(r"^[a-z+]+://", "", u)            # https://, ssh://, git+ssh://
    u = re.sub(r"^[^@/]+@", "", u)               # user@ or token@
    u = u.replace(":", "/", 1) if re.match(r"^[^/]+:[^/]", u) else u  # git@host:owner/repo
    return u.rstrip("/").removesuffix(".git")


def _git_out(*args: str, cwd: str | Path | None = None) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                           env=git_env())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def resolve_checkout(ent: "Entity", override: str | None = None) -> dict:
    """Where this project's code lives on this machine, and whether it is really that repo. Never guesses."""
    machine = machine_id()
    paths = ent.meta.get("paths") if isinstance(ent.meta.get("paths"), dict) else {}
    raw = override or paths.get(machine)
    if not raw and not paths and not str(ent.meta.get("repo") or "").strip():  # nothing to check out yet
        return {"status": "no code", "machine": machine,
                "hint": f"no code yet: once a repository exists, `engine/atlas.py map-path {ent.project} <dir>`"}
    if not raw:
        return {"status": "unmapped", "machine": machine,
                "hint": f"no path for machine `{machine}`: ask the user where the checkout is, then "
                        f"`engine/atlas.py map-path {ent.project} <dir>`"}
    path = Path(str(raw)).expanduser()
    if not path.is_dir():
        return {"status": "missing", "machine": machine, "path": str(path), "hint": f"{path} does not exist on `{machine}`"}
    top = _git_out("rev-parse", "--show-toplevel", cwd=path)
    if top is None:
        return {"status": "not a git repository", "machine": machine, "path": str(path), "hint": f"{path} is not a git checkout"}
    repo = str(ent.meta.get("repo") or "").strip()
    remotes = {_norm_remote(line.split()[1]) for line in (_git_out("remote", "-v", cwd=path) or "").splitlines() if len(line.split()) > 1}
    if repo and _norm_remote(repo) not in remotes:
        return {"status": "remote mismatch", "machine": machine, "path": str(path),
                "hint": f"{path} has remotes {', '.join(sorted(remotes)) or 'none'}, not {repo}"}
    return {"status": "ok", "machine": machine, "path": str(path),
            "branch": _git_out("rev-parse", "--abbrev-ref", "HEAD", cwd=path),
            "head": _git_out("rev-parse", "--short", "HEAD", cwd=path)}


def find_project(index: Index, ref: str) -> tuple["Entity | None", list["Entity"]]:
    """Exact slug, title or alias first; then a unique partial match. Ambiguity is an error, never a pick."""
    projects = [e for e in index.entities.values() if e.type == "project"]
    key = ref.strip().lower()
    names = lambda e: {str(e.project).lower(), e.title.lower(), *[str(a).lower() for a in (e.meta.get("aliases") or [])]}
    exact = [e for e in projects if key in names(e)]
    if len(exact) == 1:
        return exact[0], []
    partial = exact or [e for e in projects if any(key in n for n in names(e))]
    return (partial[0], []) if len(partial) == 1 else (None, partial)


def _tok(text: str) -> int:
    return len(text) // 4 + 1


def _clip(text: str, tokens: int, path: str) -> str:
    text = text.strip()
    return text if _tok(text) <= tokens else text[: tokens * 4].rstrip() + f"\n… (cut for the budget; read {path})"


def _sans_h1(body: str) -> str:
    """Boot prints its own heading for each file; the file's H1 would repeat it."""
    return H1.sub("", body, count=1).strip() if body.lstrip().startswith("#") else body.strip()


def _gist(e: "Entity") -> str:
    """One paragraph of a record, for boot."""
    return first_paragraph(e.body) or e.description


def boot_packet(index: Index, project: "Entity | None", agent: str, budget: int, checkout: str | None,
                stats: dict | None = None) -> tuple[str, list[str]]:
    """The context an agent loads before working: read-only, offline, deterministic, budgeted.
    Rules and decisions in force are never cut; everything left out is listed with its path."""
    used, warnings, omitted, files = 0, [], [], []
    get = lambda rel: index.entities.get(rel)
    def spend(text: str, essential: bool = False) -> bool:
        nonlocal used
        if essential or used + _tok(text) <= budget:
            used += _tok(text)
            return True
        return False
    S: dict[str, list[str]] = {k: [] for k in ("head", "identity", "user", "project", "rules", "decisions",
                                                 "lessons", "threads", "captures")}
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    S["head"].append(f"# Atlas boot · agent `{agent}` · {f'project `{project.project}`' if project else 'no project'} · {now}")
    S["head"].append(f"vault: {VAULT} · machine: `{machine_id()}`")

    me = get(f"agents/{agent}.md")
    if me:
        files.append(me.id)
        text = _clip(_sans_h1(me.body), min(1500, budget // 6), me.id)
        spend(text, essential=True)
        S["identity"] += [f"## You: {me.title} ({me.id})", text,
                          "Your model and harness version come from your running session, not from this file."]
    else:
        warnings.append(f"no agents/{agent}.md: write your identity file (the atlas-operator skill says how)")
    user_parts = [e for e in (get("you/profile.md"), get("you/goals.md")) if e]
    if user_parts:
        S["user"].append("## The user")
        for e in user_parts:
            files.append(e.id)
            text = _clip(_sans_h1(e.body), min(800, budget // 10), e.id)
            spend(text, essential=True)
            S["user"] += [f"### {e.title} ({e.id})", text]

    if project is None:
        projects = sorted((e for e in index.entities.values() if e.type == "project"), key=lambda e: (e.group or "", e.title))
        S["project"].append("## Projects")
        for e in projects:
            n_open = sum(1 for x in index.entities.values() if x.type == "thread" and x.project == e.project
                         and x.group == e.group and str(x.status) == "open")
            S["project"].append(f"- {e.title} [{e.group}] · {e.status or 'no status'} · {n_open} open thread(s) · {e.id}")
        if warnings:
            S["head"].append("\n".join(f"⚠ {w}" for w in warnings))
        return "\n\n".join("\n".join(v) for v in S.values() if v), files

    files.append(project.id)
    co = resolve_checkout(project, checkout)
    branch = co.get("branch")
    S["project"].append(f"## Project: {project.title} ({project.id})")
    S["project"].append(f"group: `{project.group}` · status: {project.status or 'not set'}")
    if co["status"] == "ok":
        S["project"].append(f"checkout: {co['path']} · branch `{branch}` @ {co['head']}")
    elif co["status"] == "no code":  # nothing is missing: the project has no repository yet
        S["project"].append(f"checkout: {co['hint']}.")
    else:
        S["project"].append(f"checkout: UNRESOLVED ({co['status']}). {co['hint']}. You can read the memory; "
                            "do not touch code until the checkout is resolved.")
        warnings.append(f"checkout {co['status']}: {co['hint']}")
    body = _clip(_sans_h1(project.body), min(1500, budget // 6), project.id)
    spend(body, essential=True)
    S["project"].append(body)

    group = get(f"projects/{project.group}/_group.md")
    if group:
        files.append(group.id)
        spend(group.body, essential=True)  # rules are never cut
        S["rules"] += [f"## Rules of group `{project.group}` ({group.id})", _sans_h1(group.body)]
    else:
        warnings.append(f"group `{project.group}` has no _group.md: no group rules loaded")

    mine = [e for e in index.entities.values() if e.group == project.group and e.project == project.project]
    group_lessons = [index.entities[i] for i in (group.links if group else []) if index.entities.get(i)
                     and index.entities[i].type == "lesson" and index.entities[i].project != project.project]
    def on_branch(e: "Entity") -> bool:
        b = e.meta.get("branch")
        return not b or not branch or str(b) == branch
    other_branch = [e for e in mine + group_lessons if e.type in ("thread", "decision", "lesson") and not on_branch(e)]
    pick = lambda typ, *st: sorted((e for e in mine if e.type == typ and str(e.status) in st and on_branch(e)), key=lambda e: e.title.lower())

    accepted = pick("decision", "accepted")
    if accepted:
        S["decisions"].append("## Decisions in force (accepted, any age)")
        for e in accepted:
            files.append(e.id)
            line = f"- **{e.title}**{f' ({e.date})' if e.date else ''} · {e.id}"
            spend(line, essential=True)  # constraints are never cut
            gist = f"  {_gist(e)}"
            S["decisions"] += [line] + ([gist] if spend(gist) else [])
    lessons = [(e, "") for e in pick("lesson", "validated")] + [(e, "") for e in pick("lesson", "provisional")] + \
              [(e, " (group)") for e in sorted(group_lessons, key=lambda e: e.title.lower())
               if on_branch(e) and str(e.status) in ("validated", "provisional")]
    if lessons:
        S["lessons"].append("## Lessons that apply")
        for e, origin in lessons:
            files.append(e.id)
            line = f"- [{e.status}]{origin} **{e.title}** · applies to: {e.meta.get('applies_to', '?')} · {e.id}"
            if not spend(line):
                omitted.append(e.id)
                continue
            gist = f"  {_gist(e)}"
            S["lessons"] += [line] + ([gist] if spend(gist) else [])
    proposed = pick("decision", "proposed")
    if proposed:
        S["decisions"].append("### Proposed, not decided")
        for e in proposed:
            line = f"- {e.title} · {e.id}"
            S["decisions"].append(line) if spend(line) else omitted.append(e.id)
    threads = pick("thread", "open")
    if threads:
        S["threads"].append("## Open threads (the handoff: whoever works a thread updates its next/blocked)")
        for e in threads:
            files.append(e.id)
            extra = "".join(f" · {k}: {e.meta[k]}" for k in ("next", "blocked", "branch") if e.meta.get(k))
            line = f"- **{e.title}**{extra} · {e.id}"
            S["threads"].append(line) if spend(line) else omitted.append(e.id)
    ops = [e for e in index.entities.values() if e.type == "capture" and str(e.meta.get("kind", "")) == "operational"
           and str(e.meta.get("project", "")) == project.project]
    if ops:
        oldest = min((e.date or "9999")[:10] for e in ops)
        S["captures"].append(f"## Operational captures (raw, not loaded): {len(ops)}, oldest from {oldest}; "
                             "resolve them into threads, decisions or lessons")
        S["captures"] += [f"- {e.id}" for e in sorted(ops, key=lambda e: e.id)]
    if other_branch:
        S["captures"].append(f"Left out, other branches: {', '.join(e.id for e in other_branch)}")
    if omitted:
        S["captures"].append(f"Left out for the budget ({budget} tokens): " + ", ".join(omitted))
    if warnings:
        S["head"].append("\n".join(f"⚠ {w}" for w in warnings))
    if stats is not None:  # what the project page shows: tokens per part, and what was left out
        stats.update(budget=budget, used=used, warnings=warnings, omitted=omitted,
                     other_branch=[e.id for e in other_branch],
                     sections={k: _tok("\n".join(v)) for k, v in S.items() if v and k != "head"},
                     counts={"decisions": len(accepted), "proposed": len(proposed), "lessons": len(lessons),
                             "threads": len(threads), "captures": len(ops)})
    return "\n\n".join("\n".join(v) for v in S.values() if v), files


def cmd_boot(args) -> None:
    for attempt in (1, 2):  # a file that changes while boot reads it gets one re-read
        started = time.time()
        index = Index()
        project = None
        if args.project:
            project, candidates = find_project(index, args.project)
            if not project:
                names = ", ".join(f"{e.project} ({e.id})" for e in candidates)
                sys.exit(f"project `{args.project}` is {'ambiguous: ' + names if candidates else 'unknown'}. "
                         "Projects live in projects/<group>/<slug>/project.md.")
        text, files = boot_packet(index, project, args.agent.strip().lower(), args.budget, args.checkout)
        if all((VAULT / f).stat().st_mtime < started for f in files if (VAULT / f).exists()):
            break
        if attempt == 2:
            text += "\n\n⚠ a file changed while boot was reading it; boot again before relying on this."
    agent = agent_id(args.agent)
    note_session(agent)
    if agent:  # Atlas shows which project an agent works on (disposable state, not vault content)
        ensure_state()
        PRESENCE.mkdir(parents=True, exist_ok=True)
        (PRESENCE / f"{agent}.json").write_text(json.dumps({"project": project.project if project else None,
                                                            "group": project.group if project else None, "booted": now_iso()}),
                                                encoding="utf-8")
    print(text)
    current = current_session()
    ended = open_sessions(current[1] if current else None)
    if ended:  # outside the budgeted packet: boot_packet stays deterministic
        print(f"\n## Sessions that ended without /close ({len(ended)})\n")
        print("\n".join(session_lines(ended)))


def cmd_machine(args) -> None:
    print(machine_id())
    print("(the key of `paths:` in project.md; set $ATLAS_MACHINE to name this machine differently)", file=sys.stderr)


def _top_value_span(events: list, key: str) -> tuple[int, int, int, bool] | None:
    """Where a top-level `key:` and its value sit in the YAML text, from PyYAML parse events: (start of the
    key, end of the value's content, the key's column, whether the value holds an anchor or alias).
    A block value ends at its last scalar, so comments after it stay; the last duplicate key wins, as in PyYAML."""
    import yaml

    def node(i: int) -> tuple[int, int, bool]:  # one node from events[i]: next index, end of content, anchored
        ev = events[i]
        anchored = getattr(ev, "anchor", None) is not None
        if not isinstance(ev, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
            return i + 1, ev.end_mark.index, anchored
        flows, last, i = [ev.flow_style], ev.end_mark.index, i + 1
        while flows:
            ev = events[i]
            anchored |= getattr(ev, "anchor", None) is not None
            if isinstance(ev, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                flows.append(ev.flow_style)
            elif isinstance(ev, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                if flows.pop():
                    last = ev.end_mark.index  # a flow collection ends at its bracket
            else:
                last = ev.end_mark.index
            i += 1
        return i, last, anchored

    if len(events) < 3 or not isinstance(events[2], yaml.MappingStartEvent):
        return None
    found, i = None, 3
    while not isinstance(events[i], yaml.MappingEndEvent):
        k = events[i]
        i, _, key_anchored = node(i)
        i, end, anchored = node(i)
        if isinstance(k, yaml.ScalarEvent) and k.value == key:
            found = (k.start_mark.index, end, k.start_mark.column, anchored or key_anchored)
    return found


def _set_front_path(path: Path, machine: str, target: str) -> None:
    """Set `paths.<machine>` in a note's frontmatter. Only the `paths:` value is rewritten; every other
    line, the line endings and the body stay byte-identical (a YAML round trip restyled the whole file, #29)."""
    import yaml
    text = path.read_bytes().decode("utf-8")  # read_text would turn \r\n into \n
    m = FRONT.match(text)
    if m:
        head, front, tail = text[:m.start(1)], m.group(1), text[m.end(1):]
    else:
        head, front, tail = "---\n", "", "\n---\n" + ("" if text.startswith("\n") else "\n") + text
    nl = "\r\n" if head.endswith("\r\n") else "\n"
    try:
        events = list(yaml.parse(front))
        meta, span = yaml.safe_load(front) or {}, _top_value_span(events, "paths")
    except yaml.YAMLError as err:
        sys.exit(f"{path.name}: the frontmatter is not valid YAML; fix it first ({err})")
    paths = meta.get("paths") if isinstance(meta, dict) else None
    if not isinstance(meta, dict) or (paths is not None and not isinstance(paths, dict)):
        sys.exit(f"{path.name}: `paths:` is not a mapping of machine: folder; fix it by hand first")
    want = {**(paths or {}), machine: target}
    block = yaml.safe_dump({"paths": want}, sort_keys=False, allow_unicode=True, width=1000).splitlines()
    if span and span[3]:
        sys.exit(f"{path.name}: `paths:` uses a YAML anchor or alias; set `{machine}: {target}` under it by hand")
    if span:
        start, end, column, _ = span
        line = front.rfind("\n", 0, start) + 1
        if front[line:start].strip() == "?":  # an explicit key (`? paths`): the indicator goes too
            start, column = line + front[line:start].index("?"), front[line:start].index("?")
        while end > start and front[end - 1] in " \t\r\n":
            end -= 1  # a block scalar (`|-`) ends after its newline; the line break stays outside
        candidates = [front[:start] + (nl + " " * column).join(block) + front[end:]]
    elif not meta:  # nothing but blank lines or comments
        candidates = [front + nl + nl.join(block) if front.strip() else nl.join(block)]
    else:  # a new key: try the layouts the root could have, last first; the read-back below picks
        root, first = events[2], events[3]  # a mapping with at least one key: `meta` is a non-empty dict
        columns = dict.fromkeys((root.start_mark.column, first.start_mark.column, 0))  # `?`, anchors, indents
        entry = lambda c: nl.join(" " * c + b for b in block)
        starts = dict.fromkeys(front.rfind("\n", 0, m.index) + 1 for m in (root.start_mark, first.start_mark))
        candidates = ([front + nl + entry(c) for c in columns]  # last, the usual place
                      + [front[:s] + entry(c) + nl + front[s:] for s in starts for c in columns])  # or first
    for new in candidates:  # the file is the truth: write only what reads back as the old frontmatter plus this path
        try:
            if yaml.safe_load(new) == {**meta, "paths": want}:
                path.write_text(head + new + tail, encoding="utf-8", newline="")
                return
        except yaml.YAMLError:
            pass
    sys.exit(f"{path.name}: could not set paths.{machine} without touching other lines; set `{machine}: {target}` "
             "under `paths:` by hand")


def cmd_map_path(args) -> None:
    index = Index()
    project, candidates = find_project(index, args.project)
    if not project:
        sys.exit(f"project `{args.project}` is {'ambiguous' if candidates else 'unknown'}")
    target = str(Path(args.dir).expanduser().resolve())
    probe = resolve_checkout(project, target)
    if probe["status"] != "ok":
        sys.exit(f"not mapped: {probe['hint']}")
    machine = machine_id()
    _set_front_path(VAULT / project.id, machine, target)
    print(f"{project.id}: paths.{machine} = {target} (branch {probe['branch']} @ {probe['head']})")


# --------------------------------------------------------------------------- attribution

def _set_front_key(fm_lines: list[str], key: str, value: str, only_if_missing: bool) -> bool:
    """Set a top-level `key: value` line in frontmatter lines, text-preserving. True if it changed."""
    for i, line in enumerate(fm_lines):
        if re.match(rf"^{re.escape(key)}\s*:", line):
            if only_if_missing and line.split(":", 1)[1].strip():
                return False
            fm_lines[i] = f"{key}: {value}"
            return True
    fm_lines.append(f"{key}: {value}")
    return True


def commit_drop(path: Path, types: dict) -> bool:
    """Commit a Markdown file the user dropped on Atlas, in the user's git name. A later agent commit then sees
    its history and leaves created_by unset instead of naming the agent (#42). Without git, or before the first
    commit, the file just waits in captures/."""
    top = _git_out("rev-parse", "--show-toplevel", cwd=VAULT)
    if top is None or _git_out("rev-parse", "--verify", "-q", "HEAD", cwd=top) is None:
        return False
    rel = os.path.relpath(path, top).replace("\\", "/")
    try:
        lock = _lock("git.lock")
    except SystemExit:  # an agent is committing right now; the file stays uncommitted, as before
        return False
    # No timeout, as in `commit`: a slow commit hook must finish, not be killed and leave .git/index.lock behind.
    run = lambda *a: subprocess.run(["git", *a], cwd=top, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", env=git_env()).returncode == 0  # paths are names (#48)
    try:  # `commit -- <path>` commits this file only, whatever else is staged
        if not run("add", "--", rel):
            return False
        if run("commit", "-q", "-m", f"drop: {path.name}", "--", rel):
            qmd_refresh_after_commit([os.path.relpath(path, VAULT).replace("\\", "/")], types)  # as `commit` does
            return True
        run("reset", "-q", "--", rel)  # a hook said no: unstage it, or every later `commit` stops at "unrelated changes"
        return False
    except OSError:
        return False
    finally:
        lock.close()


def stamp(path: Path, agent: str, new_file: bool) -> str | None:
    """created_by (only on a file with no history, never overwritten) and updated_by. Returns a note if the author is unknown."""
    text = path.read_text(encoding="utf-8")
    m = FRONT.match(text)
    if m:
        lines, body = m.group(1).splitlines(), text[m.end():]
    else:
        lines, body = [], text if text.startswith("\n") else "\n" + text
    has_creator = any(re.match(r"^created_by\s*:\s*\S", line) for line in lines)
    note = None
    if not has_creator:
        if new_file:
            _set_front_key(lines, "created_by", agent, only_if_missing=True)
        else:
            note = f"{path.relative_to(VAULT).as_posix()}: created_by unknown (it has history); left unset"
    _set_front_key(lines, "updated_by", agent, only_if_missing=False)
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + body, encoding="utf-8")
    return note


def _lock(name: str):
    ensure_state()
    handle = open(STATE / name, "w", encoding="utf-8")
    deadline = time.time() + 30
    while True:
        try:
            try:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except ImportError:  # Windows
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return handle
        except OSError:
            if time.time() > deadline:
                sys.exit("another `atlas.py commit` holds the git lock; try again")
            time.sleep(0.3)


def cmd_commit(args) -> None:
    """Commit exactly the paths an agent names, stamping who wrote them. Declared attribution, not authentication."""
    index = Index()
    agent = args.agent.strip().lower()
    note_session(agent_id(args.agent))
    paths = [Path(p) if Path(p).is_absolute() else (Path.cwd() / p) for p in args.paths]
    paths = [p.resolve() for p in paths]  # follows links before "..", and resolves a moved file through its folder (/var → /private/var)
    own_file = VAULT / "agents" / f"{agent}.md"
    if agent not in known_agents(index) and not (own_file.exists() and own_file.resolve() in paths):
        sys.exit(f"unknown agent `{agent}`: write agents/{agent}.md first (and commit it in the same call)")
    top = _git_out("rev-parse", "--show-toplevel", cwd=VAULT)
    if top is None:
        sys.exit("the vault is not in a git repository")
    if _git_out("rev-parse", "--verify", "-q", "HEAD", cwd=top) is None:  # the install could not commit
        sys.exit("this Atlas has no first commit yet: git needs your name and email. Set them\n"
                 '  git config --global user.name "Your Name"\n  git config --global user.email you@example.com\n'
                 f'then commit the install: git -C "{top}" commit -m "atlas: install", and run this again.')
    for p in paths:
        try:
            p.relative_to(VAULT)
        except ValueError:
            sys.exit(f"{p} is outside the vault ({VAULT})")
    lock = _lock("git.lock")
    rel_top = [os.path.relpath(p, top).replace("\\", "/") for p in paths]
    staged = set((_git_out("diff", "--cached", "--name-only", cwd=top) or "").splitlines())
    # a named folder covers what is staged inside it (a rename into it, say)
    unrelated = sorted(s for s in staged if not any(s == r or s.startswith(r.rstrip("/") + "/") for r in rel_top))
    if unrelated:
        sys.exit("unrelated changes are staged, not committing: " + ", ".join(unrelated[:8]) +
                 "\nCommit or unstage them first; this command commits only the paths you name.")
    # a path that is neither on disk nor in the index was already staged away (git mv): nothing left to add
    addable = [r for r in rel_top if (Path(top) / r).exists() or _git_out("ls-files", "--error-unmatch", "--", r, cwd=top) is not None]
    if addable:
        subprocess.run(["git", "add", "-A", "--", *addable], cwd=top, check=True, env=git_env())
    renamed_to = set()
    for line in (_git_out("diff", "--cached", "-M", "--name-status", cwd=top) or "").splitlines():
        cols = line.split("\t")
        if cols[0].startswith("R") and len(cols) == 3:
            renamed_to.add(cols[2])  # a move is not authorship
    notes = []
    files: list[tuple[Path, str]] = []  # a named folder stands for the notes in it that changed
    for line in (_git_out("diff", "--cached", "--name-only", "--diff-filter=ACMR", cwd=top) or "").splitlines():
        if any(line == r or line.startswith(r.rstrip("/") + "/") for r in rel_top):
            files.append((Path(top) / line, line))
    for p, rel in files:
        if p.suffix != ".md" or not p.is_file():
            continue
        history = _git_out("log", "-1", "--format=%h", "--", rel, cwd=top)
        note = stamp(p, agent, new_file=not history and rel not in renamed_to)
        if note:
            notes.append(note)
    if files:
        subprocess.run(["git", "add", "--", *[rel for _, rel in files]], cwd=top, check=True, env=git_env())
    if not (_git_out("diff", "--cached", "--name-only", cwd=top) or "").strip():
        print("nothing to commit")
        return
    r = subprocess.run(["git", "commit", "-q", "-m", args.message, "-m", f"Atlas-Agent: {agent}"], cwd=top,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=git_env())
    # this commit's files, read before another agent's commit can move HEAD; -z: names as they are, unquoted
    committed = [] if r.returncode else \
        (_git_out("diff-tree", "-z", "--root", "--no-commit-id", "--name-only", "-r", "HEAD", cwd=top) or "").split("\0")
    lock.close()
    if r.returncode:
        sys.exit(r.stderr.strip() or r.stdout.strip())
    print(f"committed {_git_out('rev-parse', '--short', 'HEAD', cwd=top)} as {agent}: {len(rel_top)} path(s)")
    for n in notes:
        print(f"note: {n}")
    refresh = qmd_refresh_after_commit([os.path.relpath(Path(top) / f, VAULT).replace("\\", "/") for f in committed if f],
                                       index.types)
    if refresh:
        print(refresh)


# --------------------------------------------------------------------------- qmd: search by meaning
#
# QMD (github.com/tobi/qmd) indexes five areas of the vault as collections atlas-<area>, in an index of the
# vault's own (`qmd --index <name>`): a refresh re-reads only these collections, never the user's other ones
# (or their update hooks), and names cannot collide with another vault's. Deep search and the workflows
# (atlas-qmd skill) query it. `qmd setup` creates it; `atlas.py commit` refreshes it in the background when a
# commit touched an area, one run at a time (`qmd sync`).

QMD_AREAS = [  # area, the note types it holds (their globs in the vault's registry), the context line QMD keeps
    # Every collection is rooted at the vault and narrowed by its types' globs, so a folder that does not exist
    # yet (a fresh vault has no cabinet/) is still a valid collection, and a vault that moved a folder keeps it.
    ("cabinet", ("person", "org"), "People and organizations: one card each with role, relation and timeline"),
    ("projects", ("group", "project", "thread", "decision", "lesson"),
     "Projects: project.md, threads, decisions and lessons per project"),
    ("ideas", ("sketch", "spec"), "Ideas: rough sketches and worked-out specs"),
    ("insights", ("insight", "map"), "Insights: one claim per note, the title is the claim; maps are *-map.md"),
    # captures too: a capture waiting to be distilled is what the vault knows newest, and it moves to sources/
    ("sources", ("source", "frame", "capture"), "Sources, research runs and captures waiting to be distilled"),
]


def qmd_globs(types: dict) -> dict[str, list[str]]:
    """Each area's globs, from the vault's registry."""
    return {area: list(dict.fromkeys(g for tid in tids for g in (types.get(tid) or {}).get("globs", [])))
            for area, tids, _ in QMD_AREAS}


def qmd_bin() -> str | None:
    """The resolved launcher: on Windows npm installs `qmd.cmd`, which a bare `qmd` does not find."""
    return shutil.which("qmd")


def qmd(*args: str, index: str | None = None, timeout: float = 1800) -> subprocess.CompletedProcess:
    """QMD's answer; not installed or too slow is a failed answer, never an exception."""
    exe = qmd_bin()
    if not exe:
        return subprocess.CompletedProcess(["qmd", *args], 127, "", "qmd is not installed")
    # INDEX_PATH beats --index (one database for every vault); without an index it is the user's own setting
    env = {k: v for k, v in os.environ.items() if not (index and k == "INDEX_PATH")}
    for k in ("QMD_CONFIG_DIR", "INDEX_PATH", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):  # QMD runs in the vault (below):
        if env.get(k) and not os.path.isabs(env[k]):                                 # relative paths keep their meaning
            try:
                env[k] = os.path.abspath(env[k])
            except OSError:  # the start folder itself is gone: nothing to resolve against
                pass
    try:
        # cwd: QMD's model loader stops when the server's own start folder was removed since (uv_cwd)
        return subprocess.run([exe, *(["--index", index] if index else []), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, env=env,
                              cwd=VAULT)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess([exe, *args], 124, "", f"qmd {args[0]} took longer than {timeout:.0f} s")


def qmd_config_dir() -> Path:  # where QMD keeps <index>.yml, the way QMD finds it
    if os.environ.get("QMD_CONFIG_DIR"):
        return Path(os.environ["QMD_CONFIG_DIR"])
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "qmd"


def qmd_collections(index: str = "index") -> dict[str, dict]:
    """The collections of a QMD index (`index` is QMD's default one): name -> {path, pattern}."""
    import yaml
    try:
        data = yaml.safe_load((qmd_config_dir() / f"{index}.yml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {n: {"path": Path(c["path"]), "pattern": c.get("pattern", "**/*.md")}
            for n, c in (data.get("collections") or {}).items() if isinstance(c, dict) and "path" in c}


def qmd_settings() -> dict:
    import yaml
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {} if REGISTRY.exists() else {}
    return reg.get("qmd") or {}


def qmd_state() -> str:
    """on, off or ask. YAML reads a bare `on`/`off` as true/false, so both spellings count."""
    v = qmd_settings().get("enabled", "ask")
    if v is True or str(v).lower() in ("on", "true", "yes"):
        return "on"
    if v is False or str(v).lower() in ("off", "false", "no"):
        return "off"
    return "ask"


def qmd_set(**values: str) -> None:
    """Set keys of the `qmd:` block in the vault's atlas.yaml; every other line stays as it is."""
    global REGISTRY
    own = VAULT / "atlas.yaml"
    if REGISTRY != own:  # a vault on the app's default registry gets its own copy, not a change for every vault
        shutil.copyfile(REGISTRY, own)
        REGISTRY = own
    lines = REGISTRY.read_text(encoding="utf-8").splitlines()
    if "qmd:" not in [ln.split("#")[0].strip() for ln in lines]:
        lines += ["", "qmd:                  # search by meaning (atlas-qmd)"]
    start = next(i for i, ln in enumerate(lines) if ln.split("#")[0].strip() == "qmd:")
    end, last = start + 1, start  # the block runs to the next top-level key, past blank lines and comments
    while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()
                                or lines[end].lstrip().startswith("#")):
        if lines[end].startswith((" ", "\t")) and lines[end].strip() and not lines[end].lstrip().startswith("#"):
            last = end
        end += 1
    for key, value in values.items():
        hit = next((i for i in range(start + 1, end) if lines[i].strip().startswith(f"{key}:")), None)
        if hit is None:
            lines.insert(last + 1, f"  {key}: {value}")
            last += 1
            end += 1
        else:
            comment = lines[hit][lines[hit].index("#"):] if "#" in lines[hit] else ""
            lines[hit] = f"  {key}: {value}" + (f"   {comment}" if comment else "")
    REGISTRY.write_text("\n".join(lines) + "\n", encoding="utf-8")


def qmd_plan(types: dict) -> tuple[str, list[dict]]:
    """This vault's index and its five collections. An index name another vault uses gets the vault's name added."""
    want = str(qmd_settings().get("index") or "atlas")
    globs = qmd_globs(types)
    cols = [{"area": a, "name": f"atlas-{a}", "path": VAULT.resolve(), "context": ctx,
             "mask": globs[a][0] if len(globs[a]) == 1 else "{" + ",".join(globs[a]) + "}"}
            for a, _, ctx in QMD_AREAS if globs[a]]
    for n in range(10):
        name = want if n == 0 else f"{want}-{slug(VAULT.name, 24)}" + (f"-{n}" if n > 1 else "")
        if all(c["path"].resolve() == VAULT.resolve() for c in qmd_collections(name).values()):
            return name, cols
    sys.exit("could not find a free QMD index name; set qmd.index in atlas.yaml")


def qmd_index() -> str | None:
    """The vault's QMD index when it is set up, on, and still this vault's (a copied vault keeps the setting,
    not the index: then nothing is searched or refreshed until `qmd setup` gives it one of its own)."""
    if qmd_state() != "on" or not qmd_bin():
        return None
    name = str(qmd_settings().get("index") or "atlas")
    cols = qmd_collections(name)
    return name if cols and all(c["path"].resolve() == VAULT.resolve() for c in cols.values()) else None


def qmd_areas_for(paths: list[str], types: dict) -> list[str]:
    """Which areas the vault-relative paths belong to, by the registry's globs."""
    return sorted({a for p in paths for a, globs in qmd_globs(types).items()
                   if any(glob_match(p.replace("\\", "/"), g) for g in globs)})


def glob_match(path: str, glob: str) -> bool:
    """Whether a registry glob names this path, as Path.glob finds it: `**/` may also stand for no folder."""
    return fnmatch.fnmatch(path, glob) or ("**/" in glob and fnmatch.fnmatch(path, glob.replace("**/", "")))


def _try_lock(name: str):
    """The lock, or None when another process holds it (no waiting)."""
    ensure_state()
    handle = open(STATE / name, "w", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:  # Windows
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except OSError:
        handle.close()
        return None


def qmd_sync() -> tuple[bool, str]:
    """Re-read and embed the vault's index, one run at a time. A request while a run holds the lock leaves a
    mark the run takes before it lets go, so no change waits for the next commit."""
    index = qmd_index()
    if not index:
        return True, "qmd is off for this vault"
    pending = STATE / "qmd.pending"
    ensure_state()
    pending.touch()
    runs, errors = 0, []
    while True:
        lock = _try_lock("qmd.lock")
        if lock is None:  # the holder finds the mark after it lets go, or a later run does
            return True, "a sync is running; it picks this change up when it is done" if not runs else \
                f"qmd: refreshed {index} ({runs} run(s)); a newer sync took over"
        try:
            while pending.exists():
                pending.unlink(missing_ok=True)
                runs += 1
                for step in (["update"], ["embed"]):
                    r = qmd(*step, index=index)
                    if r.returncode:
                        errors.append(f"qmd {step[0]} failed: {(r.stderr or r.stdout).strip()[-400:]}")
                        break
        finally:
            lock.close()
        if not pending.exists():
            break
    if errors:
        return False, "\n".join(errors)
    return True, f"qmd: refreshed {index} ({', '.join(f'atlas-{a}' for a, *_ in QMD_AREAS)})"


def qmd_refresh_after_commit(paths: list[str], types: dict) -> str | None:
    """Start `qmd sync` in the background when the commit touched an area, so the commit does not wait."""
    areas = qmd_areas_for(paths, types)
    if not areas or not qmd_index():
        return None
    ensure_state()
    log = open(STATE / "qmd-sync.log", "a", encoding="utf-8")
    kw = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--vault", str(VAULT), "qmd", "sync"],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
    return f"qmd: refreshing {', '.join(areas)} in the background (log: .atlas/qmd-sync.log)"


def cmd_qmd(args) -> None:
    if args.action == "off":
        qmd_set(enabled="off")
        print("qmd is off for this vault: search goes by words only. The index and QMD's models stay on "
              "this machine (`qmd --index <name> collection list` shows the index; `qmd setup` turns it on again)")
        return
    if args.action == "sync":
        ok, msg = qmd_sync()
        print(msg)
        if not ok:
            sys.exit(1)
        return
    name, cols = qmd_plan(Index().types)
    existing = qmd_collections(name)
    if args.action == "status":
        print(f"qmd: {'installed' if qmd_bin() else 'not installed'}; enabled: {qmd_state()}; index: {name}")
        for c in cols:
            print(f"  {c['name']}: {'ok' if c['name'] in existing else 'missing'}  ({c['mask']} in {c['path']})")
        return
    if not qmd_bin():  # setup
        sys.exit("qmd is not installed: `npm install -g @tobilu/qmd` (or bun), then run this again")
    for c in cols:
        if c["name"] not in existing:
            r = qmd("collection", "add", str(c["path"]), "--name", c["name"], "--mask", c["mask"], index=name)
            if r.returncode:
                sys.exit(f"qmd collection add {c['name']} failed: {(r.stderr or r.stdout).strip()}")
            qmd("context", "add", f"qmd://{c['name']}", c["context"], index=name)
        print(f"collection {c['name']} in index {name}: {c['mask']} in {c['path']}")
    qmd_set(enabled="on", index=name)
    print("embedding the collections now (the first run downloads QMD's models, about 2 GB) …")
    ok, msg = qmd_sync()
    print(msg)
    if not ok:
        qmd_set(enabled="off")
        sys.exit("search by meaning stays off until `engine/atlas.py qmd setup` succeeds")


# --------------------------------------------------------------------------- demo
#
# A demo vault to try Atlas with (app/demo/demo.yaml): notes on sleep, memory and learning, a sleep-app project
# and a thesis, written into the vault and committed in steps dated over the last days, so Home, the feed,
# the constellation's replay and the tour have something to show. The vault records what the demo wrote
# (.atlas-demo.json); `demo --remove` takes out every demo note the user has not changed since.

DEMO = APP.parent / "demo"
DEMO_MANIFEST = ".atlas-demo.json"


def _demo_text(text: str, today: dt.date, now: str) -> str:
    text = re.sub(r"\{\{day:(-?\d+)\}\}", lambda m: (today + dt.timedelta(days=int(m.group(1)))).isoformat(), text)
    return text.replace("{{now}}", now)


def _demo_commit(message: str, agent: str | None, paths: list[str], when: dt.datetime) -> bool:
    """Commit only these paths, dated `when`. False when git cannot commit (no user configured, …)."""
    env = git_env(GIT_AUTHOR_DATE=when.isoformat(), GIT_COMMITTER_DATE=when.isoformat())
    body = message + "\n\nAtlas-Demo: true" + (f"\nAtlas-Agent: {agent}" if agent else "")
    for cmd in (["add", "-A", "--", *paths], ["commit", "-q", "-m", body, "--", *paths]):
        done = subprocess.run(["git", "-C", str(VAULT), *cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        if done.returncode:
            print(f"(git {cmd[0]} failed: {(done.stderr or done.stdout).strip()[:200]}; the files are written, commit them yourself)")
            return False
    return True


def cmd_demo(args) -> None:
    """Load the demo notes into the vault, or take them out again (--remove)."""
    import yaml
    manifest = VAULT / DEMO_MANIFEST
    in_git = git("rev-parse", "--is-inside-work-tree").strip() == "true"
    now = dt.datetime.now().astimezone().replace(microsecond=0)
    if args.remove:
        if not manifest.exists():
            sys.exit(f"no demo in this vault ({DEMO_MANIFEST} is missing)")
        files = (json.loads(manifest.read_text(encoding="utf-8")) or {}).get("files", {})
        removed, kept = [], []
        for rel, digest in files.items():
            path = VAULT / rel
            if not path.exists():
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                kept.append(rel)  # the user changed it: theirs now
                continue
            path.unlink()
            removed.append(rel)
            folder = path.parent
            while folder != VAULT and not any(folder.iterdir()):  # folders only the demo used go too
                folder.rmdir()
                folder = folder.parent
        manifest.unlink()
        if in_git:
            _demo_commit("demo: removed", None, [*removed, DEMO_MANIFEST], now)
        print(f"demo removed: {len(removed)} notes")
        if kept:
            print("kept, because they changed since the demo wrote them (delete them yourself if you want):")
            for rel in kept:
                print(f"  {rel}")
        return
    if manifest.exists():
        sys.exit(f"the demo is already loaded ({DEMO_MANIFEST}); `atlas.py demo --remove` takes it out")
    demo = yaml.safe_load((DEMO / "demo.yaml").read_text(encoding="utf-8")) or {}
    plan, sources = demo.get("steps") or [], demo.get("files") or {}
    files, skipped, last = {}, [], now
    head = git("log", "-1", "--format=%cI").strip() if in_git else ""
    floor = dt.datetime.fromisoformat(head) if head else now - dt.timedelta(days=1)  # today's steps follow the install
    for i, step in enumerate(plan):
        day = now.date() + dt.timedelta(days=int(step["day"]))
        when = dt.datetime.combine(day, dt.time.fromisoformat(str(step["time"]))).astimezone()
        if when > now:  # nothing from the future, and nothing of today before the last real commit
            when = max(now - dt.timedelta(seconds=len(plan) - i), floor + dt.timedelta(seconds=i + 1))
        written = []
        for rel in step["paths"]:
            dst = VAULT / rel
            if dst.exists():  # never over the user's own notes
                skipped.append(rel)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(_demo_text(sources[rel], now.date(), now.isoformat()), encoding="utf-8")
            files[rel] = hashlib.sha256(dst.read_bytes()).hexdigest()
            written.append(rel)
        if in_git and written:
            in_git = _demo_commit(str(step["message"]), step.get("agent"), written, when)
            last = when
    manifest.write_text(json.dumps({"loaded": now.isoformat(), "files": files}, indent=1) + "\n", encoding="utf-8")
    if in_git:
        _demo_commit("demo: what the demo wrote, for `atlas.py demo --remove`", None, [DEMO_MANIFEST],
                     max(now, last + dt.timedelta(seconds=1)))
    print(f"demo loaded: {len(files)} notes over the last {-min(int(s['day']) for s in plan)} days"
          + (f"; skipped {len(skipped)} that already exist" if skipped else "")
          + ". Remove it with `atlas.py demo --remove` (the atlas-clean-demo skill).")


def cmd_tour(args) -> None:
    """Scaffold a tour of what changed since a moment and list the changed notes for the agent who writes it."""
    import yaml
    index = Index()
    since, until = _moment(args.since), _moment(args.until) or now_iso()
    ch = changes_between(index, since, until)
    rank = {t: i for i, t in enumerate(TOUR_ORDER)}
    arrived = sorted((p for p, s in ch["changed"].items() if s == "A"), key=lambda p: (rank.get(index.entities[p].type, 99), p))
    edited = sorted((p for p, s in ch["changed"].items() if s == "M"), key=lambda p: -ch["touches"][p])
    front = {"since": since, "until": until, "written_by": agent_id(args.agent), "stops": [], "mechanical": []}
    TOURS.mkdir(parents=True, exist_ok=True)
    path, n = TOURS / f"{dt.date.today().isoformat()}-since-{since[:10]}.md", 2
    while path.exists():
        path, n = TOURS / f"{dt.date.today().isoformat()}-since-{since[:10]}-{n}.md", n + 1
    day = lambda s: f"{dt.datetime.fromisoformat(s):%b} {dt.datetime.fromisoformat(s).day}" if re.match(r"\d{4}-\d{2}-\d{2}T", s) else s
    path.write_text("---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=1000) + "---\n\n"
                    f"# What changed since {day(since)}\n\nOne paragraph: the arc of the period, in your words.\n", encoding="utf-8")
    print(f"tour: {path.relative_to(VAULT).as_posix()}  ({len(arrived)} notes arrived, {len(edited)} changed, "
          f"{ch['distilled']} captures distilled)")
    print("Fill `stops` in reading order: {path, why, excerpt, look_closely?}; mechanical ones go to `mechanical`.")
    print("Atlas lists every changed note the tour leaves out, so pick what deserves a stop.\n")
    named = lambda e: e.id if e.title == Path(e.id).stem else f"{e.id}  —  {e.title[:100]}"
    print(f"Arrived ({len(arrived)}):")
    runs: dict[str, list[str]] = {}
    for p in arrived:
        e = index.entities[p]
        if e.type == "frame":  # a research run lands several documents: one line per run
            runs.setdefault(e.group or p, []).append(p)
        else:
            print(f"  A {e.type:<8} {named(e)}")
    for group, docs in runs.items():
        print(f"  A frame    {len(docs)} documents in {group}")
    print(f"\nChanged, most-touched first ({min(40, len(edited))} of {len(edited)}):")
    for p in edited[:40]:
        print(f"  M {index.entities[p].type:<8} ({ch['touches'][p]} commits) {named(index.entities[p])}")


# ---------------------------------------------------------------------------
# Sessions: agent sessions that worked in this vault, and whether /close covered them (#65)
# ---------------------------------------------------------------------------
# Claude Code and Codex keep a transcript of every session. The agent commands note the session
# they run in (~/.atlas/sessions.json, outside every vault); `close` records how far /close got.
# A session is open when it never closed, when the user wrote more after its close, or when
# anything happened after a checkpoint (an interim close after a compaction).

SESSIONS: Path | None = None  # tests point this elsewhere; None: ~/.atlas/sessions.json
SESSION_LIVE = dt.timedelta(minutes=15)  # a transcript touched this recently: the session probably still runs
SESSION_ENV = {"claude-code": ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID"),
               "codex": ("CODEX_THREAD_ID", "CODEX_SESSION_ID")}
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,63}$")
# wrappers the harnesses write into user turns; pasted text, images and typed shell input stay the user's
INJECTED = re.compile(
    r"<(task-notification|command-name|command-message|command-args|local-command-stdout|local-command-stderr|"
    r"local-command-caveat|bash-stdout|bash-stderr|system-reminder|artifact-view-context|user-prompt-submit-hook|"
    r"teammate-message|environment_context|user_instructions|user_action|turn_aborted|INSTRUCTIONS)[\s>]")
FOREVER = dt.datetime.max.replace(tzinfo=dt.timezone.utc)


def sessions_file() -> Path:
    return SESSIONS or Path.home() / ".atlas" / "sessions.json"


def current_session() -> tuple[str, str] | None:
    """(harness, session id) of the agent session this command runs in, from the harness's variables."""
    for harness, names in SESSION_ENV.items():
        for name in names:
            if os.environ.get(name):
                return harness, os.environ[name]
    return None


def load_sessions() -> dict:
    try:
        data = json.loads(sessions_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found = data.get("sessions") if isinstance(data, dict) else None
    return found if isinstance(found, dict) else {}


def save_sessions(sessions: dict) -> None:
    path = sessions_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"sessions": sessions}, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def note_session(agent: str | None) -> None:
    """Remember that the session this command runs in works in this vault. Writes only what is new."""
    found = current_session()
    if not found:
        return
    harness, sid = found
    sessions = load_sessions()
    entry = sessions.get(sid) or {}
    if entry.get("vault") == str(VAULT) and (entry.get("agent") or not agent):
        return
    sessions[sid] = {**entry, "harness": harness, "vault": str(VAULT), "first_seen": entry.get("first_seen") or now_iso(),
                     **({"agent": agent} if agent else {})}
    try:
        save_sessions(sessions)
    except OSError:
        pass  # bookkeeping: never fail an agent's command over it


def _when(value) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def _iso_utc(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds")


def transcript_path(harness: str, sid: str) -> Path | None:
    if not SESSION_ID.match(sid):
        return None
    home = Path.home()
    if harness == "codex":
        hits = sorted((home / ".codex" / "sessions").glob(f"*/*/*/rollout-*{sid}.jsonl"))
    else:
        hits = sorted((home / ".claude" / "projects").glob(f"*/{sid}.jsonl"))
    return hits[0] if hits else None


def _jsonl_lines(path: Path, wanted: tuple[str, ...]):
    """JSON objects of the lines holding one of `wanted` (both harnesses write compact JSON); transcripts run
    to hundreds of MB of request blobs, and the substring test skips those lines without decoding them."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if any(w in line for w in wanted):
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    yield obj


def _block_text(content, kinds: set[str]) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b["text"] for b in content or [] if isinstance(b, dict) and b.get("type") in kinds
                     and isinstance(b.get("text"), str)) if isinstance(content, list) else ""


def _injected(text: str) -> bool:
    s = text.lstrip()
    return not s or bool(INJECTED.match(s)) or s.startswith("# AGENTS.md instructions") or s.startswith("[Request interrupted")


def _tool_line(name, detail) -> str:
    """One line about a tool call, for the digest: its name and what it ran or touched."""
    if isinstance(detail, dict):
        detail = next((detail[k] for k in ("command", "cmd", "file_path", "path", "pattern", "url", "description")
                       if isinstance(detail.get(k), str)), json.dumps(detail, ensure_ascii=False))
    text = " ".join(str(detail or "").split())
    return f"{name or 'tool'}: {text[:200]}{'…' if len(text) > 200 else ''}"


def read_transcript(path: Path, harness: str) -> dict:
    """The user's and the agent's messages and the compaction summaries of a transcript, in order, and the
    times of every line (tool calls and results too: work without prose counts after a checkpoint)."""
    entries: list[tuple[dt.datetime | None, str, str]] = []
    activity: list[dt.datetime] = []
    title = None
    if harness == "codex":
        for obj in _jsonl_lines(path, ('"type":"compacted"', '"type":"response_item"')):
            p, at = obj.get("payload") or {}, _when(obj.get("timestamp"))
            if not isinstance(p, dict):
                continue
            if at and obj.get("type") == "response_item":
                activity.append(at)
            if obj.get("type") == "compacted" and isinstance(p.get("message"), str) and p["message"].strip():
                entries.append((at, "summary", p["message"]))
            elif p.get("type") == "message" and p.get("role") == "user":
                text = _block_text(p.get("content"), {"input_text"})
                if not _injected(text):
                    entries.append((at, "user", text))
            elif p.get("type") == "message" and p.get("role") == "assistant":
                text = _block_text(p.get("content"), {"output_text"})
                if text.strip():
                    entries.append((at, "agent", text))
            elif str(p.get("type", "")).endswith("_call"):
                entries.append((at, "tool", _tool_line(p.get("name"), p.get("input") or p.get("arguments"))))
    else:
        for obj in _jsonl_lines(path, ('"type":"user"', '"type":"assistant"', '"type":"ai-title"')):
            if obj.get("isSidechain"):
                continue
            if obj.get("type") == "ai-title" and obj.get("aiTitle"):
                title = str(obj["aiTitle"])
                continue
            at, content = _when(obj.get("timestamp")), (obj.get("message") or {}).get("content")
            if at:
                activity.append(at)
            text = _block_text(content, {"text"})
            if obj.get("type") == "assistant":
                if text.strip():
                    entries.append((at, "agent", text))
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        entries.append((at, "tool", _tool_line(b.get("name"), b.get("input"))))
            elif obj.get("type") == "user" and obj.get("isCompactSummary"):
                if text.strip():
                    entries.append((at, "summary", text))
            elif obj.get("type") == "user" and not obj.get("isMeta") and not _injected(text):
                entries.append((at, "user", text))
    times = [*activity, *(e[0] for e in entries if e[0])]
    return {"entries": entries, "activity": activity, "title": title, "started": min(times, default=None),
            "last": max(times, default=None), "users": sum(1 for e in entries if e[1] == "user")}


def session_cover(entry: dict) -> tuple[dt.datetime, bool] | None:
    """How far the newest close, checkpoint or skip reaches: (time, is a checkpoint). A summary beats a tie."""
    marks = []
    if _when(entry.get("closed_at")):
        marks.append((_when(entry["closed_at"]), False))
    if _when(entry.get("checkpoint_at")):
        marks.append((_when(entry["checkpoint_at"]), True))
    if entry.get("skipped"):
        marks.append((_when(entry["skipped"].get("through")) or FOREVER, False))
    return max(marks, key=lambda m: (m[0], not m[1]), default=None)


def needs_catch_up(scan: dict, cover: tuple[dt.datetime, bool] | None) -> bool:
    """After a close only the user's words count (the agent finishing its close adds nothing to catch
    up); after a checkpoint everything does, because the work went on."""
    if cover is None:
        return True
    at, checkpoint = cover
    if at == FOREVER:
        return False
    if checkpoint:
        return any(when > at for when in scan.get("activity") or [w for w, _, _ in scan["entries"] if w])
    return any(when and when > at and kind == "user" for when, kind, _ in scan["entries"])


def open_sessions(current: str | None = None, now: dt.datetime | None = None) -> list[dict]:
    """Earlier sessions in this vault that ended without /close, newest first. Leaves out the current
    session, sessions still running, and sessions in which the user wrote nothing."""
    now = now or dt.datetime.now(dt.timezone.utc)
    out = []
    for sid, entry in load_sessions().items():
        if not isinstance(entry, dict) or sid == current or entry.get("vault") != str(VAULT):
            continue
        path = transcript_path(entry.get("harness", ""), sid)
        if path is None:
            continue
        touched = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
        cover = session_cover(entry)
        if now - touched < SESSION_LIVE or (cover and not cover[1] and touched <= cover[0]):
            continue  # still running, or closed after its last write: no need to read it
        scan = read_transcript(path, entry.get("harness", ""))
        if not scan["users"] or not scan["last"] or now - scan["last"] < SESSION_LIVE:
            continue
        if needs_catch_up(scan, cover):
            out.append({"id": sid, "harness": entry.get("harness"), "agent": entry.get("agent"), "path": path,
                        "cover": cover, **scan})
    return sorted(out, key=lambda s: s["last"], reverse=True)


def _local_time(moment: dt.datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return moment.astimezone().strftime(fmt) if moment else "?"


def _session_label(s: dict) -> str:
    if s.get("title"):
        return s["title"]
    first = " ".join(next((t for _, k, t in s["entries"] if k == "user"), "").split())
    return first[:60] + ("…" if len(first) > 60 else "")


def session_lines(items: list[dict], limit: int = 5) -> list[str]:
    lines = []
    for s in items[:limit]:
        start, end = _local_time(s["started"], "%Y-%m-%d"), _local_time(s["last"], "%Y-%m-%d")
        if s["cover"] is None:
            state = f"{s['users']} user message(s), never closed"
        elif s["cover"][1]:
            state = f"work went on after the checkpoint of {_local_time(s['cover'][0])}"
        else:
            later = sum(1 for when, kind, _ in s["entries"] if kind == "user" and when and when > s["cover"][0])
            state = f"{later} user message(s) after the close of {_local_time(s['cover'][0])}"
        lines.append(f"- {start if start == end else start + ' → ' + end} · {s['id']} · \"{_session_label(s)}\" · {state}")
    if len(items) > limit:
        lines.append(f"- … and {len(items) - limit} more: `engine/atlas.py sessions`")
    lines.append("Catch up before new work (skill atlas-project, Catch up): `engine/atlas.py sessions digest <id>`, the "
                 "/close steps for what it shows, then the `close` command the digest prints. Nothing to keep: "
                 "`engine/atlas.py sessions skip <id> --reason \"…\"`.")
    return lines


DIGEST_CAPS = {"user": 1500, "agent": 600, "tool": 300, "summary": 8000}


def session_digest(sid: str, entry: dict, scan: dict, path: Path, max_chars: int, everything: bool) -> str:
    """A transcript, compactly, for catching it up: only what came after its close unless `everything`. Over
    budget the oldest tool lines go first, then agent messages, then user messages, then all compaction
    summaries but the newest, which is cut to fit last."""
    cover = None if everything else session_cover(entry)
    since = cover[0] if cover and cover[0] != FOREVER else None
    blocks = []
    for when, kind, text in scan["entries"]:
        if since and when and when <= since:
            continue
        text = text.strip()
        if len(text) > DIGEST_CAPS[kind]:
            text = text[:DIGEST_CAPS[kind]] + " […]"
        blocks.append([kind, f"[{_local_time(when)}] {kind.capitalize()}: {text}"])
    size = lambda: sum(len(b[1]) + 2 for b in blocks)
    summaries = [b for b in blocks if b[0] == "summary"]
    newest = summaries[-1] if summaries else None
    omitted = 0
    for drop in ("tool", "agent", "user", "summary"):
        i = 0
        while size() > max_chars and i < len(blocks):
            if blocks[i][0] == drop and blocks[i] is not newest:
                del blocks[i]
                omitted += 1
            else:
                i += 1
    if size() > max_chars and blocks:
        keep = max(0, max_chars - (size() - len(blocks[-1][1])) - 8)
        blocks[-1][1] = blocks[-1][1][:keep] + " […]"
    agent = entry.get("agent") or "<id>"
    head = [f"Session {sid} ({entry.get('harness')}), agent {agent}", f"Transcript: {path}",
            f"Span: {_local_time(scan['started'])} → {_local_time(scan['last'])}"]
    if scan.get("title"):
        head.append(f"Title: {scan['title']}")
    if since:
        head.append(f"Closed until {_local_time(since)}; this shows what came after.")
    if omitted:
        head.append(f"{omitted} older message(s) left out to fit {max_chars} characters (`--max-chars`, `--all`).")
    cut = f" --covered-until {_iso_utc(scan['last'])}" if scan["last"] else ""
    head.append(f"When its /close steps are done: `engine/atlas.py close --agent {agent} --session {sid}{cut}`")
    return "\n".join(head) + "\n\n" + "\n\n".join(b[1] for b in blocks) + "\n"


def cmd_close(args) -> None:
    """Record that /close covered a session: this one, or a caught-up one (`--session`)."""
    agent = agent_id(args.agent)
    note_session(agent)
    found = current_session()
    sid = args.session or (found[1] if found else None)
    if not sid:
        sys.exit("not inside a Claude Code or Codex session: name the session with --session <id>")
    until = _when(args.covered_until) if args.covered_until is not None else dt.datetime.now(dt.timezone.utc)
    if until is None:
        sys.exit(f"--covered-until is not an ISO time: {args.covered_until}")
    sessions = load_sessions()
    entry = sessions.get(sid) or {}
    if not entry.get("harness"):  # a session no agent command noted: find its transcript
        entry["harness"] = next((h for h in SESSION_ENV if transcript_path(h, sid)), found[0] if found else "claude-code")
    entry.setdefault("vault", str(VAULT))
    entry.setdefault("first_seen", now_iso())
    key = "checkpoint_at" if args.checkpoint else "closed_at"
    if not _when(entry.get(key)) or _when(entry[key]) < until:
        entry[key] = _iso_utc(until)
    sessions[sid] = entry
    save_sessions(sessions)
    print(f"{'checkpoint' if args.checkpoint else 'closed'}: {sid} until {_local_time(until)}")


def cmd_sessions(args) -> None:
    """List the sessions that ended without /close, print one compactly, or skip one."""
    current = current_session()
    if args.action == "list":
        items = open_sessions(current[1] if current else None)
        if args.json:
            print(json.dumps([{"id": s["id"], "harness": s["harness"], "agent": s["agent"], "path": str(s["path"]),
                               "label": _session_label(s), "last": _iso_utc(s["last"]), "user_messages": s["users"],
                               "covered_until": _iso_utc(s["cover"][0]) if s["cover"] else None,
                               "checkpoint": bool(s["cover"] and s["cover"][1])} for s in items], indent=2))
        elif items:
            print(f"{len(items)} earlier session(s) in this vault ended without /close:")
            print("\n".join(session_lines(items, limit=len(items))))
        else:
            print("No open sessions.")
        return
    if not args.id:
        sys.exit(f"sessions {args.action} needs a session id")
    sessions = load_sessions()
    entry = sessions.get(args.id) or {}
    harness = entry.get("harness") or next((h for h in SESSION_ENV if transcript_path(h, args.id)), None)
    path = transcript_path(harness, args.id) if harness else None
    if args.action == "skip":
        if not args.reason:
            sys.exit("sessions skip needs --reason")
        # the skip reaches as far as the session went; later user messages open it again
        through = read_transcript(path, harness)["last"] if path else None
        if through is None:  # a skip without a date would hide the session for good
            sys.exit(f"cannot read how far session {args.id} went: no transcript found, or it has no times")
        entry.update(harness=harness or entry.get("harness"), vault=entry.get("vault") or str(VAULT),
                     skipped={"reason": args.reason, "on": dt.date.today().isoformat(),
                              "through": _iso_utc(through)})
        sessions[args.id] = entry
        save_sessions(sessions)
        print(f"skipped: {args.id}")
        return
    if path is None:
        sys.exit(f"no transcript found for session {args.id}")
    print(session_digest(args.id, {**entry, "harness": harness}, read_transcript(path, harness), path,
                         args.max_chars, args.all), end="")


def cmd_hook(args) -> None:
    """SessionStart hook for Claude Code and Codex: the payload arrives on stdin. Prints hook JSON only
    when there is something to say: open sessions, or a checkpoint right after a compaction."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    sid = str(payload.get("session_id") or "")
    parts = []
    entry = load_sessions().get(sid) if sid else None
    if payload.get("source") == "compact" and isinstance(entry, dict) and entry.get("vault") == str(VAULT):
        agent = entry.get("agent") or "<id>"
        parts.append("Atlas: this session was just compacted. Before you continue, run the /close steps for what the "
                     "compaction summary covers (thread log lines, decisions, lessons, commit; skill atlas-project), "
                     f"then `uv run --no-project {APP / 'atlas.py'} close --agent {agent} --session {sid} --checkpoint`. "
                     "A checkpoint "
                     "is not a close: the session counts as open again once work goes on.")
    items = open_sessions(sid or None)
    if items:
        parts.append(f"Atlas ({VAULT.parent}): {len(items)} earlier session(s) ended without /close. Work from that "
                     "folder (its AGENTS.md):\n" + "\n".join(session_lines(items)))
    if parts:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "\n\n".join(parts)}}, ensure_ascii=False))


def cmd_status(args) -> None:
    s = session()
    url = f"http://localhost:{s['port']}" if s.get("port") else None
    print(json.dumps({**s, "url": url, "running": serving(url), "operator": operator_state(), "unread_for_agent":
                      max(0, len(read_jsonl(INBOX)) - (read_cursor() if CURSOR.exists() else 0))}))


def serving(url: str | None) -> bool:
    """Whether the server at `url` answers for this vault (another Atlas may have the port since)."""
    if not url:
        return False
    import urllib.request
    try:
        with urllib.request.urlopen(url + "/api/meta", timeout=2) as r:
            meta = json.loads(r.read())
    except (OSError, ValueError):
        return False
    path = meta.get("vault_path") if isinstance(meta, dict) else None  # another service may answer on the port
    try:
        return isinstance(path, str) and bool(path) and Path(path).resolve() == VAULT.resolve()
    except (OSError, ValueError):  # a path no file system takes ("\0")
        return False


def cmd_expose(args) -> None:
    wsl = "/mnt/c/Program Files/Tailscale/tailscale.exe"
    exe = shutil.which("tailscale") or (wsl if os.path.exists(wsl) else "tailscale")
    print("Expose Atlas on your tailnet only (not the internet). Run once, it persists:")
    print(f'  "{exe}" serve --bg {args.port}')
    print("Remove again with:")
    print(f'  "{exe}" serve --https=443 off')


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):  # Windows pipes default to cp1252: an emoji or umlaut would break
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--vault", dest="vault_sub", help="vault directory (default: ./vault next to engine/, or $ATLAS_VAULT)")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vault", dest="vault_top", help="vault directory (default: ./vault next to engine/, or $ATLAS_VAULT)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", parents=[common])
    s.add_argument("--operator", action="store_true", help="an agent session answers in the chat")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    w = sub.add_parser("wait", parents=[common])
    w.add_argument("--timeout", type=int, default=3300, help="seconds before giving up (then re-arm)")
    w.add_argument("--agent", help="your id (the file name in agents/): Atlas shows you by name, and several agents can listen")
    y = sub.add_parser("say", parents=[common])
    y.add_argument("text", help="message text, or - to read stdin")
    y.add_argument("--open", help="vault path Atlas should open for the user")
    y.add_argument("--agent", help="your id (the file name in agents/): the chat shows who answered")
    y.add_argument("--progress", action="store_true", help="a short status line while you work, not an answer")
    y.add_argument("--title", help='what you are doing now, e.g. "Researching loop engineering"; shown above the conversation')
    rc = sub.add_parser("recall", parents=[common], help="print the cabinet cards a text names (stdin or a Claude Code prompt hook)")
    rc.add_argument("text", nargs="*")
    mn = sub.add_parser("mentions", parents=[common], help="which notes a person or organization wrote or appears in")
    mn.add_argument("name", nargs="+")
    sub.add_parser("status", parents=[common])
    sub.add_parser("next", parents=[common])
    sub.add_parser("check", parents=[common])
    qp = sub.add_parser("qmd", parents=[common], help="search by meaning with QMD: setup, sync, status, off")
    qp.add_argument("action", choices=["setup", "sync", "status", "off"])
    bo = sub.add_parser("boot", parents=[common], help="the context an agent loads before working on a project")
    bo.add_argument("project", nargs="?", help="project slug, title or alias (omit for an overview)")
    bo.add_argument("--agent", required=True, help="your id: the file name in agents/ (claude, codex, ...)")
    bo.add_argument("--budget", type=int, default=12000, help="token budget (rules and decisions in force are never cut)")
    bo.add_argument("--checkout", help="use this checkout for this session instead of the mapped path")
    co = sub.add_parser("commit", parents=[common], help="stamp created_by/updated_by on the named paths and commit them")
    co.add_argument("--agent", required=True)
    co.add_argument("-m", "--message", required=True)
    co.add_argument("paths", nargs="+")
    dm = sub.add_parser("demo", parents=[common], help="load the demo notes into the vault, or take them out (--remove)")
    dm.add_argument("--remove", action="store_true", help="remove every demo note you have not changed")
    t = sub.add_parser("tour", parents=[common], help="scaffold a tour of what changed (tours/) and list the changed notes")
    t.add_argument("--since", required=True, help="date or timestamp, e.g. 2026-10-04")
    t.add_argument("--until", help="default: now")
    t.add_argument("--agent", required=True, help="your id: the file name in agents/ (claude, codex, ...)")
    sub.add_parser("machine", parents=[common])
    mp = sub.add_parser("map-path", parents=[common])
    mp.add_argument("project")
    mp.add_argument("dir")
    e = sub.add_parser("expose", parents=[common])
    e.add_argument("--port", type=int, default=DEFAULT_PORT)
    cl = sub.add_parser("close", parents=[common], help="record that /close covered this session (or --session <id>)")
    cl.add_argument("--agent", required=True, help="your id: the file name in agents/ (claude, codex, ...)")
    cl.add_argument("--session", help="a session caught up from another one (default: the one this runs in)")
    cl.add_argument("--covered-until", help="ISO time up to which /close covered it; `sessions digest` prints it (default: now)")
    cl.add_argument("--checkpoint", action="store_true", help="an interim close after a compaction, not the end")
    ss = sub.add_parser("sessions", parents=[common], help="sessions that ended without /close: list, digest <id>, skip <id>")
    ss.add_argument("action", nargs="?", default="list", choices=["list", "digest", "skip"])
    ss.add_argument("id", nargs="?")
    ss.add_argument("--json", action="store_true", help="list as JSON")
    ss.add_argument("--max-chars", type=int, default=24000, help="size limit for digest")
    ss.add_argument("--all", action="store_true", help="digest the whole transcript, also what a close covered")
    ss.add_argument("--reason", help="why the session needs no catch-up (for skip)")
    hk = sub.add_parser("hook", parents=[common], help="SessionStart hook for Claude Code and Codex (payload on stdin)")
    hk.add_argument("event", choices=["session-start"])
    args = ap.parse_args()
    set_vault(args.vault_sub or args.vault_top)
    if args.cmd != "expose" and not VAULT.is_dir():
        sys.exit(f"vault not found: {VAULT} (check --vault / $ATLAS_VAULT, or create the folder)")
    {"serve": cmd_serve, "wait": cmd_wait, "say": cmd_say, "status": cmd_status, "expose": cmd_expose,
     "next": cmd_next, "check": cmd_check, "boot": cmd_boot, "commit": cmd_commit, "machine": cmd_machine, "tour": cmd_tour,
     "demo": cmd_demo, "recall": cmd_recall, "mentions": cmd_mentions,
     "map-path": cmd_map_path, "qmd": cmd_qmd, "close": cmd_close, "sessions": cmd_sessions, "hook": cmd_hook}[args.cmd](args)


if __name__ == "__main__":
    main()
