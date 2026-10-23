# claude-plugins

## Where work is tracked

This project uses GitHub issues, not a `TODO.md`. Label every issue that Claude
creates with `created-by-claude`.

Every issue also carries two more labels:

- **One `plugin:` label** naming the plugin it belongs to: `plugin:evidence-discipline`,
  `plugin:agent-operations`, `plugin:ticket-craft`, `plugin:session-relay`,
  `plugin:tone-roulette`, `plugin:machines`. Use `plugin:marketplace` for packaging and
  marketplace work that belongs to no single plugin.
- **One `severity:` label:**
  - `severity:high`: wrong behaviour or lost data in normal use.
  - `severity:medium`: a real gap or defect with a workaround, or one that is reachable
    only sometimes.
  - `severity:low`: unreachable in normal use, or a design item that is not yet due.

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

## Codex and Copilot CLI manifests are generated

The files under `.claude-plugin/` are the source of truth. `scripts/sync-manifests.py`
writes the Codex marketplace (`.agents/plugins/marketplace.json`), the Copilot CLI
marketplace (`.github/plugin/marketplace.json`) and each plugin's
`.codex-plugin/plugin.json` from them. Never edit a generated file by hand: change the
Claude Code manifest, run the script, and commit both. CI runs
`scripts/sync-manifests.py --check` and fails on a stale file.

Copilot CLI looks for `.github/plugin/marketplace.json` before
`.claude-plugin/marketplace.json`, so the generated file is the one it uses. That is what
keeps `tone-roulette` out of it. `tone-roulette` is Claude Code only (output styles and
hooks), and `CLAUDE_ONLY` in the script lists it. Copilot CLI reads each plugin's
`.claude-plugin/plugin.json` directly and needs no plugin manifest of its own.

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
   installed copy. Then run `scripts/sync-manifests.py`, which carries the bump into the
   Codex manifest; Codex caches by version too.
3. **Prove the redaction with a command before committing**, not by reading:
   `grep -rniE '<real-name>|<real-name>' plugins/ && echo LEAK || echo clean`. A check that
   has only ever passed is not evidence — plant one of the strings in a scratch copy of
   `plugins/` first and confirm the grep reports LEAK.
