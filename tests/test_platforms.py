"""Regression tests for the bugs the first gate run (#8) found on Windows and macOS, and for the gate itself."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from argparse import Namespace

import pytest
from conftest import APP, ROOT

ENGINE = APP / "engine" / "atlas.py"


def engine(vault, *args, **kw):
    return subprocess.run([sys.executable, "-X", "warn_default_encoding", "-W", "error::EncodingWarning",
                           str(ENGINE), "--vault", str(vault), *args], capture_output=True, text=True,
                          encoding="utf-8", **kw)


def test_every_text_file_and_git_output_names_its_encoding(vault):
    # Without an encoding, Windows reads cp1252 and the registry's emoji stop the engine (#8, Windows run)
    for args in (["demo"], ["check"], ["next"], ["status"]):
        r = engine(vault, *args)
        assert "EncodingWarning" not in r.stderr, f"`atlas.py {args[0]}`:\n{r.stderr}"


def test_output_through_a_cp1252_pipe_keeps_its_emoji(vault):
    # Windows encodes piped stdout as cp1252: `boot` printed "⚠" and crashed (#8, second Windows run)
    assert engine(vault, "demo").returncode == 0
    r = engine(vault, "boot", "nightlight", "--agent", "codex", env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert r.returncode == 0, r.stderr
    assert "⚠" in r.stdout or "nightlight" in r.stdout.lower()


@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_commit_takes_a_moved_file_through_a_linked_folder(vault, tmp_path):
    # macOS keeps temp folders under /var, a link to /private/var: the moved file's old path was "outside the vault"
    link = tmp_path / "link"
    try:
        os.symlink(vault.parent, link, target_is_directory=True)
    except OSError:
        pytest.skip("this system does not allow symlinks")
    git = lambda *a: subprocess.run(["git", "-C", str(vault), *a], capture_output=True, text=True, check=True)
    git("init", "-q")
    git("config", "user.name", "gate")
    git("config", "user.email", "gate@example.com")
    (vault / "agents" / "gate.md").write_text("# Gate\n", encoding="utf-8")
    (vault / "captures" / "moved.md").write_text("# Moved\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "start")
    (vault / "sources").mkdir(exist_ok=True)
    (vault / "captures" / "moved.md").rename(vault / "sources" / "moved.md")
    linked = link / vault.name
    r = engine(linked, "commit", "--agent", "gate", "-m", "move a capture",
               str(linked / "captures" / "moved.md"), str(linked / "sources" / "moved.md"))
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_pr_check_fails_when_it_cannot_compare_with_the_base():
    # A missing base made an empty change list and skipped the version and screenshot rules (#8, review round 1)
    spec = importlib.util.spec_from_file_location("gate", ROOT / "ci" / "gate.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.check_pr(Namespace(base="no-such-base-ref"))
    assert any("cannot compare" in f for f in gate.failures)


@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_commit_follows_a_link_before_going_up_a_folder(vault):
    # normpath() before resolve() turned aliases/current/../note.md into aliases/note.md (#8, review round 2)
    git = lambda *a: subprocess.run(["git", "-C", str(vault), *a], capture_output=True, text=True, check=True)
    git("init", "-q")
    git("config", "user.name", "gate")
    git("config", "user.email", "gate@example.com")
    (vault / "agents" / "gate.md").write_text("# Gate\n", encoding="utf-8")
    (vault / "insights" / "subdir").mkdir(parents=True)
    (vault / "aliases").mkdir()
    try:
        os.symlink(vault / "insights" / "subdir", vault / "aliases" / "current", target_is_directory=True)
    except OSError:
        pytest.skip("this system does not allow symlinks")
    (vault / "insights" / "Linked note.md").write_text("# Linked note\n", encoding="utf-8")
    git("add", "agents")
    git("commit", "-q", "-m", "start")
    r = engine(vault, "commit", "--agent", "gate", "-m", "the linked note",
               str(vault / "aliases" / "current" / ".." / "Linked note.md"))
    assert r.returncode == 0, r.stdout + r.stderr
    committed = git("show", "--name-only", "--format=", "HEAD").stdout.split("\n")
    assert "insights/Linked note.md" in committed


def test_say_reads_utf8_from_a_cp1252_pipe(vault):
    # the engine read stdin as cp1252 while callers send UTF-8: "Grüße" arrived as "GrÃ¼ÃŸe" (#8, review round 2)
    r = engine(vault, "say", "-", input="Grüße — ein Test ✓", env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert r.returncode == 0, r.stderr
    outbox = (vault / ".atlas" / "outbox.jsonl").read_text(encoding="utf-8")
    assert "Grüße — ein Test ✓" in outbox
