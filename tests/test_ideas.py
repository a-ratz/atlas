"""Ideas (#16): sketches and specs with checks, the spec step, and projects that know where they came from."""

from __future__ import annotations

import re

OLD_SKETCH = ('  - id: sketch\n    label: Sketch\n    plural: Sketches\n    section: Ideas\n    globs: ["sketches/*.md"]\n'
              '    fields: [status, date]\n    status: status\n    date: date\n    moves:\n'
              '      - {label: "🔎 Research prior art", send: "Research prior art for this idea"}\n'
              '      - {label: "⚔️ Find the weak spots", send: "Poke holes in it, my way"}\n\n')
OLD_SPEC = ('  - id: spec\n    label: Spec\n    plural: Specs\n    section: Ideas\n    globs: ["specs/**/*.md"]\n'
            '    fields: [status, date, source_sketch]\n    status: status\n    date: date\n    moves:\n'
            '      - {label: "⚔️ Review it", send: "Review this spec: what is unclear, missing or risky?"}\n\n')
OLD_PROJECT = ('  - id: project\n    label: Project\n    plural: Projects\n    section: Projects\n'
               '    globs: ["projects/*/*/project.md"]\n    fields: [status, repo, paths]\n    status: status\n    moves:\n'
               '      - {label: "🚀 Work on it", send: "/project {project}"}\n'
               '      - {label: "🧭 What\'s next?", send: "What should happen next in this project?"}\n\n')


def replace_type(text: str, tid: str, nxt: str, block: str) -> str:
    start, end = text.index(f"  - id: {tid}\n"), text.index(f"  - id: {nxt}\n")
    return text[:start] + block + text[end:]


def as_07(vault):
    """The vault's atlas.yaml as Atlas 0.7 wrote it: no spec step, no /spec."""
    reg = vault / "atlas.yaml"
    text = reg.read_text(encoding="utf-8")
    text = replace_type(text, "sketch", "spec", OLD_SKETCH)
    text = replace_type(text, "spec", "project", OLD_SPEC)
    text = replace_type(text, "project", "thread", OLD_PROJECT)
    text = "\n".join(line for line in text.splitlines() if "name: spec," not in line) + "\n"
    reg.write_text(text, encoding="utf-8")


def test_a_registry_from_0_7_learns_the_spec_step(engine, vault):
    as_07(vault)
    index = engine.Index()
    sketch, spec, project = (index.types[t] for t in ("sketch", "spec", "project"))
    assert sketch["fields"] == ["status", "date", "origin", "spec"]
    assert [m["label"] for m in sketch["moves"]][-1] == "🧩 Turn into a spec"
    assert sketch["moves"][1]["send"] == "Poke holes in it, my way"  # the vault's own wording stays
    assert [m["label"] for m in spec["moves"]] == ["⚔️ Review it", "🚀 Start a project"]
    assert project["fields"] == ["status", "repo", "paths", "source"]
    assert "status" in sketch["checks"]["allowed"] and spec["checks"]["resolve"] == ["source_sketch"]
    names = [c["name"] for c in index.commands]
    assert names[names.index("sketch") + 1] == "spec"


def test_customized_idea_types_stay(engine, vault):
    reg = vault / "atlas.yaml"
    text = replace_type(reg.read_text(encoding="utf-8"), "sketch", "spec",
                        OLD_SKETCH.replace("fields: [status, date]", "fields: [status]").replace(
                            '      - {label: "⚔️ Find the weak spots", send: "Poke holes in it, my way"}\n', ""))
    text = re.sub(r"^commands:\n(?:  - .*\n)+", "commands:\n  - {name: mine, help: x, send: x}\n", text, flags=re.M)
    reg.write_text(text, encoding="utf-8")
    index = engine.Index()
    assert index.types["sketch"]["fields"] == ["status"]
    assert [m["label"] for m in index.types["sketch"]["moves"]] == ["🔎 Research prior art"]
    assert [c["name"] for c in index.commands] == ["mine"]


def note(vault, rel: str, meta: str, title: str = "T") -> str:
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    (vault / rel).write_text(f"---\n{meta}---\n\n# {title}\n", encoding="utf-8")
    return rel


def problems(engine, rel: str) -> list[str]:
    return {n["id"]: n["issues"] for n in engine.health(engine.Index())["notes"]}.get(rel, [])


def test_sketches_and_specs_are_checked(engine, vault):
    sketch = note(vault, "sketches/glow.md", "description: d\nstatus: idea\n")
    spec = note(vault, "specs/glow-spec.md", "description: d\nstatus: done\nsource_sketch: '[[nowhere]]'\n")
    assert any("status: idea" in p for p in problems(engine, sketch))
    assert any("status: done" in p for p in problems(engine, spec)) and any("nowhere" in p for p in problems(engine, spec))


def test_ideas_written_before_0_9_stay_valid(engine, vault):
    # a 0.8 sketch and spec without description failed `check` after the upgrade (#19, review round 1)
    sketch = note(vault, "sketches/old-idea.md", "status: sketch\ndate: 2026-10-01\n")
    spec = note(vault, "specs/old-idea.md", "status: draft\ndate: 2026-10-02\n")
    assert problems(engine, sketch) == [] and problems(engine, spec) == []


def test_the_spec_skill_follows_the_spec_a_sketch_names():
    # it checked only `<slug>-spec.md`, made a second spec for a sketch that had one, and pointed the
    # sketch and the project at the old name after writing a -v2 (#19, review round 1)
    from conftest import APP
    skill = (APP / ".agents/skills/atlas-spec/SKILL.md").read_text(encoding="utf-8")
    assert "the sketch's `spec:` already names a spec" in skill
    assert "[[<slug>-spec]]" not in skill and skill.count("[[<spec>]]") >= 2


def test_a_project_shows_the_spec_and_sketch_it_came_from(engine, vault):
    note(vault, "sketches/glow.md", "description: d\nstatus: specified\nspec: \"[[glow-spec]]\"\n", "Glow")
    note(vault, "specs/glow-spec.md", "description: d\nstatus: building\nsource_sketch: \"[[glow]]\"\n", "Glow spec")
    rel = note(vault, "projects/private/glow/project.md", "status: active\nsource: \"[[glow-spec]]\"\n", "Glow")
    index = engine.Index()
    view = engine.entity_view(index, rel)
    assert [x["id"] for x in view["provenance"]] == ["sketches/glow.md", "specs/glow-spec.md"]
    assert problems(engine, rel) == [] and problems(engine, "specs/glow-spec.md") == []
