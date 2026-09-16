# The machine declaration

A machine is a single ` ```machine ` fenced block inside a bundle's `SKILL.md`, next to the
prose that explains it. `machines.declaration.parse(text)` turns that block into a `Machine`.
It is a closed language — no expressions, no scripts, no callbacks — so every field below is
one of the eleven the parser accepts. **Any other top-level field is rejected by name**, not
silently ignored: a publisher who writes `caps: 10` is told about `caps`, not handed a machine
with a default cap they never asked for.

Every field in this document is required unless its section says otherwise. A required
field that is missing is rejected by name, the same as an unknown one. **`cap`, `fields`,
and `registers` are the top-level fields that are optional**; each optional field's absence
means something specific to it, stated in its own section below.

**Every type in this document is enforced, and every failure names the field.** A field
documented as a string must be a string; `roles` must be a mapping; each `states` and
`transitions` entry must be a mapping with its required sub-fields present; `kinds` and
`effects` must be lists of strings. A declaration that gets one of those wrong is told
which field, by name, before anything else looks at it. Nothing a publisher can write in a
machine block reaches you as a Python traceback — a crash reported as a finding would be a
checker telling you your machine is broken when it is the checker that broke.

## Scalars mean what you wrote, not what YAML 1.1 guesses

PyYAML's default loader follows YAML 1.1, under which the bare words `yes`, `no`, `on`,
`off` (and case variants) resolve to booleans — in *any* scalar position, including a
mapping key. Left alone, that is a hole through every string-valued field in this schema: a
kind declared `on`, a state named `no`, a role called `yes`, a transition's `on: yes` would
each silently become a Python `True`/`False` instead of the string the publisher wrote, and
every check built on equality or a dict key (`t.on in m.kinds`, `m.states["no"]`) would keep
working against the corrupted value with no error raised anywhere. That is worse than a
crash: coherent-looking data that is simply wrong.

**This parser narrows boolean resolution to `true`/`false` (and case variants) only,
everywhere in the declaration.** `yes`, `no`, `on` and `off` are always strings here,
whatever position they appear in. **The cost:** `signal: yes` no longer means `signal: true`
— a publisher who wants the boolean must write `true` or `false` literally. The parser
enforces this too: `signal`, `terminal` and `accepting` reject anything that isn't an actual boolean
(so `signal: yes` fails loudly as the string `"yes"` in a boolean field, rather than being
accepted as truthy).

That single rule is what lets every other section below say "string" or "boolean" and mean
exactly one thing.

## `machine`

**Type:** string. **Required.**

The machine's name. Prevents a bundle from shipping a protocol nobody can refer to when two
machines are compared or reported on.

## `version`

**Type:** string. **Required.**

The machine's version. Two machines with the same `machine` name but different `version`
strings are different protocols as far as the checker is concerned — this field is what lets
a publisher change a protocol without silently mutating one that peers already installed.

## `prefix`

**Type:** string. **Required.** **Read as a pattern, not as literal text — see the next
section before you write one.**

What every message this machine emits begins with. It is what the dispatcher matches to
route an inbound message to this machine (a later cycle), and what the installer compares
between machines to detect a collision: two machines claiming the same prefix can never
both be enabled. An empty or missing prefix would make that comparison meaningless, so the
field exists to prevent messages from being unroutable and installs from colliding
silently.

## The prefix is a pattern, not a literal

**`prefix` is parsed as an expression in a small pattern language.** A prefix made only of
ordinary letters, digits, spaces, `:` and `-` means exactly what it says — `session-relay:v1 `
claims the messages that begin with `session-relay:v1 ` and nothing else. But a prefix
containing any of

```
| * + ? ( ) [ ] . \ { }
```

means something other than those characters, and the machine you get is not the machine
you wrote. Measured on this implementation:

| You write | It actually claims |
|---|---|
| `proto(v1) ` | `protov1 ` — the parentheses are grouping, not characters |
| `session-relay:v1. ` | `session-relay:v1X ` for any `X` — `.` is "any character" |
| `[proto] ` | `p `, `r `, `o ` or `t ` — `[...]` is a character class, one character long |

Nothing reports this. Each of those compiles cleanly, `machines-check` exits `0`, and the
machine quietly fails to claim its own messages while claiming other people's.

**To match one of those characters literally, put a `\` in front of it:** `proto\(v1\) `
claims `proto(v1) `, and `session-relay:v1\. ` claims `session-relay:v1. `. A `\` before
any other character is rejected by name rather than guessed at, so there are no silent
half-escapes.

### The whole grammar

```
pattern := alt
alt     := cat ('|' cat)*          alternation
cat     := rep*                    concatenation
rep     := atom ('*' | '+' | '?')? zero-or-more, one-or-more, optional
atom    := literal | '.' | class | '(' alt ')'
class   := '[' '^'? item+ ']'      a character class, negated with '^'
item    := char '-' char | char    a range, or one character
literal := any character except | * + ? ( ) [ ] . \  -- or '\' followed by one of those
```

That is all of it. **No backreferences, no lookaround, no `{n,m}` counted repetition, no
named groups, no `\d`/`\w`/`\s` shorthand classes.** Every one of those is rejected by name
at parse time. The restriction is not taste: the installer decides "can these two machines
claim the same message" by intersecting two automata, which is only decidable because every
prefix here is a *regular* expression. A backreference is not regular, so one accepted here
would sail through every other check and silently take the framework's central guarantee
with it.

**`^` and `$` are not metacharacters in this grammar — they are ordinary literal
characters, matched literally, exactly like `a` or `9`.** The grammar above names the only
characters this language treats specially (`| * + ? ( ) [ ] . \`), and `^`/`$` are not
among them (`^` is special only inside a `class`, where it negates — `[^a]` — not as an
anchor). A prefix written `^session-relay:v1 ` does not anchor at the start of the message;
it declares a machine that only ever claims messages beginning with a literal caret
character, and it is accepted, not rejected. A publisher who writes `^`/`$` expecting anchor
semantics gets no error at parse time and a machine that silently matches something other
than what they meant.

Two further limits, both reported as errors:

- **A pattern that can match the empty string is rejected.** `a*`, `a?`, `(a|)` and the
  empty prefix all match nothing-at-all, and a prefix that matches the empty string claims
  *every* message — a machine that collides with every other installed machine, forever,
  with no single obviously-wrong machine to point at. Rejecting it at the one machine that
  caused it is the only place that failure is legible.
- **A pattern that compiles to more than 10,000 automaton states is rejected.** Nested
  repetition doubles the state count per level, so a 52-character pattern can reach half a
  million states. No message prefix needs that, and being told the limit is better than
  watching the checker allocate until it dies.

## `roles`

**Type:** mapping of string to string (role name to what it binds to). **Required.**

The set of participants who can hold a state or act in a transition. Every `holder` on a
state and every `by` on a transition (below) is checked, by `check_machine`, against the names
declared here. Without this field, a publisher could write `by: bystander` in a transition
and never learn that no such role exists until it is too late to matter. A role named `yes`
or `no` lands as that literal string, both as the key here and wherever it is referenced —
see "Scalars mean what you wrote" above.

## `kinds`

**Type:** list of strings. **Required.**

The closed vocabulary of message kinds this machine recognises. Every transition's `on`
(below) is checked, by `check_machine`, against this list. This is what keeps the language closed:
a transition cannot fire on a kind nobody declared, and a reader can find every kind the
protocol understands by reading one list instead of hunting through every transition.
**A kind no transition fires on is reported**: the declaration says the machine understands
that message and no state does anything with it, which is vocabulary that reads as
supported and is not. **Must actually be a list** — `kinds: "yes"` is rejected by name rather than silently
iterated character-by-character into `{'y', 'e', 's'}`, which is what `set("yes")` would
otherwise do with no error at all.

## `fields`

**Type:** mapping of field name to type. **Optional.** Absent or empty means this machine
declares no header fields, and `check_machine` has nothing to say about it either way —
`fields` is entirely parse-time; there is no cross-reference to make.

A field is a named, typed position in a message header: a value a peer's message carries
that a guard (below, under `` `transitions` ``) compares against, and that a register can
fold over a trace of. This document only declares the shape; nothing here evaluates a
guard, folds a trace, or reads a channel — that is cycle B's engine, not this parser.

**There are exactly two types: `int` and `bool`.** Closed on purpose, so a publisher who
writes `ballot: integer` or `ballot: number` is told the word is wrong by name, rather than
getting a machine whose guard the engine cannot evaluate. **There is deliberately no
`string`.** Every comparison a guard can express is arithmetic or an equality check on a
whole number or a boolean; nothing in this schema defines a string fold or a string
ordering for a guard to compare against, so a `string` field would be a type nothing could
ever do anything with.

**A field's name must match `^[a-z][a-z0-9_-]*$`** — lowercase letters, digits, `_` and `-`,
starting with a letter. In particular, **a field name may never contain a `.`**: the dotted
namespace (`envelope.clock` and the like) is reserved for the message envelope a later
cycle adds. That is not a stylistic rule — a declared field that collided with the
envelope's own name would be a readable route back to guarding the Lamport clock directly,
which the spec forbids outright. A machine's own field named `clock`, with no dot, is a
perfectly ordinary field and has nothing to do with the envelope's clock; the two coexist
because the envelope's is always dotted and a declared field's is never allowed to be.

**The envelope's clock is not a field, and cannot be guarded, on purpose.** `envelope.clock`
never reaches `fields` at all — a name may never contain `.`, so there is no spelling in this
language through which a publisher could declare it, and therefore no spelling through which
a `guard` (below, under `` `transitions` ``) could compare against it either. §7 is why: the
clock orders delivery, it is not protocol content, and a guard that could see it would let a
machine's behaviour depend on something no peer's message actually carries. The restriction
is enforced by there being no syntax for it, not by a check that would have to catch it after
the fact.

**A mapping, not a list of `{name, type}` objects.** A list would be a third entry shape to
validate for no gain over what a mapping already expresses, and — the reason that matters
more — a mapping cannot carry a duplicate field name at all; there is nothing to catch
because there is nowhere for it to occur.

```yaml
fields:
  ballot: int
  blocking: bool
```

## `registers`

**Type:** mapping of register name to its fold declaration. **Optional.** Absent or empty
means this machine remembers nothing across the trace.

A register is one remembered scalar: a value folded from every message of the right kind
that has arrived so far, seeded at a stated starting value. It exists so that a guard
(below, under `` `transitions` ``) can compare a field on the message just arrived against
something the protocol has already seen — the highest ballot promised so far, say —
without a publisher hand-rolling that bookkeeping in prose nobody checks.

**A register is a declaration of how a scalar would be folded, not the fold itself.** Nothing
in this document, or in cycle A's checker, evaluates a guard, folds a trace, or reads a
channel — that is cycle B's engine. `check_machine` only checks that a register's declaration
is internally consistent with the rest of the machine — see the checks below, and the one
just past them that needs a guard to exist first.

Each register is a mapping with exactly these four keys, all required:

- **`fold`** — how the register combines a new field reading with what it already remembers.
  One of `max` or `last` (see "The two folds, and why not more" below).
- **`field`** — the name of the declared header field (see `fields`, above) whose value is
  read on every message that feeds this register. `check_machine` checks that this names a
  field actually declared — a register folding something the machine never said a message
  carries would otherwise be caught nowhere.
- **`on`** — a non-empty list of declared kinds. A message of any other kind leaves the
  register untouched. `check_machine` checks that every entry names a declared kind — the
  same failure the unused-kind check answers, from the other side: a register fed by a
  message the protocol cannot receive.
- **`initial`** — the value the register holds before any matching message has arrived. An
  `int` or a `bool`. `check_machine` checks that its Python type agrees with the field's
  declared type (an `int` field takes an `int` initial, not a `bool`; a `bool` field takes a
  `bool`) — a register that starts life as a value the comparison cannot order would
  otherwise reach a guard as a type error with nothing in the declaration to point at.

**A fifth check:** a declared register that no guard names anywhere is reported. See the
`guard` bullet under `` `transitions` ``, below, for what a guard is, and for why an unread
register — unlike an unread field — is reported at all: a register has exactly one possible
consumer, a guard, so one no guard names is dead weight; a field can still be carried in
the header for the participant to read, so the same check does not exist for a field.

**A register's name must not also be a declared field's name.** The two live in the same
namespace (`NAME`, the pattern `fields` uses too — see that section), and a guard compares
one against the other by name; a register and a field sharing a name would make a guard's two
sides ambiguous to a human reader, which is the exact failure this syntax exists to prevent.

```yaml
fields:
  ballot: int
registers:
  highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }
```

### Why `on` is required and non-empty

A reader needs to see which messages move the remembered value without cross-referencing
every transition by hand. An empty (or absent) `on` would be a register that never updates —
a constant, smuggled in through a degenerate fold instead of declared as what it is.
Comparing a field against a literal constant is not expressible here at all: that is a
**stated gap**, not a feature this shape happens to also provide. A publisher who wants it
has to wait for it to be designed on purpose.

### Why there is no `type` on a register

A register's type is its field's type — enforced by the `initial` check above, and true for
the register's entire life once a machine passes `check_machine` (see "The two folds" below).
Giving a register its own `type` key would be a second place to say the same thing, and a
second place to disagree with the first.

### The two folds, and why not more

`FOLDS = ("max", "last")`. Closed on purpose, the same reason `fields`'s type vocabulary is
closed: an open fold word would let a publisher declare a register the engine cannot evaluate,
and the failure would surface far from the declaration that caused it.

A register remembers **one scalar**, seeded at `initial`, updated by **exactly one field read
per matching step**: conceptually, `register = fold(register, message.field)` for every
message whose kind is in `on`. `max` and `last` both fit that shape, and both keep the
register's value the same type as the field across every step — `max` because comparing two
values of one type yields a value of that same type, `last` because it never combines
anything, it only replaces the old value with the new reading. That is what makes the
`initial`-versus-field type check above a promise good for the register's whole life, not just
its first moment.

**`min` and `first`** are the mirror images of `max` and `last`, and would fit the same shape
just as well. Neither is declared here because nothing in this cycle needs one: the vocabulary
stays closed to what has an actual protocol behind it (`highest_promised`, tracked by `max`,
is the paxos-acceptor fixture's own register) rather than growing speculatively ahead of a
concrete use — the same restraint that kept `string` out of `fields`'s type vocabulary.

**`count` is excluded on purpose, and not for a shape reason.** A count is the fold that
invites "how many promises have I collected" — which is quorum, which is aggregation over a
set of messages, which the spec forbids a register from expressing: a register remembers one
scalar from one field, not a tally over who has responded. Refusing `count` costs this schema
nothing (no protocol in this cycle needs it) and removes the temptation to reach for it as
the readable-looking way to smuggle quorum counting past that restriction one message at a
time.

**`sum`** is excluded for a different, sharper reason: it would break the type-preservation
property above. `sum` folds arithmetically without regard to the field's type, and a running
sum of a `bool` field is not itself a `bool` (`True + True` is `2`, an `int`) — exactly the
type mismatch `check_machine`'s `initial`-versus-field check exists to catch, except this
time the mismatch would appear only after the fold had run, where nothing here can catch it
at parse time or at check time either.

### The fold/argmax boundary

**`argmax` is deliberately not in `FOLDS`, and is the fold most likely to be reached for
next.** It does not fit the one-remembered-scalar shape above: "the message that produced the
maximum" is a second value remembered alongside the scalar — which message, or which of its
other fields, broke the tie — and that second value is not in general an `int` or a `bool`
either. Admitting `argmax` means admitting a second remembered value and a second type for it,
which is a larger feature than one more string in a tuple, and it should be designed on
purpose rather than backed into.

**A third property, worth stating on its own rather than leaving it implied by the first
two:** `FIELD_TYPES` is closed to `int` and `bool`, so there is nothing a register could ever
hold that is a *payload* — only a value a guard can order or test for equality. Paxos's own
next step needs exactly a payload: once a proposer holds a quorum's worth of promises, it
must propose the *value* one of them already carried, not just the ballot that won. That
value is content, and content has no declarable field to carry it in — so no fold over this
schema's fields, `max`, `last`, or a future `argmax`, can ever be the register that remembers
it.

Nor can two registers forge it. `highest_ballot: max(ballot)` alongside `chosen: last(value)`
looks like it tracks both halves, but `value` is content with no field to name it in the
first place, and even granting one, `last` remembers the *most recent* reading, not the one
paired with the maximum — the two folds run independently and go out of step on the first
message that arrives out of order. The forgery is not merely outside the vocabulary; it
computes the wrong answer, silently, the first time it matters.

`plugins/machines/lib/machines/machine.py`'s `check_machine` carries this same reasoning,
written to stand on its own, next to the R1-R4 checks — for a reader who gets there first.

## `cap`

**Type:** either a bare positive integer, or a mapping `{ limit: <positive integer>, per:
<channel|role> }`. **Optional.** It is the one top-level field a declaration may leave out.

The two forms say the same thing when `per` is `channel`: `cap: 10` and
`cap: { limit: 10, per: channel }` parse to an identical machine. The bare form is not a
separate rule kept around for its own sake — it is the mapping form's `channel` case,
spelled without the mapping, because `channel` was the only scope this field ever needed
until it gained a second one. `limit` obeys the same positive-integer rule either way —
`0`, a negative number, a non-integer (including a quoted string), and a boolean (Python
considers `True` an `int`) are all rejected, in both forms, by the same check. In the
mapping form both keys are required — `{ limit: 10 }` and `{ per: role }` are each rejected
by name for the key they are missing — and any key besides `limit` and `per` is rejected by
name too; there is no default `per` a declaration can fall back on, for the same reason
there is no default `cap` at all: a scope the publisher did not write is not a scope they
agreed to.

The transition cap: the maximum number of outbound messages this machine's engine will ever
emit, within its scope, for one run. It caps outbound messages, not transitions and not
comments — a purely local move (`signal: false`) is not an outbound message, so it does not
count against `cap` even though it is a transition; and a bundle's own "ten messages per
role per run" rule is that bundle's choice of value, not the framework's.

### What a cap's scope counts

`per` says what the limit is measured against, not what counts as a message — that answer
(outbound, `signal: true`, above) is the same for every scope.

- **`channel`** — the whole run shares one budget. Every outbound message from every role
  counts against the same `limit`, the way a bare `cap: 10` has always been read.
- **`role`** — each declared role (see `roles`, above) gets its own budget of `limit`
  messages. A two-role protocol's two roles are counted, and capped, separately, rather than
  drawn from one shared pool.

**There is no `run` scope**, because a run is a channel under a different name here — `per:
run` would be a second spelling of `per: channel`, not a third scope, so the schema does not
carry one. **There is no per-sender scope**, and `per: sender` is rejected by name, not
accepted as another spelling of `role`: this declaration language declares `roles`, checked
against every `holder` and `by`, and has no separate field that names who sent one
particular message. `role` counts what the schema can name.

That said, `role` and a genuine per-sender count are the same thing only as long as exactly
one participant ever holds a given role in a run, which is what every declaration in this
cycle assumes. A future cycle that let more than one participant share a role at once would
make the two diverge — the budget would still be counted per role, not per the participant
that happens to be sending — and would need its own new scope if a bundle wanted the
narrower count. Nothing here anticipates that; `role` means what it says today, one bound
per declared role.

A cap cannot be disguised as `true`: the parser rejects a boolean here even though Python
considers `True` an `int`.

**A protocol needs no cap, and this framework does not require one.** Leaving `cap` out
means exactly one thing — *this protocol declares no bound on how many messages a run may
emit* — and it is the honest declaration for any protocol that has no reason to stop. There
is no default. Nothing substitutes a number the publisher did not write, and
`check_machine` skips the satisfiability check below entirely rather than measuring the
machine against an invented bound.

That is deliberate, and it is a correction. An earlier version of this schema required
`cap`, on the reasoning that a cap is what makes termination checkable and termination is
what a protocol owes. Both halves were wrong. Termination is a property of *some* protocols,
not a law of protocols, and requiring a bound of an author who has none forces them to write
a number nobody believes. **A declared bound nobody believes is the failure this framework
exists to answer, not one it should cause.**

**When a cap is written, it is compared to the machine, not just validated on its own,** and
it is compared at *every* state something is owed, not only at `initial`. A check that
measured only from `initial` would say nothing whenever `initial` happens to be accepting —
`session-relay`'s `unopened` is exactly that state, so a check with that shape never
exercises this framework's own only real declaration. `check_machine` instead treats every
**subject** — every state reachable from `initial` that is neither accepting nor terminal,
i.e. every state where something is owed and the run can still move — as a question worth
asking on its own. An accepting state is never asked: its own distance to the goal set below
is itself, zero, so no cap could ever be too small for it. A terminal non-accepting state (an
abort) is never asked either: it can reach nothing at all, by construction, so it would only
ever land in the no-accepting-state-reachable case below.

The goal set is the **accepting** states, and only the accepting states — not the terminal
ones, and not `accepting | terminal`, which is the goal set the can-a-run-stop check
(the next section) uses. The two checks ask different questions on purpose: can-a-run-stop
asks whether a run can escape limbo at all, and an abort escapes it, so terminal states count
there. This check asks whether the declared budget buys somewhere *good* — a state where
nothing is owed on purpose, not a state the run gave up in — and an abort is not somewhere
good. A cap that only reaches the error state is a cap that cannot be satisfied.

For each subject, `check_machine` counts only `signal: true` transitions on a route to an
accepting state, a `signal: false` transition costing nothing because it emits no message a
peer ever sees — the cheapest route to a goal is the one with the fewest *signalling*
transitions, not the fewest transitions of any kind, so a long detour through local moves
that fires one signal is cheaper, for this purpose, than a two-hop route that signals twice.
A subject whose cheapest route costs more than the cap is reported. A subject from which no
accepting state is reachable at all is reported by neither this check nor a second one
piled on top of it — that is already the can-a-run-stop check's finding, or the
no-accepting-state one, and a cap message would be a second symptom of the same cause.

**The cost of a route depends on the cap's scope**, `per` (see above). Under `channel`, every
role's signalling transitions draw from the one shared budget, so the cost is just the count
along the route, computed for every subject at once by a single backward search from the
goal set. Under `role`, the cost that matters is the *worst single role* on the route — the
maximum, not the sum, over each role's own signalling transitions — because each role is
capped separately. A subject whose channel-scope route already fits under the limit is
satisfiable under `role` scope for free (spreading a fixed number of transitions across roles
can only lower the per-role maximum, never raise it), so most subjects are settled without
any further search. Whatever is left needs an actual search over which role fires how many
times along which route, and that search's cost grows with the number of declared roles —
guarded by a size limit before it ever runs; see the next paragraph for what that means for
an author.

**A per-role cap on a subject phase 1 cannot clear is bounded, and past the bound this check
reports nothing about that subject rather than refusing to analyse it or hanging.** This
bounds one subject's search, not `check_machine`'s total work: phase 2 runs once per subject
phase 1 could not clear, so a machine with several such subjects costs a multiple of this
bound, not the bound itself — still finite, still returns, just not "this much work, once."
The search space for one subject is `states × (limit + 1) ^ roles`; past roughly a million
such states, `check_machine` gives up silently on that subject, the same direction §7 already
takes for the guard abstraction generally and §9 already takes for every finding an author
cannot suppress — a fatal "could not analyse" on a valid machine would be worse than a
missing finding. In practice this budget is generous for every declaration this cycle ships:
`session-relay` (5 states, `limit: 10`, 2 roles) uses 605 of it, and `paxos-acceptor`
(5 states, `limit: 6`, 2 roles) uses 245 — about three orders of magnitude of headroom for
either.

**A second, sharper bound applies before this one is even consulted.** Edge weights are 0 or
1, so a cheapest route is always achievable by some *simple* path — repeating a state only
adds cost — and a simple path visits at most `states` states, i.e. at most `states - 1`
edges. So no subject's channel-scope distance can ever exceed `states - 1`, and phase 2 is
reached at all — for *any* `limit`, at *any* role count — only when `limit ≤ states - 2`.
`states - 2` is also the `limit` at which the phase-2 product, `states × (limit + 1) ^
roles`, is *largest* (it only grows with `limit` over that range), which is exactly why the
boundary machines below fix `limit` there: it is the worst case, not merely a reachable one.

Whether that worst case still clears the budget depends on `states` *and* `roles` together,
not on `states` alone — a blanket "this guard is irrelevant to small machines at any role
count" would itself be false: a 5-state machine's product at its largest reachable `limit`,
3, first exceeds the budget at 9 declared roles (`5 × 4 ^ 9 = 1,310,720`). For the role
counts this cycle's declarations and the table below actually use (2-4), though, it holds: a
5-state machine can never have a subject more than 4 signalling transitions from an accepting
state, so `limit: 30` (or any limit above 3) never reaches phase 2 at 2, 3 or 4 declared
roles — phase 1 clears every subject first, every time. An earlier version of this paragraph
missed the `states - 2` bound entirely and named "`limit: 30`" as an example of this guard
"already tripping" on a 4-role, 5-state protocol — that example was impossible, the same
`_MAX_NFA_STATES` shape one level down, this time in the documentation rather than the code.

Measured, both bounds together — the largest `limit` at which phase 2 is ever reached at all
(`states - 2`), and the largest `limit` the search budget would still permit *if* reached:

| Shape | Reachable at all up to `limit` | Budget permits up to `limit` | This guard can bind? |
|---|---|---|---|
| 5 states, 2 roles | 3 | 446 | no — reachability is the tighter bound |
| 5 states, 3 roles | 3 | 57 | no — reachability is the tighter bound |
| 5 states, 4 roles | 3 | 20 | no — reachability is the tighter bound |
| 20 states, 2 roles | 18 | 222 | no — reachability is the tighter bound |
| 20 states, 4 roles | 18 | 13 | **yes — budget is the tighter bound** |

Only the last row can ever actually trip this guard. Where silence genuinely begins, measured
by finding the smallest single-chain machine — every signalling edge fired by one declared
role among several, `limit = states - 2` (the *largest* `limit` at which phase 2 is reached
at all, so the one most likely to trip the guard) — whose product first exceeds budget: 17
states at 4 roles (`limit: 15`, product 1,114,112), 9 states at 6 roles (`limit: 7`, product
2,359,296), 33 states at 3 roles (`limit: 31`, product 1,081,344). Below each of those state
counts, at its own role count, this guard is provably never consulted, however large `limit`
is written — phase 1 clears everything first.

The fact that still matters, stated as what it explains rather than as a separate comfort:
this search is only ever reached by a subject the free, per-channel clearance above could not
already clear — one whose cheapest route to an accepting state needs *more than `limit`*
signalling transitions in total, every role counted together. That route needing that many
transitions is exactly why it needs that many states to walk through, which is the `states -
2` bound above, not a second fact layered on top of it. Publishing a number without checking
which bound actually governs it is the exact mistake this codebase has already shipped once,
in `pattern.py`'s `_MAX_NFA_STATES`: a stated rationale wrong by a factor of ten, because the
real limit was set by something else first, and only a full review found it.

## `initial`

**Type:** string. **Required.**

The name of the state a run starts in. `check_machine` checks that this names a state actually
declared under `states` below — a publisher who mistypes it would otherwise get a machine
that can never legally start.

## Accepting is not terminal

Two properties of a state, easy to conflate, and the schema keeps them apart because they
answer different questions.

**Accepting means nothing further is *required*.** It is fine for the conversation to stop
here, because nothing is owed to anybody.

**Terminal means nothing further is *possible*.** No transition leaves the state.

The example that makes it land: *I sent a message to session B and I am now waiting for a
response.* That is clearly an unfinished conversation — my state is **not accepting**,
because something is owed and the conversation stopping there would leave it hanging. On the
other side, session B is in an accepting state the whole time. It would be fine for messages
to arrive and it could also respond, but as long as it is only answering questions it owes
nothing at any point, and those answers are **self-transitions on an accepting state**.

All four combinations are legal and all four mean something:

| | `terminal: true` | `terminal: false` |
|---|---|---|
| **`accepting: true`** | A conclusion. `session-relay`'s `concluded`: done, and nothing was left owed. | The idle responder above. Willing to answer another question, owing nobody anything. A machine made entirely of these never terminates and is perfectly well-formed. |
| **`accepting: false`** | **An error state.** An abort, a protocol violation, a peer that went away. The conversation ended *while something was still owed, and that is the point of reaching it* — the effects notify the peers and a human picks it up. `session-relay`'s `stalled`. | Waiting for a reply. Something is owed and the conversation can still continue. |

**A protocol does not have to terminate.** A machine with no terminal state at all is
well-formed, provided at least one state is accepting. A continuous protocol — two sessions
gossiping indefinitely, a watcher that reports whenever it has something to report — is a
real protocol, and nothing here asks it to invent an ending.

What the checker does insist on, which is the property worth protecting, is that **nobody is
ever owed something forever with no exit**:

- **At least one state must be accepting.** A protocol with nowhere the conversation may rest
  is never in a good state. (The default for `accepting` is `false`, so this is what a
  declaration that marks nothing accepting runs into — loudly, by name, rather than silently
  getting a machine where stopping anywhere is fine.)
- **Every state must be able to reach somewhere a run may legitimately stop** — an accepting
  state *or* a terminal one. Stopping badly is still an exit. Terminal states are exempt as
  subjects of this check, because they can reach nothing at all by construction; a terminal
  state *is* one of the places a run may stop.

**What the checker does not insist on, deliberately:** that every route leads somewhere good.
A non-accepting state whose every future ends in a terminal non-accepting state — a doomed
branch, "once the versions are incompatible, every route aborts" — is accepted. It is a true
thing to declare, there is no field with which an author could confirm they meant it, and an
unsuppressible complaint about a valid machine would be worse than a missing one.

**`accepting` is a declared assertion, not a derived one, and that limit is permanent.** A
publisher writes `accepting: true` because nothing is owed to anybody in that state — a claim
about what the protocol *means*, not about its shape. `check_machine` checks the structural
properties that surround the claim (that at least one state carries it, that every state can
reach one that does) but never checks the claim itself: nothing here can confirm that a state
a publisher marked accepting really is a fine place for a run to stop, any more than it could
catch the reverse — a state marked accepting where something is, in fact, still owed. That is
not a gap a later cycle closes. "Nothing further is required" is a fact about the protocol's
meaning, which lives with the person who wrote the declaration, not in its shape, so no
structural checker — this one or any future one — can ever verify it from the declaration
alone. Trusting `accepting` means trusting whoever wrote it.

## `states`

**Type:** list of state objects. **Required.** At least one entry. Must actually be a list
— `states: not-a-list` is rejected by name rather than raising a bare `TypeError` when the
parser tries to iterate it.

Each entry is a state, with these fields:

- **`name`** (string, required) — the state's identifier. Every other reference to a state
  (`initial`, a transition's `from`/`to`) is checked against these names. **Two states
  sharing a name is rejected at parse time** — without that check, the second `states` entry
  would silently replace the first in the `states` dict, and half the declared transitions
  would land on a state that was never declared as its author intended. A name that happens
  to be a YAML boolean-token word (`no`, `yes`, `on`, `off`) still lands as that literal
  string — see "Scalars mean what you wrote" above.
- **`holder`** (string, optional, default: none) — which declared role acts while the machine
  is in this state. Checked against `roles` above, and against the `by` of every transition
  out of this state: `holder` and `by` both say who acts next, so a state held by one role
  whose only exits are taken by another is reported.
- **`terminal`** (boolean, optional, default: `false`) — whether nothing further is
  *possible* here. `check_machine` checks that a terminal state has no outgoing transition: a
  run cannot end and continue in the same breath. That is the whole of it. **There is no
  requirement that any state be terminal**, and no requirement that a terminal state be
  accepting — see "Accepting is not terminal" above; a terminal non-accepting state is an
  error state, and it is one of the most useful states a protocol can have. If present, must
  be an actual boolean — `terminal: yes` is rejected rather than accepted as the string
  `"yes"` coerced to `True` by Python truthiness.
- **`accepting`** (boolean, optional, **default: `false`**) — whether nothing further is
  *required* here: it is fine for the conversation to stop in this state, because nothing is
  owed. Independent of `terminal` in both directions, and neither is derived from the other.
  `check_machine` checks that at least one state in the machine is accepting, and that every
  state can reach an accepting or terminal state. **The default is the conservative one on
  purpose:** an author who marks nothing accepting gets a machine the checker rejects by
  name, rather than one that silently says stopping anywhere is fine. If present, must be an
  actual boolean, for the same reason `terminal` and `signal` must.

Any field on a state entry other than `name`, `holder`, `terminal` and `accepting` is
rejected by name.

## `transitions`

**Type:** list of transition objects. **Required.** May be empty, though a machine with no
transitions can never leave its initial state. Must actually be a list — `transitions:
not-a-list` is rejected by name, the same as a malformed `states`.

Each entry is a transition, with these fields:

- **`from`** (string, required) — the state this transition fires out of. The declared
  attribute is `frm`, not `from`: `from` is a Python keyword, so the YAML field name and the
  attribute name differ on purpose. Checked against `states`.
- **`on`** (string, required) — the message kind that fires this transition. Checked
  against `kinds`. **The field name most exposed to the YAML boolean hazard above** —
  written as a bare mapping key, `on:` is exactly the word PyYAML's default resolver turns
  into the boolean `True`. Narrowing boolean resolution (see above) is what keeps `on:
  question` — and `on: yes`, should a protocol need that kind name — as the string the
  publisher wrote.
- **`by`** (string, required) — the role that must hold the state for this transition to
  fire. Checked against `roles`.
- **`to`** (string, required) — the state this transition lands in. Checked against
  `states`. Two transitions sharing `from`, `on` and `by` but naming different `to` states
  are reported: the engine is a fold over the message trace, and a fold has exactly one
  result per step, so a machine with that choice in it cannot be run at all — **unless every
  one of them carries a `guard`, all of those guards compare the same `field` to the same
  `register`, and no two of their operators' atom sets (see the table under `guard`, below)
  intersect.** A member with no guard, or a guard naming a different `field` or `register`
  than the rest, cannot be related to the others without interpreting a value the checker
  never evaluates, so it is reported exactly as an unguarded pair is. This proves the
  branches are disjoint and nothing more: a group with only one guarded member — an acceptor
  that accepts a high ballot and does nothing at all with a low one — is legal, because an
  incomplete guard set fires no transition for the outcomes it omits, which is the same
  legal outcome as an illegal message, already reported elsewhere.
- **`signal`** (boolean, optional, default: `false`) — whether firing this transition emits a
  signal to a peer, as opposed to a purely local move. If present, must be an actual boolean;
  see "Scalars mean what you wrote" above — `signal: yes` is rejected, not silently accepted
  as true.
- **`effects`** (list of strings, optional, default: empty list) — side effects to apply when
  this transition fires. `check_machine` restricts every entry to the fixed vocabulary
  `label.add:<name>`, `label.remove:<name>` and `escalate` — nothing else. This is what
  keeps the declaration inert data rather than a program: an unvalidated effect such as
  `run:curl ...` would be an instruction, and an engine that later grew to honour it would be
  executing a stranger's command.
- **`guard`** (mapping, optional) — a restriction on whether this transition fires: one
  declared header field, compared to one declared register's remembered value, by one
  operator. Exactly three keys, all required, no others tolerated:

  ```yaml
  guard: { field: ballot, op: gt, register: highest_promised }
  ```

  A guard narrows *when* a transition fires, and the determinism check above reads it: two
  guarded transitions sharing `from`, `on` and `by` are accepted when their guards compare
  the same `field` to the same `register` and their operators' atom sets are disjoint — see
  the `to` bullet, above, for the rule stated in full.

  `check_machine` cross-references a guard's `field` and `register` against `fields` and
  `registers`, and checks that the comparison it declares is type-sound:

  - **G1** — `field` must name a declared field.
  - **G2** — `register` must name a declared register.
  - **G3** — an ordering operator (`lt`, `le`, `gt`, `ge`) may only be used on an `int`
    field. Ordering two booleans has no meaning the engine could implement.
  - **G4** — the guard's field and its register's field must be declared the same type.
    Comparing an integer against a boolean passes G1–G3 individually and is still nonsense.
  - **G5** — a declared register that no guard names is reported (see `registers`, above).

  One requirement this design names has no check here, on purpose: that the value a guard
  compares against is derivable from the trace and nowhere else. It is enforced by
  construction, not by anything that could fail — a register's only source is a fold over a
  field of messages of declared kinds, and there is no syntax anywhere in this schema for a
  register to come from anything else.

  **`op` is one of six words, never a symbol.** Loaded through the shipped
  `MachineSafeLoader`, an unquoted `op: >` in block context parses to the empty string with
  no error raised anywhere — `>` is YAML's block-scalar indicator, not a comparison operator
  reaching the parser — and `op: !=` fails with a YAML error about a tag (`!`) instead of a
  named field. Both are the wrong failure mode for a publisher who tried a symbol, so the
  vocabulary is spelled out as words instead:

  | `op` | Meaning | Atoms it accepts |
  |---|---|---|
  | `eq` | equal | `EQ` |
  | `ne` | not equal | `LT`, `GT` |
  | `lt` | less than | `LT` |
  | `le` | less than or equal | `LT`, `EQ` |
  | `gt` | greater than | `GT` |
  | `ge` | greater than or equal | `EQ`, `GT` |

  `LT`, `EQ` and `GT` are the three possible outcomes of comparing two values of a totally
  ordered type — there are no others — and every operator above is exactly the union of the
  outcomes that make it true. `eq` and `ne` are meaningful on a `bool` field (there are only
  two values, so equal-or-not is all there is to ask); `lt`/`le`/`gt`/`ge` are not (G3).

  **Two engine semantics cycle B implements and this schema pins in advance**, even though
  nothing in cycle A evaluates a guard, so that cycle B is working from one fixed answer
  rather than inventing it at that point:

  1. A guard is evaluated against the register's value *before* the arriving message is
     folded into it. Otherwise a guard comparing a field against the very register that
     folds that same field over the same kind — `ballot > highest_promised`, folded by
     `max` over `prepare` — could never fire: the register would already have absorbed the
     value being compared.
  2. A guard whose field is absent from the arriving message evaluates to false, so the
     transition does not fire. Absence is never an error and never a crash; a run in which
     no transition fires is simply a run the engine does not consider legal, for reasons it
     records elsewhere.

  **One requirement this schema states and no check enforces:** a machine declaring
  anything shaped like a consensus protocol — Paxos's acceptor among them — must say so in
  its own prose: that it checks message sequencing and the invariant its guards encode, and
  that it does *not* check agreement among peers. Nothing here can verify that a publisher
  wrote that sentence. It is a discipline this schema asks for and cannot compel.

Any field on a transition entry other than `from`, `on`, `by`, `to`, `signal`, `effects` and
`guard` is rejected by name.
