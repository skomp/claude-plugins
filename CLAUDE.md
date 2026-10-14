# claude-plugins

## Where work is tracked

This project uses GitHub issues, not a `TODO.md`. Label every issue that Claude
creates with `created-by-claude`.

## What this repository is

This repository holds six Claude Code plugins. The skills come from real failures
in other projects. The project names are redacted. The dates, commands, error strings
and measurements are verbatim, and you must keep them that way.

## The marketplace name is not the repository name

The repository is `skomp/claude-plugins`. The `name` in `.claude-plugin/marketplace.json`
is `skomp-plugins`, and the two must stay different. Claude Code rejects a marketplace
named `claude-plugins` with *"Marketplace name impersonates an official Anthropic/Claude
marketplace"*, and then the marketplace does not load at all. The name was `claude-plugins`
from 2026-09-14 to 2026-10-11 and nothing in this repository reported it.

Run `claude plugin validate .` before you commit a change to the marketplace manifest or
to a `plugin.json`. It also reports a marketplace entry whose `version` differs from the
plugin's own `plugin.json`.

## Before you change a skill

**This repository is the only copy.** Until 2026-10-14 the author also kept a private,
unredacted copy of six of these skills in `~/.claude/skills/`, and that copy was often
*ahead* of this one: whole sections existed only there. On 2026-10-14 every private-only
rule was ported here — the last two were the "grep the old referent" bullet in
`completing-a-correction` and the backticks section and pre-merge
`closingIssuesReferences` probe in `tracking-work` — and the private copies were retired in
favour of the installed plugins. The retired copies are in `~/.claude/skills/.trash/` if a
question about the history ever needs them.

So a lesson learned in a session is written **here**, not into `~/.claude/skills/`, and
reaches the running sessions through a release and `claude plugin update`. If a private
copy of a skill appears again in `~/.claude/skills/`, diff it against this repository
before anything else, port any content that exists only there, and retire it again.

When you change a skill:

1. **Write it redacted from the start** — project names replaced with a generic
   description; dates, commands, measurements, error strings and version numbers kept
   verbatim. `README.md` under "On provenance" is the rule.
2. **Bump the plugin's `version`** in both its `plugin.json` and its marketplace entry.
   An installed plugin is cached by version, so a change with no bump never reaches an
   installed copy.
3. **Prove the redaction with a command before committing**, not by reading:
   `grep -rniE '<real-name>|<real-name>' plugins/ && echo LEAK || echo clean`. A check that
   has only ever passed is not evidence — plant one of the strings in a scratch copy of
   `plugins/` first and confirm the grep reports LEAK.
