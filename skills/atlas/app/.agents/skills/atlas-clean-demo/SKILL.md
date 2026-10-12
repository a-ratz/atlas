---
name: atlas-clean-demo
description: Remove the Atlas demo notes (sleep, memory and learning; the Nightlight and Thesis projects; the demo tour) from this vault, so the user starts with their own knowledge only. Use when the user says "clean the demo", "remove the demo data", "atlas-clean-demo", "start fresh", or wants an empty Atlas after trying the demo.
---

# Remove the demo

`engine/atlas.py demo` loaded the demo and recorded every note it wrote in
`vault/.atlas-demo.json`. Run from the Atlas home:

1. `uv run --no-project engine/atlas.py demo --remove`
   It deletes each demo note that is unchanged since the demo wrote it, removes
   the folders only the demo used, and commits the removal. Git history keeps
   the demo commits; nothing is rewritten.
2. It lists the demo notes the user changed and keeps them: they count as the
   user's now. Ask whether to delete those too. If yes, `git rm` them and commit.
3. Run `uv run --no-project engine/atlas.py check`. The user's own notes that
   linked to removed demo notes now show broken links; offer to fix them.
4. Tell the user in one or two lines what went and what stayed.

To load the demo again later: `uv run --no-project engine/atlas.py demo`. It
never writes over an existing note.
