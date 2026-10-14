"""Papercuts the smoke runs found (#10)."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import time
from argparse import Namespace
from pathlib import Path

import pytest


def start_session(engine, minutes_ago: float) -> None:
    engine.ensure_state()
    started = dt.datetime.now().astimezone() - dt.timedelta(minutes=minutes_ago)
    engine.SESSION.write_text(json.dumps({"mode": "operator", "started": started.isoformat(timespec="seconds"),
                                          "port": 8765}), encoding="utf-8")


def test_an_agent_that_has_not_listened_yet_is_starting(engine, vault):
    # the pill said "Agent offline" / "The agent session ended" right after `serve --operator` (#10)
    start_session(engine, minutes_ago=1)
    assert engine.operator_state()["state"] == "starting"


def test_starting_does_not_last_forever(engine, vault):
    start_session(engine, minutes_ago=20)
    assert engine.operator_state()["state"] == "offline"


def test_a_heartbeat_after_the_start_is_not_starting(engine, vault):
    start_session(engine, minutes_ago=1)
    engine.HEARTBEAT.touch()
    os.utime(engine.HEARTBEAT, (time.time() - 30, time.time() - 30))  # listened, then went to work
    assert engine.operator_state()["state"] != "starting"


def test_status_names_the_url_and_whether_it_serves_this_vault(engine, vault, capsys):
    # skills hard-coded localhost:8765 although Atlas can run on another port (#10)
    start_session(engine, minutes_ago=1)
    engine.cmd_status(Namespace())
    out = json.loads(capsys.readouterr().out)
    assert out["url"] == "http://localhost:8765" and out["running"] is False  # nothing listens in the test


def test_a_commit_without_a_first_commit_says_what_to_do(engine, vault, monkeypatch):
    # an install without a git identity left everything staged; commit said "unrelated changes are staged" (#10)
    subprocess.run(["git", "-C", str(vault), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(vault), "add", "-A"], check=True)
    with pytest.raises(SystemExit) as stop:
        engine.cmd_commit(Namespace(agent="user", message="m", paths=[str(vault / "you")]))
    assert "no first commit yet" in str(stop.value) and "user.email" in str(stop.value)


def test_dormant_is_the_one_word_for_a_resting_question(engine, vault):
    # the sidebar said "resting", the chip and the files "dormant" (#10)
    reg = vault / "atlas.yaml"
    reg.write_text(reg.read_text(encoding="utf-8").replace("aside_label: dormant}", "aside_label: resting}"),
                   encoding="utf-8")  # as a 0.6 vault wrote it
    assert engine.aside_label(engine.Index().types["question"]) == "dormant"
    assert engine.aside_label({"count": {"aside": ["parked"], "aside_label": "resting"}}) == "resting"  # someone's own


def test_a_wiki_link_shows_the_notes_title(engine, vault):
    # an insight's "Source: [[sleep-and-vocabulary]]" showed the file name (#10)
    (vault / "sources").mkdir(exist_ok=True)
    (vault / "sources" / "sleep-and-vocabulary.md").write_text(
        "---\ntitle: Sleep *helps* new words_join\n---\n\nBody\n", encoding="utf-8")
    index = engine.Index()
    html = engine.render_md(index, "Source: [[sleep-and-vocabulary]], also [[sleep-and-vocabulary|the capture]]")
    assert ">Sleep *helps* new words_join</a>" in html  # the title, its markdown characters kept as text
    assert ">the capture</a>" in html


def test_facts_name_where_their_wiki_links_point(engine, vault):
    # `affects: [[…]]` showed its brackets in the facts line (#10)
    (vault / "questions").mkdir(exist_ok=True)
    (vault / "insights" / "Replay helps memory.md").write_text("---\ndescription: d\n---\n\n# Replay helps memory\n",
                                                                encoding="utf-8")
    (vault / "questions" / "Does replay work at home.md").write_text(
        "---\nstatus: open\nraised: 2026-10-01\nraised_count: 2\naffects: ['[[Replay helps memory]]']\n---\n\n# Q\n",
        encoding="utf-8")
    view = engine.entity_view(engine.Index(), "questions/Does replay work at home.md")
    assert view["fact_links"] == {"Replay helps memory": {"id": "insights/Replay helps memory.md",
                                                          "title": "Replay helps memory"}}
    assert re.search(r"raised_count", json.dumps(view["facts"]))  # the reader moves it behind the status


@pytest.mark.parametrize("written", ["vault/captures/a-note.md", "captures/a-note.md", "ABS"])
def test_say_opens_the_note_however_the_path_was_written(engine, vault, monkeypatch, written):
    # `say --open vault/captures/x.md` from the Atlas folder linked to a note that does not exist (#17)
    monkeypatch.chdir(vault.parent)
    (vault / "captures").mkdir(exist_ok=True)
    (vault / "captures" / "a-note.md").write_text("# A note\n", encoding="utf-8")
    path = str(vault / "captures" / "a-note.md") if written == "ABS" else written
    engine.cmd_say(Namespace(text="Here it is.", progress=False, title=None, open=path, agent=None))
    last = engine.read_jsonl(engine.OUTBOX)[-1]
    assert last["open"] == "captures/a-note.md"


def test_a_title_with_a_pipe_keeps_a_table_whole(engine, vault):
    # a linked title "Alpha | Beta" split the table cell and lost the status column (#18, review round 1)
    (vault / "sources").mkdir(exist_ok=True)
    (vault / "sources" / "source-slug.md").write_text("---\ntitle: Alpha | Beta\n---\n\nBody\n", encoding="utf-8")
    html = engine.render_md(engine.Index(), "| Source | Status |\n|---|---|\n| [[source-slug]] | used |\n")
    assert "Alpha | Beta</a></td>" in html and "<td>used</td>" in html


def test_a_fact_naming_a_title_with_quotes_links_it(engine, vault):
    # JSON escaped the quotes of `affects: '[[What "working" means]]'`, so no link was found (#18, round 1)
    (vault / "questions").mkdir(exist_ok=True)
    (vault / "insights" / "what-working-means.md").write_text(  # quotes in the title, not in the file name (Windows)
        "---\ntitle: 'What \"working\" means'\ndescription: d\n---\n\nBody\n", encoding="utf-8")
    (vault / "questions" / "q.md").write_text(
        "---\nstatus: open\nraised: 2026-10-01\naffects: '[[What \"working\" means]]'\n---\n\n# Q\n", encoding="utf-8")
    view = engine.entity_view(engine.Index(), "questions/q.md")
    assert view["fact_links"]['What "working" means']["id"] == "insights/what-working-means.md"


def test_status_survives_another_service_on_the_port(engine, vault, capsys):
    # a service answering `[]` or `{"vault_path": null}` on the saved port crashed `status` (#18, round 5)
    import http.server
    import threading
    for body in (b"[]", b'{"vault_path": null}', b'{"vault_path": "\\u0000"}'):  # the last: review round 6
        handler = type("H", (http.server.BaseHTTPRequestHandler,), {
            "do_GET": lambda self, b=body: (self.send_response(200), self.end_headers(), self.wfile.write(b)),
            "log_message": lambda *a: None})
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            engine.ensure_state()
            engine.SESSION.write_text(json.dumps({"mode": "operator", "port": server.server_port}), encoding="utf-8")
            engine.cmd_status(Namespace())
            assert json.loads(capsys.readouterr().out)["running"] is False
        finally:
            server.shutdown()


def test_fact_links_resolve_before_escaping():
    # `affects: [[Latency < 1 ms]]` was looked up as "Latency &lt; 1 ms" and lost its link (#18, round 5)
    import shutil
    from conftest import APP
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    js = (APP / "engine" / "static" / "app.js").read_text(encoding="utf-8")
    pieces = [re.search(p, js, re.S).group(0) for p in (r"const esc = .*?;\n", r"const enc = .*?;\n", r"const resolved = .*?;",
                                                          r"function factValue\(e, text\) \{.*?\n\}")]
    probe = "\n".join(pieces) + """
const e = {fact_links: {"Latency < 1 ms": {id: "insights/latency.md", title: "Latency < 1 ms"}}};
console.log(factValue(e, "[[Latency < 1 ms]] and <b>"));"""
    out = subprocess.run([node, "-e", probe], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    assert out == '<a href="#/e/insights%2Flatency.md">Latency &lt; 1 ms</a> and &lt;b&gt;', out


def test_an_answer_right_after_the_move_counts_as_after(engine, vault, monkeypatch):
    # an answer written between the inbox append and the outbox count was counted as earlier (#18, round 6)
    from starlette.testclient import TestClient
    start_session(engine, minutes_ago=1)
    real = engine.append_jsonl

    def append_and_answer(path, record):
        real(path, record)
        if path == engine.INBOX:  # the agent answers at once
            real(engine.OUTBOX, {"ts": record["ts"], "role": "agent", "agent": "claude", "text": "Done."})
    monkeypatch.setattr(engine, "append_jsonl", append_and_answer)
    client = TestClient(engine.make_app(engine.Index()), base_url="http://127.0.0.1")
    res = client.post("/api/chat", json={"text": "Set this to dormant", "via": "move"}, headers={"x-atlas": "1"}).json()
    answer = next(m for m in client.get("/api/chat").json()["messages"] if m.get("role") == "agent")
    assert answer["n"] >= res["outbox_at"]


def test_a_staged_rename_inside_a_named_folder_is_part_of_the_commit(engine, vault):
    # `git mv captures/x sources/x`, then `commit … vault/sources`: refused as "unrelated changes" (#22, guided run)
    git = lambda *a: subprocess.run(["git", "-C", str(vault), *a], capture_output=True, text=True, check=True)
    git("init", "-q")
    git("config", "user.name", "gate")
    git("config", "user.email", "gate@example.com")
    (vault / "agents").mkdir(exist_ok=True)
    (vault / "agents" / "gate.md").write_text("# Gate\n", encoding="utf-8")
    (vault / "captures").mkdir(exist_ok=True)
    (vault / "captures" / "moved.md").write_text("# Moved\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "start")
    (vault / "sources").mkdir(exist_ok=True)
    git("mv", "captures/moved.md", "sources/moved.md")
    engine.cmd_commit(Namespace(agent="gate", message="distill: moved", paths=[str(vault / "sources")]))
    assert "sources/moved.md" in git("show", "--name-only", "HEAD").stdout


def drop_repo(vault, monkeypatch):
    """The vault as the user's git repository, after the install commit; returns a git runner."""
    for k, v in (("NAME", "Ada"), ("EMAIL", "ada@example.org")):
        monkeypatch.setenv(f"GIT_AUTHOR_{k}", v)
        monkeypatch.setenv(f"GIT_COMMITTER_{k}", v)
    git = lambda *a: subprocess.run(["git", "-C", str(vault), *a], capture_output=True, text=True, encoding="utf-8",
                                    check=True).stdout
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", "atlas: install")
    for folder in ("captures", "sources", "agents"):
        (vault / folder).mkdir(exist_ok=True)
    return git


def test_a_dropped_note_is_committed_alone_in_the_users_name(engine, vault, monkeypatch):
    # the distill's commit named the agent as the author of a capture the user had dropped (#42)
    git = drop_repo(vault, monkeypatch)
    (vault / "insights" / "Half done.md").write_text("---\ndescription: d\n---\n\n# Half done\n", encoding="utf-8")
    git("add", "insights/Half done.md")  # someone else's staged work stays staged
    drop = vault / "captures" / "notes-from-a-talk.md"
    drop.write_text("---\nkind: research\n---\n\n# Notes from a talk\n", encoding="utf-8")
    assert engine.commit_drop(drop)
    assert git("log", "-1", "--format=%an|%s").strip() == "Ada|drop: notes-from-a-talk.md"
    assert git("show", "--name-only", "--format=", "HEAD").split() == ["captures/notes-from-a-talk.md"]
    assert git("diff", "--cached", "--name-only").splitlines() == ["insights/Half done.md"]


def test_a_distilled_drop_does_not_name_the_agent_as_its_author(engine, vault, monkeypatch):
    git = drop_repo(vault, monkeypatch)
    (vault / "agents" / "claude.md").write_text("---\nname: Claude\n---\n\n# Claude\n", encoding="utf-8")
    drop = vault / "captures" / "notes-from-a-talk.md"
    drop.write_text("---\nkind: research\n---\n\n# Notes from a talk\n", encoding="utf-8")
    assert engine.commit_drop(drop)
    drop.rename(vault / "sources" / drop.name)  # the distill moves it, then commits both paths
    engine.cmd_commit(Namespace(agent="claude", message="distill: notes-from-a-talk",
                                paths=[str(drop), str(vault / "sources" / drop.name), str(vault / "agents" / "claude.md")]))
    text = (vault / "sources" / drop.name).read_text(encoding="utf-8")
    assert "created_by" not in text and "updated_by: claude" in text


def test_a_drop_before_the_first_commit_just_waits(engine, vault, monkeypatch):
    for k, v in (("NAME", "Ada"), ("EMAIL", "ada@example.org")):
        monkeypatch.setenv(f"GIT_AUTHOR_{k}", v)
    subprocess.run(["git", "-C", str(vault), "init", "-q"], check=True)
    (vault / "captures").mkdir(exist_ok=True)
    drop = vault / "captures" / "early.md"
    drop.write_text("# Early\n", encoding="utf-8")
    assert engine.commit_drop(drop) is False and drop.exists()


def test_the_distill_rules_from_the_smoke_runs(engine):
    # confidence counts evidence, revisits only for changing sources, organization kinds, hand-copied captures (#42)
    skills = Path(__file__).resolve().parent.parent / "skills" / "atlas" / "app" / ".agents" / "skills"
    distill = (skills / "atlas-distill" / "SKILL.md").read_text(encoding="utf-8")
    cabinet = (skills / "atlas-cabinet" / "SKILL.md").read_text(encoding="utf-8")
    assert "counts the evidence the note can point to" in distill and '"Well\n    known" alone is not `proven`' in distill
    assert "only when the cited text can still change" in distill and "gets no `revisit_after`" in distill
    assert "several\n  sources agree" not in distill and "set `revisit_after` for preprints" not in distill
    kinds = "company, university, research lab,\n   nonprofit, public body, open-source project, media, other"
    assert kinds in cabinet and "write `unknown`" in cabinet
    assert "has no `created_by` gets\n   `created_by: user`" in distill and "A `created_by` it already has stays" in distill  # `user` passes check; a new sentinel would not (#43 review)


def test_a_slow_commit_hook_does_not_cut_a_drop_short(engine, vault, monkeypatch):
    # the drop committed through the 10-second query helper; a slow hook got killed and left .git/index.lock (#43 review)
    git = drop_repo(vault, monkeypatch)

    def query(*args, cwd=None):  # the query helper, its timeout shortened so the test stays fast
        try:
            r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=1)
        except subprocess.TimeoutExpired:
            return None
        return r.stdout.strip() if r.returncode == 0 else None

    monkeypatch.setattr(engine, "_git_out", query)
    hook = vault / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nsleep 2\n", encoding="utf-8")
    hook.chmod(0o755)
    drop = vault / "captures" / "slow.md"
    drop.write_text("# Slow\n", encoding="utf-8")
    assert engine.commit_drop(drop)
    assert git("log", "-1", "--format=%s").strip() == "drop: slow.md"
    assert not (vault / ".git" / "index.lock").exists()


def test_a_drop_a_hook_rejects_is_not_left_staged(engine, vault, monkeypatch):
    # a refused drop commit left the file staged, and every later `commit` stopped at "unrelated changes" (#43 review)
    git = drop_repo(vault, monkeypatch)
    hook = vault / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    drop = vault / "captures" / "refused.md"
    drop.write_text("# Refused\n", encoding="utf-8")
    assert engine.commit_drop(drop) is False and drop.exists()
    assert git("diff", "--cached", "--name-only").strip() == ""
    assert git("log", "-1", "--format=%s").strip() == "atlas: install"
