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
                     ("https://x.test/[[note]] \u00010\u0002", {}),
                     ("`**/*.py` and **run tests**, `https://x.test`", None))
    assert out[0] == 'see <a href="#/e/insights%2Fuv.md">Prefer `uv run` over bare Python</a>'
    assert out[1] == "<b>Use <code>git status</code> before continuing</b>"
    assert out[2] == "<code>[[note]]</code> and note"
    assert out[3] == '<a href="https://x.test/" target="_blank" rel="noopener">https://x.test/</a>note 0'
    # round 3: code stays literal; bold and URLs do not reach inside it
    assert out[4] == "<code>**/*.py</code> and <b>run tests</b>, <code>https://x.test</code>"


@pytest.mark.parametrize("before, after", [
    ("", "paths:\n  laptop: /code/terrain\n"),
    ("paths:\n", "paths:\n  laptop: /code/terrain\n"),
    ("paths: {}\n", "paths:\n  laptop: /code/terrain\n"),
    ("paths: {desk: /d/terrain}\n", "paths:\n  desk: /d/terrain\n  laptop: /code/terrain\n"),
    ("paths:\n  desk: /d/terrain\n  laptop: /old\n\n", "paths:\n  desk: /d/terrain\n  laptop: /code/terrain\n\n"),
])
def test_map_path_changes_only_the_paths_entry(engine, vault, before, after):
    # map-path dumped the whole frontmatter back through YAML: flow lists became blocks, quotes changed (#29)
    keep_top = 'status: active\ntags: [game, roguelike]\nsource: "[[terrain-only-spec]]"\n'
    keep_end = "next: 'step 5'  # a comment\n"
    project(vault, "terrain", keep_top + before + keep_end)
    note = vault / "projects/private/terrain/project.md"
    front = keep_top + keep_end + after if not before else keep_top + after + keep_end  # a new key goes last
    engine._set_front_path(note, "laptop", "/code/terrain")
    assert note.read_text(encoding="utf-8") == f"---\n{front}---\n\n# terrain\n"
    engine._set_front_path(note, "laptop", "/code/terrain")  # mapping again changes nothing
    assert note.read_text(encoding="utf-8") == f"---\n{front}---\n\n# terrain\n"


def test_map_path_keeps_crlf_and_refuses_a_paths_that_is_not_a_mapping(engine, vault):
    note = vault / "projects/private/terrain/project.md"
    note.parent.mkdir(parents=True)
    note.write_bytes(b"---\r\nstatus: active\r\ntags: [game]\r\n---\r\n\r\n# terrain\r\n")
    engine._set_front_path(note, "laptop", "/code/terrain")
    assert note.read_bytes() == b"---\r\nstatus: active\r\ntags: [game]\r\npaths:\r\n  laptop: /code/terrain\r\n---\r\n\r\n# terrain\r\n"
    note.write_text("---\npaths: /code/terrain\n---\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not a mapping"):
        engine._set_front_path(note, "laptop", "/code/terrain")


@pytest.mark.parametrize("before, after", [
    # review round 1 on #30: a quoted key, a comment between entries, a flow mapping over several lines
    ('"paths": {desk: /d/terrain}\n', "paths:\n  desk: /d/terrain\n  laptop: /code/terrain\n"),
    ("paths:\n  desk: /d/terrain\n# moved in May\n  laptop: /old\n", "paths:\n  desk: /d/terrain\n  laptop: /code/terrain\n"),
    ("paths: {desk: /d/terrain,\n  laptop: /old\n}\n", "paths:\n  desk: /d/terrain\n  laptop: /code/terrain\n"),
    ("paths:\n  desk: /d/terrain\n# about next\n", "paths:\n  desk: /d/terrain\n  laptop: /code/terrain\n# about next\n"),
    # review round 2 on #30: a block scalar that ends after its newline, an explicit key
    ("paths:\n  laptop: |-\n    /old\n", "paths:\n  laptop: /code/terrain\n"),
    ("? paths\n: {desk: /d/terrain}\n", "paths:\n  desk: /d/terrain\n  laptop: /code/terrain\n"),
])
def test_map_path_finds_the_whole_paths_value(engine, vault, before, after):
    project(vault, "terrain", "status: active\n" + before + "next: step 5\n")
    note = vault / "projects/private/terrain/project.md"
    engine._set_front_path(note, "laptop", "/code/terrain")
    assert note.read_text(encoding="utf-8") == f"---\nstatus: active\n{after}next: step 5\n---\n\n# terrain\n"
    assert engine.Index().entities["projects/private/terrain/project.md"].meta["paths"]["laptop"] == "/code/terrain"


@pytest.mark.parametrize("front", ["paths: &where {desk: /d}\nalso: *where\n", "where: &w {desk: /d}\npaths: *w\n",
                                   "paths:\n  desk: &d /d\nalso: *d\n"])
def test_map_path_leaves_anchors_and_aliases_to_the_user(engine, vault, front):
    # rewriting would drop an anchor that another key still uses, or expand an alias (#30 review round 1)
    project(vault, "terrain", front)
    note = vault / "projects/private/terrain/project.md"
    before = note.read_bytes()
    with pytest.raises(SystemExit, match="anchor or alias"):
        engine._set_front_path(note, "laptop", "/code/terrain")
    assert note.read_bytes() == before


def test_map_path_writes_nothing_it_cannot_read_back(engine, vault, monkeypatch):
    # the last guard: a span that would change another key is refused, and the file stays as it was (#30 round 2)
    project(vault, "terrain", "status: active\npaths: {desk: /d}\nnext: step 5\n")
    note = vault / "projects/private/terrain/project.md"
    before = note.read_bytes()
    monkeypatch.setattr(engine, "_top_value_span", lambda events, key: (0, 20, 0, False))  # also eats `status:`
    with pytest.raises(SystemExit, match="without touching other lines"):
        engine._set_front_path(note, "laptop", "/code/terrain")
    assert note.read_bytes() == before


@pytest.mark.parametrize("front, expected", [
    # final pass on #30: a last key with a block scalar, a root mapping indented by two spaces
    ("status: active\ndescription: |\n  Two lines\n  of text", "paths:\n  laptop: /code/terrain\nstatus: active\ndescription: |\n  Two lines\n  of text"),
    ("  status: active\n  repo: x", "  status: active\n  repo: x\n  paths:\n    laptop: /code/terrain"),
    # round 4 on #30: an explicit first key; the root starts at the `?`, not at the key
    ("? status\n: active\nrepo: x", "? status\n: active\nrepo: x\npaths:\n  laptop: /code/terrain"),
    # round 5: a root anchor on its own line; the keys below it set the indentation
    ("&root\n  status: active\n  repo: x", "&root\n  status: active\n  repo: x\n  paths:\n    laptop: /code/terrain"),
    # round 6: a `?` on its own line above the first key
    ("?\n  status\n: active\nrepo: x", "?\n  status\n: active\nrepo: x\npaths:\n  laptop: /code/terrain"),
    ("# nothing yet", "# nothing yet\npaths:\n  laptop: /code/terrain"),
])
def test_map_path_adds_paths_where_it_reads_back(engine, vault, front, expected):
    note = vault / "projects/private/terrain/project.md"
    note.parent.mkdir(parents=True)
    note.write_text(f"---\n{front}\n---\n\n# terrain\n", encoding="utf-8")
    engine._set_front_path(note, "laptop", "/code/terrain")
    assert note.read_text(encoding="utf-8") == f"---\n{expected}\n---\n\n# terrain\n"


def thread(vault, slug: str, name: str, meta: str) -> None:
    folder = vault / "projects" / "private" / slug / "threads"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(f"---\n{meta}---\n\n# {name}\n", encoding="utf-8")


def test_next_offers_open_threads_before_upkeep(engine, vault):
    # during project work, `next` suggested distilling and cards, and never the blocked thread (#32)
    project(vault, "terrain", "status: active\n")
    thread(vault, "terrain", "first-slice", "status: open\nnext: step 5\nblocked: needs five testers\n")
    thread(vault, "terrain", "sound", "status: open\nnext: pick a sound set\n")
    thread(vault, "terrain", "old", "status: closed\nnext: nothing\n")
    (vault / "captures").mkdir(exist_ok=True)
    (vault / "captures" / "c.md").write_text("---\nkind: research\n---\n\n# c\n", encoding="utf-8")
    tips = engine.suggestions(engine.Index())
    threads = [t for t in tips if t.startswith("Thread ")]
    assert len(threads) == 2 and not any('"old"' in t for t in threads)
    assert any("(terrain) is blocked: needs five testers. Ask the user" in t for t in threads)
    assert any("(terrain) is open, next: pick a sound set. Offer to continue it" in t for t in threads)
    assert tips.index(threads[-1]) < next(i for i, t in enumerate(tips) if "capture(s) waiting" in t)


def test_next_lists_three_threads_and_counts_the_rest(engine, vault):
    project(vault, "terrain", "status: active\n")
    for n in range(5):
        thread(vault, "terrain", f"t{n}", "status: open\n")
    tips = engine.suggestions(engine.Index())
    assert sum(t.startswith("Thread ") for t in tips) == 3
    assert "2 more open thread(s)" in " ".join(tips)


def test_the_build_skills_answer_what_the_operator_asked():
    # the build phase's operator had to guess these (#32)
    skills = APP / ".agents" / "skills"
    op = (skills / "atlas-operator" / "SKILL.md").read_text(encoding="utf-8")
    proj = (skills / "atlas-project" / "SKILL.md").read_text(encoding="utf-8")
    agents = (APP / "AGENTS.md").read_text(encoding="utf-8")
    assert "exit 143" in op and "restart it only if you started it" in op
    assert "(`[via choice]: /close`) runs that command" in op and "runs that command too" in agents
    assert "would be revisited together are one decision" in proj and "add a dated note that links the decision" in proj
    assert "what was verified and how" in proj and "does not count" in proj and "`boot` prints it as text" in proj
    distill = (skills / "atlas-distill" / "SKILL.md").read_text(encoding="utf-8")
    # the bug phase's operator: promoting a lesson, a first insight on a new topic, bug threads, corrections
    assert "write a short capture with the lesson's evidence" in proj and 'do not force one: set `unconnected: "<why>"`' in distill
    assert "A bug gets its own\nthread" in proj and "add a dated correction that names it" in proj


def test_distill_reads_the_primary_not_the_capture():
    # a capture is a lossy summary; claims come from the primary it cites (#34)
    distill = (APP / ".agents" / "skills" / "atlas-distill" / "SKILL.md").read_text(encoding="utf-8")
    assert "## 2. Read the primary, not the capture" in distill
    assert "open the primary at the passage the claim rests on" in distill
    assert "where capture and primary differ, the primary wins" in distill
    assert "if only the capture says it, that is the capture's reading, not evidence" in distill
    assert "a summary in the capture" not in distill  # no longer counts as a citable piece
    assert "keep its confidence at\n  `speculative`" in distill and "The new evidence comes from the primary too" in distill


def test_an_insight_with_no_neighbour_yet_can_say_so(engine, vault):
    # the first insight on a new topic: no honest link exists, and atlas-map needs five insights (#33 review round 2)
    (vault / "insights").mkdir(exist_ok=True)
    def insight(name, extra=""):
        (vault / "insights" / f"{name}.md").write_text(
            f"---\ndescription: d\nconfidence: working\n{extra}---\n\n# {name}\n", encoding="utf-8")
    insight("Levels feel varied when players perceive it")
    insight("Synthetic clicks miss a page that changes under the pointer")
    assert engine.health(engine.Index())["orphans"] == 2
    insight("Synthetic clicks miss a page that changes under the pointer", 'unconnected: "first note on software testing"\n')
    assert engine.health(engine.Index())["orphans"] == 1  # the other one still counts


def test_search_snippets_show_links_as_names(engine, vault):
    # search by meaning printed QMD's snippet raw: [[tmr-cues]] instead of the note's title (#50)
    (vault / "insights").mkdir(exist_ok=True)
    (vault / "insights" / "tmr-cues.md").write_text("---\ndescription: d\nconfidence: working\n---\n\n# Cues replay memories\n",
                                                   encoding="utf-8")
    index = engine.Index()
    out = engine.snippet_links("see [[tmr-cues]], [[tmr-cues#Method|the method]] and [[gone]]", index)
    assert out == "see Cues replay memories, the method and gone"


def test_search_snippets_render_bold_and_code_but_no_links():
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    js = (APP / "engine" / "static" / "app.js").read_text(encoding="utf-8")
    pieces = [re.search(p, js, re.S).group(0) for p in (r"const esc = .*?;\n", r"const snippetHtml = .*?;\n")]
    probe = "\n".join(pieces) + "\nconsole.log(snippetHtml('Cues **help** in `NREM`, see https://x.test <b>'));"
    out = subprocess.run([node, "-e", probe], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    assert out == "Cues <b>help</b> in <code>NREM</code>, see https://x.test &lt;b&gt;"  # the card is a link: none inside


def test_the_active_search_tab_is_marked():
    # the tabs are links, and the segmented control only marked button.on (#50)
    css = (APP / "engine" / "static" / "style.css").read_text(encoding="utf-8")
    rule = next(line for line in css.splitlines() if line.startswith(".seg button.on"))
    assert ".seg a.on" in rule and '.seg a[aria-pressed="true"]' in rule
