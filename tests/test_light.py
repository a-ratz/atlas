"""`atlas.py light` (#63): which notes it finds, what it reports, and the chat record the constellation reads."""

from __future__ import annotations

import argparse
import io
import json

import pytest


def note(vault, rel: str, title: str, front: str = "description: d") -> str:
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    (vault / rel).write_text(f"---\n{front}\n---\n\n# {title}\n", encoding="utf-8")
    return rel


@pytest.fixture
def notes(vault):
    return {
        "spacing": note(vault, "insights/spacing-beats-massing.md", "Spaced practice beats massed practice"),
        "sleep": note(vault, "insights/sleep-protects-new-facts.md", "Sleep protects new facts"),
        "sketch": note(vault, "sketches/nightlight.md", "Nightlight", "status: raw"),
        "person": note(vault, "cabinet/people/ada-lovelace.md", "Ada Lovelace", "kind: person"),
    }


def light(engine, monkeypatch, capsys, *names: str, stdin: str = "", say: str | None = None):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    engine.cmd_light(argparse.Namespace(title="Sleep and memory", notes=list(names), say=say, agent=None))
    records = [json.loads(line) for line in engine.OUTBOX.read_text(encoding="utf-8").splitlines()]
    return records[-1], capsys.readouterr().out


def test_paths_names_titles_and_stdin_all_resolve(engine, vault, notes, monkeypatch, capsys):
    monkeypatch.chdir(vault.parent)
    rec, out = light(engine, monkeypatch, capsys,
                     "vault/insights/spacing-beats-massing.md",  # from the Atlas folder
                     str(vault / notes["sleep"]),  # absolute
                     "-", stdin="[[nightlight]]\n\nSpaced practice beats massed practice\n")  # a wiki link; a title (a repeat)
    assert rec["light"]["ids"] == [notes["spacing"], notes["sleep"], notes["sketch"]]
    assert rec["light"]["kinds"] == ["insight", "sketch"]  # the constellation shows hidden kinds it needs
    assert rec["light"]["name"] == "sleep-and-memory" and rec["light"]["title"] == "Sleep and memory"
    assert rec["role"] == "agent" and rec["text"] == "Lit 3 notes: Sleep and memory."
    assert "lit 3 notes: Sleep and memory (#/graph?light=sleep-and-memory)" in out


def test_it_names_what_it_could_not_light(engine, vault, notes, monkeypatch, capsys):
    rec, out = light(engine, monkeypatch, capsys, "spacing-beats-massing", "insights/nope.md", "nope", "ada-lovelace",
                     say="The strongest technique.")
    assert rec["light"]["ids"] == [notes["spacing"]] and rec["text"] == "The strongest technique."
    assert "not found: insights/nope.md" in out and "not found: nope" in out
    assert "not in the constellation (person): cabinet/people/ada-lovelace.md" in out


def test_a_missing_path_does_not_fall_back_to_a_namesake(engine, vault, notes, monkeypatch, capsys):
    """`sketches/sleep-protects-new-facts.md` does not exist: lighting the insight of that name would be a guess."""
    note(vault, "insights/other.md", "Other")
    rec, out = light(engine, monkeypatch, capsys, "sketches/sleep-protects-new-facts.md", "other")
    assert rec["light"]["ids"] == ["insights/other.md"] and "not found: sketches/sleep-protects-new-facts.md" in out


def test_nothing_to_light_exits_without_a_message(engine, vault, notes, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as err:
        engine.cmd_light(argparse.Namespace(title="People", notes=["ada-lovelace", "ghost"], say=None, agent=None))
    assert "nothing to light" in str(err.value)
    assert not engine.OUTBOX.exists() or not engine.OUTBOX.read_text(encoding="utf-8").strip()
