---
name: atlas-qmd
description: Search the vault by meaning with QMD and keep its collections set up. Use before research, distill, a sketch or a new card to find what the vault already knows; when the user asks for notes "about" something; or when they say "turn on search by meaning", "set up qmd", "qmd is broken".
---

# Search by meaning (QMD)

[QMD](https://github.com/tobi/qmd) is an optional local search engine. With it,
Atlas finds notes by what they mean, not only by the words they share. It runs
on the user's machine; nothing leaves it.

The vault has a QMD index of its own, so Atlas never touches the user's other
QMD collections. Its name is `qmd.index` in `vault/atlas.yaml` (`atlas` unless
another vault on this machine took it); every `qmd` command for the vault
carries `--index <name>`. `uv run --no-project engine/atlas.py qmd status` says
whether QMD is installed and on, the index, and which collections exist.

## Which collection answers what

| Question | Collection |
|---|---|
| What does the vault already know about X? (`atlas-learn`, step 1) | `atlas-insights`, `atlas-sources` (sources, research runs and the captures still waiting) |
| Is this claim already in the vault? (`atlas-distill`, duplicates) | `atlas-insights` |
| Who is this person or organization? (`atlas-cabinet`) | `atlas-cabinet` |
| Do we have this idea already? (`atlas-sketch`) | `atlas-ideas` |
| What did we decide or learn on a project? (`atlas-project`) | `atlas-projects` |

```bash
qmd --index <name> query $'intent: <what you are looking for>\nlex: <exact words or a name>\nvec: <the question in plain words>' \
  -c atlas-insights -n 10 --format json
```

Combine `lex:` (exact words) and `vec:` (meaning). Open each hit before you cite
or extend it; a hit is a pointer, not evidence. QMD's own guide to its query
syntax: `qmd skill show`.

## Fresh without asking

`engine/atlas.py commit` refreshes the index in the background when the commit
touched one of the five areas, one run at a time (log:
`vault/.atlas/qmd-sync.log`). Run `engine/atlas.py qmd sync` by hand only after
editing files without committing; it says when QMD failed.

## When QMD is off or missing

Search with `grep -ril "<words>" vault/<folder>` or, while Atlas runs,
`curl -s "localhost:8765/api/search?q=<words>"`. Do not install QMD unasked.

## Turn it on, off, or repair it

- **On:** ask first, also when QMD is already installed: the first setup
  downloads about 2 GB of models. Say what it creates: an index of the vault's
  own with five collections (cabinet, projects, ideas, insights, sources with
  captures), on this machine only. If `qmd --version` fails, it also needs
  Node.js or Bun: `npm install -g @tobilu/qmd`. Then
  `engine/atlas.py qmd setup`: it creates the index with the five
  collections, a context line each, and embeds them. When embedding fails, it
  says why and leaves search by meaning off.
- **Off:** `engine/atlas.py qmd off`. Atlas searches by words only; the
  index and QMD's models (about 2 GB) stay on the machine.
- After setup or off, commit the setting:
  `engine/atlas.py commit --agent <id> -m "qmd: on" vault/atlas.yaml`.
- **Repair:** `qmd status` lists what is missing; `qmd setup` again adds it.

Never remove or change a QMD collection outside the vault's index.
