# machines

Declare a communication protocol as a state machine, next to the prose that explains it,
and check it before you trust it.

## What this ships, and what it does not

**Cycle A shipped the schema and the checker; cycle A.1 built typed fields, registers,
guard and a scoped, strengthened cap check into that same schema and checker; cycle B
built the engine.** There is an engine: given a machine and the recorded trace of a
channel, it advances a state and emits a **verdict**. It still emits no message and
performs no effect, because the verdict only names what would happen. There is no
installer — nothing wires a declared machine into anything that dispatches real traffic.
There is no dispatcher — nothing routes an inbound message to the machine that owns it.
What exists is a closed declaration language, a parser for it, a set of checks that a
single machine is well-formed, a checker that runs those checks over every machine handed
to it and reports whether any two claim the same message, and an engine that folds a trace
into a verdict. The engine is a library (`machines.engine`); `bin/machines-check` does not
call it. Anything that wires the engine into a transport is a later cycle.

## The engine

`machines.engine.verdict(machine, trace)` reads a channel's recorded trace and answers
*is this a legal run of this machine, and where does it stand?* `machines.engine.gate(machine,
trace, outbound)` answers *may this outbound message be sent now?* Neither performs anything:
`escalate`, in an effect list, is a word in a tuple.

- **The fold** walks the trace and produces the state, every declared register, what each
  role has spent against the cap, and every guard reading. A guard is read against its
  register as it stood **before** the arriving message was folded in, and a guard whose
  field is absent from the message is **false**, never an error.
- **The verdict** names the state, the `holder`, `accepting`, `terminal`, `may_send`,
  `remaining`, `effects`, `order`, `concurrent_with`, every guard reading, every world read,
  the outbound clock, every refusal, and whether the fold was `truncated`.
- **`legal` answers two questions.** From `verdict()` it means *this trace is a legal run*,
  and it is false when the fold refused any message; `reason` names the first refusal. It
  is also false when the trace already exceeded a declared cap (a negative `headroom`); the
  engine does not attribute the overspend to a particular message.
  From `gate()` it means *may this message be sent now*; an old refusal in the history is
  still reported in `refusals` but does not by itself refuse an outbound message. When
  `legal` is false, `may_send` still lists the offers of the folded state — they are the
  state's offers, not a permission.
- **The clock** orders messages and detects duplicates, per sender. Four order values:
  `ok`, `duplicate`, `out-of-order`, `concurrent`; the `order` field only ever holds `ok`
  or `concurrent`, and the other two appear as a refusal's `reason`. Within one sender a clock that does not
  rise is refused. Across senders an equal or lower clock is reported as `concurrent` and
  **neither message is refused**. The gate stamps the outbound clock and discards any
  clock the caller supplied.
- **The cap is per role; the clock is per sender.** `remaining` is `None` exactly when the
  declaration has no `cap`. Otherwise `spent` and `headroom` map every declared role. Under
  `per: channel` the headroom is the same shared number for every role, so it must never be
  summed.
- **The gate** refuses for exactly five reasons: `not permitted here`, `cap exhausted`,
  `terminal state`, `ambiguous`, and the truncation refusal.
- **`effects` is one unclassified tuple.** The spec promises a `transport` / `agent` split;
  what classifies a verb is the transport declaration, which is a later cycle, so the split
  waits.
- **The fold has an engine-side limit** (10,000 messages, refused ones included). It is a
  defence against a runaway trace, not a bound on a protocol, and nothing in a declaration
  sets it. A fold that reaches it is `truncated` and the verdict is not legal.

`SCHEMA.md`'s "What the engine does with a declaration" carries the arithmetic and the
refusal reasons in full.

## What the engine does not check

The framework does not check meaning, and no part of it may appear to. The engine is the
first part of this plugin that *runs* a protocol, which is why this list is here and not
only in `SCHEMA.md`, which has it in full.

1. **Content.** A trace has no slot for a message body. The engine reads kinds, roles,
   declared fields and the envelope; whether a draft states a new fact, or an answer answers
   the question, is not visible to it.
2. **Meaning, including `accepting`.** The engine reports `accepting` because the
   declaration says so. Nothing here can confirm a state marked accepting is a fine place
   to stop.
3. **Agreement.** A consensus-shaped machine, `paxos-acceptor` among them, gets its
   sequencing and its declared invariant checked and nothing about agreement among peers.
4. **Whether a guard will fire.** `may_send` names a guarded offer without evaluating it, as
   no message exists yet. The checker cannot tell you a guard never fires either.
5. **Whether the transport told the truth.** A hostile transport can misreport which messages
   exist, and leaving messages out changes the state and can let a role past its cap. Given
   the trace it was handed, the engine cannot be made to accept a transition the declaration
   lacks, exceed its cap or report an undefined state; every guarantee is about the trace, not
   the conversation.
6. **Anything outside the channel.** A world read is carried into the verdict and the engine
   never branches on it.
7. **The clock is not `seq`, and `remaining` is not an ordinal.** One sender's tenth message
   can carry a clock of about 19. Never render a visible `n of 10` from the clock.
8. **Whether a declaration is unambiguous.** `check_machine` reports two transitions that
   share `from`, `on` and `by` unless their guards prove them disjoint, whether or not they
   agree on `to` (so two that differ only in `effects` are reported), and it reports a
   transition declared twice. It cannot vouch for a machine built in code rather than
   parsed: the engine still refuses a message that matches more than one transition as
   `ambiguous`, as the backstop.

## The declaration

A machine is a single ` ```machine ` fenced YAML block inside a bundle's `SKILL.md` — twelve
fields: `machine`, `publisher`, `version`, `prefix`, `roles`, `kinds`, `fields`, `registers`,
`cap`, `initial`, `states`, `transitions`. All of them are required except `publisher`,
`cap`, `fields`, and `registers`. Each role binds to `repository` or `session`, nothing else. Any other top-level field is rejected by name, not silently ignored.
`SCHEMA.md` documents every field and why it exists, including the two hazards worth
knowing before you write a declaration by hand.

**A protocol does not have to terminate, and does not have to declare a cap.** A state is
*accepting* when nothing further is required — it is fine for the conversation to stop
there — and *terminal* when nothing further is possible. They are different properties and
all four combinations are legal: a conclusion is both; an idle responder willing to answer
another question is accepting and not terminal; a session waiting for a reply is neither;
and an abort is terminal and *not* accepting, because the conversation ended while
something was still owed and saying so is the point of the state. Leaving `cap` out says
this protocol declares no bound, and nothing invents one for you.

**`prefix` is a pattern, not literal text.** It is read as an expression in a small regular
language, so a prefix containing `( ) [ ] . * + ? | \ { }` does not claim the characters you
typed — `proto(v1) ` claims `protov1 `, and `[proto] ` claims `p `, `r `, `o ` and `t ` —
while the checker still exits `0`. Escape those characters with `\` (`proto\(v1\) `) or keep
the prefix to letters, digits, spaces, `:` and `-`. `SCHEMA.md` carries the whole grammar.

**`yes` and `no` are not booleans here.** PyYAML's default loader treats the bare words
`yes`, `no`, `on` and `off` as booleans anywhere a string can appear, including a mapping key
(`on: yes` is exactly the kind of word this catches) — this parser narrows that resolution to
`true`/`false` only, so a state or role named `no` stays the string you wrote.

## The checker

`bin/machines-check <path>...` — each path is a declaration file directly, or a directory
to search for a `SKILL.md`. It parses every machine it finds, checks each one for
well-formedness, and checks every pair of distinctly-named machines for a prefix collision
— two protocols that could both claim the same message.

**A problem names the version it is in, a collision does not.** A problem line reads
`acme/session-relay@v1: …`, because a defect belongs to one version and an installer keeps
old versions on purpose. A collision line reads `acme/session-relay and globex/session-relay`
with no version on either side, because two protocols that claim one prefix do so in every
version they have — and that pair is reported once however many versions of either one the
run examined.

What "well-formed" covers: every referenced state, role and kind is actually declared; at
least one state is accepting; every state can reach somewhere a run may legitimately stop
(an accepting state or a terminal one); a terminal state has no way out of it; nothing is
unreachable from `initial`; a state's declared `holder` is the role that actually acts on
the way out of it; no declared kind sits there with no transition firing on it; every
declared `field` has a name and type the checker recognises; every declared `register`
names a declared field and a declared kind list to fold over, and its `initial` value
agrees in type with the field it folds; every declared register is named by some guard, or
reported as dead weight if none names it; every `guard` names a declared field and a
declared register, uses an ordering operator only on an `int` field, and compares two sides
the checker can confirm are the same type; two transitions may share a trigger and disagree
about where it leads **only** when every one of them carries a guard, all of those guards
compare the same field to the same register, and no two of their operators can both hold at
once — otherwise that is reported the same as an unguarded pair; and a declared `cap` is
large enough, from every state where something is still owed (not only from `initial`), to
reach an accepting state — measured as the fewest signalling transitions under `channel`
scope, or as the worst single role's signalling transitions under `role` scope, since each
role draws from its own budget — and is not checked at all when no cap is declared.

**Guards.** A guard restricts *when* a transition fires: one declared header field, compared
to one declared register's remembered value, by one of six named operators (`eq`, `ne`,
`lt`, `le`, `gt`, `ge` — never a bare symbol). What a guard deliberately cannot do is
aggregate over a set of messages — count how many peers have responded, say, which is
quorum, not a fold over one register. The checker treats a guarded transition as a branch
with both outcomes possible: it proves two guarded branches cannot *both* fire, which is
what makes them a legal alternative to one deterministic transition, but it never evaluates
a guard against real data, so it cannot tell you a guard never fires, or fires every time,
or which of its declared branches a given run will actually take. `SCHEMA.md`'s `guard`
section carries the full operator table and the determinism rule in full.

What it deliberately does not cover: that the machine terminates. Cycle A required that and
it was wrong — see `SCHEMA.md`'s "Accepting is not terminal".

```
plugins/machines/bin/machines-check plugins/machines/tests/fixtures/valid-session-relay.md
Examined 1 machine
```

**Three exit codes, not two:**

| Exit | Means |
|---|---|
| `0` | Every machine examined is well-formed and none collide |
| `1` | The tool ran and found a problem — a bad declaration, or a collision |
| `2` | The tool could not run at all — no paths given, a path that doesn't exist, PyYAML missing, or a broken interpreter |

A tool that cannot run must never exit `1`: that code reads as "I checked, and found a
problem," and a broken install is not a finding. `bin/machines-check` checks for `python3`
and for PyYAML before it ever tries to parse anything, and if that probe itself fails for a
reason that has nothing to do with PyYAML — a pyenv shim pointed at an interpreter that
isn't installed, say — it lets that interpreter's own error reach stderr rather than
reporting a misleading "install PyYAML" for a problem that isn't about PyYAML at all.

**The output always states how many machines were examined, including zero — and only
claims "No collisions found" when it examined a pair.** "No collisions found" after looking
at nothing is the failure `evidence-discipline` documents under a different name: a check
that passed because it checked nothing. Every run of `machines-check` that gets past the
exit-2 checks prints `Examined N machine(s)` before anything else, whether `N` is eleven or
zero; the collision verdict appears only when `N` is at least two, because a collision takes
two machines and one machine is no pair. That is why the example above, on a single file,
prints the count and stops.

## Dependency

PyYAML. Not standard library, so `bin/machines-check` checks for it and fails with the
install command (`python3 -m pip install PyYAML`) rather than a traceback if it's missing.
Everything under `lib/` besides the YAML dependency is standard library, Python 3.8+.

## Running the tests

```
cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest discover -s tests -t .
```

pytest is not assumed to be installed; the suite is plain `unittest`.

## Install it if

You are declaring a communication protocol between two agents, sessions, or services as an
explicit state machine and want it checked before you rely on it. There is no skill here to
trigger — this is a library, an engine and a command-line checker, nothing that fires on its own.

Skip it if you want something that wires a protocol into a live transport, or that checks
what a conversation *means*. The engine folds a recorded trace into a verdict; it does not
connect to a channel, dispatch a message or perform an effect, and it does not read content.
