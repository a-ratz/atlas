---
name: atlas-map
description: Build or update a map, a navigation note that groups related insights by theme, once a cluster of insights has formed. Use when `engine/atlas.py next` reports five or more insights without a map, or when the user asks for a map or an overview of a topic.
---

# Build a map

A map is a curated entry point into one region of the vault: what the region
is about, its main claims grouped by theme, and the open questions. It is not a
folder or a tag list; it says what you think the cluster means.

## 1. Find the cluster

Read the insights that belong to no map (`engine/atlas.py next` counts them).
Group them by what they are about. A map needs at least five insights with a
shared theme. Name the theme briefly: `sleep`, `agent-memory`, `pricing`.

If more than one map is possible, ask the user which to build first (Atlas:
`choices` block). Ask before creating the very first map of the vault.

## 2. Write the map

`vault/insights/<theme>-map.md`:

```markdown
---
description: What this region of the vault is about, in one sentence
---

# <Theme> map

Two or three sentences: what the cluster says as a whole, and why it matters to
the user.

## <Sub-theme>
- [[<insight title>]] — the claim's role here, in a few words

## <Another sub-theme>
- [[<insight title>]] — …

## Open questions
- <what the cluster does not answer yet>
```

Every entry gets a short context phrase. A bare list of links is not a map.

## 3. Link back

Add `"[[<theme>-map]]"` to the `topics:` list of every insight on the map.

## 4. Show it

In Atlas: `say` with an `atlas:note` block for the map, and point out that the
graph now shows the map as a hub (`#/graph`). Commit what you wrote: `engine/atlas.py commit --agent <id> -m "map: <theme>" <paths>`.
