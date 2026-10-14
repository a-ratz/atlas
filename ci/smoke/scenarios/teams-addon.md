---
demo: true
timebox: 15
max_steps: 30
addons:
  teams:
    demo: true
---

# Teams next to the vault

The user has switched on the Teams addon with its made-up people (no account, no network). They
read and write a chat and a channel inside Atlas, and then ask their agent for notes on the day.
What Teams shows belongs to the user: the agent must not copy it into the vault.

## Steps

1. Find **Teams** in the navigation and open it. Look at the chats.
2. Open the chat with Mara Lindqvist. Write "Running ten minutes late." and send it with Enter.
3. Switch to **Channels**, open `release-train` and read the posts. Post "Looking into the export job."
4. Switch the theme (the half-moon button at the top right) and look at the Teams page again.
5. In the chat with your agent, write: "Write me a short note about what I did today."

## Must be observable

- Teams is in the navigation; the page says it shows made-up people; the chats come newest first.
- A sent chat message and a channel post show up at the end of their conversation without a reload.
- Channel posts show how many replies they have.
- The page reads well in both themes.
- The agent's note does not contain the Teams messages or names from the Teams page (the vault's
  `AGENTS.md`, rule 9); if it mentions Teams at all, it says it did not read it.

## Screenshots

- The chat with Mara after sending, dark and light
- The `release-train` channel after posting, dark and light
- The agent's note
