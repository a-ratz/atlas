---
demo: false
timebox: 20
max_steps: 25
---

# Research → distill → open questions

The core loop: the user asks a question, the agent researches it into a capture, the user has it
distilled, and the vault ends up with insights, open questions and (from Atlas 0.7) cards for the
people and organizations involved.

## Steps

1. On the operator page, ask: "Research what retrieval practice is and how well it works for adults."
2. Watch the conversation title and the progress lines while the agent works.
3. Open the capture it reports. Press "Distill".
4. When the distill is done, open the new insights, the sidebar's "Open questions" and, if present,
   the cabinet (People, Organizations).
5. Open one open question and press "Later" on it; check where it went.

## Must be observable

- The bar names the work ("Researching …", then "Distilling …") while the agent works.
- The capture has sources and a section of open questions; the distill turns it into insights that
  link each other and move the capture to sources.
- Open questions: only the few that would change a claim, each naming the insight it `affects`;
  never more than 7 open. "Later" moves one to "+N resting".
- The sidebar numbers match the lists they open.

## Screenshots

- The operator page while the agent researches
- An insight page
- The open questions list and one question's page
