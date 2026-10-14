---
name: atlas-spec
description: Turn a sketch into a spec in vault/specs/, grounded in the vault's insights, with prior art, acceptance criteria, risks and a first slice to build, then hand it over to a project. Use when the user says "/spec", "turn this into a spec", "work this idea out", or presses "Turn into a spec" on a sketch.
---

# Spec a sketch

A spec says what to build and why, and where the vault's knowledge supports
it. It is not a longer sketch: it decides things, cites the insights behind
the decisions, says honestly where the vault has nothing, and names the
smallest build that would show whether the idea holds.

Budget: about 20 note reads and 5 to 8 web searches. Say it before you start.

## 1. The sketch

Use the sketch the user has open or names. An idea without a sketch gets one
first (`atlas-sketch`, capture mode): every spec has a source sketch.

Decide the spec's name now: `<spec>` from here on is its note name, without
folder and `.md` (the file is `vault/specs/<spec>.md`, links are `[[<spec>]]`):

- the sketch's `spec:` already names a spec: that one exists. Ask: rewrite it,
  or write a new version next to it (`<its name>-v2`)?
- no `spec:`, but `specs/<slug>-spec.md` exists: the same question;
- otherwise: `<slug>-spec`.

Read the sketch: its thesis, what it already decided, its open questions, and
the assumptions it makes without saying so. If it is too thin to spec, ask at
most two questions (a `choices` block where you can).

## 2. Ask the vault

Pick 3 to 7 concepts: the idea itself, its mechanism, how it could fail, and
neighbouring areas. Search insights and maps for each (QMD's `atlas-insights`
where it is on, skill `atlas-qmd`). Read the related open questions, and the
accepted decisions and lessons of related projects: an accepted decision is a
constraint.

Sort what you found into:

- **design informants:** insights a decision can rest on;
- **risk signals:** insights that say where it could fail;
- **answers:** insights that settle one of the sketch's open questions.

## 3. Prior art

Search for what already exists, within the budget. Findings worth keeping land
as a capture (`kind: research`, with sources) for a later distill; do not
write insights from them directly. If something already does the job, the spec
opens with a **build or adopt** question. Relatives that do not do the job are
prior art, not a question: name them and the difference, no decision.

## 4. Write the spec

`vault/specs/<spec>.md` (the name from step 1). The `-spec` suffix keeps
`[[<slug>]]` pointing at the sketch.

```markdown
---
title: "<Name: what the spec builds>"
description: <one sentence, max 150 characters>
status: draft             # draft | building | parked | superseded
date: YYYY-MM-DD
source_sketch: "[[<sketch slug>]]"
---

# <Name>

## Pitch
<Two or three sentences: what, for whom, why now.>

## Problem and who has it
<The situation, the person, what it costs them today.>

## Design decisions
### <Decision>
<What is decided, and the option it beat.>
> From the vault: [[<insight>]]: how it applies here.

## Scope and non-goals
- In: …
- Out: … (and why)

## Prior art and difference
<What exists; what this does differently; build or adopt, if it applies.>

## Acceptance criteria
- [ ] <observable, and able to fail>

## Risks
- <risk>: <what would show it early> ([[<insight>]] where one says so)

## Open questions
- Resolved: <question>: <answer> ([[<insight>]])
- Open: <question>: <what would settle it>

## First slice
<The smallest build that tests the riskiest assumption: what to make, how to
try it, and the result that means go on or stop.>
```

Rules for the content:

- At least three design decisions cite an insight. If the vault has too little,
  say "The vault has little on <X>" in that place and offer research on it
  (`atlas-learn`). Never invent support.
- Every open question of the sketch appears: resolved with a citation, or open.
- Where an insight contradicts the sketch, show both sides in the decision.
- Acceptance criteria can fail: "a first-time player finishes a run in under
  20 minutes", not "the game is fun".

## 5. Review in a separate context

Give the first slice, the acceptance criteria and the rules they test (the
design decisions they depend on) to a subagent where your harness has one
(otherwise a separate pass): "Does this slice test the riskiest assumption, or a
safe one? Which criterion cannot fail?" Fix what it finds and
note the review in one line under "First slice".

## 6. Close the sketch and commit

In the sketch: `status: specified` and `spec: "[[<spec>]]"`. Run
`engine/atlas.py check`, then commit the sketch, the spec and any capture
together: `engine/atlas.py commit --agent <id> -m "spec: <slug>" <paths>`.

## 7. Hand over

`say` an `atlas:note` block for the spec. Its moves offer the next step:

- **Start a project** (skill `atlas-project`):
  - `projects/<group>/<slug>/project.md` with `source: "[[<spec>]]"`;
  - a thread for the first slice, whose `next:` is its first step;
  - when prior art exists, the build-or-adopt question as a decision with
    `status: proposed`.

  The spec becomes `status: building`. Atlas then shows the line project →
  spec → sketch in the margin.
- **Research an open question** (`atlas-learn`).
- **Keep it as a draft.**
