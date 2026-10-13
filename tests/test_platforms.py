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
