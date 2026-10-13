@AGENTS.md

## Claude Code specifics

- **Smoke runs:** run the operator and the user role as two subagents with the briefs `run.py prepare`
  writes (`operator.md`, `user.md`); start the operator first. Give the user role a browser tool
  (Playwright or Claude in Chrome). Run the operator once more in Codex with `codex exec` and the same
  brief.
- **Screenshots:** take them with a browser tool from a running build on a throwaway vault, never from
  your own Atlas.
- **Reviews:** `codex review` runs from the repository folder; post its output with paths made
  repository-relative.
