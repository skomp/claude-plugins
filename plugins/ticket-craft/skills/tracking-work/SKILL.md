---
name: tracking-work
description: "Read BEFORE writing or editing any ticket. Load when you are about to write a GitHub issue, a sub-issue, a user story, acceptance criteria, or a `TODO.md` entry; edit the body of an existing issue; file a ticket for work you are deferring; label an issue you created; or decide where this project tracks its work."
---

# Tracking Work

Two questions, one moment: **where does this get written down, and how is it worded.**

## Part 1 — Where it goes

Capture next steps and known gaps somewhere durable, not only in chat.

Two options: a `TODO.md` file, or GitHub issues (preferred in general, but overkill for very small projects). Task tracking is a **per-project choice**:

1. Check that project's `CLAUDE.md` for an existing tracking preference and follow it.
2. If none is recorded, **ask the user which to use (GitHub issues vs. `TODO.md`) before writing anything**, then record the answer in that project's `CLAUDE.md` so future sessions don't need to ask again.

Write down anything deliberately deferred — an entry in the project's chosen tracker, or a deferral comment marker your project already uses (`TODO:`, `FIXME:`, or your own) — instead of leaving it implicit.

### Label every issue Claude creates

Label every GitHub issue Claude creates with `created-by-claude`, so automatically created issues are identifiable. If the repo doesn't have the label yet, create it first:

```bash
gh label create created-by-claude --description "Issue created automatically by Claude" --color D97706
```

Worth a one-line tripwire in your `CLAUDE.md` as well, because an unlabelled issue is outward-facing. **CLAUDE.md carries the bare obligation; this skill carries the command and the reasoning.**

## Who writes it: the `ticket-writer` agent

Wording a ticket in STE100 is rule-following, not reasoning, so this plugin ships an agent
that does it on a smaller model: `ticket-craft:ticket-writer`, on Haiku. Your session keeps
the parts that need the conversation:

1. **Decide where it goes** (Part 1). Ask the user if the project has no recorded choice.
   The agent cannot ask.
2. **Collect the facts** into the dispatch brief: the repository as `owner/repo` (or the
   issue number to edit, or the `TODO.md` path), what happened, the evidence, what done
   looks like, and any project labels beyond `created-by-claude`. Paste commands, error
   strings, paths and measurements verbatim. The agent uses nothing that is not in the
   brief.
3. **Dispatch the agent**, one ticket per dispatch.
4. **Check what it filed** before you report it: `gh issue view <n> --repo <owner/repo>`.
   Read the title, the labels and every verbatim string against your brief.

If the agent is not available — a tool other than Claude Code, or a session where
subagents are blocked — write the ticket yourself with the rules below.

## Part 2 — How it is worded

Every ticket you write uses **ASD-STE100 Simplified Technical English**: GitHub issue titles and bodies, sub-issues, user stories, `TODO.md` entries, acceptance criteria, and edits to an existing issue body.

**Why:** the readers include people with no context on the change and non-native English speakers, and STE removes the ambiguity that otherwise costs a clarifying round-trip.

The rules that earn the most:

- **One instruction per sentence.** Keep procedural steps under 20 words and descriptive sentences under 25.
- **Active voice, with a named actor.** "The API returns 404" — not "A 404 is returned".
- **One word, one meaning, every time.** Do not alternate "ticket"/"issue"/"task" or "user"/"caller"/"client" in one document. Choose one term and repeat it.
- **Simple approved verbs.** "remove", not "get rid of"; "start", not "kick off"; "change", not "touch up". Avoid phrasal verbs.
- **Simple present, past or future only.** "when the cache expires", not "on the cache expiring". Avoid `-ing` forms used as verbs.
- **Keep the articles.** "Add the flag to the config file", never "Add flag to config".
- **No noun stack longer than three words.** "the timeout for the token refresh", not "the token refresh timeout config value".
- **One topic per paragraph**, short paragraphs, and a list for any set of steps or conditions.
- **Say what to do, not what to avoid**, and put a warning before the step it applies to.

### Precision wins

Where STE and precision conflict, **precision wins**: identifiers, file paths, commands, error strings and API names stay verbatim, however long or unapproved the words are. **Never simplify a symbol name to make a sentence read better.**

### Scope

This is about tickets. Chat replies, commit messages, code comments and design docs keep their normal voice.

One rule reaches further, because it governs all prose including chat: **always qualify an issue or PR reference with the repo.** Never write a bare `#123`; write `PR: <repo>#<number>` for a pull request (`PR: repo-b#56`) and `repo#123` for an issue (`repo-a#81`). It applies to every ticket you write here too.

### The qualification rule collides with GitHub's closing keywords

A tutorial-authoring project, 2026-09-13. Three commits carried `Closes courseware-runner#24`,
`Closes courseware-runner#26`, `Closes courseware-runner#27`, were pushed to the default
branch, and **closed nothing**. All three issues were still open afterwards and had to be
closed by hand.

GitHub parses a closing keyword followed by `#123` (same repository) or by
`owner/repo#123`. It does **not** parse `repo#123` — the short qualified form this skill
asks for everywhere else. The reference renders as plain text, the issue stays open, and
nothing reports a problem: the push succeeds, the commit looks right, and the board is
silently wrong.

So the two rules want different spellings, and both are correct in their place:

| Where | Write | Why |
|---|---|---|
| prose, tickets, chat, plan documents | `repo-a#81`, `PR: repo-b#56` | a bare `#123` is unresolvable across repos |
| a **closing keyword** in a commit message or PR body | `Closes owner/repo-a#24` | the only qualified form GitHub's parser acts on |

The owner-qualified form satisfies both — it names the repository unambiguously *and* it
closes. Use it whenever the reference is load-bearing for automation.

### The second way it fails: backticks

A tutorial-authoring project, 2026-09-14. PR: courseware-runner#39 carried
`Closes owner/courseware-runner#28` and `Closes owner/courseware-runner#29` — the
owner-qualified form this skill asks for, spelled correctly — and closed neither issue. Both
were written inside backticks, to set them off typographically in the PR body.

**A closing keyword inside a code span or a fenced block is never parsed.** GitHub linked
nothing: `closingIssuesReferences` came back empty. The reference is right, the rendering
looks deliberate and tidy, and the automation sees an inert string.

So a keyword has to be correct twice: the **owner-qualified form**, and **bare prose** — no
backticks, no fence. The instinct that makes a reference look like a reference is the
instinct that breaks it.

**Do not trust the close to have happened.** After pushing a commit that claims to close
something, check each issue directly: `gh issue view <n> --repo <owner/repo> --json state -q
.state`. The failure is silent by construction, and an issue that a commit message says is
closed is exactly the issue nobody looks at again. Do not grep `gh issue list` output for
`#<n>` instead: its columns need not contain that string, and that grep once reported
still-open issues as closed.

For a **PR** the keyword fires on merge, not on push, so the better probe runs *before*
merging and does not depend on issue state at all:

```bash
gh api graphql -f query='{repository(owner:"OWNER",name:"REPO"){pullRequest(number:N){closingIssuesReferences(first:10){nodes{number title}}}}}'
```

An empty list means GitHub linked nothing, whatever the body looks like. Run it when you
open the PR, while the fix is one `gh pr edit` rather than a round of manual closes.
