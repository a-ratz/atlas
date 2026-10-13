"""Open pages follow their note (#13): a note the agent moved points to its new place."""

from __future__ import annotations

import os
import shutil

from starlette.testclient import TestClient


def entity(engine, index, rel):
    return TestClient(engine.make_app(index), base_url="http://127.0.0.1").get("/api/entity", params={"id": rel})


def test_a_moved_note_says_where_it_went(engine, vault):
    (vault / "captures").mkdir(exist_ok=True)
    (vault / "sources").mkdir(exist_ok=True)
    (vault / "captures" / "octopus-field-notes.md").write_text("---\ntitle: Octopus field notes\n---\n\nBody\n",
                                                                 encoding="utf-8")
    index = engine.Index()
    (vault / "captures" / "octopus-field-notes.md").rename(vault / "sources" / "octopus-field-notes.md")
    index.refresh(force=True)
    gone = entity(engine, index, "captures/octopus-field-notes.md")
    assert gone.status_code == 404
    assert gone.json()["moved_to"] == "sources/octopus-field-notes.md"


def test_a_deleted_project_is_no_move_to_another(engine, vault):
    # every project is project.md: a basename match sent the reader to an unrelated project (#14, review round 1)
    for slug in ("lamp", "kettle"):
        (vault / "projects" / "private" / slug).mkdir(parents=True, exist_ok=True)
        (vault / "projects" / "private" / slug / "project.md").write_text(f"---\nstatus: active\n---\n\n# {slug}\n",
                                                                          encoding="utf-8")
    index = engine.Index()
    shutil.rmtree(vault / "projects" / "private" / "lamp")
    index.refresh(force=True)
    gone = entity(engine, index, "projects/private/lamp/project.md")
    assert gone.status_code == 404 and "moved_to" not in gone.json()


def test_rev_tells_two_writes_in_one_second_apart(engine, vault):
    # `modified` has whole seconds: a rewrite within the same second left the old body on screen (#14, round 1)
    note = vault / "insights" / "Octopuses hide in under a second.md"
    note.write_text("---\ndescription: d\nconfidence: working\n---\n\n# Octopuses hide in under a second\n",
                    encoding="utf-8")
    rel = "insights/Octopuses hide in under a second.md"
    os.utime(note, (1_800_000_000.25, 1_800_000_000.25))
    index = engine.Index()
    first = entity(engine, index, rel).json()
    os.utime(note, (1_800_000_000.75, 1_800_000_000.75))
    index.refresh(force=True)
    second = entity(engine, index, rel).json()
    assert first["modified"] == second["modified"] and first["rev"] != second["rev"]
