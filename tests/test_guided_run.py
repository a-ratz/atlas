"""What the guided run's operators found (#24)."""

from __future__ import annotations

import json

import pytest

from conftest import APP


def project(vault, slug: str, meta: str) -> None:
    folder = vault / "projects" / "private" / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project.md").write_text(f"---\n{meta}---\n\n# {slug}\n", encoding="utf-8")


def test_a_project_without_code_says_so(engine, vault):
    # boot warned "checkout unmapped" for a project from a spec that had no repository yet (#24)
    project(vault, "terrain", "status: active\n")
    index = engine.Index()
    co = engine.resolve_checkout(index.entities["projects/private/terrain/project.md"])
    assert co["status"] == "no code" and "map-path terrain" in co["hint"]
    project(vault, "kettle", "status: active\nrepo: https://example.org/kettle\n")
    co = engine.resolve_checkout(engine.Index().entities["projects/private/kettle/project.md"])
    assert co["status"] == "unmapped"  # a repository that is not checked out here is still a warning


def test_a_second_atlas_on_the_same_vault_stops(engine, vault, monkeypatch):
    # a second server overwrote session.json and the first, in operator mode, turned standalone (#24)
    engine.ensure_state()
    engine.SESSION.write_text(json.dumps({"mode": "operator", "port": 8765, "pid": 1}), encoding="utf-8")
    monkeypatch.setattr(engine, "port_free", lambda host, port: True)
    monkeypatch.setattr(engine, "serving", lambda url: url == "http://localhost:8765")
    args = type("A", (), {"host": "127.0.0.1", "port": 8799, "operator": False})()
    with pytest.raises(SystemExit) as stop:
        engine.cmd_serve(args)
    assert "already runs for this vault at http://localhost:8765" in str(stop.value)
    assert json.loads(engine.SESSION.read_text(encoding="utf-8"))["mode"] == "operator"  # untouched


def test_the_idea_skills_answer_what_the_operators_asked():
    skills = APP / ".agents" / "skills"
    sketch = (skills / "atlas-sketch" / "SKILL.md").read_text(encoding="utf-8")
    spec = (skills / "atlas-spec" / "SKILL.md").read_text(encoding="utf-8")
    proj = (skills / "atlas-project" / "SKILL.md").read_text(encoding="utf-8")
    assert "the red-team's answer on this idea" in sketch and "A read is a note read in" in sketch
    assert "the rules they test" in spec and "prior art, not a question" in spec
    assert "when prior art exists" not in spec  # the hand-over follows the same rule (#25, review round 1)
    assert "No code yet" in proj
