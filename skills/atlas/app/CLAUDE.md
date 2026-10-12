# CLAUDE.md

Everything an agent needs is in AGENTS.md, which is shared by all harnesses:

@AGENTS.md

Claude Code specifics:

- The workflows are also available as skills (`.claude/skills` links to
  `.agents/skills`): `atlas-operator`, `atlas-learn`, `atlas-distill`,
  `atlas-map`, `atlas-sketch`, `atlas-project`.
- Use listening mode A: run `uv run --no-project engine/atlas.py wait --agent <id>`
  with `run_in_background: true`. The task notification wakes you when the user
  writes. Re-arm it before you end every turn.
- Run the server itself with `run_in_background: true` too.
