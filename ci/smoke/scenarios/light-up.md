---
demo: true
timebox: 12
max_steps: 20
---

# Light up a topic in the constellation

The user asks the agent to show everything about a topic. Atlas should take them to the
constellation with those notes lit and the rest dimmed, without a new note in the vault.

## Steps

1. On Home, write in the chat: "Light up everything about sleep in the constellation."
2. Wait for the agent. Watch where Atlas takes you, and read the chip above the graph.
3. Hover one lit note, then click an empty spot of the graph. Then press ✕ on the chip.
4. Open the operator page and write: "Now light up the notes about spacing." Stay on the operator
   page until the agent is done, then use the link in its message.

## Must be observable

- Atlas switches to the constellation by itself after step 1: the named notes are lit, the rest is
  dimmed, and a chip shows the topic and the number of notes.
- Clicking the empty graph keeps the highlight; ✕ removes it, and the graph looks normal again at once.
- On the operator page Atlas stays put and says what the agent lit; the message's link opens the lit
  constellation.
- No new note appears in the vault for a highlight (no temporary map in Maps, no new file).

## Screenshots

- The lit constellation after step 2
- The operator page with the agent's message after step 4
