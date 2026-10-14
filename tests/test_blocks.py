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


def test_a_quoted_example_html_lines_and_stray_returns(engine, vault):
    # round 3: a closed example in a blockquote swallowed the prose after it; an HTML-like line hid an open
    # block; a bare carriage return made the whole message an error (#21)
    quoted = "> ```atlas:choices\n> options: [A]\n> ```\nThat is all."
    blocks = engine.render_agent_message(engine.Index(), quoted)
    assert [b["kind"] for b in blocks] == ["md"] and "That is all." in blocks[0]["html"]
    assert kinds(engine, "<br>\n```atlas:choices\noptions: [A, B]\n")[-1] == "choices"
    assert kinds(engine, "Done.\rNext steps:\n```atlas:choices\noptions: [A, B]\n")[-1] == "choices"


def test_fences_are_followed_by_their_delimiter(engine, vault):
    # round 4: a backtick line inside an open ~~~ example flipped a parity count; an indented fence inside a
    # YAML label stopped the closing; an opener one to three spaces in was missed (#21)
    inside_tildes = "~~~text\n```\n```atlas:choices\noptions: [A]\n"
    blocks = engine.render_agent_message(engine.Index(), inside_tildes)
    assert [b["kind"] for b in blocks] == ["md"]
    yaml_label = "```atlas:choices\noptions:\n  - label: |\n      ```python\n      print(1)\n    send: run it\n"
    assert kinds(engine, yaml_label)[-1] == "choices"
    assert kinds(engine, "Pick:\n  ```atlas:choices\noptions: [A, B]\n")[-1] == "choices"
