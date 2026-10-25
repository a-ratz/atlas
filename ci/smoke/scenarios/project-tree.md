---
demo: true
timebox: 15
max_steps: 20
---

# Projects as a tree in the sidebar

The user finds their projects in the sidebar under their groups. A group opens and closes and stays
that way after a reload. The agent starts a project in a group that does not exist yet, and it shows
up in a node of its own.

## Steps

1. Find the projects in the sidebar. Close the group "Work". Reload the page.
2. On the operator page, ask: "Start a project 'Garden planner' in a new group 'Hobby', with one
   thread: choose the seeds for spring."
3. When the agent says it is done, look at the sidebar without reloading.
4. Open "Projects" (the link above the tree) and from there the project "Thesis", while "Work" is
   still closed. Then go Home and reload.

## Must be observable

- The groups show their titles ("Private", "Work") and how many projects each holds; "Work" stays
  closed after the reload in step 1.
- After step 2 the new project sits in its own group node (titled from the group's note if the agent
  wrote one), without a reload.
- In step 4 the sidebar shows "Thesis" inside an opened "Work"; after going Home and reloading,
  "Work" is closed again, as the user left it.

## Screenshots

- The sidebar with "Work" closed after the reload
- The sidebar with the new group and project
