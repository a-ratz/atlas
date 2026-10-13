"""Search by meaning (#5): the vault's own QMD index, settings, the refresh after a commit, deep search."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import ROOT


class FakeQmd:
    """Stands in for the qmd launcher: records every call, answers from `replies`, can run a side effect."""

    def __init__(self, engine, monkeypatch, conf: Path):
        self.calls: list[list[str]] = []
        self.envs: list[dict] = []
        self.fail: set[str] = set()
        self.during: dict[str, callable] = {}
        self.hits: list[dict] = []
        self.conf = conf
        monkeypatch.setenv("QMD_CONFIG_DIR", str(conf))
        monkeypatch.setattr(engine.shutil, "which", lambda name: "/opt/qmd/bin/qmd.cmd" if name == "qmd" else None)
        real = subprocess.run

        def run(args, **kw):
            if args[0] != "/opt/qmd/bin/qmd.cmd":
                return real(args, **kw)
            self.calls.append(args)
            self.envs.append(kw.get("env") or {})
            rest = args[3:] if args[1] == "--index" else args[1:]
            if rest[0] in self.during:
                self.during.pop(rest[0])()
            if rest[0] in self.fail:
                return subprocess.CompletedProcess(args, 1, "", f"{rest[0]}: model download failed")
            if rest[:2] == ["collection", "add"]:  # what QMD writes: <index>.yml with the collection
                index = args[2] if args[1] == "--index" else "index"
                self.add(index, rest[rest.index("--name") + 1], Path(rest[2]), rest[rest.index("--mask") + 1])
            if rest[0] == "query":
                return subprocess.CompletedProcess(args, 0, json.dumps(self.hits), "")
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(engine.subprocess, "run", run)

    def add(self, index: str, name: str, path: Path, pattern: str = "**/*.md") -> None:
        import yaml
        cfg = self.conf / f"{index}.yml"
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
        data.setdefault("collections", {})[name] = {"path": str(path), "pattern": pattern}
        self.conf.mkdir(parents=True, exist_ok=True)
        cfg.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture
def fake(engine, vault, monkeypatch, tmp_path):
    return FakeQmd(engine, monkeypatch, tmp_path / "qmd-config")


def test_setup_builds_the_vaults_own_index(engine, vault, fake):
    engine.cmd_qmd(Namespace(action="setup"))
    assert all(call[1:3] == ["--index", "atlas"] for call in fake.calls)  # never QMD's default index
    names = {c[c.index("--name") + 1] for c in fake.calls if "add" in c and "collection" in c}
    assert names == {"atlas-cabinet", "atlas-projects", "atlas-ideas", "atlas-insights", "atlas-sources"}
    assert engine.qmd_settings() == {"enabled": True, "index": "atlas"}


def test_a_waiting_capture_is_found_by_meaning(engine, vault, fake):
    # a capture the agent just wrote was never indexed, and "what do we know" missed captures (#15, smoke run)
    engine.cmd_qmd(Namespace(action="setup"))
    sources = next(c for c in fake.calls if "atlas-sources" in c)
    assert "captures" in sources[sources.index("--mask") + 1]
    assert engine.qmd_areas_for(["captures/a-note-of-mine.md"]) == ["sources"]


def test_a_second_vault_gets_an_index_of_its_own(engine, vault, fake):
    fake.add("atlas", "atlas-insights", Path("/somewhere/else/vault"))  # another vault on this machine
    name, _ = engine.qmd_plan()
    assert name == f"atlas-{engine.slug(vault.name, 24)}"


def test_qmd_runs_through_the_resolved_launcher(engine, vault, fake):
    # a bare "qmd" does not find npm's qmd.cmd on Windows (#15, review round 1)
    engine.qmd("status", index="atlas")
    assert fake.calls[-1][0] == "/opt/qmd/bin/qmd.cmd"


def test_a_sync_touches_only_the_vaults_index(engine, vault, fake):
    # `qmd update` re-read every collection on the machine and ran their update hooks (#15, review round 1)
    engine.cmd_qmd(Namespace(action="setup"))
    fake.calls.clear()
    assert engine.qmd_sync()[0]
    assert [c[1:] for c in fake.calls] == [["--index", "atlas", "update"], ["--index", "atlas", "embed"]]


def test_a_failed_embed_is_reported_and_setup_stays_off(engine, vault, fake):
    # sync said "refreshed" and setup turned QMD on although embedding failed (#15, review round 1)
    fake.fail.add("embed")
    with pytest.raises(SystemExit):
        engine.cmd_qmd(Namespace(action="setup"))
    assert engine.qmd_state() == "off"
    engine.qmd_set(enabled="on")
    ok, msg = engine.qmd_sync()
    assert not ok and "embed failed" in msg and "model download failed" in msg


def test_a_change_during_a_sync_gets_its_own_run(engine, vault, fake):
    # a busy sync overwrote the waiting areas, and a request in the last pass was dropped (#15, review round 1)
    engine.cmd_qmd(Namespace(action="setup"))
    fake.calls.clear()
    fake.during["update"] = lambda: (vault / ".atlas" / "qmd.pending").touch()  # a commit lands mid-run
    assert engine.qmd_sync()[0]
    assert [c[3] for c in fake.calls] == ["update", "embed", "update", "embed"]


def test_a_busy_sync_leaves_a_mark_for_the_running_one(engine, vault, fake):
    engine.cmd_qmd(Namespace(action="setup"))
    held = engine._try_lock("qmd.lock")
    try:
        assert "picks this change up" in engine.qmd_sync()[1]
        assert (vault / ".atlas" / "qmd.pending").exists()
    finally:
        held.close()


def test_on_and_off_whatever_yaml_makes_of_them(engine, vault):
    for written, state in (("on", "on"), ("true", "on"), ('"on"', "on"), ("off", "off"), ("ask", "ask")):
        engine.qmd_set(enabled=written)
        assert engine.qmd_state() == state, written


def test_settings_keep_the_rest_of_atlas_yaml(engine, vault):
    before = (vault / "atlas.yaml").read_text(encoding="utf-8")
    engine.qmd_set(enabled="on", index="atlas-two")
    after = (vault / "atlas.yaml").read_text(encoding="utf-8")
    assert engine.qmd_settings() == {"enabled": True, "index": "atlas-two"}
    assert len(after.splitlines()) == len(before.splitlines())
    assert "# ask | on | off" in after  # the comment stays


def test_settings_land_in_the_vault_not_the_apps_default(engine, vault):
    # a vault without atlas.yaml had `qmd off` written into the app's registry.default.yaml (#15, round 1)
    (vault / "atlas.yaml").unlink()
    engine.set_vault(vault)
    default = (engine.APP / "registry.default.yaml").read_text(encoding="utf-8")
    try:
        engine.qmd_set(enabled="off")
        assert (vault / "atlas.yaml").exists() and engine.qmd_state() == "off"
        assert (engine.APP / "registry.default.yaml").read_text(encoding="utf-8") == default
    finally:
        (engine.APP / "registry.default.yaml").write_text(default, encoding="utf-8")


def test_off_means_deep_search_does_not_call_qmd(engine, vault, fake):
    # after `qmd off`, deep search kept returning QMD's results (#15, review round 1)
    engine.cmd_qmd(Namespace(action="setup"))
    engine.qmd_set(enabled="off")
    fake.calls.clear()
    assert engine.deep_search(engine.Index(), "animals that hide") == []
    assert fake.calls == []


def test_deep_search_reads_the_vaults_index(engine, vault, fake):
    note = vault / "insights" / "Octopuses hide in under a second.md"
    note.write_text("---\ndescription: d\nconfidence: working\n---\n\n# Octopuses hide in under a second\n",
                    encoding="utf-8")
    engine.cmd_qmd(Namespace(action="setup"))
    fake.hits = [{"file": "qmd://atlas-insights/insights/Octopuses hide in under a second.md?index=atlas",
                  "score": 0.9, "snippet": "x"}]
    results = engine.deep_search(engine.Index(), "animals that hide")
    assert [r["id"] for r in results] == ["insights/Octopuses hide in under a second.md"]
    assert fake.calls[-1][1:3] == ["--index", "atlas"]


@pytest.fixture
def repo(engine, vault, monkeypatch):
    """The vault as a git repository with an agent that may commit; returns the paths each refresh got."""
    started = []
    monkeypatch.setattr(engine, "qmd_refresh_after_commit", lambda paths: started.append(paths))
    for k, v in (("NAME", "t"), ("EMAIL", "t@example.com")):
        monkeypatch.setenv(f"GIT_AUTHOR_{k}", v)
        monkeypatch.setenv(f"GIT_COMMITTER_{k}", v)
    subprocess.run(["git", "-C", str(vault), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(vault), "commit", "-q", "--allow-empty", "-m", "start"], check=True)
    (vault / "agents").mkdir(exist_ok=True)
    (vault / "agents" / "tester.md").write_text("---\nname: Tester\n---\n\n# Tester\n", encoding="utf-8")
    return started


def commit(engine, vault, *paths):
    engine.cmd_commit(Namespace(agent="tester", message="m",
                                paths=[str(vault / p) for p in paths] + [str(vault / "agents" / "tester.md")]))


def test_a_folder_commit_refreshes_its_area(engine, vault, repo):
    # `commit vault/insights` passed "insights" without a slash, and no refresh started (#15, review round 1)
    (vault / "insights" / "A new claim.md").write_text("---\ndescription: d\n---\n\n# A new claim\n", encoding="utf-8")
    commit(engine, vault, "insights")
    assert "insights/A new claim.md" in repo[0]
    assert engine.qmd_areas_for(repo[0]) == ["insights"]


def test_a_note_with_umlauts_refreshes_its_area(engine, vault, repo):
    # git quoted "Grüße" as "insights/Gr\303\274\303\237e.md", which matched no area (#15, review round 2)
    (vault / "insights" / "Grüße 🌙.md").write_text("---\ndescription: d\n---\n\n# Grüße\n", encoding="utf-8")
    commit(engine, vault, "insights/Grüße 🌙.md")
    assert "insights/Grüße 🌙.md" in repo[0]


def test_the_refresh_reads_its_own_commit_not_a_later_one(engine, vault, repo, monkeypatch):
    # another agent's commit right after the lock let go hid this commit's insight from the refresh (#15, round 2)
    real_lock = engine._lock

    def lock_then_race(name):
        held = real_lock(name)
        close = held.close

        def close_and_commit():
            close()
            (vault / "you").mkdir(exist_ok=True)
            (vault / "you" / "goals.md").write_text("# Goals\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(vault), "add", "you/goals.md"], check=True)
            subprocess.run(["git", "-C", str(vault), "commit", "-q", "-m", "other agent"], check=True)
        return type("Held", (), {"close": staticmethod(close_and_commit)})()
    monkeypatch.setattr(engine, "_lock", lock_then_race)
    (vault / "insights" / "A raced claim.md").write_text("---\ndescription: d\n---\n\n# A raced claim\n", encoding="utf-8")
    commit(engine, vault, "insights/A raced claim.md")
    assert "insights/A raced claim.md" in repo[0]


def test_an_index_of_another_vault_is_not_this_ones(engine, vault, fake):
    # a copied vault keeps `qmd.index` and would search and refresh the original's index (#15, review round 2)
    fake.add("atlas", "atlas-insights", Path("/somewhere/else/vault"))
    engine.qmd_set(enabled="on", index="atlas")
    assert engine.qmd_index() is None
    assert engine.qmd_refresh_after_commit(["insights/x.md"]) is None


def test_qmd_never_sees_index_path(engine, vault, fake, monkeypatch):
    # INDEX_PATH beats --index in QMD: every vault would share one database (#15, review round 2)
    monkeypatch.setenv("INDEX_PATH", "/elsewhere/qmd/index.sqlite")
    engine.qmd("status", index="atlas")
    assert fake.envs[-1] and "INDEX_PATH" not in fake.envs[-1]
    engine.qmd("status")  # QMD's default index, which a user may keep at INDEX_PATH (#15, review round 3)
    assert fake.envs[-1]["INDEX_PATH"] == "/elsewhere/qmd/index.sqlite"


def smoke_run():
    spec = importlib.util.spec_from_file_location("smoke_run", ROOT / "ci" / "smoke" / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    return run


def test_smoke_runs_keep_qmd_inside_the_run(tmp_path):
    # INDEX_PATH from the developer's shell sent the run's QMD database outside the run (#15, round 1)
    env = {"HOME": str(tmp_path), "INDEX_PATH": "/elsewhere/qmd/index.sqlite"}
    smoke_run().isolate_qmd(env)
    assert "INDEX_PATH" not in env
    assert env["XDG_CACHE_HOME"].startswith(str(tmp_path)) and env["QMD_CONFIG_DIR"].startswith(str(tmp_path))


def test_the_operator_gets_the_whole_isolation(tmp_path, monkeypatch):
    # the brief named HOME and the git identity only; QMD's folders reached the operator's shell by luck
    monkeypatch.setenv("INDEX_PATH", "/elsewhere/qmd/index.sqlite")
    run = smoke_run()
    env = {k: v for k, v in run.os.environ.items() if k != "INDEX_PATH"}
    env.update(HOME=str(tmp_path / "home"), ATLAS_VAULT=str(tmp_path / "vault"))
    run.isolate_qmd(env)
    run.write_env(tmp_path, env)
    sh = (tmp_path / "env.sh").read_text(encoding="utf-8")
    for key in ("HOME", "ATLAS_VAULT", "XDG_CACHE_HOME", "QMD_CONFIG_DIR"):
        assert f"export {key}=" in sh
    assert "unset INDEX_PATH" in sh
    assert "Remove-Item Env:INDEX_PATH" in (tmp_path / "env.ps1").read_text(encoding="utf-8")
