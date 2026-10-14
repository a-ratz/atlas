---
name: atlas-revisit
description: Re-check insights whose revisit_after date has come against their sources as they stand now, and record whether each claim still holds, changed, or no longer holds. Use on "/revisit", "/revisit all", the Revisit button under Needs you or on an insight, or when `engine/atlas.py next` reports insights past revisit_after.
---

# Revisit due insights

An insight with `revisit_after` rests on a source that can still change: a
preprint without a final version, tool docs or a changelog, live data
(atlas-distill sets it only there). When the date has come, check the claim
against the source as it stands today and leave a dated record of what you
found. Nothing is deleted.

## 1. Pick the insights

- `/revisit <insight>` or the move on an insight's page: that insight, due or
  not.
- `/revisit` or `/revisit all`, the Needs you button: every insight in
  `vault/insights/` whose `revisit_after` is today or earlier and that has no
  `superseded_by`, oldest date first, **at most five per run**. Say how many
  remain.

## 2. Read the source as it stands now

For each insight, read the note, its `source:` capture in `vault/sources/`,
and the primary the note cites (the paper, the docs, the repository, the
data). Open the current version: for a preprint, the abstract page shows the
newest version; look for a journal or conference version too (the arXiv
comments or journal reference, or the title on the venue's site), because the
arXiv page does not always name it. For docs, the page as it is today. Read
the passages the claim rests on, as atlas-distill step 2 says: quotes,
figures, attributions and qualifiers come from the primary. The full text
decides, not a landing page's abstract, which can be older than the paper.
Leave the `source:` capture as it is: it records what was read back then.

## 3. Decide, and write it down

- **Holds.** The current version still says it. Add a dated line above the
  footer: `Revisited YYYY-MM-DD: <source, version> still says <the deciding
  point>.` Update the cited version if it changed.
- **Changed in detail.** A figure, a qualifier or the scope moved, but the
  title still states the claim. Correct the body, and keep the old wording
  visible: `An earlier version said <old>; <source, new version> says <new>
  (revisited YYYY-MM-DD).` Adjust `confidence` by atlas-distill's rule.
- **No longer holds,** or the title no longer states the claim. Write a new
  insight with the claim as it stands now (atlas-distill, step 4), and set
  `superseded_by: "[[<new title>]]"` on the old one, with one line saying why.
  Do not rename or delete the old note: links to it stay valid.
- **Source gone or unreachable** (try an archived copy first). Say so in a
  dated line, set `confidence: speculative`, and keep `revisit_after` for
  another try.

After a check that read the source, set `revisit_after` again (about three
months out) only if the text can still change, and remove it when the source
has a final version now or is stable by nature. A source you could not read
keeps a date for another try, final version or not. A superseded insight
loses its `revisit_after`; its replacement carries the date, if its source can
still change.

## 4. Close the loop

1. Run `uv run --no-project engine/atlas.py check` and fix what it flags.
2. Commit what you changed, from the Atlas folder:
   `engine/atlas.py commit --agent <id> -m "revisit: <n> insights" <paths>`.
3. Answer in Atlas with the notes and one line each: holds, changed (what),
   superseded (by what), or source unreachable. Then how many are still due.

   ````text
   Revisited 2 insights:
   ```atlas:notes
   - insights/<title 1>.md
   - insights/<title 2>.md
   ```
   - <title 1>: holds; arXiv v3 still reports …
   - <title 2>: changed; the effect is now …
   ````
