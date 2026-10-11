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

Two copies of these skills exist. This repository holds the public, redacted copy. The
author keeps a private copy in `~/.claude/skills/`, and that is the copy that actually
runs, so it is the copy sessions edit in the moment a lesson is learned.

**Neither copy is canonical in practice.** This repository is the publication target and
the place a rule is meant to end up, but the private copy is frequently *ahead*: whole
sections have existed only there, never in any commit here. Measured 2026-09-13, public
lines against private: `writing-plans-and-dispatches` 54 / 101 and `tracking-work` 57 / 83
were each missing an entire rule, and `parallel-sessions` 281 / 363 was missing four
sections. `completing-a-correction` 30 / 30, `recovering-a-session` 53 / 53 and
`verifying-claims` 184 / 182 differed only by redaction and voice.

So before you change either copy:

1. **Diff them first**, per skill, and read the diff:
   `diff "$(find plugins -name SKILL.md -path "*/<skill>/*")" ~/.claude/skills/<skill>/SKILL.md`
2. **Expect two kinds of difference and treat them differently.** Redaction and voice
   differences are correct — the public copy replaces project names and addresses the
   reader as "you". A missing *heading* is never correct; it is content that exists in one
   place only.
3. **Port private-only material into this repository, redacted** — project names replaced
   with a generic description, dates, commands, measurements, error strings and version
   numbers kept verbatim. `README.md` under "On provenance" is the rule.
4. **Never overwrite `~/.claude/skills/` with a copy from here.** On 2026-09-13 a session
   did exactly that with `cp` and destroyed about 4KB — 108 lines — that existed nowhere
   else; it was recovered from another session's transcript by luck, and verified
   byte-exact at 17573 bytes. A plugin reinstall overwrites that directory too, so material
   that lives only there is one reinstall from gone. Read it, never write it, unless the
   human asks for that write specifically.
5. **Prove the redaction with a command before committing**, not by reading:
   `grep -rniE '<real-name>|<real-name>' plugins/ && echo LEAK || echo clean`. A check that
   has only ever passed is not evidence — plant one of the strings in a scratch copy of
   `plugins/` first and confirm the grep reports LEAK.
