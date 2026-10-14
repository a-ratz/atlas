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


def test_crlf_answers_keep_their_text(engine, vault):
    # with CRLF a closed block looked open, and the prose after it disappeared into it (#21, review round 1)
    text = "```atlas:choices\r\noptions: [A, B]\r\n```\r\nAnd then some words.\r\n"
    assert kinds(engine, text) == ["choices", "md"]


def test_an_opener_quoted_in_another_code_block_stays_quoted(engine, vault):
    # an unfinished example inside ~~~ or four backticks became an empty choices block (#21, round 1)
    for fence in ("~~~", "````"):
        text = f"Write it like this:\n{fence}text\n```atlas:choices\noptions: [A]\n{fence}\nThat is all."
        blocks = engine.render_agent_message(engine.Index(), text)
        assert [b["kind"] for b in blocks] == ["md"] and "That is all." in blocks[0]["html"], fence


def test_indented_code_and_inline_spans_are_not_fences(engine, vault):
    # an indented ```python example or an inline ```python``` span hid the open choices at the end (#21, round 2)
    for before in ("    ```python\n    print(1)\n", "Use ```python``` for code.\n"):
        text = before + "\n```atlas:choices\noptions: [A, B]\n"
        assert kinds(engine, text)[-1] == "choices", before
