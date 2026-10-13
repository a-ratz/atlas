---
demo: true
needs: [qmd]
timebox: 20
max_steps: 25
---

# Search by meaning (QMD)

A user with QMD on the machine turns on search by meaning, finds notes by a paraphrase, and a new
note becomes findable without anyone running an index by hand.

## Steps

1. On the operator page, ask: "Can you search my notes by meaning?" Say yes when the agent offers to set it up.
2. When the agent is done, open the search and look for a paraphrase of a demo note, not its words
   (for the sleep demo: "being woken by sounds at night").
3. Ask the agent: "What do we know about waking people gently?"
4. Ask the agent to capture a thought: "Note that cue volume should ramp up from silence." Wait a minute,
   then search for it by meaning ("start the sound quietly").
5. Ask the agent to turn search by meaning off, then search again with words from a note's title.

## Must be observable

- The agent asks before it sets anything up and names what it creates: five collections
  (cabinet, projects, ideas, insights, sources) under one prefix.
- Atlas' search finds the demo note for the paraphrase, each note once.
- The agent's answer in step 3 cites notes it found by meaning, by their titles.
- The new note is findable by meaning within about a minute, with no command from the user.
- After "off", search still works by words, and the agent says what stayed on the machine.

## Screenshots

- The agent's setup answer
- Search results for the paraphrase
- The new note found by meaning
