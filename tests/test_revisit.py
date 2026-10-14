"""Revisits (#52): the skill, the command and move, how a 0.9 registry learns them, and what `next` says."""

from __future__ import annotations

from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "skills" / "atlas" / "app"


def as_09(vault, *drop: str):
    """The vault's atlas.yaml as Atlas 0.9 wrote it: no /revisit, no revisit move (and without `drop` lines)."""
    reg = vault / "atlas.yaml"
    gone = ("name: revisit,", '"🔁 Revisit its source"', *drop)
    reg.write_text("\n".join(line for line in reg.read_text(encoding="utf-8").splitlines()
                             if not any(g in line for g in gone)) + "\n", encoding="utf-8")


def test_both_registries_ship_the_command_and_the_move():
    for reg in (APP / "engine" / "registry.default.yaml", APP / "vault" / "atlas.yaml"):
        text = reg.read_text(encoding="utf-8")
        assert '{name: revisit, args: "[insight | all]"' in text and 'send: "/revisit {args}"' in text
        assert '{label: "🔁 Revisit its source", send: "/revisit this insight"}' in text


def test_a_registry_from_0_9_learns_revisit(engine, vault):
    as_09(vault)
    index = engine.Index()
    names = [c["name"] for c in index.commands]
    assert names[names.index("map") + 1] == "revisit"
    assert [m["label"] for m in index.types["insight"]["moves"]][-1] == "🔁 Revisit its source"


def test_a_registry_the_user_changed_keeps_its_own_commands(engine, vault):
    as_09(vault, "name: tour,")  # not the shape 0.9 shipped: leave it alone
    assert "revisit" not in [c["name"] for c in engine.Index().commands]


def test_next_names_the_revisit_command(engine, vault):
    (vault / "insights").mkdir(exist_ok=True)
    (vault / "insights" / "Old claim.md").write_text(
        "---\ndescription: d\nconfidence: working\nrevisit_after: 2020-01-01\n---\n\n# Old claim\n", encoding="utf-8")
    assert any("/revisit" in s and "atlas-revisit" in s for s in engine.suggestions(engine.Index()))


def test_the_revisit_skill_records_instead_of_deleting():
    skill = (APP / ".agents" / "skills" / "atlas-revisit" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: atlas-revisit\n")
    assert "**at most five per run**" in skill and "that has no\n  `superseded_by`" in skill and "superseded_by" in skill and "Do not rename or delete" in skill
    assert "An earlier version said" in skill and "only if the text can\nstill change" in skill


def test_a_superseded_insight_is_not_due(engine, vault):
    # review round 1 on #53: a replaced claim kept coming back in every revisit batch
    (vault / "insights").mkdir(exist_ok=True)
    (vault / "insights" / "Old claim.md").write_text(
        '---\ndescription: d\nconfidence: working\nrevisit_after: 2020-01-01\nsuperseded_by: "[[New claim]]"\n---\n\n# Old claim\n',
        encoding="utf-8")
    index = engine.Index()
    assert engine.needs_you(index)["revisits_total"] == 0
    assert not any("revisit" in s for s in engine.suggestions(index))


def test_the_revisit_button_speaks_through_the_registry():
    # review round 1 on #53: the Needs you button sent hardcoded text and skipped a vault's own /revisit wording
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    js = (APP / "engine" / "static" / "app.js").read_text(encoding="utf-8")
    pieces = [re.search(p, js, re.S).group(0) for p in (
        r"const esc = .*?;\n", r"const commandSend = \(name, args = \"\"\) => \{.*?\n\};\n",
        r"const fillMove = .*?;\n", r"function revisitButton\(n, r\) \{.*?\n\}\n")]
    stubs = ('const commandList = () => [{name: "revisit", send: "Check {args} offline only"}];\n'
             'let moves = [{label: "Mine", send: "Re-read this insight\'s source, offline"}];\n'
             "const movesOf = () => moves;\n")
    probe = stubs + "\n".join(pieces) + (
        '\nconst r = {id: "insights/a.md", title: "A claim"};'
        "\nconsole.log(revisitButton({revisits_total: 2}, r));"
        "\nmoves = [{label: \"🔁 Revisit its source\", send: \"/revisit this insight\"}];"
        "\nconsole.log(revisitButton({revisits_total: 1}, r));"
        "\nmoves = [{label: \"Revisit\", send: \"Revisit {title} using {path}\"}];"
        "\nconsole.log(revisitButton({revisits_total: 1}, r));"
        "\nmoves = [];"
        "\nconsole.log(revisitButton({revisits_total: 1}, r));")
    out = subprocess.run([node, "-e", probe], capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    assert 'data-send="Check all offline only" data-via="command"' in out[0]  # the vault's own command text
    assert 'data-send="/revisit this insight" data-via="move"' in out[1]
    assert 'data-send="Revisit A claim using insights/a.md" data-via="move"' in out[2]  # review round 2: placeholders filled
    assert 'data-send="Check this insight offline only" data-via="command"' in out[3]  # no revisit move: the command
