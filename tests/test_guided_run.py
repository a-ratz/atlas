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


def test_log_lines_carry_their_links(engine, vault):
    # "Where we left off" showed [[when-an-effect-reaches-along-a-line-check-the-whole-line]] as written (#27)
    (vault / "insights" / "Ice reaches along a line.md").write_text("---\ndescription: d\n---\n\n# Ice reaches along a line\n",
                                                                     encoding="utf-8")
    folder = vault / "projects" / "private" / "terrain" / "threads"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "slice.md").write_text("---\nstatus: open\n---\n\n# Slice\n\n## Log\n"
                                     "- 2026-10-14 (claude): stop rule fired, see [[Ice reaches along a line]].\n", encoding="utf-8")
    index = engine.Index()
    line = engine.thread_log(index.entities["projects/private/terrain/threads/slice.md"], index)[0]
    assert line["links"] == {"Ice reaches along a line": {"id": "insights/Ice reaches along a line.md",
                                                          "title": "Ice reaches along a line"}}


def run_inline(*cases) -> list[str]:
    """inline() from app.js, run in node on (text, links) pairs."""
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    js = (APP / "engine" / "static" / "app.js").read_text(encoding="utf-8")
    pieces = [re.search(p, js, re.S).group(0) for p in (
        r"const esc = .*?;\n", r"const enc = .*?;\n", r"const inlineText = .*?;\n(?=//)",
        r"const resolved = .*?;", r"function inline\(s, links\) \{.*?\n\}")]
    probe = "\n".join(pieces) + "\n" + "\n".join(
        f"console.log(inline({json.dumps(t)}, {json.dumps(links)}));" for t, links in cases)
    return subprocess.run([node, "-e", probe], capture_output=True, text=True, encoding="utf-8").stdout.splitlines()


def test_inline_keeps_code_and_ignores_inherited_names():
    # review round 1 on #28: `[[note]]` in a code span lost its formatting; [[constructor]] became an empty link
    out = run_inline(("Use `[[note]]` in the file", None),
                     ("see [[constructor]] and [[toString]]", {}),
                     ("see [[A note]], **now**", {"A note": {"id": "insights/a.md", "title": "A note"}}))
    assert out[0] == "Use <code>[[note]]</code> in the file"
    assert out[1] == "see constructor and toString"
    assert out[2] == 'see <a href="#/e/insights%2Fa.md">A note</a>, <b>now</b>'


def test_inline_links_with_backticks_and_bold_around_code():
    # review round 2 on #28: backticks inside a link split it; bold around a code span lost its delimiters
    links = {"Prefer `uv run` over bare Python": {"id": "insights/uv.md", "title": "Prefer `uv run` over bare Python"}}
    out = run_inline(("see [[Prefer `uv run` over bare Python]]", links),
                     ("**Use `git status` before continuing**", None),
                     ("`[[note]]` and [[note]]", {}),
                     ("https://x.test/[[note]] \u00010\u0002", {}))
    assert out[0] == 'see <a href="#/e/insights%2Fuv.md">Prefer `uv run` over bare Python</a>'
    assert out[1] == "<b>Use <code>git status</code> before continuing</b>"
    assert out[2] == "<code>[[note]]</code> and note"
    assert out[3] == '<a href="https://x.test/" target="_blank" rel="noopener">https://x.test/</a>note 0'
