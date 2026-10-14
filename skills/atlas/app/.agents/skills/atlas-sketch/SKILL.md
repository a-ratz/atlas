---
name: atlas-sketch
description: Write down an idea as a sketch in vault/sketches/, or generate ideas from what the vault knows and keep only the ones that survive. Use when the user says "I have an idea", "what if we…", "ich hab eine Idee" (capture), or "give me ideas for…", "what could we build from this?", "/sketch ideas for …" (generate).
---

# Sketch an idea

A sketch records an idea at the maturity it has right now. It is rough on
purpose. It becomes a spec (`atlas-spec`) only when the user decides to work it
out. Two modes write the same file:

- **Capture** (about 2 minutes): the user has an idea. Record it; do not improve it.
- **Generate** (5 to 10 minutes): the user wants ideas. Build candidates from
  the vault, kill most of them, and let the user pick.

## Capture mode

1. **Listen.** Write down what the user said, in their words. Ask at most one
   question, and only if the core of the idea is unclear. Your own thoughts go
   in "Agent's notes", never into the idea.
2. **Check for a duplicate** in `sketches/`, `specs/` and every
   `projects/*/*/project.md` (search the titles and one-liners; with QMD, the
   `atlas-ideas` and `atlas-projects` collections, skill `atlas-qmd`). Found:
   - the same idea: add the new angle to it, dated, instead of a new file. If
     that sketch is already `specified`, the angle goes to its spec instead
     (under "Open questions", dated) and you say so;
   - an extension of a project: it goes to that project (a thread or a note,
     skill `atlas-project`), not into a sketch.
3. **Link 2 to 5 insights** the idea touches (search `insights/`), one line each
   on how it relates.
4. **Write and show it** (below), with `origin: user`.

## Generate mode

Say the budget before you start: about 15 note reads, at most 6 web searches,
one red-team. The point is a few ideas that survived honest attempts to kill
them, not many ideas.

### 1. Frame

Restate the goal in three lines:

- **Target:** what the idea must be (e.g. "a roguelike one developer can
  prototype in a month").
- **Constraints:** what it must respect (from the user and `you/goals.md`).
- **Dead if:** what kills a candidate (e.g. "a shipped game already has this
  core loop").

Ask one `choices` question only if the target is ambiguous or a constraint is
the user's to set. Otherwise go on.

### 2. Read narrowly

- The maps nearest the goal and 8 to 15 of their insights (search, or QMD).
- `questions/` with `status: open`: an idea whose build would answer one is a
  strong seed.
- Existing sketches, specs and projects: for duplicates and things already tried.
- The cabinet only for who owns the prior art or who the users are.

From what you read, note the **atoms**: mechanisms, findings, failure modes,
open problems. Ideas come from these, not from your general knowledge.

### 3. Generate 8 to 12 candidates

Use at least two operators:

- **Combine:** one insight from the target's map with one or two from another
  map, at least one pair that is not linked yet.
- **Invert:** take a strong insight and negate it, or push it to its extreme.
- **Answer:** a build that would settle an open question.

Each candidate is a short card:

```text
<n>. <Name>: <one-liner>
   from: [[insight]] + [[insight]] (operator)
   nearest prior art: <what exists> / difference: <what is new here>
   smallest test: <the cheapest thing that could kill it>
   dead if: <the result that kills it>
```

### 4. Kill pass

Gates only, no scores. A candidate dies when:

- it cannot be said as "when <situation>, <who> gets <outcome>";
- its insights are name-dropped, not load-bearing (remove them: is it the same idea?);
- it duplicates a sketch, spec or project;
- it needs more than one miracle (one unproven assumption is a bet; two are a wish);
- it repeats the move of another candidate (motif collapse): keep the strongest of each cluster;
- a search finds the graveyard (it was tried and failed) and the card names no change since.

Spend the web searches here: one or two per remaining card, on prior art.
Write one line per kill: the candidate and the gate that killed it.

### 5. Red-team the survivors

Take the 3 or 4 survivors to a separate context: a subagent where your harness
has one (it gets only the cards and the goal), otherwise a separate pass that
you write before you rank. For each card: "Write the strongest honest case
against this idea: the weakest grounding, the likeliest way it fails, and
whether it is the obvious idea anyone would have." Keep the answer verbatim.

### 6. Rank in pairs

Compare the survivors in pairs, each pair in both orders (A vs B, B vs A); a
pair that flips is a tie. No numbers. Label each survivor **obvious** or
**non-obvious**: obvious ideas are not wrong, but say so.

### 7. Let the user pick

`say` the top three at most, as a `choices` block: one-liner, why it survived,
what kills it. Add "None of these: change the constraints". The pick is the
user's. One round with changed constraints is fine; after that, stop.

If nothing survives, say so and say what the vault lacks to do better (a
missing area, an unanswered question). Offer research on it (`atlas-learn`).
A thin vault is an honest result.

### 8. Write the sketch

One sketch per pick, with `origin: "generated: <goal>"`. Killed and unpicked
candidates go into its "Alternatives considered", one line each with the reason.
They get no files of their own, and none go to `captures/` or `questions/`.

## The sketch file

`vault/sketches/<short-slug>.md`:

```markdown
---
title: "<Name: one-line description>"
description: <one sentence, max 150 characters>
status: sketch            # sketch | specified | parked | superseded
date: YYYY-MM-DD
origin: user              # user | "generated: <goal>"
---

# <Name>

## One-liner
<What it is, in one sentence.>

## The idea
<Capture: the user's words, lightly ordered. Generate: the card, written out.>

## Grounded in
- [[<insight>]]: how the idea rests on it

## Prior art and difference
<What exists, and what is new here. "Not searched" is an honest entry.>

## Smallest test
<The cheapest test that could kill it, and the result that would.>

## Red-team
<Generate mode: the red-team's answer, verbatim.>

## Alternatives considered
- <name>: <one line> (killed: <gate>, or not picked)

## Open questions
- <what decides whether this is worth doing>

## Agent's notes
<Your additions, clearly separated.>
```

Leave out sections that stay empty in capture mode. `atlas-spec` later sets
`status: specified` and `spec:`.

## Show it

Commit what you wrote: `engine/atlas.py commit --agent <id> -m "sketch: <slug>" <paths>`.
Then `say` with an `atlas:note` block for the sketch; its moves offer the next
steps (research prior art, find the weak spots, turn it into a spec).
