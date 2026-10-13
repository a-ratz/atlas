---
name: atlas-qmd
description: Search the vault by meaning with QMD and keep its collections set up. Use before research, distill, a sketch or a new card to find what the vault already knows; when the user asks for notes "about" something; or when they say "turn on search by meaning", "set up qmd", "qmd is broken".
---

# Search by meaning (QMD)

[QMD](https://github.com/tobi/qmd) is an optional local search engine. With it,
Atlas finds notes by what they mean, not only by the words they share. It runs
on the user's machine; nothing leaves it.

`uv run --no-project engine/atlas.py qmd status` says whether QMD is installed
and on for this vault, and which collections exist. The prefix is `qmd.prefix`
in `vault/atlas.yaml` (`atlas` unless another vault on this machine took it).

## Which collection answers what

| Question | Collection |
|---|---|
| What does the vault already know about X? (`atlas-learn`, step 1) | `<prefix>-insights`, `<prefix>-sources` |
| Is this claim already in the vault? (`atlas-distill`, duplicates) | `<prefix>-insights` |
| Who is this person or organization? (`atlas-cabinet`) | `<prefix>-cabinet` |
| Do we have this idea already? (`atlas-sketch`) | `<prefix>-ideas` |
| What did we decide or learn on a project? (`atlas-project`) | `<prefix>-projects` |

```bash
qmd query $'intent: <what you are looking for>\nlex: <exact words or a name>\nvec: <the question in plain words>' \
  -c <prefix>-insights -n 10 --format json
```

Combine `lex:` (exact words) and `vec:` (meaning). Open each hit before you cite
or extend it; a hit is a pointer, not evidence. QMD's own guide to its query
syntax: `qmd skill show`.

## Fresh without asking

`engine/atlas.py commit` refreshes the collections a commit touched in the
background, one run at a time (log: `vault/.atlas/qmd-sync.log`). Run
`engine/atlas.py qmd sync [cabinet projects ideas insights sources]` by hand
only after editing files without committing.

## When QMD is off or missing

Search with `grep -ril "<words>" vault/<folder>` or, while Atlas runs,
`curl -s "localhost:8765/api/search?q=<words>"`. Do not install QMD unasked.

## Turn it on, off, or repair it

- **On:** if `qmd --version` fails, ask first (it needs Node.js or Bun, and its
  first run downloads about 2 GB of models), then `npm install -g @tobilu/qmd`.
  Then `engine/atlas.py qmd setup`: it creates the five collections with a
  context line each and embeds them.
- **An older collection over the whole vault** doubles every result:
  `engine/atlas.py qmd setup --replace-old` removes it.
- **Off:** `engine/atlas.py qmd off` (the collections stay in QMD).
- **Repair:** `qmd status` lists what is missing; `qmd setup` again adds it.

Never remove or change a QMD collection that does not belong to this vault.
