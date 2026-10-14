# Smoke test protocol

The gate (`ci/gate.py`, `ci/browser.py`, `tests/`) proves that Atlas loads, answers and renders. It
cannot tell whether a person and their agent can actually *use* a feature. A smoke run does: a fresh,
isolated Atlas, installed the way a user installs it, an agent connected to it with nothing but the
Atlas skill, and a second agent that plays the user in the browser.

**When:** every pull request that changes the engine, a skill or the installer, after the gate is
green and before the merge. Documentation-only pull requests skip it.

## 1. Prepare

```bash
uv run ci/smoke/run.py prepare <scenario>                 # first-run, research-to-questions, …
uv run ci/smoke/run.py prepare upgrade --ref <last release or main>
```

`prepare` creates a run folder with its own `HOME`, installs this checkout's skill with
`npx skills add <checkout> -g -s atlas` (Claude Code and Codex), runs the installer, loads the demo
if the scenario asks for it, starts Atlas in operator mode on a free port, and writes two briefs into
the run folder: `operator.md` and `user.md`. It prints the run as JSON (folder, URL, port, version).
Nothing outside the run folder is touched; the developer's own Atlas and vault stay out of it.

## 2. Run the two roles

- **Operator:** an agent that knows only the installed Atlas (its `AGENTS.md` and skills) and the
  brief `operator.md`. It runs the `wait` / `say` loop and does what the chat asks.
- **User:** an agent with a browser (Playwright) and the brief `user.md`, which embeds the scenario.
  It knows what the screen shows and what the pull request's description promises, not the diff,
  so missing guidance on screen is a finding.

Start the operator first, then the user. In Claude Code both are subagents; the operator role also
runs once in Codex (`codex exec` with `operator.md` as the prompt), because Atlas promises to work
with both. Routine runs may use a smaller model for the user role.

## 3. Report

The user role fills in [`report-template.md`](report-template.md) and returns it as its answer
(subagents may not be allowed to write report files); the lead saves it as `report.md` in the run
folder, next to the screenshots the scenario names in dark and light. The report goes into the pull request as
a comment headed "Smoke run: <scenario>". Findings are sorted:

- **bug** → an issue from the bug template, linked from the report; it blocks the merge when the
  pull request caused it;
- **papercut** → listed in the pull request; fix it there or open a task;
- **idea** → optional, listed.

The operator's `operator-log.md` goes into the same comment, shortened to what went wrong or was
unclear in the skills.

## 4. Stop

```bash
uv run ci/smoke/run.py stop <run folder> [--clean]
```

## Scenarios

`scenarios/*.md`, one per user journey: frontmatter (`demo`, `timebox` in minutes, `max_steps`),
the steps a user takes, what must be observable, and the screenshots to take. A pull request that
adds or changes a feature adds it to a scenario or writes a new one.

| Scenario | Covers |
|---|---|
| [first-run](scenarios/first-run.md) | an empty Atlas, the first chat, a note |
| [research-to-questions](scenarios/research-to-questions.md) | research → capture → distill → insights, open questions, cards |
| [upgrade](scenarios/upgrade.md) | the last release with content, upgraded to this checkout |
| [idea-to-project](scenarios/idea-to-project.md) | ideas from the vault, a spec, a project that knows where it came from |

## Budget

A scenario names its timebox (usually 10 to 20 minutes) and a step limit. The run stops there and
reports what it reached; a run that hits the limit is a finding about the feature or the scenario,
not a reason to keep going.
