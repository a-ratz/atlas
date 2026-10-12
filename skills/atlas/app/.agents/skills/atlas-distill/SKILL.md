---
name: atlas-distill
description: Turn a capture into atomic insights (one claim per note, title = claim), link them to existing insights and maps, and move the capture to sources/. Use when the user agrees to distill, says "distill", or captures are waiting and the user wants to keep what they found.
---

# Distill a capture into insights

Insights are the durable layer. Each one is a single claim the vault is willing
to defend, written so that a reader can find it, judge it and link to it
without dragging in unrelated context.

`/distill all` (the arrow between Captures and Insights in Atlas): every
capture in `captures/` that is not `kind: operational`, oldest first. Take them
one at a time through steps 1 to 5, post a progress line per capture, and
commit each capture on its own.

## 1. Read

Read the capture completely. Read the `Insight candidates`, but judge every
claim yourself: keep only claims the evidence supports.

## 2. Check every figure against its source

The most common error in a knowledge vault is not a source that changed later.
It is a note that never matched its source: a number taken from a blog post
about a paper and cited as the paper, a "always" the source never said, two
percentages with different denominators compared as one. So, for every number,
named result and strong word ("always", "monotonic", "doubles") in a claim:

- find the line in the source that says it, and keep a short quote of it in the
  note (`> "…"` plus the source);
- if only a secondary piece says it (a blog, press, a summary in the capture),
  cite that piece, not the primary source;
- if you cannot find it, drop or soften the claim.

## 3. Check for duplicates

For each claim, search `insights/` (grep on key terms, or the Atlas search API).
If an existing insight already says it, extend that note with the new evidence
instead of creating a second one.

## 4. Write one note per claim

File name = the title. Avoid `/ \ : * ? " < > |` in it.
`vault/insights/<Claim stated as a sentence>.md`:

```markdown
---
description: One sentence that adds context beyond the title (max 150 characters)
category: <a short topic label; reuse the labels already in the vault>
confidence: speculative | working | proven
source: <capture file name without .md>
revisit_after: YYYY-MM-DD   # only if the claim rests on a preprint or fast-moving source
topics: []                  # map links like "[[sleep-map]]" once a map exists
---

# <Claim stated as a sentence>

Why this holds: the evidence, the mechanism, and where it stops holding.
In your own words, not a copy of the source.

---

Source: [[<capture file name without .md>]]

Relevant insights:
- [[<existing insight title>]] — how they relate
```

Quality bar:

- **Title test:** "This note argues that <title>" reads as a sentence someone
  could disagree with. "Sleep and memory" fails;
  "Slow-wave sleep strengthens declarative memories more than REM sleep" passes.
- **Description test:** it says something the title does not (the mechanism,
  the scope, the evidence).
- **Confidence:** `speculative` (one source, or inference), `working` (several
  sources agree), `proven` (replicated or well-established).
- **Links:** link at least one existing insight whenever one is related. The
  connections are what turns a list into knowledge.
- Cite paper versions (`2609.16247v2`) and set `revisit_after` for preprints
  (about three months out).

## 5. Close the loop

1. Move the capture to `vault/sources/` (keep its name) so `captures/` only
   holds what still waits. If it names its authors or organizations but has no
   `authors:` or `orgs:` yet, add them to its frontmatter (AGENTS.md, Cabinet).
2. If a map covers the topic, add each new insight to it, and add the map to
   the insight's `topics`.
3. In Atlas, show what you made and what is next:

   ````text
   Three insights from the capture:
   ```atlas:notes
   - insights/<title 1>.md
   - insights/<title 2>.md
   ```
   ````

4. Run `uv run --no-project engine/atlas.py check` and fix what it flags: a
   link that matches no note (usually a typo or a title you changed), a
   description over 150 characters, a missing `confidence`, an insight with no
   connection.
5. Run `uv run --no-project engine/atlas.py next`. If it reports five or more
   insights without a map, offer to build one (`atlas-map`).
6. Commit what you wrote, including the capture's old path (it moved):
   `engine/atlas.py commit --agent <id> -m "distill: <capture slug>" <paths>`.
