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
    assert "An earlier version said" in skill and "only if the text can still change" in skill
    assert "A source you could not read\nkeeps a date for another try, final version or not" in skill  # final pass on #53


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
    # review rounds 1-3 on #53: hardcoded text skipped a vault's own /revisit; matching move wording picked the wrong move
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    js = (APP / "engine" / "static" / "app.js").read_text(encoding="utf-8")
    pieces = [re.search(p, js, re.S).group(0) for p in (
        r"const esc = .*?;\n", r"const commandSend = \(name, args = \"\"\) => \{.*?\n\};\n",
        r"function revisitButton\(n, r\) \{.*?\n\}\n")]
    stubs = ('let commands = [{name: "revisit", send: "Check {args} offline only"}];\n'
             "const commandList = () => commands;\n"
             'const movesOf = () => [{label: "Challenge", send: "Revisit the assumptions behind this claim"}];\n')
    probe = stubs + "\n".join(pieces) + (
        '\nconst r = {id: "insights/a.md", title: "A claim"};'
        "\nconsole.log(revisitButton({revisits_total: 2}, r));"
        "\nconsole.log(revisitButton({revisits_total: 1}, r));"
        "\ncommands = [];"
        "\nconsole.log(revisitButton({revisits_total: 1}, r));")
    out = subprocess.run([node, "-e", probe], capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    assert 'data-send="Check all offline only" data-via="command" data-ctx="insights/a.md"' in out[0]  # the vault's wording
    assert 'data-send="Check this insight offline only" data-via="command"' in out[1]  # not the challenge move
    assert 'data-send="/revisit this insight"' in out[2]  # a registry without the command: the plain command
