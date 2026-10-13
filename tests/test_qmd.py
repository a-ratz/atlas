"""Search by meaning (#5): collections, prefix, settings, the refresh after a commit, deep search."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_the_five_collections_and_a_free_prefix(engine, vault):
    cols = engine.qmd_plan({})
    assert [c["name"] for c in cols] == ["atlas-cabinet", "atlas-projects", "atlas-ideas", "atlas-insights", "atlas-sources"]
    assert all(c["path"] == vault.resolve() for c in cols)  # rooted at the vault: a missing folder is fine
    taken = {"atlas-insights": Path("/somewhere/else/vault")}  # another vault on this machine uses "atlas"
    assert engine.qmd_plan(taken)[0]["name"] == f"atlas-{engine.slug(vault.name, 24)}-cabinet"


def test_paths_map_to_areas(engine):
    paths = ["insights/A claim.md", "sketches/idea.md", "research/run/brief.md", "cabinet/people/x.md", "you/goals.md"]
    assert engine.qmd_areas_for(paths) == ["cabinet", "ideas", "insights", "sources"]


def test_on_and_off_whatever_yaml_makes_of_them(engine, vault):
    for written, state in (("on", "on"), ("true", "on"), ('"on"', "on"), ("off", "off"), ("ask", "ask")):
        engine.qmd_set(enabled=written)
        assert engine.qmd_state() == state, written


def test_settings_keep_the_rest_of_atlas_yaml(engine, vault):
    before = (vault / "atlas.yaml").read_text(encoding="utf-8")
    engine.qmd_set(enabled="on", prefix="atlas-two")
    after = (vault / "atlas.yaml").read_text(encoding="utf-8")
    assert engine.qmd_settings() == {"enabled": True, "prefix": "atlas-two"}
    assert len(after.splitlines()) == len(before.splitlines())
    assert "# ask | on | off" in after  # the comment stays


def test_a_commit_starts_a_background_refresh_only_when_qmd_is_on(engine, vault, monkeypatch):
    started = []
    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/qmd" if name == "qmd" else None)
    monkeypatch.setattr(engine.subprocess, "Popen", lambda args, **kw: started.append(args))
    engine.qmd_set(enabled="off")
    assert engine.qmd_refresh_after_commit(["insights/x.md"]) is None
    engine.qmd_set(enabled="on")
    assert engine.qmd_refresh_after_commit(["you/goals.md"]) is None  # nothing QMD indexes
    assert "insights" in engine.qmd_refresh_after_commit(["insights/x.md", "insights/y.md"])
    assert started and started[0][-3:] == ["qmd", "sync", "insights"]


def test_a_busy_sync_hands_its_areas_to_the_running_one(engine, vault, monkeypatch):
    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/qmd")
    engine.qmd_set(enabled="on")
    held = engine._try_lock("qmd.lock")
    try:
        assert "picks this change up" in engine.qmd_sync(["cabinet"])
        assert (vault / ".atlas" / "qmd.dirty").read_text(encoding="utf-8") == "cabinet"
    finally:
        held.close()


def test_deep_search_shows_a_note_once(engine, vault, monkeypatch):
    note = vault / "insights" / "Octopuses hide in under a second.md"
    note.write_text("---\ndescription: d\nconfidence: working\n---\n\n# Octopuses hide in under a second\n", encoding="utf-8")
    old_and_new = {"atlas": vault, "atlas-insights": vault}  # an older whole-vault collection and an area one
    monkeypatch.setattr(engine, "qmd_collections", lambda: old_and_new)
    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/qmd")
    hits = [{"file": f"qmd://{c}/insights/Octopuses hide in under a second.md", "score": s, "snippet": "x"}
            for c, s in (("atlas", 0.9), ("atlas-insights", 0.8))]
    real_run = subprocess.run
    monkeypatch.setattr(engine.subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, json.dumps(hits), "")
                        if args[:2] == ["qmd", "query"] else real_run(args, **kw))
    results = engine.deep_search(engine.Index(), "animals that hide")
    assert [r["id"] for r in results] == ["insights/Octopuses hide in under a second.md"]
