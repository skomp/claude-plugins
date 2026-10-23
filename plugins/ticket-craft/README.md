# ticket-craft

One skill and one agent, one job: decide where work gets written down, and word it in
ASD-STE100 Simplified Technical English.

## What it's for

**`tracking-work`** — two questions at one moment. *Where it goes*: task tracking is a
per-project choice (GitHub issues, preferred in general, or a `TODO.md` for very small
projects); check the project's `CLAUDE.md` for an existing preference, and if there isn't
one, ask before writing anything and record the answer for next time. Every issue Claude
creates carries the `created-by-claude` label. *How it's worded*: every ticket — issue
titles and bodies, sub-issues, user stories, acceptance criteria, `TODO.md` entries — uses
STE100: one instruction per sentence, active voice with a named actor, one word per
meaning, simple approved verbs, no noun stack longer than three words. Identifiers, file
paths, commands, error strings and API names stay verbatim even where that fights the
style — precision wins over simplification there.

See `skills/tracking-work/SKILL.md` for the full rule set.

**`ticket-writer`** — the agent that does the wording, on Haiku. Your session decides where
the ticket goes and collects the facts; it then dispatches `ticket-craft:ticket-writer`,
which reads the skill's wording rules, writes the ticket in STE100, files it, and returns
the URL. The wording is rule-following, so it does not need your session's model.
Measured on 2026-10-23: one `TODO.md` entry, written on `claude-haiku-5-5` for $0.0037,
with every command and path kept verbatim. The agent is Claude Code only; in Codex and
Copilot CLI the skill tells the session to write the ticket itself.

How a Claude Code agent is built:

- Subagent files, their frontmatter and the `model` field:
  https://code.claude.com/docs/en/sub-agents
- Where a plugin keeps its agents (`agents/`) and how they are named
  (`plugin-name:agent-name`): https://code.claude.com/docs/en/plugins-reference#standard-layout

## Install it if

You want STE100 enforced on every ticket. Deliberately packaged alone, separate from
`evidence-discipline` and `agent-operations`, so wanting the verification or coordination
rules never drags this one in too.
