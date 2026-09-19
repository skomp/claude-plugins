# tone-roulette — design

**Date:** 2026-09-13
**Status:** approved, ready for implementation
**Plugin:** `plugins/tone-roulette/`

## Purpose

A deliberately frivolous plugin that demonstrates what a Claude Code plugin can actually
do. On session start it rolls a random conversational tone, announces which one it rolled,
and holds that tone for the rest of the session.

It is the first plugin in this marketplace that is not skill-only: it combines an output
style catalogue, a `SessionStart` hook, a shell handler and a skill. The demonstration
value is the combination — no single component can deliver the behaviour alone.

## Requirements

1. The tone is selected **randomly**, not chosen by the model.
2. Selection happens **when the plugin is enabled**, that is at session start — not only
   when a command is typed.
3. The selected tone is **announced** to the user.
4. The tone **holds for the rest of the session**, including across context compaction.
5. The user can **change the tone** mid-session.
6. The user can **return to the default tone**, by command mid-session or by disabling the
   plugin between sessions.
7. The tone governs **conversational prose only**. Code, commit messages, file contents,
   issue bodies and tool arguments are never affected.

## Verified mechanism facts

Everything below was confirmed against Claude Code 2.1.259 on disk, not from documentation.

| Fact | Evidence |
|---|---|
| `hooks/hooks.json` is auto-discovered; `plugin.json` needs no `hooks` key | `learning-output-style/.claude-plugin/plugin.json` carries no hooks key, yet its hook fires |
| A `SessionStart` hook runs a shipped script via `${CLAUDE_PLUGIN_ROOT}` | `learning-output-style/hooks/hooks.json` |
| Instructions are injected as `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}` | `learning-output-style/hooks-handlers/session-start.sh` |
| `SessionStart`'s matcher is tested against a `source` field whose observed values are `startup`, `resume`, `clear`, `compact`, `fork` | the binary's `matcherMetadata` for `SessionStart`: `fieldToMatch:"source", values:["startup","resume","clear","compact","fork"]` |
| Hook stdin JSON includes `session_id` | hook documentation embedded in the 2.1.259 binary |
| `systemMessage` displays a message to the user, for all hook events | same |
| `outputStyles` is a valid plugin manifest key | manifest key list in the 2.1.259 binary |
| `force-for-plugin` exists but applies only to plugin output styles | binary carries the guard string `" has force-for-plugin set, but this option only applies to plugin output styles. Ignoring."` |
| A plugin's `hooks/hooks.json` can declare more than one event; they are sibling keys under one top-level `"hooks"` object, each with its own matcher/hooks array | this plugin's own `hooks/hooks.json`, which declares both `SessionStart` and `UserPromptSubmit` this way |
| `UserPromptSubmit` accepts `hookSpecificOutput.additionalContext`, same shape as `SessionStart`'s (`{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"..."}}`) | the binary's own hook-output validator lists `additionalContext` as valid "for UserPromptSubmit" (alongside PreToolUse/PermissionRequest/PostToolUse/PostToolBatch/Stop/SubagentStop), and the `/hooks` quick reference's own line for the event: "When the user submits a prompt … Exit code 0 - stdout shown to Claude" |
| **`UserPromptSubmit` has no matcher support at all** — unlike `SessionStart`, which does | the binary's per-event metadata table gives `SessionStart` a `matcherMetadata` of `{fieldToMatch:"source", values:[...]}`, but `UserPromptSubmit`'s own entry in that same table has no `matcherMetadata` key whatsoever; the `/hooks` TUI's own logic (`ge.matcherMetadata!==void 0`) treats that as "this event has no matcher step" — confirming Step 0's instruction not to assume the two events are identical |
| `UserPromptSubmit`'s stdin JSON carries `session_id` but **no timestamp field of any kind** | the binary's own input-object construction for this event spreads the same common-fields object every hook input uses (`session_id, transcript_path, cwd, scratchpad_dir, prompt_id, permission_mode, agent_id, agent_type, effort`) plus `hook_event_name, prompt, session_title` — no `timestamp`, `time`, or similar key anywhere in either object literal. The handler must therefore stamp its own wall-clock time (`date +%s`) rather than reading one from the hook payload |
| `additionalContext` from `UserPromptSubmit` is delivered to the model, not shown to the user in the transcript | same `/hooks` quick-reference line as above: "Exit code 0 - stdout shown to Claude" — the same "to Claude" vs. "to user" distinction the reference uses everywhere else to mark context-only vs. user-visible output; consistent with how this plugin's own `SessionStart` handler already treats `additionalContext` as invisible and reserves user visibility for `systemMessage` |

`commands/*.md` is documented in `example-plugin` as the legacy layout; new plugins should
use `skills/<name>/SKILL.md`. Both load identically.

## Architecture

Three jobs that need different mechanisms:

- **Holding** a tone is what output styles are for. They sit at system-prompt level,
  `/config` → Output style switches between them, and disabling the plugin removes them.
  Requirements 4, 5 and 6 come free.
- **Rolling** a tone is what output styles cannot do. A static Markdown file cannot pick
  randomly. That is the `SessionStart` script's job.
- **Being impatient about something true** is what neither of the above can do on its own:
  a tone file can instruct a *register*, but it cannot know how long the user actually took
  to reply. That requires a live measurement taken on every turn, which is the
  `UserPromptSubmit` script's job — see "The gap-measuring hook" below.

The join: **one tone is one file, read two ways.** Each `output-styles/*.md` file is loaded
natively by Claude Code *and* read by the roll script, which picks one at random, strips the
frontmatter and emits the body as `additionalContext`. There is no second catalogue, and no
tone text that exists in two places.

```
plugins/tone-roulette/
├── .claude-plugin/plugin.json          # "outputStyles": "./output-styles/"
├── hooks/hooks.json                    # SessionStart (matcher: startup|resume|clear|compact)
│                                        #   and UserPromptSubmit (no matcher — see Verified
│                                        #   mechanism facts) as sibling events
├── hooks-handlers/
│   ├── tone-common.sh                  # shared helpers: is a style chosen (and which one),
│   │                                    #   resolve this session's id, the shared state
│   │                                    #   directory, is a given tone the one in force —
│   │                                    #   sourced by both handlers below, never run itself
│   ├── session-start.sh                # roll, persist, announce, inject
│   └── user-prompt-submit.sh           # measure the gap since the previous prompt; inject a
│                                        #   factual line only while impatient is the active tone
├── output-styles/                      # 20 tone files, one per tone — the directory itself
│                                        #   is the catalogue; this tree does not enumerate them
└── skills/tone/SKILL.md                # /tone, /tone roll
```

`force-for-plugin` is deliberately **not** used. It force-applies a single style, which is
the opposite of rolling one, and avoiding it removes the design's only dependency on a field
that could not be confirmed against a working example.

### The gap-measuring hook

`impatient` is the one tone in the catalogue whose register is *about* something measurable —
real elapsed time — rather than a fixed personality, so it is the one tone this plugin backs
with a live fact instead of leaving the model to invent one. `hooks-handlers/user-prompt-submit.sh`
fires on every `UserPromptSubmit` event, in every session where the plugin is enabled, for
every tone — so its first and only unconditional job is to cost nothing when its output would
be pointless: it calls `tone_is_active "impatient" session_id state_dir` (in `tone-common.sh`)
before touching any state, and returns immediately, printing nothing, whenever that answer is
no. `tone_is_active` implements exactly the rule the brief specified: an explicitly chosen
`outputStyle` of `impatient` counts (checked first, since a chosen style pre-empts a rolled one
everywhere else in this plugin), and otherwise the tone `session-start.sh` most recently rolled
or resumed into this session's state file counts.

When impatient *is* active, the handler reads a second per-session file —
`~/.claude/tone-roulette/<session_id>.last-prompt`, a single line holding the unix time of the
prompt before this one — computes the gap against `date +%s`, and, only when that gap is at
least `GAP_THRESHOLD_SECONDS` (120 — two minutes; a shorter gap is normal reading-and-typing
time, not a real wait), emits
`{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"Factual note
for tone purposes: the user's previous message in this session was <N minutes/hours/days> ago."}}`.
The timestamp file is rewritten on every impatient-active turn regardless of whether this run
injects anything, so the reference point for the *next* prompt is always "the previous
prompt", not "the last time a gap happened to clear the threshold". The first prompt of a
session (no `.last-prompt` file yet) and a malformed one (anything not a plain non-negative
integer) are both treated the same way as "no previous timestamp" — inject nothing, still
write the current time for next turn.

This file deliberately sits beside `session-start.sh`'s own `~/.claude/tone-roulette/<session_id>`
file rather than inventing a second state location, with a `.last-prompt` suffix rather than a
second line in that same file: several of `test-handler.sh`'s own assertions compare that
file's *entire* content, byte-for-byte, against a bare tone name or the literal `__off__`, so
appending anything to it would have broken every one of them. A sibling file in the same
directory gets a second per-session fact into the one place this plugin already keeps
per-session state, without touching a format other tests already pin down.

## Data flow

Every tone in the catalogue is also a real Claude Code output style (shipped via the
manifest's `"outputStyles"` key), and Claude Code's own `outputStyle` settings key already
holds a **chosen** style — instantly, via `/config`, with no model turn — and persists it in
a settings file rather than the transcript, so it survives compaction and restart on its own.
The handler's own state file only ever needs to hold one thing beyond that: a **rolled** tone,
since nothing native can pick one at random. So before anything else, on every source
(`startup`, `resume`, `clear`, `compact` — `fork` never reaches the handler at all, see Known
limitations), the handler checks whether a style has been explicitly chosen:

- **An output style is set** (`outputStyle` is a non-empty value in any settings file the
  handler can read — see "Detecting a chosen style" below) — stand down completely. Print
  nothing, exit 0. The state file is not read, not rolled, not rewritten; Claude Code's own
  mechanism owns the tone for the rest of that setting's life, on every source, not just
  `startup`. This is what stops the two mechanisms fighting: before this check existed,
  picking a style and then hitting `/clear` or letting the context compact would silently
  re-inject whatever the state file still held, reverting the user's own choice.
- **No output style is set**, `SessionStart` fires with a matcher value in its stdin JSON:
  - **`startup`** — roll. Pick a file from `output-styles/` at random, write the chosen tone
    name to the state file, emit `systemMessage` (`"🎲 Tone rolled: <name>"`) and
    `additionalContext` carrying the file body.
  - **`resume` / `clear` / `compact`, with a still-valid tone in the state file** — do not
    roll. Read the state file, re-emit that same tone's `additionalContext`, and also emit a
    `systemMessage` — but worded `"🎲 Tone held: <name>"`, not `"rolled"`, because nothing was
    rolled this run. This is what satisfies requirement 4: compaction can drop the injected
    instruction, so it is re-injected unchanged rather than re-rolled, and the message is kept
    (not dropped) because the user may not remember which tone is active after a `/clear`.
  - **`resume` / `clear` / `compact` emit nothing when the state file holds `__off__`.** This
    token is a legacy artifact: an earlier version of the `/tone off` command wrote it
    instead of deleting the state file, so absence kept meaning "roll" and "off" got its own
    explicit representation. The skill no longer writes it — turning the tone off is now
    `/config` → Output style → Default, which the output-style check above already handles —
    but the handler still honors a leftover `__off__` from a state file written before this
    change, or from manual editing. `startup` alone ignores a leftover `__off__` and always
    rolls a fresh tone — switching off was always per-session, and it must never leak into a
    new one.

### Detecting a chosen style

`outputStyle` is a plain top-level string key that can live in any Claude Code settings file.
The handler checks the same precedence order Claude Code itself applies (highest first),
stopping at the first file that actually sets the key:

1. Managed settings (organization policy) — the file-based form only:
   `/Library/Application Support/ClaudeCode/managed-settings.json` on macOS,
   `/etc/claude-code/managed-settings.json` on Linux. An MDM profile (macOS) or an
   HKLM/HKCU registry value (Windows) is not a file this script can read, and neither is a
   `claude --settings` CLI override for this session — see Known limitations.
2. Project local settings (`.claude/settings.local.json`) — the file `/config` itself writes
   to.
3. Shared project settings (`.claude/settings.json`).
4. User settings (`~/.claude/settings.json`).

`$CLAUDE_PROJECT_DIR` is what Claude Code itself sets in a command hook's environment for the
project root (confirmed by reading the installed `claude` binary's strings: hook subprocesses
are spawned with `CLAUDE_PROJECT_DIR` already in their env); `$PWD` is the fallback for a
standalone or test invocation where it is unset.

The extraction is the same pull already used for `session_id`/`source`, not `jq` or
`python` (Global Constraint 3 forbids both in the handler). It is done with bash's own
builtins — `$(<file)` to read, `${x//$'\r'/ }`/`${x//$'\n'/ }` to flatten, and `[[ =~ ]]`
with `BASH_REMATCH` to match — rather than the `tr | printf | grep | head | sed` pipeline it
was first written as. That is a cost change, not a semantic one: the pattern, the
flattening and the precedence order are unchanged, and the argument below applies to both
spellings verbatim. The regex is held in a variable and referenced unquoted, which is what
bash 3.2 requires. It is exact, not a heuristic:
Claude Code constrains an `outputStyle` value to `^[a-z][a-z0-9_-]*$` (a plugin style's
catalogue name — confirmed against the same schema string that validates plugin manifest
names in the 2.1.259 binary) or one of five capitalized built-in names (`Default`,
`Proactive`, `Concise`, `Explanatory`, `Learning`), so the value can never contain a quote or
span multiple lines, and every real-world settings file checked against this writes one key
per line.

The hook's own stdin JSON was checked first and does **not** carry the active output style at
all (confirmed against the `SessionStart` schema embedded in the 2.1.259 binary: `session_id`,
`transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `agent_id`, `agent_type`, `source`,
`model`, `session_title`, and three resume/fork-only cache-cost fields — no `outputStyle` or
`output_style` field anywhere), so reading settings files is not a fallback, it is the only
way.

State lives at `~/.claude/tone-roulette/<session_id>`, a single line holding the tone name.
`session_id` comes from the hook's stdin JSON. If the state file is missing when `resume` /
`clear` / `compact` fires, the script rolls a fresh tone rather than failing.

**Pruning stale state files (issue #6).** After a `startup` roll persists, the handler
removes other files directly under the state directory whose mtime is older than 30 days,
via `find <state_dir> -maxdepth 1 -type f -mtime +30 ! -name <this session's file> -exec rm
-f {} +`. This runs only on `startup`, never on `resume`/`clear`/`compact` — those paths only
read state for what may still be a live session, and a prune racing that read is how a live
session loses its tone. The current session's own file is excluded by name and is never
removed regardless of age. Age is the only available signal (session ids are UUIDs; the
handler has no way to ask whether a session ended), and 30 days is generous specifically
because `resume`/`clear`/`compact` never rewrite the state file, so a long-running session's
file keeps its original `startup` mtime for as long as the session stays open. This same prune
also sweeps up a stale session's leftover `<session_id>.last-prompt` file (see "The gap-measuring
hook" above) once its tone file ages past 30 days, since neither is excluded by name except the
current run's own tone file.

`get_output_style_value()` (the value-returning form of the check above), `resolve_session_id()`
and `tone_state_dir()` were extracted into `hooks-handlers/tone-common.sh` once
`user-prompt-submit.sh` needed the identical "is a style chosen, and which session's state file
does this stdin's `session_id` name" detection — not rewritten, only relocated, so both handlers
share one copy instead of one of them drifting from the other. `session-start.sh` sources it and
otherwise behaves exactly as described above; the extraction is invisible from stdin/stdout.

### The impatience gap

`user-prompt-submit.sh` fires on `UserPromptSubmit` — a different event from `SessionStart`,
with no matcher of its own (see Verified mechanism facts) and a different stdin shape (`prompt`
instead of `source`; no `outputStyle`, and — checked specifically because a gap measurement
was the point — no timestamp field of any kind, so the handler stamps its own via `date +%s`).
It shares `tone-common.sh`'s `tone_is_active()` to decide, before reading or writing anything,
whether `impatient` is the tone in force for this session (a chosen `outputStyle` of `impatient`,
or, with none chosen, a rolled tone of `impatient` in `session-start.sh`'s own state file). See
"The gap-measuring hook" under Architecture for the rest of the mechanism (the `.last-prompt`
file, the threshold, the phrasing), and Error handling below for its failure paths.

## Tone file format

```markdown
---
name: noir-detective
description: World-weary 1940s private eye narrating your codebase
---

## Ground rules

<the shared prose-only block, byte-identical in every tone file>

## Voice

<tone-specific instructions>
```

The ground-rules block enforces requirement 7 and must appear in every file, because a file
selected natively through `/config` is never seen by the script and so cannot have the
rules prepended to it. That means twenty copies of the same paragraph, which is a drift
hazard. It is accepted deliberately and guarded by a test asserting that every tone file
contains the block byte-for-byte.

## The `/tone` skill

| Invocation | Behaviour |
|---|---|
| `/tone` | Report the current tone — chosen via `/config`, rolled at session start, re-rolled mid-session, or off — and how it was selected |
| `/tone roll` | Pick a fresh tone at random, adopt it immediately, and update the state file |

Switching to a named tone, listing the catalogue, and turning the tone off are no longer this
skill's job: every tone is a real Claude Code output style, so `/config` → **Output style**
already does all three instantly, with no model turn, and keeping a slower copy here would
just give the two mechanisms something to disagree about. When a user asks for one of these,
the skill points at `/config` rather than performing an equivalent action itself.

Frontmatter sets `disable-model-invocation: true`, so the skill fires only when the user
types it. A tone plugin that re-rolled itself because the model thought it relevant would be
a bug.

## Cost

Both handlers block the thing they hook: `SessionStart` delays the first turn of every
session, `UserPromptSubmit` delays every prompt in every session the plugin is enabled in,
including the sessions where the plugin has already decided to do nothing. On a shell
handler this cost is almost entirely `fork`+`exec`, not work — a process spawn measured
~2.6ms on the author's macOS machine (arm64, Darwin 25.6.0), so the process count is the
number worth managing, and the body of the script is not.

Measured 2026-09-16 on that machine, 20 runs each, `bash <handler>` with the catalogue at
20 tones:

| handler | before | after | external processes per run |
|---|---|---|---|
| `session-start.sh` (startup roll) | 107ms | 35ms | 40 → 4 |
| `user-prompt-submit.sh` (impatient active) | 42ms | 26ms | 13 → 4 |

The single largest item was `basename` forked once per catalogue entry to turn
`output-styles/<name>.md` into `<name>` — 20 processes, ~52ms, roughly half the
`SessionStart` handler's entire wall time, spent on a string operation `${f##*/}` and
`${b%.md}` do for free. The rest came from spelling small extractions as pipelines:
`tr | printf | grep | head | sed` per settings-file candidate (up to four candidates),
`grep | head | sed` for `session_id` and again for `source`, `head | tr` to read the state
file, `uname -s` to choose between two managed-settings paths that are never both present,
and four chained command substitutions to JSON-escape the body where one `awk` pass that
maps each input character exactly once does the same job — and is order-independent by
construction, where the four-pass version was only correct because of the order.

None of this changed what either handler emits. The rewrite was verified by running the
old and new handlers against all 20 catalogue tones × 6 `source` values × both bash 3.2
(`/bin/bash`) and bash 5, and comparing stdout byte-for-byte: 240 comparisons, all
identical.

## Error handling

**`session-start.sh` (`SessionStart`):**

| Condition | Behaviour |
|---|---|
| An output style is explicitly set (`outputStyle` in any settings file the handler can read) | Emit nothing, exit 0. Checked first, before the catalogue or the state file, on every source — not only `startup` |
| `output-styles/` missing or empty | Emit nothing, exit 0. The session proceeds untoned |
| State file unreadable, or holds an unknown tone name | Roll fresh; do not fail |
| State file holds the literal value `__off__` | On `resume`/`clear`/`compact`: emit nothing, exit 0, session stays untoned. On `startup`: ignore it and roll fresh, same as any other source |
| `session_id` absent from stdin | Fall back to a single state file keyed by working directory |
| Pruning the state directory fails (permission denied, race, etc.) | Swallowed (`2>/dev/null`); the session's own roll/announce/inject already completed and is unaffected |
| Shared helper file (`tone-common.sh`) missing or unreadable | Emit nothing, exit 0. Checked (readability, then a successful `source`, then that every function the caller uses is actually defined) before either handler does anything else, so a partial install degrades the same way a missing catalogue does |

**`user-prompt-submit.sh` (`UserPromptSubmit`):**

| Condition | Behaviour |
|---|---|
| `impatient` is not the tone in force (a different style is chosen, or the state file names a different tone, or nothing is active) | Emit nothing, exit 0. Checked first, before the timestamp file is read or written — this is the "cost nothing" contract |
| First prompt of the session (no `.last-prompt` file yet) | Emit nothing, exit 0. Write the current time so the *next* prompt has something to compare against |
| `.last-prompt` file holds anything other than a plain non-negative integer (corrupted, truncated, hand-edited) | Treated the same as "no previous timestamp" — emit nothing, overwrite it with the current time |
| Gap since the previous prompt is below `GAP_THRESHOLD_SECONDS` (120s) | Emit nothing, exit 0. The timestamp file is still rewritten |
| `date +%s` itself fails (returns nothing) | Emit nothing, exit 0. Nothing is written or compared |
| Malformed, empty or closed stdin | `session_id` extraction finds nothing and falls back to a `$PWD`-keyed state file, same as `session-start.sh`; never fatal |
| Shared helper file (`tone-common.sh`) missing or unreadable | Emit nothing, exit 0. Same guard as `session-start.sh`: readability, then a successful `source`, then that every function this handler uses (`resolve_session_id`, `tone_state_dir`, `tone_is_active`) is actually defined, all checked before anything else runs |

Every failure path exits 0 on both handlers. A hook belonging to a fun plugin must never
degrade a session.

## Verification

- `claude plugin details tone-roulette` reports 20 output styles, 2 hooks and 1 skill.
- The handler script, run directly with crafted stdin JSON, emits valid JSON for each
  matcher value — asserted with `jq`, not by eye.
- Rolling repeatedly across many runs yields more than one distinct tone. This proves the
  roll is real and not a fixed pick.
- `resume`, `clear` and `compact` with an existing state file return the *same* tone the
  state file holds.
- Every tone file contains the ground-rules block byte-for-byte.
- `user-prompt-submit.sh`, run directly with crafted stdin JSON and a pre-seeded
  `.last-prompt` file, injects only when `impatient` is the active tone and the gap is at
  least `GAP_THRESHOLD_SECONDS`; stays silent for every other tone, for a chosen non-impatient
  style even over a stale impatient state file, on the first prompt of a session, and below
  the threshold — each asserted directly, not inferred from the absence of a crash.
- **A broken variant with the "is impatient active" check removed was run against the same,
  unmodified test suite** (`tests/test-user-prompt-submit.sh`) to confirm the suite actually
  discriminates rather than merely running: it caught the break on 4 of its 19 assertions —
  both assertions of test1 (a different rolled tone must produce no output *and* must leave
  the timestamp file untouched), test2 (a chosen non-impatient style must stand the hook down
  even over a stale impatient state file), and the second assertion of test13 (no tone active
  at all must not write a timestamp file either). This is exactly the failure that matters: a
  hook that injects for every tone, in every session, for every user who picked a different
  style.
- Live check, needs a human: enable the plugin, start a session, confirm the announcement
  appears and the tone holds, and confirm `/config` → Output style lists all twenty.

## Known limitations

- **A `claude --settings` CLI override and MDM-delivered policy (a macOS configuration
  profile, or a Windows registry value) are invisible to the stand-down check.** Both can set
  `outputStyle` at a higher precedence than every file the handler reads, but neither is a
  file the handler reads: a CLI override is never written to disk or exposed to a hook's
  stdin or environment, and MDM policy lives in a plist or the registry, not
  `managed-settings.json`. In both cases the handler can wrongly conclude no style is chosen
  and roll over one that in fact takes effect. This is a narrow, rare gap — most machines
  running this plugin have neither in play — documented rather than silently accepted.
- **The standalone `/output-style` command is gone.** It was deprecated in Claude Code
  v2.1.73 and removed in v2.1.91 (confirmed against the installed 2.1.259 binary: running it
  now prints "`/output-style` moved → Output style in `/config`" and does nothing else).
  `/config` → **Output style** is the current way to choose or list a style with no model
  turn; this plugin's skill and README point at `/config`, not at the old command, for
  exactly that reason. A user on an older release where `/output-style` still works can use
  it interchangeably — the `outputStyle` settings key the handler checks is the same either
  way.
- **Subagents do not inherit the tone.** Forks inherit the parent's system prompt; other
  subagents run their own. Implementer and reviewer agents answer in the default voice.
  This is not fixable from a plugin, and is documented in the README.
- **Disabling the plugin mid-session does not retract the tone.** Text already injected is
  in the conversation history. Choosing a different style via `/config` is the mid-session
  path; disabling the plugin is the between-sessions path.
- **Only `startup` rolls unconditionally.** `resume`, `clear` and `compact` re-inject the
  stored tone from the state file without re-rolling *when the state file names a still-valid
  tone*. When it doesn't — missing, unreadable, or naming a tone no longer in the catalogue —
  they roll fresh exactly as `startup` would (see Error handling); `resume` with no state file
  is not an error case, it is this same fallback. `fork` is deliberately excluded from the
  matcher:
  if a fork gets a new `session_id` the handler would find no state file and roll a second,
  different tone with its own announcement; if a fork shares the parent's `session_id` the
  resume path would re-emit the same `additionalContext` into a context that already
  contains it. Both outcomes are wrong, so `fork` never fires the hook.
- **Tone adherence depends on the model.** Tested on Haiku and Sonnet: on Sonnet the tone
  lands reliably; on Haiku it frequently does not, even though the hook still fires and a
  tone is still rolled and written to the state file — the mechanism works, the model just
  doesn't follow the injected instruction. Other models have not been tested.
- **Four tones perform doubt or pessimism** (`negative-nancy`, `hedging-hannah`,
  `second-guess-sid`, `nervous-nellie`), and their hedging is a speech register, not a
  confidence signal — the underlying assessment is unchanged, and each file's `## Voice`
  section says so explicitly. A reader who does not know this can mistake the performance
  for the substance: "I think the tests maybe passed?" reads as uncertainty about the test
  result, when the result itself was never in doubt. Anyone who needs the assistant's actual
  confidence should ask directly or switch tones via `/config`.
- **Switching away from `impatient` and back resets the gap history.** The timestamp file is
  only ever read or written while `impatient` is the active tone (see "cost nothing" in
  Architecture); a session that rolls `impatient`, gets re-rolled to something else, and is
  later switched back will find no `.last-prompt` file and treat the next prompt as the first
  one — silently, not a bug report waiting to happen, but a real gap the mechanism does not
  track across a detour through another tone.
- **The gap is measured against the machine's own clock, with no correction for clock changes
  or suspend/resume.** A system clock adjusted backwards between two prompts (NTP correction,
  manual change, a laptop waking with a slow clock) can produce a negative or understated gap,
  which the handler simply treats as "below threshold" rather than flagging the anomaly —
  consistent with every other failure path here (never crash, never degrade the session), but
  worth naming as a case where the injected fact could be wrong on a machine with an unreliable
  clock.
- **The threshold (`GAP_THRESHOLD_SECONDS`, 120s) is a fixed constant, not configurable.**
  Every user of the `impatient` tone gets the same two-minute floor; there is no per-user or
  per-session tuning, by design (the brief calls for "a sensible floor", not a setting).

## Out of scope

Dialect and language are orthogonal to tone and are not addressed here. Claude Code already
has a `language` setting for the former.
