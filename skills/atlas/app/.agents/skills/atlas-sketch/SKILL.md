---
name: atlas-sketch
description: Capture an idea as a sketch in vault/sketches/, in the user's own words, checked against existing ideas and linked to related insights. Use when the user says "I have an idea", "what if we…", "ich hab eine Idee", or describes something they might build or do.
---

# Sketch an idea

A sketch records an idea at the maturity it has right now. It is rough on
purpose: no business plan, no polish. A sketch becomes a spec in `specs/` later,
only when the user decides to work it out.

## 1. Listen first

Capture what the user actually said. Ask at most one question, and only if the
core of the idea is unclear. Do not expand the idea with your own features;
put your thoughts in a separate section.

## 2. Check for duplicates

Search `sketches/` and `specs/` for the same idea. If one exists, add the new
angle to it (with today's date) instead of creating another file.

## 3. Write it

`vault/sketches/<short-slug>.md`:

```markdown
---
title: "<Name — one-line description>"
description: <one sentence, max 150 characters>
status: sketch
date: YYYY-MM-DD
---

# <Name>

## One-liner
<What it is, in one sentence.>

## The idea
<The user's idea in their words, lightly ordered. Keep their phrasing.>

## Why it might matter
<Problem, who has it, why now.>

## Open questions
- <what decides whether this is worth doing>

## Related
- [[<insight or other sketch>]] — how it relates

## Agent's notes
<Your additions, clearly separated: risks, prior art you know of, a first test.>
```

## 4. Show it

In Atlas: `say` with an `atlas:note` block for the sketch, plus `choices`
such as "Research prior art" (`atlas-learn`), "Turn it into a spec", "Keep it
as is". Commit what you wrote: `engine/atlas.py commit --agent <id> -m "sketch: <slug>" <paths>`.
