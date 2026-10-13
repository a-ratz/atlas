"""Cabinet depth (#9): minimal cards, Expand, and vault registries copied before 0.7."""

from __future__ import annotations


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
    text = "\n".join(line for line in text.splitlines() if "name: expand-cards" not in line) + "\n"
    reg.write_text(text, encoding="utf-8")
    index = engine.Index()
    person = index.types["person"]
    assert person["status"] == "depth"
    assert {"depth", "checked"} <= set(person["fields"])
    assert [m["label"] for m in person["moves"]] == ["🔎 Expand", "🔄 Update"]
    assert person["moves"][1]["send"] == "Update this card, my way"  # the vault's own move stays as it was
    assert any(c.get("name") == "expand-cards" for c in index.commands)
