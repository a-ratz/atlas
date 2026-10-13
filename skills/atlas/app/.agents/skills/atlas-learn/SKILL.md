---
name: atlas-learn
description: Research a question or topic for the user and land the result as a capture in vault/captures/, with sources and graded evidence. Use when the user asks a research question, names a topic to look into, asks "what's new in…", or wants to understand a field.
---

# Research into a capture

The goal is one honest, self-contained capture the user can read now and that
can later be distilled into insights. Use only your harness's built-in web
search and page fetching. Optional extras (QMD for searching the vault, social
or GitHub CLIs) only if they are installed and the user wants them.

## 1. Check what the vault already knows

Search `vault/` for the topic (grep, or `curl -s "<url>/api/search?q=<words>"` with the `url` from `engine/atlas.py status`
while Atlas runs). If notes exist, read them and build on them instead of
starting over. Say what was already known.

## 2. Scope

If the request is ambiguous in a way that changes the research, ask one short
question (in Atlas: a `choices` block). Otherwise pick a sensible scope and
state it in the capture.

## 3. Research

Research takes minutes. If Atlas runs, post a progress line at each real step
so the user is not left with "agent is working…" (`engine/atlas.py say --agent <id> --progress "…"`;
give the first one `--title "Researching <topic>"`):
the scope you picked, how many sources you found, which ones you are reading,
that you are writing the capture.

- Search broadly, then open the primary sources: papers, official docs,
  repositories, datasets. Aim for 4–10 sources that actually carry the answer.
- For every material claim, note where it comes from. Grade the evidence:
  - **primary**: the paper, the official page, the source code;
  - **secondary**: reporting about it;
  - **weak**: forum and social posts. Useful for leads and opinions, never
    proof on their own.
- For papers, record the version you read (`arXiv 2609.16247v2`) and whether
  it is a preprint.
- Attribute every number to the page you read it on. A figure that only a blog
  post or press piece reports is that piece's claim, not the paper's, even when
  the piece is about the paper.
- Look for counter-evidence and say when you could not find any.
- Never invent a source or a quote. Quote only what you read.

## 4. Write the capture

`vault/captures/YYYY-MM-DD-<short-slug>.md`:

```markdown
---
kind: research
source_type: research
question: "<the question as the user asked it>"
date: YYYY-MM-DD
sources:
  - "<title>, <author/org>, <date or version>: <url>"
authors: []   # people who wrote the main sources, as they are named there
orgs: []      # organizations the sources come from or are about
---

# <The answer stated as one sentence>

## Answer
Three to six sentences that answer the question directly.

## Findings
- <finding> ([source](url), primary|secondary|weak)

## Contested or uncertain
- <what disagrees, what is missing, what you could not verify>

## Insight candidates
1. <a claim worth keeping, stated as a sentence> (confidence: proven|working|speculative)

## Open questions
- <what to research next>
```

Use the user's language for prose if they wrote in it; keep source titles as
published.

## 5. Show it

If Atlas runs, answer there. The capture card brings its own buttons (Distill,
Next research avenues, Dig deeper); add choices only for a specific follow-up:

````text
Done: <one-line answer>.
```atlas:note
captures/YYYY-MM-DD-<short-slug>.md
```
```atlas:choices
options:
  - label: Go deeper on <subtopic>
    send: Research <subtopic> in more depth
```
````

If the research answered a file in `questions/` (the user pressed "Research
this" on it, or the capture settles it), set its `status: answered` and add
`- answered in [[<capture file name without .md>]] (YYYY-MM-DD)`. A question
the research only narrowed stays open; update its text.

Commit what you wrote: `engine/atlas.py commit --agent <id> -m "learn: <slug>" <paths>`.

Do not distill in the same step unless the user asked for it; the capture is the
checkpoint where the user decides what is worth keeping.
