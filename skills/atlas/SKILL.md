---
name: atlas
description: Atlas - a knowledge vault the user grows by talking to their agent and reads in the browser. Use when the user says "start atlas", "atlas starten", "open atlas", "/atlas", "install atlas", "set up atlas", "where is my atlas", "update atlas", "restore the atlas skills", or wants to research, distill, sketch or work on a project in their Atlas from any folder. On first use it installs Atlas into a folder the user picks; afterwards it points every harness at that folder.
---

# Atlas

This skill installs Atlas and points to it. The app ships in `app/` next to
this file: the engine, an empty vault, and the workflow skills. The user's
Atlas is a copy of it in a folder of their own, the **home**. After the
install, this skill does three things:

- it knows where the home is (`config.json`);
- it hands every request over to the home;
- it keeps the factory copy, for upgrades and for restoring changed files.

Every harness that has this skill installed globally finds the same home.

`<skill>` means the folder that contains this SKILL.md (Claude Code shows it as
"Base directory for this skill"). The helper needs uv:

```bash
uv run --no-project <skill>/scripts/atlas_install.py status
```

## 1. Find the home

Run `status`:

- **not installed**: this is the first run. Follow
  `<skill>/references/onboarding.md`. It asks at most three short questions.
- **home missing**: the folder moved or was deleted. Ask where it is now, then
  run `atlas_install.py locate <dir>`. If it is gone, offer a fresh install
  (onboarding).
- **ok · home: `<dir>`**: continue with step 2. If status says an upgrade is
  available, mention it in one line, and do not upgrade unless asked.

After `npx skills update` the skill folder is replaced. Status brings the
pointer back from `~/.config/atlas/config.json` by itself.

## 2. Hand over to the home

Work from the home: `cd <home>`, or use absolute paths. Read `<home>/AGENTS.md`;
it is the manual for everything that follows. Then do what the user asked:

- start Atlas: `<home>/.agents/skills/atlas-operator/SKILL.md`;
- research, distill, maps, sketches, projects, `/close`: the skill that
  AGENTS.md's workflow table names, read by path from `<home>/.agents/skills/`.

## Maintenance (only when the user asks)

| The user says | Run (`atlas_install.py …`) |
|---|---|
| "update atlas", or status reports an upgrade | `upgrade --dry-run`, show the list, then `upgrade`; commit in the home |
| "restore the learn skill", "reset Atlas to factory" | `restore <what> --dry-run`, then `restore <what>`; `<what>` is a skill name (`atlas-learn`), `skills`, `engine`, `agents-md`, `registry` or `all` |
| "my atlas is somewhere else now", "use this clone" | `locate <dir>` |
| "where is my atlas", "which version" | `status` |
| "remind agents of sessions that ended without /close", "install the session hook" | `hooks install` (Claude Code and Codex); `hooks status`, `hooks remove` |

What these commands do and never do:

- `upgrade` replaces only app files the user has not changed, and adds new
  ones. It never touches `vault/`, which is the user's knowledge, except to add
  template files that are new in this version.
- `restore` first moves the current file to `.atlas-backup/<time>/`.
- Neither command pushes.
- `hooks install` adds one SessionStart hook to `~/.claude/settings.json` and
  `~/.codex/hooks.json` and keeps every other hook; `hooks remove` takes only
  that one out. It tells agents about sessions that ended without `/close` and
  asks for a checkpoint after a compaction; it prints nothing otherwise.

To get a new version of this skill, the user runs
`npx skills update atlas`. After that, `upgrade` brings the home up to date.
