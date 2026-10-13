---
demo: true
timebox: 10
max_steps: 15
before_upgrade: []
---

# Upgrade with content in the vault

Prepared with `run.py prepare upgrade --ref <the last release>`: Atlas from that ref with the demo
vault, then the skill and the app upgraded to this checkout. The user opens Atlas afterwards.

## Steps

1. Open Home, the operator page, every list in the sidebar and three notes of different kinds.
2. Ask the agent: "What changed in Atlas since the last version?"
3. Use one feature the pull request adds, the way its description says.

## Must be observable

- Every page renders; nothing from the demo vault is missing or broken.
- The new feature works on the upgraded vault, not only on a fresh one.
- The agent's skills are the new ones (it knows the new feature).

## Screenshots

- Home after the upgrade
- The new feature on the upgraded vault
