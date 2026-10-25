"""The navigation shows projects as a tree under their groups (#67)."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient


def write_project(vault: Path, group: str, slug: str, title: str) -> None:
    folder = vault / "projects" / group / slug
    folder.mkdir(parents=True)
    (folder / "project.md").write_text(f"---\ntitle: {title}\nstatus: active\n---\n\n# {title}\n", encoding="utf-8")


def test_meta_names_every_group_of_a_project_with_the_title_of_its_group_note(engine, vault):
    write_project(vault, "work", "thesis", "Thesis")
    write_project(vault, "side", "garden", "Garden")  # a group without _group.md keeps its folder name
    meta = TestClient(engine.make_app(engine.Index()), base_url="http://127.0.0.1").get("/api/meta").json()
    assert meta["groups"] == [{"id": "side", "title": "side"}, {"id": "work", "title": "Work"}]
    assert {p["title"]: p["group"] for p in meta["projects"]} == {"Garden": "side", "Thesis": "work"}


def test_a_group_without_projects_is_no_node(engine, vault):
    write_project(vault, "work", "thesis", "Thesis")  # the template vault also has a "private" group note
    meta = TestClient(engine.make_app(engine.Index()), base_url="http://127.0.0.1").get("/api/meta").json()
    assert [g["id"] for g in meta["groups"]] == ["work"]
