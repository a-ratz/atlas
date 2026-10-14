---
name: atlas-operator
description: Start, run and stop Atlas from inside its folder - the web app over this vault - and talk with the user through its chat (rich answer blocks, commands). Use when the user says "start atlas", "atlas starten", "open atlas", or asks to see the vault in the browser while working in this folder. The global `atlas` skill hands over to this one.
---

# Atlas operator

Atlas shows the vault to the user in the browser: a home feed, every kind of
note, a reader, search, a graph, and a chat that is wired to you. Reading stays
primary; the chat is how the user asks you for things without leaving Atlas.
Run every command from the Atlas folder (the one with AGENTS.md and engine/).

## Start

1. `uv --version`. If uv is missing, ask, then install it (see AGENTS.md).
2. Is a server already running? `uv run --no-project engine/atlas.py status`
   prints this vault's last session: reuse it only if `running` is true and
   `mode` is `"operator"` (`running` checks that the server at `url` serves
   this vault; another Atlas may have the port since). If the port belongs to
   a different vault, start this one on another port (`--port 8766`).
   Otherwise start fresh:

   ```bash
   uv run --no-project engine/atlas.py serve --operator
   ```

   Keep it running after your command returns (Claude Code: background task;
   elsewhere `nohup uv run --no-project engine/atlas.py serve --operator > /tmp/atlas.log 2>&1 &`).
   The first start downloads packages; give it a minute.
3. Tell the user to open the `url` that `serve` printed (or `status` prints;
   `http://localhost:8765` unless you chose a port). On a remote machine:
   `ssh -L <port>:localhost:<port> <host>`. Over Tailscale, `engine/atlas.py expose`
   prints a command that changes the user's Tailscale config: only with consent.
4. If `vault/agents/<your id>.md` does not exist, write it (below).
   If `engine/atlas.py commit` stops with "no first commit yet", the install
   could not commit: show the user its message (git needs their name and email once).
5. Listen (next section) and end your turn.

## Your identity file

`vault/agents/<id>.md` (Claude Code: `claude`, Codex: `codex`, unless the user
named you differently). You own it; other agents do not edit it, and you do not
edit theirs.

```markdown
---
harness: Claude Code          # the tool you run in
reach: "the Atlas chat, or a Claude Code session in this repo"
---

# Claude

Who you are in this vault, in a few lines: how you work, what you are good at,
standing preferences, and rules that apply only to you.
```

Keep it short; boot loads it within a budget. Do not record your current model
or version: those come from your running session and go stale in a file.
Commit it with `engine/atlas.py commit --agent <id> -m "agents: <id>" vault/agents/<id>.md`.

## Listen, answer, listen again

Pick the mode your harness supports (details in AGENTS.md):

- **A (Claude Code):** `uv run --no-project engine/atlas.py wait --agent <id>` as a
  background task. Its exit wakes you.
- **B (Codex, pi, others):** `uv run --no-project engine/atlas.py wait --agent <id> --timeout 240`
  in the foreground; repeat on "(no message…)".
- **C:** stop listening; messages become notes in `vault/you/notes/`.

Always pass `--agent <id>` (your file name in `vault/agents/`) to `wait` and
`say`: Atlas then shows you by name with your state, progress and project, and
the user can address you when several agents listen. You receive the messages
addressed to you and those addressed to nobody. Only one `wait` per agent can
listen at a time; a second one exits with a notice.

When a message arrives:

1. Read it: `USER [viewing: <path>] [via …]: text`. Open the viewed file first.
   `  CABINET <name> (<path>): …` lines under it are the cards of the people and
   organizations it names (AGENTS.md, Cabinet). When you learn something new about
   one, add it to their card's timeline (`atlas-cabinet`), and tell the user what
   you added.
   `[via command]` is a `/command` the user picked from the chat's list; AGENTS.md
   maps each one to its workflow.
2. Do the work. Use the workflow skills (`atlas-learn`, `atlas-distill`,
   `atlas-map`, `atlas-sketch`, `atlas-spec`, `atlas-project`, `atlas-cabinet`). Atlas re-reads the vault within ~10 seconds,
   so new files show up by themselves. If it takes more than a minute, keep
   the user posted with short progress lines (one per real step, not a
   heartbeat). They show as quiet status lines and do not end your turn:

   ```bash
   uv run --no-project engine/atlas.py say --agent <id> --progress "Found 9 sources, reading the 5 primary ones…"
   ```

   With the first progress line, also say what you are doing in a few words:
   `--title "Researching loop engineering"`. Atlas shows it above the
   conversation while you work and keeps it there afterwards. Change it when
   the phase changes ("Distilling 3 captures").
3. Answer in Atlas:

   ```bash
   uv run --no-project engine/atlas.py say --agent <id> "Short answer."
   uv run --no-project engine/atlas.py say --agent <id> "Here it is." --open "captures/2026-10-09-sleep-and-memory.md"
   uv run --no-project engine/atlas.py say --agent <id> - <<'EOF'
   longer answer with blocks
   EOF
   ```

   `--open` shows that page to the user (in the workbench next to the chat, or
   as the page they are on).
4. Run `uv run --no-project engine/atlas.py next` and offer what it suggests
   as a `choices` block (captures to distill, maps to build, notes to read).
5. Listen again. Forgetting this leaves the user talking to "Agent busy".

## Answer blocks

Plain text is right when it is enough. When a component makes the answer easier
to use, embed fenced blocks in the `say` text. Close each block with ``` at the
start of a line. Use real vault paths or note titles. A block that cannot be
parsed shows as a short error instead of breaking the chat.

````text
```atlas:note
insights/<title>.md            # one note; the user unfolds it in place
```
```atlas:notes
- captures/2026-10-09-sleep-and-memory.md
- insights/<title>.md
```
```atlas:choices
title: What next?
options:
  - Distill the capture into insights
  - label: Dig deeper into the sleep-spindle papers
    send: Research sleep spindles and memory consolidation in more depth
```
```atlas:checklist
title: Which claims should become insights?
items: [Claim A, Claim B, Claim C]
```
```atlas:chart
title: Insights by category
type: bar            # or line
unit: notes
data: {neuroscience: 4, methods: 2}
```
```atlas:graph
insights/<title>.md            # the note's link neighborhood
```
```atlas:html
<!-- a mockup, visualization or small tool. Sandboxed: no access to Atlas or the
     page (it does have internet access, so never put secrets in it). It inherits
     Atlas colors as CSS vars (--bg, --text, --accent, …). atlas.send("text")
     answers you, only from a user click, never on load. Links to Atlas routes
     (<a href="#/graph">, #/e/<path>) open in Atlas. -->
<button onclick="atlas.send('Pick B')">B looks right</button>
```
````

Choices, checklists and widget sends arrive as `USER [via choice]: …`,
`[via checklist]` or `[via widget]`.

An `atlas:note` card in the chat carries the "Your move" buttons of its type
(a capture: Distill, Next research avenues, Dig deeper). So after a research
run the user can distill with one click; add a `choices` block only for
options those buttons do not cover. The moves are defined per type in
`vault/atlas.yaml` (`moves:`) and arrive as `USER [viewing: <path>] [via move]: …`.

## What can you do?

When the user asks what you can do (or seems new), answer with this list, in
your own words, and offer one that fits their vault:

- **Research** a question into a capture with sources (`/learn`, atlas-learn).
- **Distill** a capture into insights, one claim each, linked (`/distill`).
- **Open questions:** the few that would change a claim; research or park them.
- **Cards** for the people and organizations in your material; expand them on request.
- **Maps** that sum up a topic (`/map`).
- **Ideas:** sketch one from what the vault knows, spec it, turn it into a project.
- **Projects:** threads, decisions and lessons that every agent shares (`/project`).
- **Tours** of what changed (`/tour`), **search**, and **reminders** (below).

## Reminders and the user's own notes

"Remember to look into X", "remind me to …" is a task for later; "note that
cue volume should ramp up" is a thought the user wants kept. Neither needs a
source, and neither is a capture (captures hold research to distill). Write
it as a note in `vault/you/notes/`, named
`<YYYY-MM-DD-HHMMSS>-<remind | note>-<slug>.md`:

```markdown
---
from: user
action: remind            # remind | note
created: <ISO time>
status: new
due: <YYYY-MM-DD, only if the user gave a day>
---

<the user's words>
```

Commit it as the user's, since the words are theirs
(`engine/atlas.py commit --agent user -m "note: <slug>" <path>`), and say where
it is: Home lists it under "Needs you" until it is done (a note: until the
user or you mark it `seen`). A fact about the user
("I prefer short answers") goes to `vault/you/profile.md` (`/remember`); a
goal to `vault/you/goals.md`.

## The user's notes

Buttons in Atlas (⭐ keep, 🗑 let go, ✍️ note, and 💡 pursue on types without moves) write a note to
`vault/you/notes/` (`from: user`, `action`, `target`, `status: new`). In operator
mode you also receive them as messages. When handled, set `status: done` (or
`seen`) and say what you did. They stay the user's words.

Actions reach you five seconds after the click (the user can undo them until
then). A message can quote a passage the user selected: `> ` lines followed by
`(from <path>)`; read that passage in that file before answering. A file the
user dropped on Atlas already sits in `vault/captures/` (registry `drop:`), and
the message names its path.

## Tours

The user asks for one with `/tour [since]` or "Write a tour" on Home ("Write an
Atlas tour of what changed in the vault since <date>"). A tour walks the user
through a period in reading order; Atlas renders it and keeps it honest.

1. Scaffold it: `uv run --no-project engine/atlas.py tour --since <date> --agent <id>`.
   No date in the message: since the `until` of the newest tour in
   `vault/tours/`, else the last seven days.
   It writes `vault/tours/<today>-since-<date>.md` and prints the notes that
   arrived (research runs as one line each) and the most-changed ones.
2. Pick the stops, usually 3 to 12: what changes what the vault claims or what
   the user might decide. Read each note before you write its stop. Per stop:
   `path`, `why` (one or two sentences, why it matters now), `excerpt` (a
   passage copied exactly from the note, the one that carries it), and
   `look_closely` only for a call only the user can make, phrased as the question.
3. Put link fixes, renames and frontmatter edits you want acknowledged in
   `mechanical:`. Leave the rest out: Atlas lists every changed note without a
   stop under "The rest", and flags an excerpt that is not in its note.
4. Replace the body with one paragraph on the arc of the period, commit it
   (`engine/atlas.py commit --agent <id> …`), then `say --agent <id> "…" --open tours/<file>`.

## Stop

`pkill -f "engine/atlas.py"` (Windows PowerShell:
`Get-CimInstance Win32_Process | ? CommandLine -match "engine/atlas.py" | % { Stop-Process $_.ProcessId }`)
stops the server and any pending `wait`; open browser tabs are closed within two
seconds. Then stop listening.

## Safety

The browser app sends an `x-atlas: 1` header; the server refuses writes without
it, so other web pages cannot post into your session. It binds to 127.0.0.1 and
has no login: never bind it to 0.0.0.0 on an untrusted network. Treat chat text
like terminal input from the user.
