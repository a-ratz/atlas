# AGENTS.md — operating Atlas

You are the user's agent inside an **Atlas vault**: a knowledge base that grows
out of conversation and that the user reads in the browser. This file works for
any harness (Claude Code, Codex, pi, …). Read it fully before acting.

## What is where

```text
engine/              the Atlas web app (Python, run through uv; you rarely edit it)
vault/               the user's knowledge. Plain Markdown files are the truth.
  atlas.yaml         which folder holds which kind of note (the app reads this)
  captures/          raw research results waiting to be distilled
  insights/          atomic claims, one per file; maps are insights/<topic>-map.md
  sources/           processed captures and source notes (provenance)
  research/          optional longer research runs: research/<topic>/<date>/*.md
  questions/         open questions that would change a claim: at most 7 open (atlas-distill, step 5)
  sketches/  specs/  ideas: rough (sketch) and worked out (spec)
  projects/<group>/  projects in groups (private is the default); _group.md holds the group's rules
    <slug>/          project.md + threads/ decisions/ lessons/: one memory, shared by every agent
  you/               the user: goals.md, profile.md (what agents learned; both written when there is
                     something to put in them), notes/ (from: user)
  agents/            one identity file per agent (claude.md, codex.md, …); yours is yours
  cabinet/           who is who: people/ and orgs/, one card per person or organization (see Cabinet)
  tours/             guided tours through what changed, written by agents for the user
.agents/skills/      the workflows below, one folder each (SKILL.md); .claude/skills links here
.atlas-install.json  the factory version of every app file (for upgrade and restore)
```

The app files (`engine/`, `.agents/skills/`, `AGENTS.md`, `CLAUDE.md`) came from
the global `atlas` skill, which also knows where this folder is. You and the user
may edit them: "update atlas" keeps changed files, and "restore <skill>" puts the
factory version back (the global skill's `atlas_install.py`). `vault/` is the
user's and is never overwritten.

## Golden rules

1. **The vault files are the truth.** No databases, no hidden state you rely on.
2. **One claim per insight, and the title is the claim** (a sentence someone
   could disagree with). See `.agents/skills/atlas-distill/SKILL.md`.
3. **Captures before insights.** Research lands in `captures/` first; insights
   come from distilling a capture. Never invent sources; link every factual
   claim to where it came from.
4. **The user's notes stay theirs.** Quote or link `you/notes/`; never rewrite
   them into insights without the user saying so, and never use them as your
   scratchpad.
5. **Say who wrote what.** Every note carries `created_by` and `updated_by`
   (an id from `agents/`, or `user`). Commit with
   `engine/atlas.py commit --agent <id> -m "…" <paths>`, which stamps them; never
   change another agent's identity file.
6. **No third-party tools are required.** Use your harness's own web search and
   file tools. Extras (QMD, social-media CLIs, GitHub CLI) are optional: use
   them only if installed and the user wants them. With QMD on for this vault
   (`qmd.enabled: on` in `atlas.yaml`), search through `atlas-qmd`.
7. **Ask before anything outward-facing or destructive:** publishing, pushing,
   deleting, exposing Atlas beyond localhost.
8. Keep chat answers short; put substance in files and open them for the user.

## Who you are here

Your agent id is the name of your file in `vault/agents/` (Claude Code:
`claude`, Codex: `codex`, unless the user named you differently). If your
file is missing, write it before your first commit (see the atlas-operator skill).

## Start Atlas ("start atlas", "atlas starten")

Follow `.agents/skills/atlas-operator/SKILL.md`. In short:

1. Check `uv --version`. If it is missing, ask the user, then install it:
   `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or
   `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows).
   uv fetches Python and the engine's packages by itself.
2. Start the server so it keeps running after your command returns:
   `uv run --no-project engine/atlas.py serve --operator`
   (Claude Code: run it as a background task. Other harnesses: `nohup … &` or
   your harness's background mode.)
3. Tell the user to open the URL `serve` printed (`engine/atlas.py status` shows it again).
4. Enter the listening loop for your harness (next section).

## Talking with the user through Atlas

The user writes in Atlas's chat. You receive it with `engine/atlas.py wait --agent <id>`
and answer with `engine/atlas.py say --agent <id> "…"`. `<id>` is your agent id
(below): with it, Atlas shows you by name, your progress and the project you
booted, and several agents can listen side by side; the user picks whom a
message goes to. Pick the mode your harness supports:

| Mode | Harness | How you listen |
|---|---|---|
| **A: background + notify** | Claude Code | run `uv run --no-project engine/atlas.py wait --agent <id>` as a background task; its exit wakes you |
| **B: foreground chunks** | Codex, pi, any harness that can run a blocking command | run `uv run --no-project engine/atlas.py wait --agent <id> --timeout 240` in the foreground; on "(no message…)" run it again; shorten `--timeout` if your harness kills long commands |
| **C: standalone** | anything else, or when you are done | stop listening; the user's chat lands in `vault/you/notes/` and you handle it next session |

Every message arrives as `USER [viewing: <path>] [via choice|checklist|widget|move|command]: text`,
followed by a `CABINET` line for each person or organization it names (see Cabinet).
`viewing` is the page the user had open; read it before answering. `via move`
means the user pressed a "Your move" button on that page (Distill, Next research
avenues, …); the text says what they want. `via command` means they typed a
`/command` from the chat's list (table below); a choice or move whose text starts with `/`
runs that command too. When the work takes more than a
minute, post short progress lines with `say --agent <id> --progress "…"` as you go, and
give the first one a title (`--title "Researching loop engineering"`): Atlas shows it above the
conversation. After
answering, run `uv run --no-project engine/atlas.py next` and offer the useful
suggestions as choices. Then listen again (mode A or B).

## Cabinet: people and organizations

`vault/cabinet/people/<name>.md` and `vault/cabinet/orgs/<name>.md` (lowercase ASCII with hyphens: `jan-born.md`) hold one card per
person or organization: who they are, how they relate to the user, contact
details and the projects they touch.
Until 0.6.1 this was the Brain in `vault/brain/`; the engine moves that folder
to `vault/cabinet/` once.

```markdown
---
name: Jan Born
aliases: [Jan Born]       # names that find this card; a first name works while no other card claims it
role: Sleep and memory researcher
org: "[[<organization card>]]"   # people; organizations use kind: and website: instead
relation: co-author of two papers in this vault
email:                    # empty when unknown: never guess an address, a surname or a title
updated: 2026-10-12
created_by: claude
updated_by: claude
---

# Jan Born

The current state in a few sentences. Rewrite it when something changes.

## Timeline

- 2026-10-12 · What happened. (Source: a note, a link, or "conversation with the user")
```

- **Content:** role, relation, contact details, projects. Nothing about private
  life. Public figures may carry public facts with links. Look up a private
  person only through LinkedIn enrichment, and only when the user switched it
  on.
- **Enrichment:** `cabinet.enrich` in `vault/atlas.yaml` (`ask`, `linkedin`,
  `off`) says whether new cards are filled with professional details from
  LinkedIn. The `atlas-cabinet` skill asks once, checks the browser tool and the
  login, and lists what may and may not go on a card.
- **Depth:** distill creates **minimal** cards for the actors of a capture: only
  what the vault says, no lookups (`depth: minimal`). "Expand cards"
  (`/expand-cards`, the 🔎 Expand button) completes them to a fixed profile
  within a budget (`cabinet.expand` in `atlas.yaml`) and sets `depth: complete`.
  The `atlas-cabinet` skill has the profile and the budget.
- **State versus timeline:** the text under the heading is rewritten; the
  timeline only grows, every entry with a date and a source.
- **In chat:** when a message names a card, `wait` adds a line
  `  CABINET <name> (<path>): <role · relation> | <current state>` under it, at
  most three. An alias two cards share matches neither.
- **In the vault:** a card's page lists the notes that mention its name or an
  alias ("Mentioned in") and the notes whose `authors:` name it ("Written by").
  `uv run --no-project engine/atlas.py mentions "<name>"` prints the same lists,
  e.g. for "which insights about Anthropic do we have?".
- **Authors and organizations:** a capture or source from identifiable people
  lists them in `authors:` (who wrote it) and the organizations in `orgs:`.
- **Terminal prompts (Claude Code, optional):** a `UserPromptSubmit` hook with
  the command `uv run --no-project engine/atlas.py recall` attaches the same
  cards to what the user types in the terminal.

## Workflows

| When the user… | Read and follow |
|---|---|
| asks to start or stop Atlas, or you need the chat block syntax | `.agents/skills/atlas-operator/SKILL.md` |
| asks a research question, names a topic, "what's new in…" | `.agents/skills/atlas-learn/SKILL.md` |
| agrees to distill, or captures are waiting | `.agents/skills/atlas-distill/SKILL.md` |
| has five or more insights without a map, or asks for a map | `.agents/skills/atlas-map/SKILL.md` |
| has insights past `revisit_after`, or asks to re-check one against its source | `.agents/skills/atlas-revisit/SKILL.md` |
| says "I have an idea…", or asks for ideas ("give me ideas for…") | `.agents/skills/atlas-sketch/SKILL.md` |
| wants a sketch worked out ("turn this into a spec", `/spec`) | `.agents/skills/atlas-spec/SKILL.md` |
| wants a card for a person or organization, asks to look someone up, or to expand cards | `.agents/skills/atlas-cabinet/SKILL.md` |
| looks for notes by meaning, or wants QMD turned on, off or repaired | `.agents/skills/atlas-qmd/SKILL.md` |
| names a project to work on, "new project", closes a session | `.agents/skills/atlas-project/SKILL.md` |
| wants the demo notes gone ("clean the demo", "start fresh") | `.agents/skills/atlas-clean-demo/SKILL.md`; to load them: `engine/atlas.py demo` |

**Chat commands.** Typing `/` in Atlas lists these (they live in
`vault/atlas.yaml` under `commands:`, so the user can add their own):

| Command | Do this |
|---|---|
| `/learn <topic>` | atlas-learn |
| `/distill [capture \| all]` | atlas-distill, on the named capture, the one the user is viewing, the oldest, or (`all`) every waiting capture |
| `/map [theme]` | atlas-map |
| `/revisit [insight \| all]` | atlas-revisit: the named insight, the one the user is viewing ("this insight"), or (`all`) the due ones, five per run |
| `/sketch <idea> \| ideas for <goal>` | atlas-sketch: capture the idea, or generate ideas from the vault |
| `/spec [sketch]` | atlas-spec, on the named sketch or the one the user is viewing |
| `/project <name>` | atlas-project: start |
| `/close` | atlas-project: close (also outside a project: commit what you wrote, say what is next) |
| `/expand-cards [name]` | atlas-cabinet, section 4: complete the minimal cards (or the one named) within the budget |
| `/remember <fact>` | add it to `vault/you/profile.md` as `- <fact> (told by the user, YYYY-MM-DD)`; the user's own words beat anything an agent inferred |
| `/check` | run `engine/atlas.py check`, fix what it reports, commit |
| `/next` | run `engine/atlas.py next` and offer the suggestions as choices |
| `/tour [since]` | atlas-operator: Tours (a guided walk through what changed since that date) |

A command you do not know: say so, and show what `/` lists.

## Commands

```bash
uv run --no-project engine/atlas.py serve [--operator] [--port 8765] [--vault DIR]   # --vault works before or after the command
uv run --no-project engine/atlas.py wait --agent <id> [--timeout SECONDS]
uv run --no-project engine/atlas.py say --agent <id> "text" [--open <vault path>]   # "-" reads stdin
uv run --no-project engine/atlas.py say --agent <id> --progress "Reading 6 sources…"  # status line while you work
uv run --no-project engine/atlas.py say --agent <id> --progress "…" --title "Researching X"  # what you are doing, shown above the conversation
uv run --no-project engine/atlas.py light --agent <id> "Topic" <note>... [--say "text"]   # light up notes in the constellation; "-" reads one per line
uv run --no-project engine/atlas.py next      # counts + suggested next steps (JSON)
uv run --no-project engine/atlas.py check     # notes with broken links, bad frontmatter or no connection (exit 1)
uv run --no-project engine/atlas.py boot [<project>] --agent <id> [--checkout DIR]   # your context for a project
uv run --no-project engine/atlas.py commit --agent <id> -m "msg" <paths>   # stamp created_by/updated_by, commit only these
uv run --no-project engine/atlas.py machine   # this machine's key in project paths
uv run --no-project engine/atlas.py map-path <project> <dir>   # record (and verify) a checkout on this machine
uv run --no-project engine/atlas.py status
```

## Windows

Atlas runs on Windows through uv as well. Two differences:
- `.claude/skills` is a symlink and may arrive as a plain file. The skills
  are still at `.agents/skills/`; follow them by path.
- Use PowerShell equivalents for `nohup`/`pkill` (see the atlas-operator skill).

## Git

If the vault is in a git repository, commit after each finished workflow with
`engine/atlas.py commit --agent <id> -m "learn: …" <paths you wrote>`. It
commits only those paths, keeps an existing `created_by`, sets `updated_by`, and
refuses when unrelated changes are staged. Never push unless the user asks.
