---
demo: true
timebox: 35
max_steps: 30
---

# From the vault's knowledge to a project

The user asks the vault for ideas, picks one, has it worked out into a spec and starts a project
from it. The demo vault knows about sleep, memory and learning.

## Steps

1. On the operator page, ask: "/sketch ideas for a second feature of Nightlight that a small team
   could ship in a month".
2. Read what the agent offers. Pick the one you find most interesting.
3. Open the sketch it wrote. Press "Turn into a spec".
4. Open the spec when it is ready. Read its design decisions and its first slice. Press "Start a project".
5. Open the new project's page.

## Must be observable

- The agent says its budget, then offers at most three ideas as choices, each with why it survived
  and what would kill it. It says how many candidates it made and dropped.
- The sketch keeps the candidate, the insights it rests on, a red-team section and the alternatives
  it dropped, with the reason for each.
- The spec cites insights in at least three design decisions (or says where the vault has little),
  has acceptance criteria that could fail, and a first slice that tests the riskiest assumption.
  The sketch is now "specified".
- The project page shows where it came from: the spec and the sketch. It has a thread for the
  first slice.

## Screenshots

- The ideas the agent offers
- The sketch
- The spec's design decisions
- The project page with "Came from"
