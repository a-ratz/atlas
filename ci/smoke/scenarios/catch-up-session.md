---
demo: true
stage: [earlier-session]
timebox: 15
max_steps: 20
---

# A session that ended without /close gets caught up

Two days ago an agent worked on Nightlight's cue timing with the user: it measured three nights, the
user decided on a cue window and named the next step. Then the window was closed without `/close`,
so none of it reached the project. The next agent should notice that session and catch it up before
new work.

## Steps

1. In the chat, write: "Hi! Anything I should know before we go on with Nightlight?"
2. Wait until the agent is done. Read what it says about earlier sessions.
3. Open the project Nightlight, then its thread "Cue timing". Look at the log and the next step.
4. Look at Nightlight's decisions.
5. In the chat, type `/next`. Read the suggestions.

## Must be observable

- The agent says, without being asked about it, that an earlier session ended without `/close`,
  and that it caught it up. It names what it recorded.
- The thread "Cue timing" has a log line dated two days ago (the earlier session's day, not today)
  with the measured latency (180 ms) and the cues in N2, and its next step is the fourth night with
  the new firmware.
- Nightlight has a decision about the cue window ending 30 minutes after the first N3 phase.
- `/next` no longer suggests catching up a session.

## Screenshots

- The thread "Cue timing" after the catch-up
- The chat with the agent's catch-up report
