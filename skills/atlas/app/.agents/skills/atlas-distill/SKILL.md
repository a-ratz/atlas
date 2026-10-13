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
one at a time through steps 1 to 7, post a progress line per capture, and
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

## 5. File the open questions that matter

A capture ends with `## Open questions`. Most of them stay where they are: in the
source, after step 6 moves it. A question gets its own file only if it passes
all three tests:

- the new insights do not answer it;
- you can name the evidence that would answer it (a measurement, a source, an
  experiment);
- the answer would change or qualify a specific insight. That insight goes into
  `affects:`.

Research directions ("compare loop architectures on a task") are never
questions. A large research session should yield a handful, not dozens.

Before filing, look through `questions/` for one that already covers it:

- **open** or **dormant**: do not file a second one. Raise its `raised_count` by
  one and append `- also raised in [[<capture>]] (YYYY-MM-DD)`. A dormant one
  becomes `open` again.
- **dropped**: the user said they are not interested. Leave it.
- **answered**: file the new question only if it asks something the answer did
  not cover.

`vault/questions/<question as a short sentence>.md`:

```markdown
---
status: open
raised: YYYY-MM-DD
raised_count: 1
affects: "[[<insight title>]]"
source: <capture file name without .md>
---

# <The question, as a sentence ending in "?">

Why it matters: what would change in [[<insight title>]] if the answer went
either way. What would answer it.

- raised in [[<capture file name without .md>]] (YYYY-MM-DD)
```

**At most 7 open questions.** `engine/atlas.py check` fails past seven. Before
adding the eighth, answer one, merge two that ask the same thing, or set the
coldest (lowest `raised_count`, then oldest `raised`) to `status: dormant`.
Dormant questions are not lost: when a capture raises them again, they come
back. The user moves questions with the buttons on their page: "Not interested"
means `status: dropped`, "Later" means `status: dormant`.

## 6. Minimal cards for the actors

The cabinet grows from what you distill. Give a card to each *actor* of this
capture: a person or organization who wrote, said, built or measured something
the new insights rest on, and everyone in the capture's `authors:` and `orgs:`
(add those fields first if the capture names its authors but lacks them). A name
that is only mentioned ("as Netflix does") gets no card.

1. Look for an existing card first (`engine/atlas.py mentions "<name>"`, the
   aliases in `cabinet/`). If one exists, add a timeline entry and the new links.
2. Otherwise write a **minimal card**: only what the capture and the insights say.
   No search, no lookup, nothing inferred: no guessed first name, employer, title
   or email.

   ```markdown
   ---
   name: <the name as the source writes it, e.g. "Dumay">
   aliases: [<the same, plus other spellings the source uses>]
   role: <one line on their role in this context: "first author of the 2007 study on sleep and new words">
   depth: minimal
   created_by: <your id>
   updated_by: <your id>
   updated: YYYY-MM-DD
   ---

   # <name>

   <One or two sentences: what they did that this vault uses.>

   ## Timeline

   - YYYY-MM-DD · Card created from [[<capture file name without .md>]]; named in [[<insight>]]. (Source: the capture)
   ```

   People go to `cabinet/people/<name>.md`, organizations to
   `cabinet/orgs/<name>.md` (with `kind:` instead of `role:`).
3. At most **five new cards per capture**, the actors the insights lean on most.
   List the others as candidates in your summary.

## 7. Close the loop

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

   Name the questions you filed or raised in one line ("One open question
   filed, one raised again"), or that you filed none. Name the cards you
   created; when there are minimal cards, offer "Expand cards" as a choice
   (`/expand-cards`).

4. Run `uv run --no-project engine/atlas.py check` and fix what it flags: a
   link that matches no note (usually a typo or a title you changed), a
   description over 150 characters, a missing `confidence`, an insight with no
   connection.
5. Run `uv run --no-project engine/atlas.py next`. If it reports five or more
   insights without a map, offer to build one (`atlas-map`).
6. Commit what you wrote, including the capture's old path (it moved):
   `engine/atlas.py commit --agent <id> -m "distill: <capture slug>" <paths>`.
