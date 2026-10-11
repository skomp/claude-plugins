# claude-plugins

Six Claude Code plugins, of four kinds. Three hold rules that were learned the
expensive way — each one traceable to a specific failure, with the measurement that
exposed it kept intact. `session-relay` is a design, specified and built in one session
on 2026-09-13, with no incident behind it. `tone-roulette` is neither: a demonstration
of what a plugin can do beyond skills, and a joke. `machines` is not a rule at all: it
is a schema and a checker — a declaration language for a communication protocol, and the
tool that checks a declaration for well-formedness and for collisions against its peers.
Each row in the table below says which kind it is, because the four are not
interchangeable and the difference is the point.

Nothing in the first three is advice in the abstract. Every rule there exists because
something broke: a security check that passed because its needle was empty, an agent that
reverted a human's work because it could not account for it, fourteen defects that all came
from code written into a plan document, a session that grew too large to reopen.
`session-relay` has no such failure behind it, but it does have measurements in front of
it: a check whose planted fault could not fail, an addressing rule that could not reach one
live session in four, a precedence rule the protocol never stated, and a rule written as a
condition that therefore never fired. All four were found by running it, and all four were
fixed before it shipped. Its seven verification items have since been run against a live
pair of sessions, and the transport wrapper the guard strips is now observed rather than
assumed.

## Install

Two steps, typed into Claude Code. Nothing here installs itself.

**1. Add this marketplace.** Once per machine:

```
/plugin marketplace add skomp/claude-plugins
```

The marketplace registers as `skomp-plugins`, not as the repository's name: Claude Code
rejects a marketplace called `claude-plugins` as impersonating an official one. Where a
plugin name needs qualifying, the form is `tone-roulette@skomp-plugins`.

**2. Install the plugins you want.** Each is packaged separately on purpose, so taking one
never drags in another:

```
/plugin install evidence-discipline
/plugin install agent-operations
/plugin install ticket-craft
/plugin install session-relay
/plugin install tone-roulette
/plugin install machines
```

Or run `/plugin` and pick from the menu.

**If you take only one, take `evidence-discipline`.** Nothing in it is specific to Claude
Code, and it is the one that pays for itself on the first day: prove a check can fail
before you trust that it passed, and finish a correction everywhere the claim appears.

The table below says what each of the others is for, and who should skip it.

## The six plugins

| Plugin | Install it if | README |
|---|---|---|
| **evidence-discipline** | Always. Nothing in it is specific to Claude Code — it is "prove the check can fail before you trust that it passed", and "a fix is not done until every copy of the claim is fixed" | [plugins/evidence-discipline/README.md](plugins/evidence-discipline/README.md) |
| **agent-operations** | You dispatch subagents or run git worktrees. Useless if you work alone in one session | [plugins/agent-operations/README.md](plugins/agent-operations/README.md) |
| **ticket-craft** | You want ASD-STE100 Simplified Technical English enforced on every ticket. Deliberately packaged alone, so wanting the verification rules never drags this in | [plugins/ticket-craft/README.md](plugins/ticket-craft/README.md) |
| **session-relay** | Your project spans multiple repositories, each with its own live Claude session, and you track work in GitHub issues. Skip it if you work in one repository alone, or that repository tracks work on a `TODO.md` — both are hard preconditions the protocol refuses to run without | [plugins/session-relay/README.md](plugins/session-relay/README.md) |
| **tone-roulette** | You want a demonstration of what a plugin can do beyond skills — output styles, a `SessionStart` hook and a `UserPromptSubmit` hook, two shell handlers sharing common code — rather than another rule. It is a joke, not a lesson: it rolls a random conversational tone at session start and holds it for the session. Skip it if you only want the operating rules | [plugins/tone-roulette/README.md](plugins/tone-roulette/README.md) |
| **machines** | You are declaring a communication protocol as a state machine and want it checked for well-formedness and for prefix collisions against its peers before you trust it. Cycle A ships the schema and the checker only — no engine, no installer, no dispatcher. Skip it if you want something that actually runs a protocol; that is not built yet | [plugins/machines/README.md](plugins/machines/README.md) |

## tone-roulette: known limitations

- **Subagents do not inherit the tone.** Forks inherit the parent's system prompt; other
  subagents run their own. Implementer and reviewer agents answer in the default voice.
- **Disabling the plugin mid-session does not retract a tone already injected.** The text
  is already in the conversation history. `/tone off` is the mid-session path; disabling
  the plugin is the between-sessions path.
- **Only `startup` rolls.** A resumed session re-injects the stored tone rather than
  rolling a new one, so `--resume` keeps whatever tone was already in play.
- **Tone adherence depends on the model.** Tested on Haiku and Sonnet: on Sonnet the tone
  lands reliably. On Haiku it frequently does not — the hook still fires, a tone is still
  rolled and written to the state file, but the model answers in the plain default voice
  anyway. The mechanism is working in that case; the model is not following the injected
  instruction. A Haiku user who sees no tone is looking at a model limitation, not a broken
  plugin. Other models have not been tested.

## Three rules to put in your own CLAUDE.md

Each skill's frontmatter `description` is its trigger — that is the mechanism that fires
it, and it needs no help from you.

But a description only *routes*; it is not itself an instruction that gets obeyed. Three
rules here have to hold even when the skill is never opened, because the cost of missing
them lands outside your session. Paste these into your `CLAUDE.md`:

```markdown
- Never `git add -A` or `git commit -a` while an agent of yours is live in the same
  checkout. Stage explicit paths you own.
- Every GitHub issue you create carries the `created-by-claude` label.
- Never agree a coordination convention with another session — a freeze, a handoff word,
  an ownership map. Send facts about your own state; ask me for anything more.
```

The second only applies if you install `ticket-craft`. The third is the one a session
breaks before it would ever open a skill: it is already composing the message.

## On provenance

Project names are redacted — where a rule says "a GPU renderer project, 2026-08-20", the
original named a real repository. Dates, measurements, commands, error strings and version
numbers are unchanged, because those are the part that is worth anything. A redacted name
costs a reader nothing; a rounded measurement costs them the lesson.

A few passages are marked *"Recorded from a concurrent session"*. Those were written down
by one session observing another's failure, and have not been reviewed by the session that
lived it. They are flagged rather than quietly folded in, because an unmarked second-hand
account reads as settled practice to whoever comes next — which is itself one of the
failures documented here.

## Known limitation

These skills have not been tested against a live agent under pressure. The first six, in
`evidence-discipline`, `agent-operations` and `ticket-craft`, are faithful records of
failures that already happened, not instruments anyone has watched fire. `session-relay`
is not a record of anything — it is a design. Its two skills **have** now been run against
a live fleet: seven verification items on 2026-09-13 and 2026-09-14, against two
throwaway repositories with one session bound to each. All seven passed. That run found
three defects no review had: a precedence rule the protocol never stated, a rule written
as a condition that therefore never fired, and a guard that leaked protocol commentary
into ordinary replies. What it does **not** establish is use on real work — nobody has
yet had a genuine cross-repository fault triaged this way.

The untested property, for the five plugins that ship skills, is retrieval: whether each `description`
actually triggers at the moment it should. If you find one that does not fire when it
ought to, that is the most useful issue you could open.

## License

MIT
