# A guided run: from research to a playable roguelike

This page walks through one real session with Atlas, from an empty vault to a game you can
play. The topic was roguelike games. In about two hours the vault went from nothing to:

- 2 research captures, distilled into 19 insights;
- 6 open questions and 10 people and organization cards;
- 2 maps and search by meaning;
- one idea, picked from eleven candidates, then a spec;
- a project with 6 decisions and 3 lessons;
- a greybox of the game, tested.

**[▶ Play the result: Terrain Only](https://a-ratz.github.io/atlas/guided-run/)**, a turn-based
roguelike in which you cannot attack. Each turn you change one tile, and the terrain does the
killing.

How the run was set up:

- Atlas 0.9.0, freshly installed in a new folder: empty vault, no QMD index, no cards. The
  game's code went into a separate, empty git repository.
- The operator was Claude Code in operator mode, wired to Atlas's chat. It saw only what reached
  the chat and the files it read itself.
- The user's side was a second agent driving the browser through a script. It typed the messages
  quoted below and pressed the same buttons a person would.
- Screenshots come from the run, in dark mode, with the machine name set to `laptop`
  (`ATLAS_MACHINE`). The run found bugs in what steps 2, 4 and 7 showed (answer buttons as raw
  text, search snippets with frontmatter). Those screenshots were retaken on the release that
  fixed them; see [What the run changed](#what-the-run-changed).

| Step | The user wrote or pressed | Skill the agent used |
|---|---|---|
| [1. An empty vault](#1-an-empty-vault) | nothing yet | |
| [2. Research the landscape](#2-research-the-landscape) | "Research the current roguelike landscape…" | atlas-learn |
| [3. Research the craft](#3-research-the-craft) | "Now research roguelike game-design best practice…" | atlas-learn |
| [4. Distill both](#4-distill-both) | `/distill all` | atlas-distill |
| [5. Questions and cards](#5-open-questions-and-the-cabinet) | a move, two requests | atlas-distill, atlas-cabinet |
| [6. Maps](#6-maps) | "Build maps for the insights…" | atlas-map |
| [7. Search by meaning](#7-search-by-meaning) | "Can you search my notes by meaning too?" | atlas-qmd |
| [8. Sketch an idea](#8-sketch-an-idea-from-the-vault) | `/sketch ideas for a novel roguelike…` | atlas-sketch |
| [9. Spec it](#9-spec-it) | the move "Turn this sketch into a spec" | atlas-spec |
| [10. Start a project](#10-start-a-project) | the move "Start a project from this spec" | atlas-project |
| [11. Build the first slice](#11-build-the-first-slice) | "Let's work on Terrain Only…" | atlas-project |
| [12. Close the session](#12-close-the-session) | `/close` | atlas-project |

## 1. An empty vault

![Home on an empty vault](assets/guided-run/01-empty-home.webp)

Home on a new vault asks one question and offers three starters. Every section in the
sidebar is empty: insights, maps, sources, questions, ideas, projects, cards.

**Take away:** you start by asking; Atlas does not need a setup step first.

## 2. Research the landscape

**The user:** "Research the current roguelike landscape: which games and subgenres define it in
2025 and 2026, what is new, and what players love and complain about."

![The operator page while the agent researches](assets/guided-run/02-researching.webp)

The agent posts a progress line at each step. The workbench on the right shows the pages
the agent opens. Eleven minutes later it answered:

> Done. Short version: roguelites were Steam's #1 genre tag among 2025's hits, by units and by
> revenue (GameDiscoverCo). […] Sales figures come from the studios' own posts, the review data
> straight from Steam's API. Player opinions are graded weak because they come from a sample of
> the most-helpful reviews.

![The answer, its capture card and three next steps](assets/guided-run/03-research-answer.webp)

The answer ends with the capture as a card you can unfold in place, and three next steps as
buttons: distill it, dig into the Slay the Spire 2 review split, or measure the meta-progression
complaint properly. (The card shows the note as it is today: after step 4 it became a source.)
The capture itself is a page with the question, the scope the agent picked, the answer and its
24 sources:

![The research capture](assets/guided-run/04-capture.webp)

**Take away:** research lands as a capture, a pending note marked "not yet knowledge". Its
claims count only after they are distilled and traced to a source.

## 3. Research the craft

**The user:** "Now research roguelike game-design best practice: what makes runs replayable,
fair and deep. Primary sources: designer talks, postmortems and papers."

![The design capture](assets/guided-run/05-capture-design.webp)

The agent read 12 talks (from their transcripts), 2 designer essays and 3 papers. It linked the
new capture to the first one: Darkest Dungeon's 2016 corpse patch and Slay the Spire 2's nerfs
both caused an early-access review collapse. It also named a gap: every source argues for
meta-progression, and none measures what it costs in grind.

**Take away:** say which sources count ("primary sources"), and the agent picks its scope and
states it at the top of the capture.

## 4. Distill both

**The user:** `/distill all` (the arrow between Captures and Insights does the same).

![The distill answer](assets/guided-run/06-distill-answer.webp)

Both captures became 19 insights, 6 open questions and 10 cards, one commit per capture. The
answer opens with a correction:

> **Correction:** I had said grind was the top player complaint. Counting the 90 negative
> reviews showed otherwise: balance comes first (mostly Slay the Spire 2), then luck, then
> grind and repetition. […] I fixed the source and wrote the insight from the count.

![Insights](assets/guided-run/07-insights.webp)

![One insight with its provenance](assets/guided-run/08-insight.webp)

Each insight states its claim in the title, with a confidence bar (speculative, working,
proven). The margin traces it back to its source.

**Take away:** distilling is where the claims get checked. Here the check overturned a claim
the agent had made in its own research.

## 5. Open questions and the cabinet

Distilling raised 6 open questions: claims the sources could not settle, each with what would
answer it.

![Open questions](assets/guided-run/09-questions.webp)

**The user** pressed the move "Set this open question to dormant: not now" on the question about
zero-review releases. The question stays and drops out of the open list. A later capture that
raises it again brings it back.

![A dormant question](assets/guided-run/11-question-dormant.webp)

Distilling also created cards for the people and organizations the sources named: 7 people and
3 organizations, each at `depth: minimal`. These were the vault's first cards, so the agent
asked whether to enrich them from LinkedIn:

![The LinkedIn question](assets/guided-run/06b-linkedin-question.webp)

**The user:** "No LinkedIn, please. Public sources are enough for the cards." The agent recorded
that in `atlas.yaml` (`cabinet.enrich: off`).

**The user:** "Expand the cards of Derek Yu and Mega Crit."

![People](assets/guided-run/10-people.webp)

| Before | After |
|---|---|
| ![A minimal card](assets/guided-run/12-card-minimal.webp) | ![A complete card](assets/guided-run/13-card-complete.webp) |

The expanded card links every fact to its page, records what it did not find (GitHub,
LinkedIn) and counts the lookups (5). It leaves out the email address on Derek Yu's site,
because a card's contact details come only from the user.

**Take away:** questions and cards are by-products of distilling. You decide which ones get
more work.

## 6. Maps

**The user:** "Build maps for the insights: one for market and reception, one for design."

![The design map](assets/guided-run/14-map.webp)

A map is a page that orders insights into an argument; the design map goes through replayability,
fairness and depth. Every insight now names its map in `topics`, and two belong to both maps.

![The constellation](assets/guided-run/15-graph.webp)

**Take away:** maps are where 19 loose claims become something you can read in order.

## 7. Search by meaning

**The user:** "Can you search my notes by meaning too? If it needs a setup, go ahead."

The agent set up [QMD](https://github.com/tobi/qmd) for this vault: one local index, five
collections, nothing sent off the machine. Search then has two tabs, "By words" and "By
meaning":

![Search by meaning](assets/guided-run/16-search-by-meaning.webp)

"losing a run to bad luck" finds the insight on what players complain about, the design
capture and the insight on enemy intent. The screenshot was retaken after the run, so the
spec from step 9 ranks first.

**Take away:** word search works from the start. Search by meaning takes one request to set up,
and it runs on your machine.

## 8. Sketch an idea from the vault

**The user:** `/sketch ideas for a novel roguelike that one developer can build as a browser
game in a weekend, grounded in what this vault knows about the genre and its design`

![The agent generating ideas](assets/guided-run/17-ideating.webp)

The atlas-sketch skill generates ideas by combining insights, inverting them and answering open
questions. It then tries to kill each one. Eleven candidates came out. Seven died at the gates,
two of them because Scoundrel and NetHack's bones files had already shipped them. A reviewer in
a separate context, given only the cards and the goal, tried to kill the last four. Three were
left, offered as choices:

![Three ideas to pick from](assets/guided-run/18-ideas.webp)

> **1. Terrain Only.** A turn-based grid roguelike where you have no attack at all. […] **What
> would kill it:** one move (light the grass) solving most boards, or chain reactions too hard
> to foresee. **Fairly obvious:** the reviewer called it "Into the Breach minus the guns".

**The user** pressed "Sketch Terrain Only".

![The sketch](assets/guided-run/19-sketch.webp)

![The red-team and the alternatives](assets/guided-run/20-sketch-redteam.webp)

The sketch keeps the five insights it rests on and the reviewer's full case against it. It also
lists the ten other ideas, each with why it died or was not picked, and the smallest test that
could kill it.

**Take away:** an idea in Atlas comes with its grounding and its strongest objection, so a
later reader can disagree on evidence.

## 9. Spec it

**The user** pressed the sketch's move "Turn this sketch into a spec".

![The spec](assets/guided-run/21-spec.webp)

The spec makes nine design decisions; seven rest on vault insights and two are named as gaps.
A reviewer in a separate context found the hole that mattered:

> Enemies walked their announced path whatever happened, so "water on the announced tile" would
> have won every turn. Enemies now avoid visible water, chasms and fire, so every kill needs a
> second piece.

![Design decisions in the spec](assets/guided-run/22-spec-decisions.webp)

The reviewer also showed that several acceptance criteria could not fail. They were rewritten
so they can. A greedy bot must lose most boards, and no single kill pattern may exceed 40%. The
first slice starts on paper, with a stop rule: if a greedy policy wins two of three boards,
change the rules before writing any code.

**Take away:** a spec states what would prove it wrong, and the review checks that each
criterion can fail.

## 10. Start a project

**The user** pressed the spec's move "Start a project from this spec".

![The new project](assets/guided-run/23-project.webp)

The project page shows the line from project to spec to sketch, one open thread (the first
slice) and its next step. "What an agent loads here" shows what `boot` hands every agent that
works on the project, with its size in tokens. No code existed yet, so the agent mapped no
checkout. Atlas still warned about an unmapped checkout here; since
[#24](https://github.com/a-ratz/atlas/issues/24), a project without code says "no code yet".

**Take away:** a project knows where it came from, and every agent that boots into it reads
the same next step.

## 11. Build the first slice

**The user:** "Let's work on Terrain Only. The code goes into
/tmp/atlas-smoke-guided-run-0b55d2bm/code/terrain-only, an empty git repository I just made.
Map it, then do the first slice."

The agent recorded the checkout under `paths:` (`map-path`), wrote the rules page and three
boards, and played the greedy policy by hand. **The stop rule fired:**

> Greedy wins Meadow and Rink in three turns each. […] The culprit is not fire on grass, as the
> spec expected, but ice: one placed ice slides a walker along the whole line into a chasm, even
> one three tiles away (4 of 8 kills).

It wrote no code. It proposed a rule change as a decision with `status: proposed` and blocked
the thread, because a change to the spec's rules is the user's call.

![The stop rule fired](assets/guided-run/24-slice-result.webp)

**The user** pressed "Accept the proposed ice rule. Update the rules and the spec, replay greedy
on paper on the same three boards, and build the greybox if it passes."

![The accepted ice decision](assets/guided-run/30-decision.webp)

With the new rule, greedy won one board of three, so the test passed and the agent built the
greybox: one static HTML file and two test suites. The tests replay every paper trace in code.
That replay found one error in the agent's hand traces; the verdict held. A second check plays
300 boards through the page in headless Chrome. The agent's answer separates what it checked
from what it could not:

> **Not verified:** anything a person does. The rest of the slice needs five cold testers, each
> playing every board twice, and you would have to find them.

| The game | Its preview |
|---|---|
| ![Terrain Only, turn 1](assets/guided-run/26-game.webp) | ![The preview shows ice on f3 sliding W3 into the chasm](assets/guided-run/27-game-preview.webp) |

Point at a tile and the game previews the turn: ice on f3 slides walker W3 into the chasm
below it. [Play it](https://a-ratz.github.io/atlas/guided-run/).

**Take away:** the agent writes decisions and lessons as it works. The ice rule has its
why, what was rejected and what it changed. The traces gave a lesson: "When a check was done
by hand on paper, replay it in code before relying on it."

## 12. Close the session

**The user:** `/close`

![The project after the session](assets/guided-run/28-project.webp)

Closing writes the thread's last log line, updates the project page and checks the vault. The
page now shows where the work stopped: steps 1 to 4 of the first slice done, 6 decisions in
force, 3 provisional lessons, and the next step blocked until five playtesters are found.

![The first-slice thread](assets/guided-run/29-thread.webp)

The thread log reads as the session's history: each line has a date, the agent, what changed
and links to the decisions and lessons it produced.

**Take away:** the next session, by you or another agent, starts from this page.

## What the run changed

The run used Atlas the way a new user would. Each thing that went wrong became an issue and a
pull request with Codex review rounds and regression tests, merged before this page shipped:

| Found in step | What went wrong | Fixed in |
|---|---|---|
| 2–4 | An answer whose last block was left open showed raw YAML instead of buttons. | [#20](https://github.com/a-ratz/atlas/issues/20), [PR #21](https://github.com/a-ratz/atlas/pull/21) |
| 5, 7 | The facts line repeated the type's status; search by meaning failed when the server's working folder was gone; snippets showed frontmatter. | [#22](https://github.com/a-ratz/atlas/issues/22), [PR #23](https://github.com/a-ratz/atlas/pull/23) |
| 8–10 | The idea skills left open what to do in four places, and a project without code warned about an unmapped checkout. A second Atlas on the same vault turned the first one standalone. | [#24](https://github.com/a-ratz/atlas/issues/24), [PR #25](https://github.com/a-ratz/atlas/pull/25) |
| 9, 11 | Table cells broke words mid-word; thread log lines showed `[[wiki links]]` as raw text. | [#27](https://github.com/a-ratz/atlas/issues/27), [PR #28](https://github.com/a-ratz/atlas/pull/28) |
| 11 | `map-path` rewrote the whole frontmatter of `project.md`. | [#29](https://github.com/a-ratz/atlas/issues/29), [PR #30](https://github.com/a-ratz/atlas/pull/30) |

The idea skills themselves, atlas-sketch's generate mode and atlas-spec, came in just before
the run ([#16](https://github.com/a-ratz/atlas/issues/16),
[PR #19](https://github.com/a-ratz/atlas/pull/19)). The run was their first real use.

## Try it yourself

Install Atlas ([Quick start](../README.md#quick-start)), start it, and ask your first question
in its chat. To follow this run, use the same prompts: they are quoted above, in order.
