# First run: install Atlas

The user does not want an onboarding. Ask at most three short questions, then
start Atlas. If your harness has a question tool (Claude Code: AskUserQuestion),
use it with the options below. Otherwise ask in one message with numbered
options.

## 0. uv

Run `uv --version`. If uv is missing, ask, then install it:

- macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

## 1. Where should Atlas live?

Atlas becomes a folder of its own: the app plus the user's vault, in one git
repository. Offer these options:

1. **`~/atlas`** (recommended).
2. **Here**, meaning the current folder. Offer this only if the folder is
   empty. If it is not empty, offer `<current folder>/atlas` instead.
3. **Another folder:** ask for the path.
4. **"I already have an Atlas."** This covers a folder on this machine, or a git
   URL of one the user set up elsewhere:
   - a folder: `atlas_install.py locate <dir>`;
   - a URL: `git clone <url> <dir>`, then `locate <dir>`.

   In both cases, skip to step 5.

## 2. Install

```bash
uv run --no-project <skill>/scripts/atlas_install.py install <dir>
```

The script does all of this:

- it copies the app;
- it links `.claude/skills` to `.agents/skills`;
- it records the factory version of every file in `.atlas-install.json`;
- it runs `git init` and the first commit;
- it saves the pointer to the new folder.

If git has no user name or email, the script says so. In that case, ask the
user whether to set them, and commit afterwards.

## 3. Demo notes?

Ask: "Load demo notes, so you can try Atlas with a full vault right away? You
can remove them any time." Offer:

1. **Yes, load the demo** (recommended for a first install).
2. **No, start empty.**

The demo is a researcher's vault on sleep, memory and learning, with two
projects, open questions, a research run and a tour, committed in steps over
the last ten days. If the user says yes:

```bash
uv run --no-project <dir>/engine/atlas.py demo
```

It never writes over an existing note. `atlas-clean-demo` (or
`engine/atlas.py demo --remove`) takes the demo out again and keeps every demo
note the user changed.

## 4. A private GitHub backup? (optional)

Ask only if `gh auth status` succeeds. The question: "Back it up to a private
GitHub repository?" The default answer is no.

If the user says yes:

```bash
gh repo create <name> --private --source <dir> --remote origin --push
```

`<name>` defaults to the folder name. The vault holds the user's own
knowledge, so the repository is always private. With this backup, another
machine can install Atlas there and pick option 4 with the repository URL.

## 5. Start

Hand over to the home. Follow `<dir>/.agents/skills/atlas-operator/SKILL.md`,
which also has you write your own identity file in `vault/agents/`.

Then tell the user, in two or three lines:

- where Atlas lives;
- that every harness with this skill now finds it ("start atlas" from
  anywhere);
- that typing `/` in Atlas's chat lists what it can do;
- with the demo: that it is demo data, and "clean the demo" removes it.
