"""Sessions that ended without /close (#65): noting them, telling open from closed, catching up, the hook."""

from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
DAY = NOW - dt.timedelta(days=1)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home folder of its own: transcripts live under it, never the real ones."""
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: path))
    return path


def stamp(moment: dt.datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def user(text: str, at: dt.datetime, **extra) -> dict:
    return {"type": "user", "timestamp": stamp(at), "message": {"role": "user", "content": text}, **extra}


def agent_says(text: str, at: dt.datetime) -> dict:
    return {"type": "assistant", "timestamp": stamp(at), "message": {"content": [{"type": "text", "text": text}]}}


def claude_transcript(home: Path, sid: str, objects: list[dict]) -> Path:
    path = home / ".claude" / "projects" / "-work-app" / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(o, separators=(",", ":")) + "\n" for o in objects), encoding="utf-8")
    last = max(dt.datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")) for o in objects if "timestamp" in o)
    os.utime(path, (last.timestamp(), last.timestamp()))
    return path


def session(engine, sid: str, *objects: dict, home: Path, harness: str = "claude-code", **entry) -> None:
    """A session the engine noted in this vault, with its transcript."""
    if objects:
        claude_transcript(home, sid, list(objects))
    sessions = engine.load_sessions()
    sessions[sid] = {"harness": harness, "vault": str(engine.VAULT), "agent": "claude",
                     "first_seen": stamp(DAY), **entry}
    engine.save_sessions(sessions)


def basic(start: dt.datetime) -> list[dict]:
    return [{"type": "ai-title", "aiTitle": "Parser fix"}, user("Please fix the parser", start),
            agent_says("Fixed the off-by-one.", start + dt.timedelta(minutes=1))]


def open_ids(engine, current: str | None = None) -> list[str]:
    return [s["id"] for s in engine.open_sessions(current)]


def run(engine, monkeypatch, capsys, *argv: str, stdin: str = "") -> str:
    monkeypatch.setattr(sys, "argv", ["atlas.py", "--vault", str(engine.VAULT), *argv])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    vault, sessions = engine.VAULT, engine.SESSIONS
    engine.main()
    engine.set_vault(vault)  # main() points the module at the vault again; keep the test's paths
    engine.SESSIONS = sessions
    return capsys.readouterr().out


# --- noting sessions -------------------------------------------------------------------------------

def test_an_agent_command_notes_its_session_once(engine, vault, home, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-claude-0001")
    engine.note_session("claude")
    first = engine.load_sessions()["sess-claude-0001"]
    engine.note_session("claude")

    assert first["harness"] == "claude-code"
    assert first["vault"] == str(vault)
    assert first["agent"] == "claude"
    assert engine.load_sessions()["sess-claude-0001"] == first


def test_outside_a_harness_nothing_is_noted(engine, vault, home):
    engine.note_session("claude")

    assert engine.load_sessions() == {}


# --- open or closed ------------------------------------------------------------------------------

def test_a_session_that_never_closed_is_open(engine, vault, home):
    session(engine, "sess-never-0001", *basic(DAY), home=home)

    items = engine.open_sessions()

    assert [s["id"] for s in items] == ["sess-never-0001"]
    assert items[0]["title"] == "Parser fix"
    assert items[0]["cover"] is None


def test_after_a_close_only_the_users_words_reopen(engine, vault, home):
    closed = stamp(DAY + dt.timedelta(minutes=5))
    session(engine, "sess-closed-001", *basic(DAY), agent_says("Pushed.", DAY + dt.timedelta(minutes=30)),
            home=home, closed_at=closed)
    session(engine, "sess-more-0001", *basic(DAY), user("one more thing", DAY + dt.timedelta(minutes=6)),
            home=home, closed_at=closed)

    assert open_ids(engine) == ["sess-more-0001"]


def test_work_after_a_checkpoint_reopens_until_a_close(engine, vault, home):
    session(engine, "sess-check-0001", *basic(DAY), agent_says("Implemented the rest.", DAY + dt.timedelta(minutes=40)),
            home=home, checkpoint_at=stamp(DAY + dt.timedelta(minutes=10)))
    assert open_ids(engine) == ["sess-check-0001"]
    assert "after the checkpoint" in "\n".join(engine.session_lines(engine.open_sessions()))

    sessions = engine.load_sessions()
    sessions["sess-check-0001"]["closed_at"] = stamp(DAY + dt.timedelta(minutes=45))
    engine.save_sessions(sessions)
    assert open_ids(engine) == []


def test_tool_work_after_a_checkpoint_reopens(engine, vault, home):
    tool = {"type": "assistant", "timestamp": stamp(DAY + dt.timedelta(minutes=30)),
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest"}}]}}
    result = {"type": "user", "timestamp": stamp(DAY + dt.timedelta(minutes=31)),
              "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "3 passed"}]}}
    session(engine, "sess-tools-0001", *basic(DAY), tool, result, home=home,
            checkpoint_at=stamp(DAY + dt.timedelta(minutes=10)))

    assert open_ids(engine) == ["sess-tools-0001"]


def test_the_digest_shows_tool_work(engine, vault, home, monkeypatch, capsys):
    tool = {"type": "assistant", "timestamp": stamp(DAY + dt.timedelta(minutes=30)),
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest -q"}}]}}
    session(engine, "sess-tooldig-01", *basic(DAY), tool, home=home, checkpoint_at=stamp(DAY + dt.timedelta(minutes=10)))

    out = run(engine, monkeypatch, capsys, "sessions", "digest", "sess-tooldig-01")

    assert "Tool: Bash: pytest -q" in out


def test_a_skip_reaches_as_far_as_the_session_went(engine, vault, home):
    session(engine, "sess-skip-00001", *basic(DAY), home=home,
            skipped={"reason": "a quick question", "through": stamp(DAY + dt.timedelta(minutes=1))})
    assert open_ids(engine) == []

    session(engine, "sess-skip-00002", *basic(DAY), user("back for real work", DAY + dt.timedelta(hours=4)), home=home,
            skipped={"reason": "a quick question", "through": stamp(DAY + dt.timedelta(minutes=1))})
    assert open_ids(engine) == ["sess-skip-00002"]


def test_current_running_foreign_and_empty_sessions_stay_out(engine, vault, home):
    session(engine, "sess-current-01", *basic(DAY), home=home)
    session(engine, "sess-running-01", *basic(NOW - dt.timedelta(minutes=3)), home=home)
    session(engine, "sess-other-vlt1", *basic(DAY), home=home, vault=str(vault.parent / "elsewhere"))
    session(engine, "sess-silent-001", agent_says("hello?", DAY), home=home)
    session(engine, "sess-gone-00001", home=home)  # its transcript was deleted

    assert open_ids(engine, current="sess-current-01") == []


def test_codex_transcripts_drop_what_codex_wrote_into_user_turns(engine, vault, home):
    sid = "01a12f70-e8f8-7e80-b793-ae386e5b315c"
    path = home / ".codex" / "sessions" / "2026" / "10" / "16" / f"rollout-2026-10-16T10-00-00-{sid}.jsonl"
    path.parent.mkdir(parents=True)
    lines = [{"timestamp": stamp(DAY), "type": "session_meta", "payload": {"id": sid, "originator": "codex-tui"}}]
    for i, (role, text) in enumerate([("user", "# AGENTS.md instructions\n..."), ("user", "<environment_context>x"),
                                      ("user", "<task>Review the PR</task>"), ("assistant", "Two findings.")]):
        kind = "input_text" if role == "user" else "output_text"
        lines.append({"timestamp": stamp(DAY + dt.timedelta(minutes=i)), "type": "response_item",
                      "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]}})
    path.write_text("".join(json.dumps(o, separators=(",", ":")) + "\n" for o in lines), encoding="utf-8")
    os.utime(path, (DAY.timestamp() + 300, DAY.timestamp() + 300))
    session(engine, sid, home=home, harness="codex")

    items = engine.open_sessions()

    assert [s["id"] for s in items] == [sid]
    assert [(k, t) for _, k, t in items[0]["entries"]] == [("user", "<task>Review the PR</task>"),
                                                           ("agent", "Two findings.")]


# --- catching up ---------------------------------------------------------------------------------

def test_the_digest_shows_what_came_after_the_close_and_names_the_cutoff(engine, vault, home, monkeypatch, capsys):
    session(engine, "sess-digest-001", *basic(DAY), user("and the docs too", DAY + dt.timedelta(hours=2)),
            home=home, closed_at=stamp(DAY + dt.timedelta(minutes=5)))

    out = run(engine, monkeypatch, capsys, "sessions", "digest", "sess-digest-001")

    assert "Please fix the parser" not in out
    assert "and the docs too" in out
    cutoff = engine._iso_utc(DAY + dt.timedelta(hours=2))
    assert f"close --agent claude --session sess-digest-001 --covered-until {cutoff}" in out


def test_the_digest_stays_within_its_limit(engine, vault, home):
    scan = {"entries": [(DAY + dt.timedelta(minutes=i), "summary", f"summary {i} " + "x" * 8000) for i in range(4)],
            "title": None, "started": DAY, "last": DAY + dt.timedelta(minutes=3), "users": 0}

    out = engine.session_digest("sess-long-0001", {"harness": "claude-code"}, scan, Path("t.jsonl"), 1000, False)

    body = out.split("\n\n", 1)[1]
    assert len(body) <= 1100 and "summary 3" in body and "summary 0" not in body


def test_close_records_this_session_and_a_caught_up_one(engine, vault, home, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-here-00001")
    (vault / "agents").mkdir(exist_ok=True)

    run(engine, monkeypatch, capsys, "close", "--agent", "claude")
    run(engine, monkeypatch, capsys, "close", "--agent", "claude", "--checkpoint")
    run(engine, monkeypatch, capsys, "close", "--agent", "claude", "--session", "sess-older-0001",
        "--covered-until", "2026-10-16T08:00:00Z")

    sessions = engine.load_sessions()
    assert engine._when(sessions["sess-here-00001"]["closed_at"]) <= dt.datetime.now(dt.timezone.utc)
    assert "checkpoint_at" in sessions["sess-here-00001"]
    assert sessions["sess-older-0001"]["closed_at"].startswith("2026-10-16T08:00:00")
    for bad in ("yesterday", ""):
        with pytest.raises(SystemExit):
            run(engine, monkeypatch, capsys, "close", "--agent", "claude", "--covered-until", bad)


def test_skip_from_the_command_line(engine, vault, home, monkeypatch, capsys):
    session(engine, "sess-cli-skip01", *basic(DAY), home=home)

    run(engine, monkeypatch, capsys, "sessions", "skip", "sess-cli-skip01", "--reason", "a quick question")

    assert open_ids(engine) == []
    assert engine.load_sessions()["sess-cli-skip01"]["skipped"]["reason"] == "a quick question"
    with pytest.raises(SystemExit):  # without its transcript the skip would have no end
        run(engine, monkeypatch, capsys, "sessions", "skip", "sess-missing-01", "--reason", "typo")


# --- where open sessions show --------------------------------------------------------------------

def test_next_and_boot_point_at_open_sessions(engine, vault, home, monkeypatch, capsys):
    session(engine, "sess-show-00001", *basic(DAY), home=home)

    tips = engine.suggestions(engine.Index())
    out = run(engine, monkeypatch, capsys, "boot", "--agent", "claude")

    assert any("ended without /close" in t for t in tips)
    assert "## Sessions that ended without /close (1)" in out and "sess-show-00001" in out


def test_the_hook_lists_open_sessions_and_asks_for_a_checkpoint_after_a_compaction(engine, vault, home, monkeypatch,
                                                                                  capsys):
    session(engine, "sess-earlier-01", *basic(DAY), home=home)
    session(engine, "sess-compact-01", *basic(DAY), home=home)

    out = run(engine, monkeypatch, capsys, "hook", "session-start",
              stdin=json.dumps({"session_id": "sess-compact-01", "source": "compact"}))

    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "just compacted" in context and "close --agent claude --session sess-compact-01 --checkpoint" in context
    listed = context.split("ended without /close", 1)[1]
    assert "sess-earlier-01" in listed and "sess-compact-01" not in listed


def test_the_hook_is_silent_when_there_is_nothing_to_say(engine, vault, home, monkeypatch, capsys):
    out = run(engine, monkeypatch, capsys, "hook", "session-start",
              stdin=json.dumps({"session_id": "sess-unknown-01", "source": "compact"}))

    assert out == ""


# --- installing the hook -------------------------------------------------------------------------

@pytest.fixture
def installer(tmp_path, monkeypatch, home):
    spec = importlib.util.spec_from_file_location("atlas_installer", ROOT / "skills" / "atlas" / "scripts" / "atlas_install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    atlas = tmp_path / "Atlas"
    (atlas / "engine").mkdir(parents=True)
    (atlas / "engine" / "atlas.py").write_text("", encoding="utf-8")
    (atlas / "AGENTS.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(mod, "load_cfg", lambda: {"home": str(atlas)})
    return mod


def test_install_twice_then_remove_keeps_every_other_hook(installer, home):
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir()
    other = {"model": "x", "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "bash mine.sh"}]}],
                                     "Stop": [{"hooks": [{"type": "command", "command": "bash stop.sh"}]}]}}
    settings.write_text(json.dumps(other), encoding="utf-8")
    (home / ".codex").mkdir()

    installer.hooks("install", None)
    installer.hooks("install", None)  # the command carries a quoted path: it must still be found as ours
    groups = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
    codex = json.loads((home / ".codex" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["SessionStart"]

    assert len(groups) == 2 and groups[0] == other["hooks"]["SessionStart"][0]
    assert groups[1]["hooks"][0]["command"].endswith("hook session-start")
    assert len(codex) == 1 and codex[0]["matcher"] == "startup|resume|compact"

    installer.hooks("remove", None)
    assert json.loads(settings.read_text(encoding="utf-8")) == other
    assert json.loads((home / ".codex" / "hooks.json").read_text(encoding="utf-8")) == {}


def test_settings_that_are_not_plain_json_are_left_alone(installer, home):
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text("{ // my comment\n}", encoding="utf-8")

    with pytest.raises(SystemExit):
        installer.hooks("install", "claude-code")
    assert settings.read_text(encoding="utf-8") == "{ // my comment\n}"
