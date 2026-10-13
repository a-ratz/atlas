# AGENTS.md: working on Atlas

This file is for agents and people who change Atlas itself. The README explains what Atlas is and how
it works; this file covers what the README leaves out: where things live, the rules the code keeps,
and how a change gets from an issue to `main`.

**Two AGENTS.md files.** This one, at the repository root, is for contributors.
`skills/atlas/app/AGENTS.md` is part of the product: it ships into every user's Atlas and tells
*their* agents how to work inside a vault. Change that one only when the behavior of Atlas changes.

## Where things live

| Path | What it is |
|---|---|
| `skills/atlas/` | the package `npx skills add` installs: `SKILL.md`, `scripts/atlas_install.py`, `references/onboarding.md` |
| `skills/atlas/app/` | what gets copied into a user's Atlas folder: `engine/`, the vault template `vault/`, `demo/`, the vault agents' `AGENTS.md`, `CLAUDE.md`, `.agents/skills/`, `VERSION` |
| `skills/atlas/app/engine/atlas.py` | the whole engine: one file, its dependencies in the script header, run with `uv run --no-project` |
| `skills/atlas/app/engine/static/` | the front end: plain ES modules and CSS, no build step |
| `skills/atlas/app/engine/registry.default.yaml` | types, fields, checks, moves, commands; `vault/atlas.yaml` is the same file as a vault copies it |
| `site/` | the click dummy at https://a-ratz.github.io/atlas/: `build.py` records the real engine over the demo vault and `scene.yaml`, `demo.js` replays it |
| `ci/` | the gate (`gate.py`, `browser.py`) and the smoke protocol (`smoke/`) |
| `tests/` | regression tests; one per review finding |

## Rules the code keeps

- **The vault's files are the truth.** The index is disposable; nothing important lives only in it.
  Atlas never writes into a user's vault unless they or their agent asked for it.
- **A registry, not code**, for anything a vault might want different: types, fields, checks, buttons.
  A registry key a vault copied earlier must keep working: when a default changes, migrate the old
  shape (see `Index.__init__`) instead of breaking copies.
- **Every platform.** Name `encoding="utf-8"` on every text read, write, `open` and subprocess call;
  Windows defaults to cp1252 and fails on the first emoji. Resolve paths with `Path.resolve()`.
  The gate checks both on Windows and macOS.
- **Both themes.** Every UI change is checked in dark and light.
- **Checks protect a claim.** A check must be able to fail and cost seconds; anything that is only
  process warns instead of blocking.
- **Public repository.** No absolute home paths, machine names, private names or customer names in
  files, commits, issues or PR comments. Review tools print absolute paths: make them
  repository-relative before posting.

## From issue to `main`

1. **Issue** from a template in `.github/ISSUE_TEMPLATE/` (feature, task, bug, risk). A feature has
   a description, acceptance criteria as checkboxes and technical notes. `status:ready-for-refinement`
   stays on it until the owner has agreed to the proposal.
2. **Branch and pull request** that closes the issue. Raise `skills/atlas/app/VERSION` and the README's
   "Atlas X is the current release" line with every app change (the gate checks it).
3. **Screenshots** for every UI change: the final state, in dark and light, in every state that matters.
   Commit them on the branch, embed them with the commit's blob URL plus `?raw=true`, and remove them
   in a later commit so they never reach `main`.
4. **The gate** must be green on Ubuntu, macOS and Windows (`.github/workflows/gate.yml`). Locally:
   `uv run ci/gate.py static docs hygiene tests operator upgrade installer`, `uv run site/build.py`,
   `uv run ci/browser.py`.
5. **Local Codex review rounds** as PR comments: run `codex review --base main`, post its findings
   verbatim under "**Local Codex review, round N**", fix them, post a "fixed in <sha>" comment per
   finding with the test that covers it, then review the fixes (`--base <previous sha>`). Stop when a
   round finds nothing actionable, or after three rounds when only improvements remain; list those.
6. **Smoke run** for every change to the engine, a skill or the installer: [`ci/smoke/README.md`](ci/smoke/README.md).
   The report goes into the pull request.
7. **Merge** (squash) after the owner approves, or when the owner has delegated it: the gate green,
   the review clean, the smoke run passed. Tick the issue's acceptance criteria first.

Every review finding and every bug the gate or a smoke run finds gets a regression test in `tests/`
(or a check in `ci/`), named after what it protects.

## The click dummy stays current

https://a-ratz.github.io/atlas/ is built from the real engine by `site/build.py` and deployed by
`.github/workflows/pages.yml` after every merge to `main`. The gate builds it on every pull request,
so a change that breaks it cannot merge. When a pull request adds something a visitor should see,
it also adds it to `site/scene.yaml` (the chat, the notes the scene writes) or says in the PR why not.
