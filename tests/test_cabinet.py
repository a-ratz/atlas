"""Cabinet depth (#9): minimal cards, Expand, and vault registries copied before 0.7."""

from __future__ import annotations

import re


def card(vault, kind: str, name: str, depth: str | None = None) -> str:
    rel = f"cabinet/{'people' if kind == 'person' else 'orgs'}/{name.lower()}.md"
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    meta = f"name: {name}\naliases: [{name}]\n" + (f"depth: {depth}\n" if depth else "")
    (vault / rel).write_text(f"---\n{meta}---\n\n# {name}\n", encoding="utf-8")
    return rel


def test_minimal_cards_suggest_expanding_them(engine, vault):
    card(vault, "person", "Dumay", "minimal")
    card(vault, "org", "Acme", "complete")
    tips = engine.suggestions(engine.Index())
    assert any("1 cabinet card(s) are minimal" in t for t in tips)


def test_depth_is_minimal_or_complete(engine, vault):
    rel = card(vault, "person", "Gaskell", "partial")
    issues = {n["id"]: n["issues"] for n in engine.health(engine.Index())["notes"]}
    assert rel in issues and any("depth" in i for i in issues[rel])


def test_a_registry_from_0_6_learns_depth_and_expand(engine, vault):
    reg = vault / "atlas.yaml"
    text = reg.read_text(encoding="utf-8")
    old_person = ('  - id: person\n    label: Person\n    plural: People\n    section: Cabinet\n'
                  '    globs: ["cabinet/people/*.md"]\n    fields: [role, org, relation, email, phone, updated]\n'
                  '    date: updated\n    recall: true\n    moves:\n'
                  '      - {label: "🔄 Update", send: "Update this card, my way"}\n\n')
    start, end = text.index("  - id: person"), text.index("  - id: org")
    text = text[:start] + old_person + text[end:]
    text = "\n".join(line for line in text.splitlines()  # the commands 0.6 shipped
                     if "name: expand-cards" not in line and "name: spec," not in line and "name: revisit," not in line) + "\n"
    reg.write_text(text, encoding="utf-8")
    index = engine.Index()
    person = index.types["person"]
    assert person["status"] == "depth"
    assert {"depth", "checked"} <= set(person["fields"])
    assert [m["label"] for m in person["moves"]] == ["🔎 Expand", "🔄 Update"]
    assert person["moves"][1]["send"] == "Update this card, my way"  # the vault's own move stays as it was
    assert any(c.get("name") == "expand-cards" for c in index.commands)
    assert any(c.get("name") == "spec" for c in index.commands)  # and then what 0.9 added (#16)
    assert any(c.get("name") == "revisit" for c in index.commands)  # and what 0.10 added (#52)


def test_explicit_cabinet_customizations_stay(engine, vault):
    # the migration overrode `moves: []`, trimmed fields and `commands: []` on every load (#12, review round 1)
    reg = vault / "atlas.yaml"
    text = reg.read_text(encoding="utf-8")
    start, end = text.index("  - id: person"), text.index("  - id: org")
    mine = ('  - id: person\n    label: Person\n    plural: People\n    section: Cabinet\n'
            '    globs: ["cabinet/people/*.md"]\n    fields: [role]\n    date: updated\n    recall: true\n'
            '    moves: []\n\n')
    text = text[:start] + mine + text[end:]
    text = re.sub(r"^commands:\n(?:  - .*\n)+", "commands: []\n", text, flags=re.M)
    reg.write_text(text, encoding="utf-8")
    index = engine.Index()
    assert index.types["person"]["fields"] == ["role"]
    assert index.types["person"]["moves"] == []
    assert "status" not in index.types["person"]
    assert index.commands == []


def test_depth_counts_whatever_the_status_field_is(engine, vault):
    # with `status: relationship`, a minimal card was never suggested for Expand (#12, review round 1)
    reg = vault / "atlas.yaml"
    text = reg.read_text(encoding="utf-8")
    start = text.index("  - id: person")
    text = text[:start] + text[start:].replace("    status: depth", "    status: relationship", 1)
    reg.write_text(text, encoding="utf-8")
    rel = card(vault, "person", "Tamminen", "minimal")
    path = vault / rel
    path.write_text(path.read_text(encoding="utf-8").replace("depth: minimal\n", "depth: minimal\nrelationship: active\n"),
                    encoding="utf-8")
    assert any("1 cabinet card(s) are minimal" in t for t in engine.suggestions(engine.Index()))


def test_expand_keeps_private_contacts_off_the_open_web():
    # Expand searched the web for every card; private contacts may only be looked up through LinkedIn (#12, round 1)
    from conftest import APP
    skill = (APP / ".agents/skills/atlas-cabinet/SKILL.md").read_text(encoding="utf-8")
    assert "A private contact" in skill and "stays vault-only" in skill
