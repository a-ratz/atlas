---
name: atlas-project
description: Work on a project that lives in the vault - load its memory, group rules and checkout with `atlas.py boot`, keep its threads, decisions and lessons current, close the session with a handoff, and catch up sessions that ended without /close. Use when the user says "/project <name>", "let's work on <project>", "new project", "/close", "close the session", when boot, `next` or a start hook lists sessions that ended without /close, after a compaction asks for a checkpoint, or when you notice something during project work that is worth remembering.
---

# Projects

Every project has one memory that all agents share. Nobody keeps a private
copy of it:

```text
vault/projects/<group>/_group.md              rules of the group (private is the default)
vault/projects/<group>/<slug>/project.md      what the project is, its repo, paths per machine
vault/projects/<group>/<slug>/threads/        ongoing topics: the handoff lives here
vault/projects/<group>/<slug>/decisions/      choices and why; accepted ones are constraints
vault/projects/<group>/<slug>/lessons/        "when X, do Y", learned in this project
```

`<id>` below is your agent id: the name of your file in `vault/agents/`.

## Start: `/project <name>`

1. Load the project:

   ```bash
   uv run --no-project engine/atlas.py boot <name> --agent <id>
   ```

   Read all of it. If the name is unknown or ambiguous, boot says so: ask
   the user (an Atlas `choices` block with the candidates), or offer to create
   the project (below).
2. **Checkout.** Boot says whether the code was found on this machine and
   whether its git remote matches the project's `repo`.
   - Unresolved: ask the user where the checkout is, or whether there is
     code at all. Then `uv run --no-project engine/atlas.py map-path <name> <dir>`,
     which checks the repo before it writes the mapping.
   - For one session in another checkout (a worktree, say), run
     `boot … --checkout <dir>`.
   - Never guess a path. Never touch code while the checkout is unresolved.
3. **Rules.** The group rules in boot apply to everything you do in this
   project. If a request conflicts with one, say so and ask.
4. Tell the user, in two lines, where the project stands (open threads,
   blockers) and what you will do next.

## A new project

The group is `private` unless the user names another. Create
`vault/projects/<group>/<slug>/project.md`:

```markdown
---
description: One sentence about the project
status: active            # active | paused | done
repo: https://github.com/owner/repo   # if there is code
aliases: []               # other names the user uses for it
source: "[[<spec>]]"      # the spec (or sketch) it came from, if any
---

# <Project name>

What it is, for whom, and why it exists.
```

**From a spec** ("Start a project" on a spec, `atlas-spec` step 7): `source:`
names the spec. Write one thread for the spec's first slice, with `next:` its
first step. If the spec asks build or adopt, write that as a decision with
`status: proposed`. Then set the spec's `status: building`. Atlas shows the
line project → spec → sketch in the project's margin.

If there is a checkout on this machine, record it with `map-path`, not by
hand. No code yet (a project from a spec, say): leave out `repo:` and say so
in a sentence of `project.md`; boot then reports "no code yet" instead of an
unmapped checkout. Once a repository exists, `map-path` records it. A new group
is just a new folder with a `_group.md`.

## While you work

**Threads** carry the handoff, one per ongoing topic.
`threads/<slug>.md`:

```markdown
---
status: open              # open | closed
next: the exact next action
blocked: what blocks it   # leave out when nothing does
branch: feature-x         # only when the thread belongs to one branch
---

# <Topic>

What this thread is about.

## Log
- 2026-10-10 (claude): what happened, what was verified, what was not.
```

Whoever works a thread updates its `next` and `blocked`. Add log lines; never
rewrite another agent's lines. Update a thread when you get blocked or
interrupted, not only at the end. A log line that turns out wrong or
overstated stays; add a dated correction that names it. A bug gets its own
thread, even when it is fixed in the same session: close it once the fix is
verified, with a reopen condition in `next:`, and reopen it when the reporter
says it still happens. A log line says what was verified and how
(the command, how many checks), and what was not; longer evidence goes into a
file in the repository, and the line points to it. A `[[link]]` in `next:` or
`blocked:` shows as a link on the project page; `boot` prints it as text.

**Decisions:** `decisions/<slug>.md`. Frontmatter:

- `status: proposed | accepted | superseded`;
- `date`;
- `superseded_by: "[[newer decision]]"` when one replaces it;
- `branch`, only when it holds on one branch.

The body gives the decision, why it was taken (and what was rejected), and its
consequences. An accepted decision is a constraint on every later session,
whatever its age. Supersede it; never delete it. Choices made together that
would be revisited together are one decision; a choice that can change on its
own gets its own file. When a decision changes the spec the project came from,
edit the spec where it changes and add a dated note that links the decision.

**Lessons:** `lessons/<slug>.md`. The title is the lesson, "When X, do Y".
Frontmatter:

- `status: provisional | validated | superseded`;
- `applies_to`: this project, the group, or everywhere;
- `evidence`: what showed it;
- `branch`, only when it holds on one branch.

A new lesson is provisional. It becomes validated after a later successful use
or an explicit check; add a log line saying which. Evidence from the session
that produced the lesson does not count. A lesson for the whole group
gets a link in `_group.md` under "Lessons for the whole group". A lesson that
holds everywhere is worth an insight: offer to distill it. Insights come only
from captures, so write a short capture with the lesson's evidence (the case,
and any source you check), distill it with `atlas-distill`, and set
`promoted_to:` on the lesson.

**Something you noticed but do not understand yet** (a failed deploy, a flaky
test, a suspicion): write an operational capture, not research.

`captures/YYYY-MM-DD-<slug>.md` with this frontmatter:

```yaml
kind: operational
project: <slug>
date: YYYY-MM-DD
```

Operational captures are not distilled into insights. They resolve into a
thread, decision or lesson; then delete them, or move them to `sources/` if
they are evidence worth keeping. `next` shows how old the oldest one is.

**Branches.** Records that hold only on a branch get `branch:`, and boot leaves
them out on other branches. When the branch is merged, remove the field from
the records that survived it; close or supersede the rest.

## Close: `/close`

1. For every thread you worked on:
   - update `next` and `blocked`;
   - add a dated log line saying what happened, what you verified, and what you
     did not verify;
   - close the threads that are finished.
2. Record the decisions taken (accepted or proposed) and the lessons learned
   (provisional).
3. Resolve the operational captures you can.
4. Run `uv run --no-project engine/atlas.py check` and fix what it reports.
5. Commit what you wrote, naming every path (for a move, the old path as
   well):

   ```bash
   uv run --no-project engine/atlas.py commit --agent <id> -m "project <slug>: <what changed>" <paths…>
   ```

6. In Atlas, say what changed and what comes next. Put the threads you worked
   on in an `atlas:notes` block.
7. Mark the session closed, so the next agent does not catch it up again:

   ```bash
   uv run --no-project engine/atlas.py close --agent <id>
   ```

## Catch up: sessions that ended without `/close`

Sessions often end without `/close`: the window stays open for days, or the
user closes it. Atlas notes every Claude Code or Codex session that runs an
agent command here, and `boot`, `next` and the start hook list those that
ended without `/close`, or where the user wrote more after it. For each one,
before new work:

1. Post a progress line first (`say --agent <id> --progress "Catching up a
   session from <date> that ended without /close"`): catching up takes a few
   minutes, and the user should know why the answer waits.
2. Read it: `uv run --no-project engine/atlas.py sessions digest <id>`. It shows
   the user's and the agent's messages, one line per tool call and the
   compaction summaries, only what came after the last close.
3. Run the `/close` steps 1 to 5 for what that session did, and only for that:
   - a thread log line carries the session's date, not today's, and goes where
     that date belongs in the log; credit it as
     `- <date> (<the session's agent>; caught up by <id> from the transcript): …`;
   - say what you could not re-check (the transcript is the only source);
   - resolve operational captures only when that session produced them.
4. Run the `close` command the digest prints, with your own id for `--agent`.
   Its `--covered-until` keeps the mark at what you read, even if that session
   goes on in another window.
5. Tell the user in one line per session what you caught up.

A session that holds nothing worth keeping (a quick question):
`uv run --no-project engine/atlas.py sessions skip <id> --reason "…"`. If the
user writes in it again later, it comes back.

## Checkpoint: right after a compaction

When the start hook says the session was just compacted, run the `/close`
steps 1 to 5 for what the compaction summary covers, then the `close … --checkpoint`
command the hook prints. A checkpoint is not a close: once work goes on, the
session counts as open again until `/close`.
