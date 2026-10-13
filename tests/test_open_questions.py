"""Regression tests for the review findings of #4 (open questions), one per finding."""

from __future__ import annotations

from conftest import write_question
from starlette.testclient import TestClient


def test_check_flags_only_the_coldest_questions_past_the_cap(engine, vault):
    hot = [write_question(vault, f"Hot question {i}", raised=f"2026-10-0{i}", count="3") for i in range(1, 8)]
    cold_old = write_question(vault, "Cold and old", raised="2026-09-01")
    cold_new = write_question(vault, "Cold but newer", raised="2026-09-15")
    flagged = {n["id"] for n in engine.health(engine.Index())["notes"] if any("cap is 7" in i for i in n["issues"])}
    assert flagged == {cold_old, cold_new}
    assert not flagged & set(hot)


def test_resting_questions_do_not_count_against_the_cap(engine, vault):
    for i in range(7):
        write_question(vault, f"Open question {i}")
    write_question(vault, "Resting question", status="dormant")
    assert engine.health(engine.Index())["questions"] == 0


def test_a_non_finite_raised_count_falls_back_to_one(engine, vault):
    rel = write_question(vault, "Raised infinitely often", count=".inf")
    index = engine.Index()
    assert engine._raised(index.entities[rel]) == 1
    engine.health(index)  # used to raise OverflowError and take every page down


def test_a_registry_from_0_6_3_keeps_its_research_move_and_gets_the_new_ones(engine, vault):
    reg = vault / "atlas.yaml"
    text = reg.read_text(encoding="utf-8")
    start = text.index("  - id: question")
    end = text.index("  - id: sketch")
    old = ('  - id: question\n    label: Open question\n    plural: Open questions\n    section: Knowledge\n'
           '    globs: ["questions/*.md"]\n    fields: [status, raised]\n    status: status\n    date: raised\n'
           '    moves:\n      - {label: "🔎 Research this", send: "Research this open question, primary sources only"}\n\n')
    reg.write_text(text[:start] + old + text[end:], encoding="utf-8")
    moves = engine.Index().types["question"]["moves"]
    assert moves[0]["send"] == "Research this open question, primary sources only"
    assert [m["label"] for m in moves] == ["🔎 Research this", "🙅 Not interested", "⏸ Later"]


def test_meta_names_the_status_each_sidebar_count_counts(engine, vault):
    write_question(vault, "Open one")
    write_question(vault, "Resting one", status="dormant")
    write_question(vault, "Dropped one", status="dropped")
    client = TestClient(engine.make_app(engine.Index()), base_url="http://127.0.0.1")
    question = next(t for t in client.get("/api/meta").json()["types"] if t["id"] == "question")
    assert (question["count"], question["aside"]) == (1, 1)
    assert (question["count_status"], question["aside_status"]) == ("open", "dormant")
