---
name: atlas-cabinet
description: Create and update Cabinet cards for people and organizations in vault/cabinet/, expand minimal cards to a fixed profile within a budget ("Expand cards", /expand-cards), and enrich them from LinkedIn when the user has switched that on. Use when a person or organization should get a card ("leg eine Akte an", "add a card for…"), when you learn something new about someone with a card, or when the user asks to look someone up ("check her LinkedIn", "enrich the card").
---

# Cabinet cards

One card per person in `vault/cabinet/people/<name>.md` and per organization in
`vault/cabinet/orgs/<name>.md`, the name in lowercase ASCII with hyphens
(`jan-born.md`, `university-of-tuebingen.md`). AGENTS.md, Cabinet, has the card format and the
content rules. This skill covers creating cards, keeping them current, and
optional enrichment from LinkedIn.

## 1. Create or update a card

1. Search first: `uv run --no-project engine/atlas.py mentions "<name>"` and the
   aliases of existing cards. Update a card rather than creating a second one.
2. Fill what the user or a source in the vault says. Leave unknown fields empty.
   Never guess an email address, a surname or a title.
3. Add a timeline entry with a date and a source for every new fact.
4. Tell the user what you created or added.

When this is the first person card in the vault and `cabinet.enrich` in
`vault/atlas.yaml` is `ask` or missing, ask the question in step 2 below once,
after the card exists.

## 2. LinkedIn enrichment: the setting

`vault/atlas.yaml` holds:

```yaml
cabinet:
  enrich: ask      # ask | linkedin | off
  tool: ""         # the browser tool that passed the check
  checked: ""      # date of the last passing check
```

A missing block means `enrich: ask`. Ask once:

> Should I enrich new person and organization cards from LinkedIn? I would read
> only professional details (headline, role, employer, past roles, education,
> public talks and projects) through your logged-in browser. They see the
> profile visit unless you switch LinkedIn's private mode on.

On **no**, set `enrich: off`. On **yes**, run the check before setting anything:

1. **Tool:** Is a browser-control tool available to you in this session? For
   example, Claude in Chrome, a Playwright MCP server, or your harness's own
   browser tool. If none is available, set `enrich: off` and say why.
2. **Login:** Open `https://www.linkedin.com/feed/`. If the page lands on a login
   or "authwall" page, the user is not logged in. Set `enrich: off` and ask them
   to log in and say "check LinkedIn again". Never type a password or a code.
3. **Pass:** Set `enrich: linkedin`, record the tool name in `tool` and today's
   date in `checked`, and tell the user.

The user can change the answer at any time ("stop the LinkedIn lookups",
"check LinkedIn again"). Rerun the check whenever a lookup fails because the
tool is missing or the session has logged out. Until it passes, treat the
setting as off.

## 3. Enrich a card

Do this when `enrich: linkedin` is set and you create a person or organization
card, or when the user asks you to enrich one.

1. **Find the profile.** Search LinkedIn people (or companies) with the name
   plus the employer or city from the card. Open a profile only when one
   result clearly matches. When several could match, list them with name,
   headline and location, and let the user pick.
2. **Read only professional details:** headline, current role and employer,
   earlier roles with years, education with years, location at city or region
   level, certificates, public talks, projects and publications. For an
   organization: industry, size, headquarters, website.
3. **Leave out** private life, family, photos, age, health, politics and
   religion. Leave out contact details too; the card's `email` and `phone` come
   from the user only. Opinions belong on the card only when they are public,
   professional, and relevant to how the user works with this person. Label
   them as positions taken in posts.
4. **Write it down.** Put a "LinkedIn (viewed <date>)" section into the card's
   body with the profile link, update `role:` if the current role differs, and
   add a timeline entry: `<date> · LinkedIn profile viewed: <what you took>.
   (Source: <profile URL>)`.
5. **Report** what you added, and remind the user once per session that the
   person sees the profile visit.

## 4. Expand cards

Distill leaves **minimal** cards (`depth: minimal`): only what the vault says.
"Expand cards" (`/expand-cards [name]`, the 🔎 Expand button on a card) completes
them. Expand only when the user asks; distill itself never searches.

**Complete is a fixed profile, not everything findable:**

| Person | Organization |
|---|---|
| current role and organization | what it does, in one line |
| up to 3 earlier roles, with years | headquarters region |
| one line of expertise | size band (e.g. 50–200 people) |
| up to 3 public works that matter to this vault, linked | website |
| public professional channels: website, GitHub, X or Bluesky, LinkedIn URL | up to 3 products or works that matter to this vault |
| | people who already have cards, linked |

Every fact gets its source URL and the date you checked it. A field you cannot
find is written as `not found (YYYY-MM-DD)`, never filled with a guess. A card
is complete when every field is filled or marked not found: then set
`depth: complete` and `checked: YYYY-MM-DD`.

**Who may be looked up on the web:** organizations, and people the vault knows
through their *public work*: authors of a source, speakers, founders, people
named in the press. Cards from a distill are these. A private contact (someone
the user knows personally, a colleague, a customer contact) stays vault-only:
expand it only from the vault, and through LinkedIn only when
`cabinet.enrich: linkedin` is set (section 3). When unsure, ask.

**Budget** (`cabinet.expand` in `vault/atlas.yaml`): at most `lookups_per_card`
searches or page fetches per card (default 6), about three minutes, and at most
`cards_per_run` cards per run (default 10), the most-linked minimal cards first.
Look in this order: the vault, then, for organizations and people known for
public work, the entity's own site and profiles and a web search, then LinkedIn
only if `cabinet.enrich: linkedin` is set. Stop a card when the profile is full
or its budget is spent.

**Report** in Atlas: which cards became complete, which fields stayed not found,
and every profile you visited (LinkedIn shows the visit). A complete card is
expanded again only when the user asks, or when its `checked` date is older
than `stale_months`.

## Rules

- Never connect, follow, message, react, endorse, or change a LinkedIn setting.
- Never expand or enrich a card unless the user asked for it (a button, a
  command, a sentence). No crawling of colleagues, connections or "people also
  viewed".
- A card that is about the user stays as the user wrote it.
- Professional details only; when in doubt, leave it out and ask.
