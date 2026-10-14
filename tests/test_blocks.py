"""Answer blocks in the chat (#20)."""

from __future__ import annotations


def kinds(engine, text: str) -> list[str]:
    return [b["kind"] for b in engine.render_agent_message(engine.Index(), text)]


def test_a_block_left_open_at_the_end_is_closed(engine, vault):
    # both research answers in the guided run ended with ```atlas:choices and no closing fence (#20)
    text = "Done.\n```atlas:choices\noptions:\n  - Distill it\n  - Dig deeper\n"
    assert kinds(engine, text) == ["md", "choices"]


def test_closed_blocks_stay_as_they_are(engine, vault):
    text = "Done.\n```atlas:choices\noptions: [A, B]\n```\nAnd then some words."
    assert kinds(engine, text) == ["md", "choices", "md"]


def test_after_a_closed_block_an_open_last_one_is_closed_too(engine, vault):
    text = "```atlas:choices\noptions: [A]\n```\nNext:\n```atlas:choices\noptions: [B, C]\n"
    assert kinds(engine, text) == ["choices", "md", "choices"]


def test_a_plain_code_block_left_open_is_not_touched(engine, vault):
    text = "Here is code:\n```python\nprint(1)\n"
    assert kinds(engine, text) == ["md"]
