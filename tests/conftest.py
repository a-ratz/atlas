"""Load the engine once and give each test a fresh copy of the template vault.

Run through the gate, which brings the engine's own dependencies: `uv run ci/gate.py tests`.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "skills" / "atlas" / "app"


@pytest.fixture(scope="session")
def engine():
    spec = importlib.util.spec_from_file_location("atlas_engine", APP / "engine" / "atlas.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look their module up while the class is built
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def vault(engine, tmp_path, monkeypatch):
    path = tmp_path / "vault"
    shutil.copytree(APP / "vault", path, ignore=shutil.ignore_patterns(".atlas"))
    engine.set_vault(path)
    # no test sees the agent session it may run in, or the machine's session list (#65)
    for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(engine, "SESSIONS", tmp_path / "sessions.json")
    return path


def write_question(vault: Path, title: str, status: str = "open", raised: str = "2026-10-01", count="1") -> str:
    rel = f"questions/{title}.md"
    (vault / "questions").mkdir(exist_ok=True)
    (vault / rel).write_text(f"---\nstatus: {status}\nraised: {raised}\nraised_count: {count}\n---\n\n# {title}?\n",
                             encoding="utf-8")
    return rel
