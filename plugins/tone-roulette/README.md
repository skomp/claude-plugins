# tone-roulette

A demonstration plugin, not an operating rule. It rolls a random conversational tone at
session start and holds it for the session, and while the `impatient` tone holds, notes a
real gap since your last message so it has something true to be impatient about.

## What it ships

A catalogue of tones under `output-styles/` — each one is a real Claude Code output style,
installed through the plugin manifest. A `SessionStart` hook and a `UserPromptSubmit` hook
(`hooks/hooks.json`, `hooks-handlers/`). A `tone` skill, invoked only via the user typing
`/tone` — reports the current tone and how it was set, or rolls a fresh one with
`/tone roll`. Point at `output-styles/` for the current tone count and names rather than
trusting a number here — that list has already gone stale in this repository's own history.

## The division of labour

Every tone in the catalogue is also a real Claude Code output style, so `/config` (under
**Output style**) already lists and switches between all of them instantly, with no model
turn, and Claude Code persists that choice in a settings file rather than the conversation —
it survives `/clear` and restart on its own. The plugin's `SessionStart` hook exists for the
one thing `/config` can't do: pick a tone at random. It checks first whether you've already
chosen a style; if you have, it does nothing at all, on every session start, resume, clear or
compact, not only the first one. Only when nothing is chosen does it roll, hold the roll in a
small per-session state file, and re-inject it across compaction. `/tone roll` is the only
`/tone` verb left that does its own work — switching to a specific tone, listing the
catalogue, and turning the tone off are all faster done through `/config` directly, and the
`tone` skill just points you there. See the design spec's Data flow section for the
mechanics.

A second hook, on `UserPromptSubmit`, backs the `impatient` tone with a real measurement
instead of leaving it to invent one: it times the gap since your previous message and, only
while `impatient` is the tone actually in force, notes it (`"...was 11 minutes ago"`) so the
tone can be pointedly impatient about something true rather than generically grumbling. It
fires on every prompt, in every session, for every tone in the catalogue — so for every other
tone, and for anyone who has chosen a different style, it does nothing at all and costs
nothing beyond one cheap check. Gaps under two minutes go unremarked; the first prompt of a
session has nothing to compare against yet. Both hooks share their "is a style chosen, which
tone is this session's" detection from one file (`hooks-handlers/tone-common.sh`) rather than
keeping two copies of it.

## No tone rolled? Check this first

The hook stands down completely — silently, by design — whenever an `outputStyle` key is set
in any settings file it can read, in Claude Code's own precedence order: managed settings,
then `.claude/settings.local.json`, then `.claude/settings.json`, then
`~/.claude/settings.json`. `/config` writes to `.claude/settings.local.json`, **per project**,
so choosing a style once in one repository turns the roulette off in that repository for good
while leaving it running everywhere else. That is the usual reason a tone appears in some
projects and not others:

```
grep -l outputStyle .claude/settings.local.json .claude/settings.json ~/.claude/settings.json 2>/dev/null
```

Remove the key (or pick **Default** in `/config`) to hand the tone back to the roulette.
`/tone` reports the current tone and how it was set. The other reasons for a quiet session
are in Known limitations below — a `resume` re-injects rather than rolls, a fork never fires
the hook at all, and on some models the tone is rolled but simply not followed.

## Known limitations

- **Subagents do not inherit the tone.** Forks inherit the parent's system prompt; other
  subagents run their own. Implementer and reviewer agents answer in the default voice.
- **Disabling the plugin mid-session does not retract a tone already injected.** The text
  is already in the conversation history. Choosing a different style via `/config` is the
  mid-session path; disabling the plugin is the between-sessions path.
- **Only `startup` rolls, and only when no output style is chosen.** A resumed session
  re-injects the stored *rolled* tone rather than rolling a new one, so `--resume` keeps
  whatever was already in play — but if you've chosen a style via `/config` since the last
  `startup`, the hook stands down instead, on every source, and neither rolls nor re-injects
  over your choice.
- **A `claude --settings` CLI override or an MDM-delivered policy can pick a style the hook
  can't see.** Both take effect over anything in a settings file, but neither is a file the
  hook can read, so on the rare machine where one is in play the hook may roll over a style
  that in fact takes effect. See the design spec's Known limitations for detail.
- **Tone adherence depends on the model.** Tested on Haiku and Sonnet: on Sonnet the tone
  lands reliably. On Haiku it frequently does not — the hook still fires, a tone is still
  rolled and written to the state file, but the model answers in the plain default voice
  anyway. The mechanism is working in that case; the model is not following the injected
  instruction. A Haiku user who sees no tone is looking at a model limitation, not a broken
  plugin. Other models have not been tested.
- **Four tones perform doubt or pessimism** — `negative-nancy`, `hedging-hannah`,
  `second-guess-sid` and `nervous-nellie`. Their hedging is a speech register, not a
  confidence signal: the underlying assessment is unchanged whether or not the tone is
  hedging it. If you need to know how confident the assistant actually is, ask directly or
  switch tones via `/config`.
- **Switching away from `impatient` and back loses the gap history.** The previous-prompt
  timestamp is only ever read or written while `impatient` is the active tone, so a detour
  through another tone and back is treated as a fresh session for gap purposes — the next
  prompt after switching back is never announced as a gap, even if the detour itself was long.

  This is deliberate: the alternative is tracking timestamps for every tone all the time,
  which is exactly the "cost nothing when not impatient" contract this hook exists to keep.

## Install it if

You want a demonstration of what a plugin can do beyond skills — output styles, a
`SessionStart` hook and a `UserPromptSubmit` hook, two shell handlers sharing common code —
rather than another rule. It is a joke, not a lesson. Skip it if you only want the
operating rules.
