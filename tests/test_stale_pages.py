"""Open pages follow their note (#13): a note the agent moved points to its new place."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_a_moved_note_says_where_it_went(engine, vault):
    (vault / "captures").mkdir(exist_ok=True)
    (vault / "sources").mkdir(exist_ok=True)
    (vault / "sources" / "octopus-field-notes.md").write_text("---\ntitle: Octopus field notes\n---\n\nBody\n", encoding="utf-8")
    client = TestClient(engine.make_app(engine.Index()), base_url="http://127.0.0.1")
    gone = client.get("/api/entity", params={"id": "captures/octopus-field-notes.md"})
    assert gone.status_code == 404
    assert gone.json()["moved_to"] == "sources/octopus-field-notes.md"


def test_a_deleted_note_is_just_not_found(engine, vault):
    client = TestClient(engine.make_app(engine.Index()), base_url="http://127.0.0.1")
    gone = client.get("/api/entity", params={"id": "captures/never-there.md"})
    assert gone.status_code == 404 and "moved_to" not in gone.json()
