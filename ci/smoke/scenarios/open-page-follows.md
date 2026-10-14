---
demo: true
timebox: 15
max_steps: 20
---

# The open page follows the agent

The user keeps a note open while the agent works on it. The page should show the agent's result
without a reload: a distilled capture moves to sources, a question pressed "Later" changes status.

## Steps

1. Open "Captures" in the sidebar and open the oldest capture. Scroll down a little.
2. Press "Distill into insights" (the first button under the note). Stay on the capture page while the
   agent works; watch it.
3. When the agent says it is done, look at the page without reloading it.
4. Open "Open questions", open one question and press "Later". Stay on the question page until the
   agent is done, and look at it again without reloading.

## Must be observable

- The capture page follows the capture to `sources/` by itself, with a short notice, and keeps
  roughly the scroll position. It never shows "Not found".
- The question page shows its new status once the agent is done, without a reload.
- The sidebar numbers change with it.

## Screenshots

- The capture page after it followed the move
- The question page after "Later"
