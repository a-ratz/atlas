# Atlas

A knowledge vault you grow by talking to your agent, and read in the browser.

You ask a question in Atlas's chat. Your agent researches it, and you watch the
first captures come in. They get distilled into insights; once a few exist,
Atlas suggests maps; "I have an idea" becomes a sketch. Everything is plain
Markdown in `vault/`, in your own git repository. No database, no account,
no onboarding.

## Quickstart

1. Install the skill once, for every agent harness on this machine:
   `npx skills add a-ratz/atlas -g -s atlas`.
2. In Claude Code, Codex or any other harness, say **"start atlas"**. The first
   time, it asks where Atlas should live (default `~/atlas`) and installs it
   there; this folder is then your Atlas. It also offers demo notes, so you
   can try a full vault at once; "clean the demo" removes them again.
3. Open **http://localhost:8765** and type what you are curious about, or `/`
   for commands.

The agent needs [uv](https://docs.astral.sh/uv/) to run the engine and installs
it after asking you if it is missing. uv brings Python and the engine's
packages along; nothing else is required.

**Optional extras:**
- git, for the "what changed" feed and history.
- [QMD](https://github.com/tobi/qmd), for semantic deep search.
- Tailscale, to open Atlas on your phone.

## What you get

- **Home:** what changed, what needs you (snooze a row until tomorrow, next
  week or next month), the latest ideas and research.
- **Tours:** your agent walks you through what changed since your last visit,
  stop by stop, and marks what needs your call. Atlas checks every quoted
  passage and lists every changed note the tour leaves out.
- **Chat with your agent,** whose answers can contain notes you unfold in
  place, charts, choices, checklists and live mockups.
- **Every kind of note** with filters, and a reader with backlinks and a note
  on how far to trust the page. Hover a link to see where it goes; select a
  passage to ask your agent about it or challenge it.
- **⌘K / Ctrl+K** to jump to any note, project or place; `>` lists the chat
  commands.
- **Drop a file or a link** on Atlas: it lands in `captures/` and your agent
  takes it from there.
- **A graph of everything,** once there is something to graph.
- **Your move on any page:** buttons that fit the kind of note (a capture:
  distill, next research avenues, dig deeper; an insight: find connections,
  challenge it), plus keep, let go or leave a note (undo within five seconds). The agent reads it.

The navigation shows every kind of note with its count, and lights up where
something new arrived since you last looked.

- **Projects** in groups (private, work, …) with group rules and one shared
  memory per project (threads, decisions, lessons). Any agent loads it with
  `atlas.py boot <project> --agent <id>`.
- **You and your agents:** your goals, profile and notes; one identity file per
  agent; every note says which agent wrote and last edited it.
- **Commands in the chat:** type `/` to see them (`/learn`, `/distill`,
  `/project`, `/close`, …). Add your own in `vault/atlas.yaml`.

## Layout

```text
engine/        the web app (Python; `uv run --no-project engine/atlas.py --help`)
vault/         your knowledge (Markdown) and atlas.yaml, which says which folder is what
.agents/skills the agent workflows: atlas-operator, atlas-learn, atlas-distill, atlas-map,
               atlas-sketch, atlas-project (.claude/skills links here)
AGENTS.md      instructions for any agent harness (CLAUDE.md imports it)
.atlas-install.json  the factory version of every app file, for `upgrade` and `restore`
```

Status: early prototype (v0). See `docs/design-notes.md` in the Atlas repository for decisions, known
limits and the empty-vault test plan.
