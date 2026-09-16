# `machines` Cycle A.1 — Typed Fields, Registers, Guards and a Real Cap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the declaration schema so a message can carry named, typed fields; so a
machine can remember one scalar derived from the trace; and so a transition can test one
field against one remembered value — and extend the checker to validate all three, to scope
the cap, to measure the cap from every state where something is owed, and to answer *"is this
machine well-formed"* completely when asked directly. **No engine. Nothing here evaluates a
guard.**

**Architecture:** Unchanged from cycle A. A declaration is a fenced `machine` block inside a
bundle's `SKILL.md`, written in a closed YAML language; `declaration.py` parses it into a
`Machine`, `machine.py` checks one machine, `registry.py` checks a set. A.1 adds two
top-level fields (`fields`, `registers`), one transition field (`guard`), one alternative
form for `cap`, and six checks. **The checker abstracts a guard into a branch with both
outcomes possible**, which is what keeps every graph property in the spec's §9 decidable.

**Tech Stack:** Python 3 (stdlib + PyYAML), `unittest`, bash entry point, GitHub Actions.
Nothing new.

**Spec:** `docs/superpowers/specs/2026-09-14-machines-framework-design.md` — read §4's layer
table, §7's *"Typed header fields, and the guards that test them"*, §9's *"The guard checks"*
and *"The cap check is weak"*, §10's item 1 and its row-7 paragraph, §11.7, §11.12, and
§13's A.1 proposal. **The plan argues from the spec; both travel together, and §"Where this
plan contradicts its inputs" below lists three places where the spec contradicts itself.**

**Issues:** `claude-operating-rules#31` (typed fields and guards),
`claude-operating-rules#28` (the backport walk, the weak cap check, the deferred checker
work). Both read 2026-09-15; `#31` has no comments, `#28` has four.

---

## Read this before you write a line

**All code in this plan is a PROPOSAL, not a requirement.** `writing-plans-and-dispatches`
rule 1 records fourteen real defects on one project, every one of them in code written into a
plan and transcribed faithfully because it arrived looking like requirements. **Cycle A's own
plan then produced seven more**, including a brief that contradicted itself between two
sections, a test list that omitted a test its own prose required, and a body that emitted N+2
problems from one typo. The contracts below — names, signatures, types, and the failure each
thing must prevent — are the binding part. The bodies are a sketch.

**Be sceptical. Report defects rather than fixing them silently.** If you conclude something
here is wrong, say so with evidence rather than implementing something you believe is
incorrect. This plan was written expecting to be contradicted, and the section *"Where this
plan contradicts its inputs"* is where it contradicts the spec on purpose — read it before
you decide a task is wrong.

**One thing you must not do:** do not add the effect-vocabulary change from the spec's §7
(*"a transport declares the verb set it implements"*). The shipped `check_machine` hardcodes
`label.add:`, `label.remove:` and `escalate`; §7 calls that a generalising-from-one-instance
failure and §13 puts the fix in **cycle C**, because it needs a transport declaration that
does not exist yet. Leave it exactly as it is.

---

## What A.1 delivers, and what it does not

Eight deliverables, all schema or checker. Every one of them is a property of a declaration
or a property of the graph a declaration describes. **Nothing in A.1 reads a channel, folds a
trace, evaluates a guard, or emits a verdict.** That is cycle B, and A.1 exists specifically
so that B's charter — *"needs A's schema"* — has a fixed input (§13).

| | Delivers | Task |
|---|---|---|
| 1 | Two cwd-dependent CLI tests fixed | 1 |
| 2 | Prefix validation moves from `check_all` into `check_machine` (§11.7) | 2 |
| 3 | `fields` — named, typed header fields | 3 |
| 4 | `registers` — one remembered scalar, folded from the trace | 4 |
| 5 | `guard` — one field against one register, on a transition | 5 |
| 6 | Determinism under guards — the branch rule that keeps the fold a function | 6 |
| 7 | `cap` gains a scope (§10 item 1, §11.12) | 7 |
| 8 | The stronger cap check, from every state where something is owed (§9) | 8 |
| — | `SCHEMA.md`, `README.md`, a worked guarded fixture, the plugin version | 9 |
| — | The spec's own "not built" marks, corrected | 10 |

### Explicitly out of scope, and why — read this before you add something helpful

- **The engine.** Cycle B. A.1 must not add anything that evaluates.
- **The transport declaration and the open effect vocabulary.** Cycle C (§13, and §7's own
  "verified 2026-09-15" paragraph).
- **The envelope's Lamport clock.** Cycle B (§4). §7 is explicit that it must never become a
  guardable field: *"duplicate and out-of-order detection is a comparison against one
  remembered integer that every protocol gets for free, and turning it into something an
  author declares reintroduces the thing an author can forget."* Task 3 reserves the
  namespace for it and declares nothing.
- **Two of the three shipped defects in §9.** §13 calls all three *"the natural contents of
  A.1"*, and the brief for this plan names only one of them (prefix validation's home). The
  other two are therefore **not planned here**, and this is flagged rather than quietly
  absorbed:
  - *the collision skip keyed on `name` alone* — `registry.py`'s `if a.name == b.name:
    continue` skips two different publishers who choose one name. Fixing it needs a
    publisher-qualified identity, which is a new top-level field, which is schema work and
    would sit naturally in Task 3. Sized: one optional `publisher` field, one change to the
    skip predicate, three tests. **Add it only if the author says so.**
  - *`roles` binds only names* — the values under them are unchecked. Sized: one check, one
    test, and a decision about what a role value *means*, which nothing has yet written down.
- **§11.10's second bound.** Refused by §11.10's own fourth comment on `#28`: the free local
  loop needs an epsilon move or a waiting verb, neither of which exists, so the gap is
  conditional on a feature nobody has built.
- **Row 7 as a guard.** §10 is explicit: *"Guards change what row 7 could be, and must not
  change what it is."* Task 9 therefore does **not** add `blocking` to the `session-relay`
  fixture. See the back-compatibility section.

---

## Measurements — already taken, do not re-derive

Every row was measured on this machine on 2026-09-15, from
`plugins/machines`, unless the provenance column says otherwise.

| Fact | Provenance |
|---|---|
| Python **3.11.9**, PyYAML **6.0.3**. `pytest` is not installed. | Measured |
| **193 tests pass** with `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest discover -s tests -t .` — `Ran 193 tests in 0.414s`, `OK` | Measured |
| **Two of them fail from the repository root.** `tests.test_registry.TestCli.test_a_valid_fixture_exits_0_and_reports_the_count` and `...test_one_machine_examined_claims_no_collision_check`, both `AssertionError: 2 != 0`. `test_registry.py:135` and `:161` pass the literal `"tests/fixtures/valid-session-relay.md"` to `main()`, the path does not exist relative to the root, and `_resolve_path` correctly returns exit 2. | Measured, both invocations |
| **CI never sees it.** `.github/workflows/machines-tests.yml` runs `cd plugins/machines && …`, so the suite is green in CI and red from the root. That is why the defect survived. | Read |
| `check_machine(m) -> List[str]`. Empty list means well-formed. It returns problems rather than raising, so a publisher gets every problem at once. | Read `machine.py` |
| `check_all(machines) -> Report`, with `examined: int`, `problems: Dict[str, List[str]]`, `collisions: List[Tuple[str, str]]`. A machine with no problems is **absent** from `problems`, not present with an empty list. | Read `registry.py` |
| **Import graph.** `machine.py` imports only `collections.deque` — nothing from the package. `pattern.py` imports only `.errors`. `product.py` imports `.pattern`. `registry.py` imports `.machine`, `.pattern`, `.product`. **So adding `machine.py → pattern.py` creates no cycle**, and it is the right direction: `machine` is protocol, `pattern` is the automaton library. | Read |
| `compile_pattern("x")` **compiles**. Every hand-built test machine in `test_machine.py` uses `prefix="x"`, so Task 2 adds no problems to any existing test. `compile_pattern("")` and `compile_pattern("a*")` raise `PatternError` (nullable). | Measured |
| `_MAX_PREFIX_LENGTH = 400` (`declaration.py:215`), `_MAX_GROUP_DEPTH = 100` (`pattern.py:106`). `registry.py` also catches `RecursionError` as a backstop. | Read |
| The shipped determinism message is exactly `"transitions from %r on %r by %r are nondeterministic: they lead to %s"`. | Read |
| The shipped cap message is exactly `"cap %d is too small: the shortest run from %r to an accepting state fires %d signalling transitions"`. | Read |
| **`tests/fixtures/valid-session-relay.md` and `tests/test_declaration.py`'s `VALID` carry byte-identical machine blocks.** They are two copies of one declaration and nothing keeps them in step. | Measured by diff |
| `test_machine.py`'s `mutate(old, new)` **asserts the splice landed**. `test_declaration.py` uses bare `VALID.replace(...)`, which silently no-ops when `old` stops occurring. A cap-syntax change in `VALID` would fail loudly in one file and silently in the other. | Read |
| `plugins/machines/.claude-plugin/plugin.json` is at version **`0.1.0`**. | Read |

### The YAML operator hazard — measured, and it decides the guard syntax

Loaded through the shipped `MachineSafeLoader`:

| Source | Result |
|---|---|
| `{op: ==}` | `{'op': '=='}` |
| `{op: <}` | `{'op': '<'}` |
| `{op: <=}` | `{'op': '<='}` |
| `{op: >}` | **`ScannerError`** |
| `{op: >=}` | **`ScannerError`** |
| `{op: !=}` | **`ScannerError`** (scanning a tag) |
| `op: >` (block context) | **`{'op': ''}`** — silently the empty string |
| `{op: gt}` | `{'op': 'gt'}` |

`>` is YAML's folded-scalar indicator and `!` starts a tag. In block context — the style the
shipped fixture uses for `transitions` entries — **`op: >` parses to the empty string with no
error at all.** That is the same class of failure as §7's `signal: yes`: a closed language
silently mis-parsed, so the machine that runs is not the machine that was written. Word
operators are not a style preference here; they are the measurement.

### The stronger cap check, run against every machine the shipped tests build

A read-only probe re-implemented the proposed check and ran it beside the shipped one over
every cap-relevant machine in `tests/test_machine.py`. **Exactly one verdict changes.**

| Machine | Shipped | Proposed |
|---|---|---|
| `VALID` fixture, `cap: 10` | 0 problems | 0 problems |
| **`VALID` fixture, `cap: 1`** | **0 problems** | **1: `awaiting-answer`, 2 signalling transitions** |
| `_linear_machine(cap=1)` | 1 (`start`) | 1 (`start`) |
| `_linear_machine(cap=2)` | 0 | 0 |
| `_linear_machine(cap=None)` | 0 | 0 |
| `local-moves-test`, cap 1 | 0 | 0 |
| `signal-only-test`, cap 1 | 1 (`start`, 2 transitions) | 1 (`start`, 2 transitions) |
| `recap`, cap 1 | 1 (`start`, 2 transitions) | 1 (`start`, 2 transitions) |
| `free-moves`, cap 1 | 0 | 0 |
| `gossip`, no cap | 0 | 0 |

**The one row that changes is the point of the change.** `test_an_accepting_initial_state_satisfies_every_cap`
(`test_machine.py:182`) asserts that `session-relay` with `cap: 1` has no cap problem —
which is true only because the shipped check measures from `initial`, and `unopened` is
accepting, so the distance is 0 and no positive cap can ever be reported. Under the stronger
form, `awaiting-answer` needs two signalling transitions to reach `concluded` and `cap: 1`
cannot buy them. **That test must be rewritten, not deleted** — see Task 8.

### The per-role cap, measured on `session-relay`

Same probe, computing the minimum over paths of the maximum over roles of that role's
signalling count, with counters clamped:

| Subject state | `per: channel`, limit 1 | `per: role`, limit 1 | `per: role`, limit 10 |
|---|---|---|---|
| `awaiting-triage` | 1 — OK | 1 — OK | 1 — OK |
| `awaiting-answer` | **2 — REPORTED** | 1 — OK | 1 — OK |

The two scopes give different verdicts on a real machine at limit 1, and agree at the real
limit 10. That is the demonstration that the scope is a real distinction and not decoration.

---

## The syntax, and why it is shaped this way

The spec fixes the semantics and leaves the concrete form open. This is that form. **Each
choice below is argued, and each argument is a place to push back.**

### The whole of it, in one block

This is a **proposal**, and it is also the fixture Task 9 writes. It is a Paxos acceptor,
which is the protocol §7 and `#31` both reason from.

```yaml
machine: paxos-acceptor
version: v1
prefix: "paxos:v1 "
roles:
  proposer: session
  acceptor: session
kinds: [prepare, promise, accept-request, accepted, rejected]
fields:
  ballot: int
registers:
  highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }
cap: { limit: 6, per: role }
initial: idle
states:
  - { name: idle,     holder: proposer, accepting: true }
  - { name: prepared, holder: acceptor }
  - { name: promised, holder: proposer, accepting: true }
  - { name: proposed, holder: acceptor }
  - { name: decided,  terminal: true, accepting: true }
transitions:
  - { from: idle, on: prepare, by: proposer, to: prepared, signal: true,
      guard: { field: ballot, op: gt, register: highest_promised } }
  - { from: idle, on: prepare, by: proposer, to: idle, signal: true,
      guard: { field: ballot, op: le, register: highest_promised } }
  - { from: prepared, on: promise, by: acceptor, to: promised, signal: true }
  - { from: promised, on: accept-request, by: proposer, to: proposed, signal: true,
      guard: { field: ballot, op: eq, register: highest_promised } }
  - { from: promised, on: accept-request, by: proposer, to: idle, signal: true,
      guard: { field: ballot, op: ne, register: highest_promised } }
  - { from: proposed, on: accepted, by: acceptor, to: decided, signal: true }
  - { from: proposed, on: rejected, by: acceptor, to: idle, signal: true }
```

**This machine was checked, not sketched (do not re-derive).** It was rebuilt with the shipped
`Machine`/`State`/`Transition` classes, guards stripped, and run through the shipped
`check_machine`. **The only problems it produces are the two determinism reports that Task 6
makes legal:**

```
transitions from 'idle' on 'prepare' by 'proposer' are nondeterministic: they lead to 'idle', 'prepared'
transitions from 'promised' on 'accept-request' by 'proposer' are nondeterministic: they lead to 'idle', 'proposed'
```

Everything else is clean: all five states reachable, every kind fired on, every `holder`
agreeing with its outgoing `by`, every state able to reach somewhere a run may stop. The
per-channel distance to an accepting state is 1 from `prepared` and 1 from `proposed`
(`promised` and `idle` are accepting and so are not subjects), well inside `limit: 6`. Under
the proposed determinism rule both guard groups share one `(field, register)` pair, and their
operator atom sets are disjoint **and** complete — `{GT}` ∪ `{LT, EQ}` and `{EQ}` ∪ `{LT, GT}`
each cover all three outcomes. `patterns_collide("paxos:v1 ", "session-relay:v1 ")` is
`False`.

### Choice 1 — a guard is a **shape**, not a string

`guard: { field: ballot, op: gt, register: highest_promised }`, never
`guard: "ballot > highest_promised"`.

Three reasons, in order of weight.

1. **A string needs a parser, and this project's stated position is that every parser defect
   becomes a framework defect.** It has already paid for that once: `pattern.py` is 770
   lines, it acquired a `RecursionError` reachable through the shipped CLI, and it now
   carries **two** separate depth guards (`_MAX_PREFIX_LENGTH = 400`,
   `_MAX_GROUP_DEPTH = 100`) plus a `RecursionError` backstop in `registry.py`, each added
   after the fact. A guard grammar would be a second parser and a second set of that. The
   structured form has no grammar: PyYAML parses it and the existing `_reject_unknown`
   machinery validates it.
2. **The asymmetry enforces the boundary structurally.** §7's rule — *"a guard tests one
   message against one remembered value"* — is a property of the shape here, not a check
   performed after parsing. `field` is always the arriving message's; `register` is always
   the remembered value's. There is no name resolution, no way to write field-against-field,
   and no way to write register-against-register. A string form would have to *check* what
   this form cannot express.
3. **Word operators, because the symbols are measured to be unsafe.** See the YAML table
   above: `op: >` in block context parses to the empty string with no error. A form whose
   most natural spelling silently mis-parses is disqualified on §7's own scalar-semantics
   argument, and quoting every operator (`op: ">"`) is no more readable than `op: gt` while
   being one more thing to forget.

**The cost, stated:** `{ field: ballot, op: gt, register: highest_promised }` is more
characters than `"ballot > highest_promised"`. A reviewer who thinks the string form reads
better is not wrong about that, and it is the one thing the string form wins.

**Operator vocabulary:** `eq`, `ne`, `lt`, `le`, `gt`, `ge`. Nothing else, and no negation, no
conjunction and no disjunction — a conjunction would be a second guard on one transition, and
a disjunction would be two transitions. Both are already expressible without new syntax.

### Choice 2 — exactly one guard per transition

Not a list. A list of guards ANDed together is still *"one message against one remembered
value"* per element, so it does not cross §7's boundary — but it does make the determinism
rule of Task 6 an intersection over sets of conjunctions instead of an intersection over
three atoms, and it buys nothing no author has asked for. **One guard, and an author who
needs two conditions splits the state.** If that turns out to bite, it is additive to fix.

### Choice 3 — `fields` is a name-to-type mapping, and there are exactly two types

```yaml
fields:
  ballot: int
  blocking: bool
```

- **`int`** — §7: *"a pattern cannot order two numbers. The schema needs integers."* Paxos
  needs it; epochs need it.
- **`bool`** — `session-relay`'s `blocking`. The brief names it.
- **`string` is refused, and the refusal is load-bearing.** Three reasons: the enumerable use
  of a string is already `kinds`, which is a closed vocabulary with its own checks; the
  non-enumerable use is content, and a checker cannot tell an identifier from a sentence, so
  a string field is the one shape that could make §4's third row look erased; and the one
  plausible string field, `ref`, is sender identity, which §10 says the **envelope** already
  carries and which *"needs nothing from the declaration"*. Adding a type later is additive
  and cheap. Removing one is a breaking change.
- **No `float`, no `enum`, no list, no mapping.** Nothing has asked.

**Field names must match `^[a-z][a-z0-9_-]*$`.** This is not tidiness. It forbids a `.` in a
field name, which **reserves the dotted namespace for the envelope**, so that when cycle B
adds the clock the two can never collide and §7's prohibition does not have to be re-argued
against a machine that already declared a field called `envelope.clock`. It also removes the
YAML-token hazard at the source: a field cannot be named `True`, `null` or `~`.

**A field the schema knows nothing about is not declarable, so the clock cannot be guarded.**
A.1 adds no envelope, declares no reserved names it would have to guess, and states in
`SCHEMA.md` that a machine's own field called `clock` is the machine's own integer and has
nothing to do with the envelope's.

**A declared field that no guard reads is NOT reported**, and the reason is §10's row 7.
`session-relay` must be able to declare `blocking` *without* guarding on it, because §10 is
explicit that the engine's unavoidable comparison is the right answer for row 7 and a guard
is the worse one. An unused-field check would force an author to choose between a field
nobody reads and a guard the spec forbids. (Contrast `kinds`, where the shipped unused-kind
check is right, because a kind no transition fires on is genuinely unreachable vocabulary.)

#### The asymmetry: an unread **register** is reported, an unused **field** is not

Task 5's check G5 reports a register no guard names, and nothing here reports a field no guard
tests. That is deliberate, and the argument belongs in the plan rather than in a report,
because **an asymmetry a reader cannot account for will be "fixed" by a later session into
whichever half is easier to argue for.**

> **A field has a second legitimate consumer; a register does not.** A declared field that no
> guard tests can still be carried in the header for the participant to read —
> `session-relay`'s `blocking` is exactly that, and §10 says a guard over it is the *worse*
> answer. A register exists only to be compared against. An unread one has no other use, so it
> is dead weight and probably an error.

So the two checks are not two answers to one question. They are one answer — *report a
declaration that has no possible consumer* — applied to two things with different numbers of
consumers. **If a later cycle gives registers a second consumer** (say, the verdict reporting
every register's value for readability, not only the ones a guard touched), G5 stops being
justified and must go. Whoever does that should delete it rather than weaken it.

### Choice 4 — a register is one scalar, folded from the trace, and this is where the Paxos line is drawn

```yaml
registers:
  highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }
```

Five keys, all required:

| Key | Type | The failure it prevents |
|---|---|---|
| `fold` | `max` \| `last` | — |
| `field` | a declared field name | the register's type is *derived* from the field, so there is no second place to declare a type and no second place for it to disagree |
| `on` | non-empty list of declared kinds | a register that silently absorbs a value from a message the author never thought about. A reader sees which messages move the remembered value, in one line |
| `initial` | matches the field's type | a default of `0` would be an invented number — the same failure as a default `cap` |

**`max` and `last` only.** `max` is §7's acceptor invariant (`ballot > highest_promised`).
`last` is §7's round matching (`epoch == current_epoch`, where `current_epoch` is the epoch of
the most recent round-defining message). `min` and `first` are their mirrors and cost one line
each, and are **refused because no protocol in hand needs them** — a feature with no instance
is a guess, which is exactly what §7's effect-vocabulary paragraph calls a
generalising-from-one-instance failure running in reverse. **`count` is refused for a
different and stronger reason:** a count is the shape that invites *"how many promises have I
collected"*, which is quorum, which is the aggregation over a set that §7 forbids. Refusing it
costs nothing and removes the temptation.

#### Where the fold/argmax line is, and why it holds

A reviewer will raise this first, so here it is first. The brief puts it exactly right: a
running maximum is a fold, `max(current, new)`, the same shape the framework already uses for
state. Paxos's proposer rule — *choose the value from the promise with the highest ballot* —
selects a payload associated with a maximum across a set, and is not allowed.

**"It is a fold" is not the line, and saying it is would be wrong.** The proposer rule is also
a fold:

```
acc' = (m.ballot > acc.ballot) ? (m.ballot, m.value) : acc
```

The real line is two properties of the accumulator, and A.1 enforces both by construction
rather than by rule:

1. **A register's accumulator is exactly one scalar.** An argmax needs a pair — the compared
   component and the carried one — and the carried one exists only *because of* the other's
   comparison. That coupling is where selection begins, and a one-scalar accumulator cannot
   express it. There is no syntax for a second component and no syntax for a projection.
2. **The fold's step reads exactly one field of the arriving message.** `max` reads
   `m.ballot` and writes `acc`. There is no form in which a step reads `m.ballot` to decide
   and `m.value` to store.

**And a third fact closes the escape route:** the only scalar types are `int` and `bool`, so
there is nothing a register *could* carry that is a payload. Paxos's proposer needs the
proposal value, which is content, which is not a declarable field at all.

**Could an author fake it with two registers** — `highest_ballot: max(ballot)` and
`chosen: last(value)`? No. `value` is content and there is no string type, so it is not
declarable; and even if it were, `last` is *the most recent*, not *the one that had the
maximum*, so the two registers go out of step on the first out-of-order message. The forgery
is not merely forbidden, it does not work.

> **The consequence the author should weigh, because it is a real cost of adding `string`
> later:** the argument above leans on the type set. If `string` is ever added, property 3
> disappears and the boundary rests on properties 1 and 2 alone. They still hold — but the
> case becomes an argument instead of a construction, and whoever adds `string` owes this
> section a rewrite. That is another reason to refuse it now.

**What the checker does not check about a register:** whether it is ever updated before it is
read. `initial` is required, so the register always has a value, and *"has a `prepare` arrived
yet"* is a runtime fact. Nothing is reported.

**What it does check:** a declared register that **no guard names is reported** (Task 5, check
G5). A register has exactly one consumer in the whole framework — a guard — so an unread
register has no other use and is probably an error. **A field is different because it has a
second legitimate consumer**: the participant reading the header. The full argument, and the
condition under which G5 must be deleted rather than weakened, is under *Choice 3*.

**Comparison against a literal constant is not expressible.** `ballot > 0` has no form:
a guard's right-hand side is always a register, per the brief. A constant *could* be faked by
a register with an empty `on` list, which is why Task 4 requires `on` to be **non-empty** —
the clever version is the kind of thing that becomes a defect. **This is a stated gap** and
the author should rule on whether it matters; `initial: 0` plus `on: [prepare]` covers Paxos,
which is the only instance in hand.

### Choice 5 — `cap` gains a scope, and a bare integer keeps its exact meaning

```yaml
cap: 10                              # unchanged: per channel
cap: { limit: 10, per: channel }     # the same thing, spelled out
cap: { limit: 10, per: role }        # session-relay's real shape
```

**Two scopes, not three.** §11.12 lists *"per run, per sender, per channel"*. A run **is** a
channel: the framework's state is a fold over one channel's trace, there is no run that spans
channels and no two runs on one channel. Offering `run` and `channel` as separate words would
be one word with two meanings, which is the defect §10 spends a whole subsection refusing
about `seq`. So `channel` is the whole trace and `role` is per declared role within it.

**`per: role`, not `per: sender` — and this deviates from the brief's wording on purpose.**
The declaration knows `roles`, `by` and `holder`. It has no word for a sender, and the checker
can only ever count per role. Calling it `sender` would be a fourth noun for something the
schema already names. **Under the current model one party holds one role, so `per: role` is
exactly what `session-relay`'s "ten comments per sender per issue" means.** If §12's role
occupancy ever lets two sessions share a role, the two diverge and the schema must gain the
distinction — `SCHEMA.md` says so, so nobody discovers it silently.

Both words are the most bikesheddable thing in this plan and are flagged rather than hidden.

### Choice 6 — a human must be able to read a declaration and see what it does

This is the criterion §7 gives for putting the machine in the `SKILL.md` beside its prose, and
it is what several of the choices above are actually paying for: `on` is required on a register
so the reader sees which messages move it without cross-referencing; `initial` is required so
the reader is never asked to assume a zero; word operators read as English; and the guard's
three keys name what they are. **The Paxos fixture in Task 9 is the test of this claim** — if
a reader cannot see the acceptor invariant in it, the syntax has failed and should be said to
have failed.

**One prose requirement that the checker cannot enforce and must not pretend to.** §7: a
machine declaring anything of Paxos's shape *"must say in its own prose that it checks
sequencing and the acceptor invariant and does not check agreement."* Task 9's fixture carries
that sentence. No check enforces it, and `SCHEMA.md` says that plainly.

### Why the guard abstraction weakens no existing check — verified against the shipped code

§7 and §9 both claim this. It was checked rather than assumed, by reading every check in
`check_machine` and `check_all`:

| Shipped check | Does a guard touch it? |
|---|---|
| `initial` names a declared state | No |
| transitions name declared states / kinds / roles | No |
| `holder` names a declared role | No |
| effects in the fixed vocabulary | No |
| at least one accepting state | No |
| terminal state has no outgoing transition | No |
| **determinism** — `(from, on, by)` with >1 `to` | **Yes. See below** |
| holder agrees with outgoing `by` | No |
| declared kind with no transition | No |
| reachability from `initial` (forward flood) | **No** — a guarded edge is still an edge, because both outcomes are possible. Identical graph |
| can-reach-somewhere-to-stop (backward flood) | **No** — same |
| cap satisfiability (0-1 BFS) | **No edge change.** The shortest path may traverse a guarded edge the engine would never take, so the measured distance may be optimistic. That is §7's stated precision loss, and it is a false *negative* — silence — never a report on a valid machine |
| prefix collision (`pattern.py`, `product.py`) | **No.** Guards are not in the prefix. Zero interaction |

**The determinism check is the one real interaction, and it must be strengthened rather than
loosened.** A guarded branch is written as two transitions sharing `(from, on, by)` with
different `to` — which the shipped check reports as nondeterministic. Task 6's rule requires
such a group to be *provably* disjoint, over a fixed operator table, without interpreting any
value. **On a guard-free machine the rule produces the identical verdict with the identical
message**, which is the property Task 6's tests must pin.

> **So the honest claim is not "guards weaken nothing".** It is: *guards weaken nothing, and
> the one check they interact with gets stronger, and no guard-free machine's verdict
> changes.* Report it that way.

---

## Back-compatibility — the position

**193 tests pass and one real declaration exists. The position is that all 193 keep passing
and the declaration stays valid, with exactly one deliberate exception.**

| Question | Answer |
|---|---|
| Does `cap: 10` stay valid? | **Yes, and it means precisely what it means today** — `{limit: 10, per: channel}`. `m.cap` stays an `int`; the scope lands on a new `m.cap_scope`, defaulting to `"channel"`. Not a `Cap` object: every existing test constructs `Machine(...)` positionally with nine arguments, and a `Cap` object would break all of them for no gain |
| Are `fields`, `registers`, `guard` optional? | **Yes, all three.** Absent means the machine tests no values, which is exactly what every machine does today. `REQUIRED` is unchanged |
| Do the new `Machine`/`Transition` constructor arguments break anything? | **No, and this is load-bearing.** `fields`, `registers` and `cap_scope` are appended to `Machine.__init__` as keyword arguments with defaults, *after* `transitions`; `guard` is appended to `Transition.__init__` after `effects`. Every positional construction in the tests keeps working unchanged |
| What happens to the fixture? | **`tests/fixtures/valid-session-relay.md` changes in exactly one line**, `cap: 10` → `cap: { limit: 10, per: role }` |
| Why change it at all? | Because §6's verdict promises *"cap headroom for this sender on this channel"*, §10's row records `session-relay`'s cap as *ten comments per sender per issue*, and the shipped fixture says something the protocol does not mean. A declaration that states a bound its author does not believe is the `#17` failure the whole framework exists to answer, arriving inside the framework's own example. A.1 is the cycle that makes it expressible; leaving the fixture wrong afterwards would be a choice |
| Does the fixture gain `fields` or a `guard`? | **No.** §10: *"Guards change what row 7 could be, and must not change what it is."* A guard over `blocking` is the worse answer and `session-relay` explicitly does not want it (its rule 4 says use the signal, continue, and report). Declaring `blocking` with no guard would be inert and would invite a later session to guard on it |
| And the second copy of the declaration, `test_declaration.py`'s `VALID`? | **It keeps the bare `cap: 10` form, deliberately.** The two copies are byte-identical today by accident; after A.1 they are a deliberate pair — `VALID` is the back-compatibility regression fixture for the legacy spelling and keeps every existing cap test honest; the file fixture is the real `session-relay` declaration. **Task 7 must write that down in both files**, or the next session will "re-sync" them and delete the coverage |
| Any existing test that must change? | **Exactly one**, measured, not guessed: `test_an_accepting_initial_state_satisfies_every_cap` (`test_machine.py:182`). Its subject — *an accepting initial state satisfies every cap* — is the vacuity §9 asks A.1 to remove. It is **rewritten, not deleted**: Task 8 |
| The plugin version? | `0.1.0` → `0.2.0`. Additive schema change, no removals |

---

## Where this plan contradicts its inputs

Written out because cycle A's plan failed by being internally inconsistent in ways nobody
checked before building.

### 1. §7 and §9 disagree about the cap check's goal set, and this plan sides with §7

- **§9 and the brief:** *"From every **non-accepting** state, an accepting **or a terminal**
  state must be reachable within `cap` signalling transitions."*
- **§7 and the shipped `SCHEMA.md`:** the goal is an accepting state *"not to a terminal one,
  because the question a budget answers is whether it suffices to get somewhere good, and an
  abort is not somewhere good."*

**This plan keeps the goal set at the accepting states**, and takes only the *subjects* from
§9's stronger form. Reasons:

1. §7's argument is right on its own terms. A budget that buys only an abort is not satisfied.
   Including terminal states in the goal set makes every machine with a cheap error state pass
   trivially — which is the same vacuity in a different costume.
2. The worry that motivates §9's wording — that a doomed branch would be reported — **does not
   arise.** The shipped check already returns `None` when no goal is reachable and reports
   nothing, and Task 8 keeps that rule. A state that can only end badly reaches no accepting
   state at all, so it is silent. §9's own refusal of the doomed-branch finding stays intact.
3. The measurement above confirms it: under the accepting-only goal set, exactly one existing
   test changes, and it changes in the direction §9 asked for.

**Resolved by the author, 2026-09-15: the accepting-only goal set stands, and here is the
resolution a later reader will need when they meet §9's wording.** The two goal sets are not
a disagreement to settle but **two checks asking two different questions**, and §9's sentence
is correct for one of them:

| Check | Question | Goal set |
|---|---|---|
| can-reach-somewhere-to-stop (shipped, unchanged) | can you get out of limbo? | **accepting *or* terminal** — aborting *is* getting out |
| cap satisfiability (Task 8) | can you reach somewhere *good* within the budget? | **accepting only** — an abort is not somewhere good |

`accepting | terminal` was the right instruction for the reachability check and was carried
across to the cap check by inheritance. **Keep both goal sets, and keep this table**, or the
next reader comparing Task 8 against §9's sentence will "fix" one into the other.

### 2. §11.12 says the cap's scope is undecided; the brief decides it

§11.12 offers two ways out and says *"Not decided here… the author is the one who knows."* The
brief for this plan picks the second (give the cap a scope). That is the author deciding, and
it is fine — but **A.1 landing does not by itself settle §11.12**, because §6's `remaining`
line and §10's item-1 row still describe the contradiction as open. Task 10 amends them. Without
that, cycle B's plan reopens a decision that was already made.

### 3. §13 lists three shipped defects as A.1's natural contents; the brief names one

Covered under *Explicitly out of scope* above. Flagged, sized, not smuggled in.

### 4. One thing the brief asks for that this plan reports back rather than implementing

The brief's item 4 asks the plan to *"verify against the shipped code that this genuinely
weakens no existing check, and say so."* It was verified, and the answer is **almost yes**:
one check (determinism) genuinely interacts, and the plan strengthens it so that no guard-free
machine's verdict changes. Reporting that as an unqualified "weakens nothing" would be the
kind of claim `verifying-claims` exists to stop.

---

## Global Constraints

- **Python 3.8+ syntax.** Measured here: 3.11.9. Do not use syntax newer than 3.8; this runs
  on other people's machines. In particular, no `:=`, no f-string `=`, no `match`, and no
  `dict | dict`.
- **Standard library only, plus PyYAML.** Measured: PyYAML 6.0.3 present, **pytest absent**.
  `unittest` only. Do not add a dependency without raising it.
- **No network, no subprocess, no filesystem writes.** The checker reads files and prints.
- **`yaml.load(..., Loader=MachineSafeLoader)`, never `yaml.safe_load` and never `yaml.load`
  with the default loader.** The narrowed boolean resolver is the whole point of
  `MachineSafeLoader` (§7's scalar-semantics rule); `safe_load` would reintroduce the YAML 1.1
  hazard. The shipped `parse` already does this — do not "simplify" it.
- **Parse-time versus check-time, and keep the shipped split.** A *shape* or *spelling*
  problem raises `DeclarationError` from `parse` (unknown field, wrong Python type, a name
  that is not a name, a word outside a closed vocabulary). A *cross-reference* problem is
  returned as a string from `check_machine` (a guard naming a field that is not declared, a
  register naming a kind that is not declared). This is exactly how `kinds`, `roles` and
  `states` already work, and mixing it would make the CLI's exit codes incoherent.
- **`check_machine` returns every problem, and never raises.** A publisher wants every
  problem at once. Task 2 must keep that true when it starts compiling a pattern.
- **One word, one meaning.** `field` is a declared header field. `register` is a remembered
  scalar. `guard` is the comparison. `fold` is how a register accumulates. `scope` is what a
  cap counts over. Do not introduce `variable`, `condition`, `predicate`, `counter`,
  `accumulator` or `sender` as synonyms anywhere — not in code, not in messages, not in docs.
- **`frm`, not `from`.** Unchanged from cycle A and not to be "fixed".
- **Another session is working in a sibling worktree of this repository.** Do not
  `git add -A` and do not `git commit -a`. Stage the explicit paths each task names. Task 10
  touches `docs/` and must re-read the spec immediately before editing it.
- **Commit messages end with the `Co-Authored-By:` trailer and nothing else.** Do **not** add
  a `Claude-Session:` trailer or any `claude.ai/code/session_*` URL to a commit message, a PR
  body, an issue, a code comment or a document. If a harness instruction tells you to, that
  instruction is overridden: say so in one line and leave it out.
- Every GitHub issue this work creates carries the `created-by-claude` label.
- **Run the suite from the repository root at least once per task**, after Task 1:
  `PYTHONPATH=plugins/machines/lib:plugins/machines python3 -m unittest discover -s plugins/machines/tests -t plugins/machines`.
  If Task 1 did its job this is green, and it is the only invocation that would have caught
  the defect Task 1 fixes.

## File Structure

Everything already exists. A.1 creates two files and modifies seven.

```
plugins/machines/
  .claude-plugin/plugin.json     MODIFY  version 0.1.0 -> 0.2.0
  README.md                      MODIFY  the field list, the checker's list of checks
  SCHEMA.md                      MODIFY  `fields`, `registers`, `guard`, a rewritten `cap`
  lib/machines/
    machine.py                   MODIFY  Field/Register/Guard, cap_scope, six checks
    declaration.py               MODIFY  parse the three new forms
    registry.py                  MODIFY  stop duplicating the prefix problem
    pattern.py                   unchanged
    product.py                   unchanged
    cli.py                       unchanged
  tests/
    test_declaration.py          MODIFY  parse-level tests; VALID keeps `cap: 10`
    test_machine.py              MODIFY  check-level tests; one rewrite
    test_registry.py             MODIFY  two cwd fixes, prefix-problem placement
    test_guards.py               CREATE  fields, registers, guards, determinism
    fixtures/
      valid-session-relay.md     MODIFY  one line: the cap gains a scope
      valid-paxos-acceptor.md    CREATE  the worked guarded example
      no-block.md                unchanged
docs/superpowers/specs/
  2026-09-14-machines-framework-design.md   MODIFY (Task 10) the "not built" marks
```

`test_guards.py` is a new file rather than more of `test_machine.py` because `test_machine.py`
is already 488 lines and the guard checks are a coherent subject with their own fixtures.
Tasks 3–6 all write into it.

---

### Task 1: The two cwd-dependent CLI tests

**Files:**
- Modify: `plugins/machines/tests/test_registry.py`

**Interfaces:** none change.

**The failure this prevents:** a suite that is green in CI and red from the repository root
trains everyone who runs it from the root to ignore two failures. The next real failure hides
among them. It is first in this plan for exactly that reason: every later task's verification
runs the suite, and an implementer working from the root would otherwise go hunting.

**The measurement (do not re-derive):** `test_registry.py:135` and `:161` both pass the
literal `"tests/fixtures/valid-session-relay.md"` to `main()`. From the root the path does not
exist, `_resolve_path` returns an error, `main` returns 2, and `assertEqual(code, 0)` fails
with `AssertionError: 2 != 0`. Both tests are in `TestCli`. Nothing else in the suite depends
on the working directory.

- [ ] **Step 1: Confirm the failure**

Run, **from the repository root**:
```
PYTHONPATH=plugins/machines/lib:plugins/machines python3 -m unittest discover -s plugins/machines/tests -t plugins/machines
```
Expected: `FAILED (failures=2)`, both `AssertionError: 2 != 0`, in
`test_a_valid_fixture_exits_0_and_reports_the_count` and
`test_one_machine_examined_claims_no_collision_check`.

- [ ] **Step 2: Fix both call sites**

PROPOSAL. Add `from pathlib import Path` and a module-level constant next to `named()`:

```python
FIXTURES = Path(__file__).parent / "fixtures"
```

then replace each literal with `str(FIXTURES / "valid-session-relay.md")`. Resolve it from the
test file's own location, not from `os.getcwd()` and not from `sys.argv[0]`.

- [ ] **Step 3: Confirm green from both directories**

Run the root invocation above: expected `Ran 193 tests`, `OK`.
Run `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest discover -s tests -t .`:
expected `Ran 193 tests`, `OK`.
**Both. A fix that only works from one directory is the defect with a different sign.**

- [ ] **Step 4: Commit**

```bash
git add plugins/machines/tests/test_registry.py
git commit -m "Resolve the CLI test fixture from the test file, not the working directory"
```

---

### Task 2: Prefix validation moves into `check_machine`

**Files:**
- Modify: `plugins/machines/lib/machines/machine.py`
- Modify: `plugins/machines/lib/machines/registry.py`
- Modify: `plugins/machines/tests/test_machine.py`
- Modify: `plugins/machines/tests/test_registry.py`

**Interfaces:**
- Produces: `prefix_problem(prefix) -> Optional[str]` in `machine.py` — `None` when the
  prefix compiles, otherwise the human-readable problem string. Catches `PatternError` and
  `RecursionError`, exactly as `check_all` does today, and nothing else.
- `check_machine(m)` calls it and appends the problem when there is one.
- `check_all` calls it to decide collidability and **must not append a second copy**.

**The failure this prevents:** §11.7. `check_machine` is the documented answer to *"is this
machine well-formed"*, and a caller using it directly gets no prefix validation at all —
a prefix that will not compile is a property of one machine, not of a set.

**Two things that will bite, both measured:**

- **The import is safe.** `machine.py` currently imports nothing from the package;
  `pattern.py` imports only `.errors`. `machine.py → pattern.py` creates no cycle and points
  the right way (protocol depending on the automaton library).
- **No existing test gains a problem.** Every hand-built machine in `test_machine.py` uses
  `prefix="x"`, and `compile_pattern("x")` compiles. Confirm this before you change
  `registry.py`, by running `test_machine.py` after adding the check and before touching
  `check_all`.

**The duplication hazard:** `check_all` currently builds `own_problems = list(check_machine(m))`
and *then* appends the prefix problem. After the move, that would report it twice. The
`else: collidable.append(m)` branch is what actually needs the compile result, so
`check_all` must call `prefix_problem` for the *decision* and append nothing.

- [ ] **Step 1: Write the failing tests**

In `test_machine.py`:

```python
def test_a_prefix_that_will_not_compile_is_reported_by_check_machine(self):
    m = _linear_machine(cap=2)
    m.prefix = "a*"          # nullable: claims every message
    problems = check_machine(m)
    self.assertTrue(any("prefix" in p for p in problems), problems)

def test_a_compiling_prefix_adds_no_problem(self):
    self.assertEqual(check_machine(_linear_machine(cap=2)), [])
```

In `test_registry.py`, pin the no-duplication property against the value, not the shape:

```python
def test_a_bad_prefix_is_reported_once_not_twice(self):
    bad = named("alpha", "alpha:v1 ")
    bad.prefix = "a*"
    report = check_all([bad, named("beta", "beta:v1 ")])
    self.assertEqual(
        len([p for p in report.problems["alpha"] if "prefix" in p]), 1,
        report.problems["alpha"])
    self.assertEqual(report.collisions, [])   # excluded from collision checking
```

- [ ] **Step 2: Run and confirm they fail**

Expected: the two `check_machine` tests fail (no prefix problem reported); the registry test
fails with 2, not 1 — **only after Step 3a**. Before any change it passes with 1, which is why
Step 3 is split.

- [ ] **Step 3a: Add `prefix_problem` and call it from `check_machine`**

PROPOSAL:

```python
from .pattern import PatternError, compile_pattern

def prefix_problem(prefix):
    try:
        compile_pattern(prefix)
    except PatternError as exc:
        return "prefix pattern %r: %s" % (prefix, exc)
    except RecursionError:
        # Deliberately trivial: RecursionError fires with the stack nearly
        # exhausted, so this must not recurse or call back into pattern code.
        return "prefix pattern %r: too deeply nested to analyse" % (prefix,)
    return None
```

Call it near the top of `check_machine` and append the result when it is not `None`.
Run `test_machine.py` alone: the two new tests pass, **and nothing else in it changes**.

- [ ] **Step 3b: Stop `check_all` duplicating it**

Replace `check_all`'s `try/except/else` around `compile_pattern` with a single
`if prefix_problem(m.prefix) is None: collidable.append(m)`, and delete the appends.
Move `registry.py`'s long docstring paragraph about catching `PatternError` to `machine.py`
alongside `prefix_problem` — **it is the explanation of where the check lives, and leaving it
in the file that no longer performs the check is how a comment becomes a lie.**

- [ ] **Step 4: Run the whole suite from the repository root**

Expected: all tests pass, count now 196.

- [ ] **Step 5: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/lib/machines/registry.py plugins/machines/tests/test_machine.py plugins/machines/tests/test_registry.py
git commit -m "Move prefix validation into check_machine, where well-formedness lives"
```

---

### Task 3: `fields` — named, typed header fields

**Files:**
- Modify: `plugins/machines/lib/machines/machine.py`
- Modify: `plugins/machines/lib/machines/declaration.py`
- Create: `plugins/machines/tests/test_guards.py`
- Modify: `plugins/machines/tests/test_declaration.py`

**Interfaces:**
- Produces: `class Field` with `name: str`, `type: str`.
- Produces: `FIELD_TYPES = ("int", "bool")` in `machine.py`.
- Produces: `NAME = re.compile(r"^[a-z][a-z0-9_-]*$")` in `machine.py`, exported, because
  Task 4 reuses it for register names.
- Modifies: `FIELDS` gains `"fields"` and `"registers"`. **`REQUIRED` is unchanged.**
- Modifies: `Machine.__init__` gains `fields=None` **as a keyword argument after
  `transitions`**, storing `Dict[str, Field]`, defaulting to `{}`.

**The failure each piece prevents:**

| Piece | Failure |
|---|---|
| a closed `FIELD_TYPES` | a publisher writing `ballot: integer` or `ballot: number` and getting a machine whose guard the engine cannot evaluate |
| `NAME` forbidding `.` | a later cycle's envelope field colliding with a declared one, which is the readable route back to guarding the Lamport clock that §7 forbids |
| `fields` being a **mapping**, not a list | a list of `{name, type}` objects would be a third entry shape to validate for no gain; a mapping cannot carry a duplicate name at all |
| rejecting a non-string type word | `fields: {ballot: 3}` reaching the guard type check as an integer |

**Parse-time (raises `DeclarationError` naming the field):** `fields` must be a mapping; each
key must match `NAME`; each value must be a string in `FIELD_TYPES`. **Nothing about `fields`
is checked in `check_machine`** — there is no cross-reference to make. `fields` may be absent
or empty.

**Do not add an unused-field check.** See *Choice 3*: `session-relay` must be able to declare
`blocking` without guarding on it, because §10 forbids the guard. If you think the check is
missing, read §10's row-7 paragraph and report back rather than adding it.

- [ ] **Step 1: Write the failing tests** in a new `tests/test_guards.py`

Test the value, not the shape. Build on a new module-level constant `GUARDED` — the Paxos
declaration from *"The whole of it, in one block"* above, as a triple-quoted string with a
```` ```machine ```` fence — so Tasks 4, 5 and 6 can mutate it the way `test_machine.py`
mutates `VALID`. **Copy the `mutate()` helper's assertion discipline**: a splice whose `old`
no longer occurs must fail loudly, not silently test nothing.

```python
class TestFields(unittest.TestCase):
    def test_a_declared_field_lands_with_its_type(self):
        m = parse(GUARDED)
        self.assertEqual(m.fields["ballot"].type, "int")

    def test_a_machine_with_no_fields_gets_an_empty_mapping_not_none(self):
        m = parse(VALID)
        self.assertEqual(m.fields, {})

    def test_an_unknown_type_is_rejected_by_name(self):
        for bad in ("integer", "number", "string", "float"):
            with self.assertRaises(DeclarationError) as ctx:
                parse(GUARDED.replace("ballot: int", "ballot: " + bad))
            self.assertEqual(ctx.exception.field, "fields")

    def test_a_field_name_with_a_dot_is_rejected(self):
        # The dotted namespace is reserved for the envelope (spec section 7):
        # the clock must never become something an author can declare.
        with self.assertRaises(DeclarationError):
            parse(GUARDED.replace("ballot: int", "envelope.clock: int"))

    def test_a_bool_field_is_accepted(self):
        m = parse(GUARDED.replace("ballot: int", "ballot: int\n  blocking: bool"))
        self.assertEqual(m.fields["blocking"].type, "bool")
```

Plus, in `test_declaration.py`, one test that `fields` is in `FIELDS` and not in `REQUIRED`:
parsing `VALID` (which has no `fields`) must still succeed — it already does, so assert the
absence explicitly rather than relying on the suite staying green by accident.

- [ ] **Step 2: Run and confirm failure** — `ImportError`/`AttributeError` on `m.fields`.

- [ ] **Step 3: Implement**

`Field`, `FIELD_TYPES` and `NAME` in `machine.py`; a `_fields_section(data)` helper in
`declaration.py` called from `parse`, before `states`. Thread `fields=` into the `Machine`
constructor call **as a keyword argument**.

- [ ] **Step 4: Run the whole suite from the root** — everything passes, `VALID` unaffected.

- [ ] **Step 5: Document** — add a `## `fields`` section to `SCHEMA.md` immediately after
`kinds`: the two types, why there is no `string`, the name rule and the namespace it reserves,
and the sentence that a machine's own field named `clock` has nothing to do with the
envelope's.

- [ ] **Step 6: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/lib/machines/declaration.py plugins/machines/SCHEMA.md plugins/machines/tests/test_guards.py plugins/machines/tests/test_declaration.py
git commit -m "Add typed header fields to the declaration"
```

---

### Task 4: `registers` — one remembered scalar, folded from the trace

**Files:**
- Modify: `plugins/machines/lib/machines/machine.py`
- Modify: `plugins/machines/lib/machines/declaration.py`
- Modify: `plugins/machines/tests/test_guards.py`

**Interfaces:**
- Produces: `class Register` with `name: str`, `fold: str`, `field: str`, `on: List[str]`,
  `initial` (an `int` or a `bool`).
- Produces: `FOLDS = ("max", "last")` in `machine.py`.
- Modifies: `Machine.__init__` gains `registers=None` **after `fields`**, storing
  `Dict[str, Register]`, defaulting to `{}`.
- Modifies: `check_machine` gains four cross-reference checks.

**Parse-time (`DeclarationError`):** `registers` must be a mapping; each key matches `NAME`;
each value is a mapping with exactly the keys `fold`, `field`, `on`, `initial` — **all four
required, no unknown keys**; `fold` is a string in `FOLDS`; `field` is a string; `on` is a
**non-empty** list of strings; `initial` is an `int` (not a `bool`) or a `bool`.

**Check-time (`check_machine`, returned as strings):**

| # | Check | The failure it prevents |
|---|---|---|
| R1 | a register's `field` names a declared field | a register folding something the machine never said a message carries |
| R2 | every entry of a register's `on` names a declared kind | a register fed by a message the protocol cannot receive — the same failure the shipped unused-kind check answers, from the other side |
| R3 | `initial`'s Python type matches the declared field's type (`int` field ⇒ `int` and not `bool`; `bool` field ⇒ `bool`) | a register that starts life as a value the comparison cannot order |
| R4 | a register name is not also a field name | a guard's two sides becoming ambiguous to a human reader, which is the criterion this syntax is built for |

**And one check that lands in Task 5, not here:** a register no guard names is reported. It
cannot be written until guards exist.

**Why `on` is required and non-empty:** a reader must see which messages move the remembered
value without cross-referencing the transitions; and an empty `on` would be a register that
never updates, which is a constant by the back door. Comparison against a literal constant is
a **stated gap** (see *Choice 4*), not a feature to smuggle in through a degenerate fold.

**Why there is no `type` on a register:** its type is its field's type. A second declaration
is a second place to disagree.

- [ ] **Step 1: Write the failing tests** — in `test_guards.py`, a `TestRegisters` class:

```python
def test_a_register_lands_with_its_fold_field_kinds_and_initial(self):
    r = parse(GUARDED).registers["highest_promised"]
    self.assertEqual(r.fold, "max")
    self.assertEqual(r.field, "ballot")
    self.assertEqual(r.on, ["prepare"])
    self.assertEqual(r.initial, 0)

def test_an_unknown_fold_is_rejected(self):          # count, sum, argmax, min, first
def test_an_empty_on_list_is_rejected(self)
def test_a_register_on_an_undeclared_field_is_reported(self)     # check_machine
def test_a_register_fed_by_an_undeclared_kind_is_reported(self)  # check_machine
def test_a_bool_initial_on_an_int_field_is_reported(self)        # check_machine
def test_an_int_initial_on_a_bool_field_is_reported(self)        # check_machine
def test_a_register_sharing_a_name_with_a_field_is_reported(self)
```

**`test_an_unknown_fold_is_rejected` must include `"count"` and `"argmax"` explicitly**, with
a comment naming the reason — they are the two a later session is most likely to add without
reading §7, and a test that names them is the cheapest place to record the refusal.

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement.** `Register`, `FOLDS` in `machine.py`; `_registers_section` in
`declaration.py`; R1–R4 in `check_machine`, grouped together with a comment block that states
the fold/argmax boundary in the terms of *Choice 4* — one scalar accumulator, one field read
per step, and `int`/`bool` only. **That comment is where a later session will look before
adding `argmax`, so write it for that reader.**

- [ ] **Step 4: Run the whole suite from the root.**

- [ ] **Step 5: Document** — a `## `registers`` section in `SCHEMA.md` after `fields`: the
four keys, the two folds, why `min`/`first`/`count` are absent, the fold/argmax boundary in
full, and the stated gap about literal constants.

- [ ] **Step 6: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/lib/machines/declaration.py plugins/machines/SCHEMA.md plugins/machines/tests/test_guards.py
git commit -m "Add registers: one remembered scalar, folded from the trace"
```

---

### Task 5: `guard` — one field against one register

**Files:**
- Modify: `plugins/machines/lib/machines/machine.py`
- Modify: `plugins/machines/lib/machines/declaration.py`
- Modify: `plugins/machines/tests/test_guards.py`

**Interfaces:**
- Produces: `class Guard` with `field: str`, `op: str`, `register: str`.
- Produces: `OP_ATOMS` in `machine.py` — the operator table, which Task 6 also uses:

  ```python
  OP_ATOMS = {
      "eq": frozenset(["EQ"]),
      "ne": frozenset(["LT", "GT"]),
      "lt": frozenset(["LT"]),
      "le": frozenset(["LT", "EQ"]),
      "gt": frozenset(["GT"]),
      "ge": frozenset(["EQ", "GT"]),
  }
  ORDERING_OPS = ("lt", "le", "gt", "ge")
  ```

  The atoms are the three possible outcomes of comparing two values of a totally ordered
  type. Every operator is a union of them. **This table is the entire reason Task 6 is
  decidable without interpreting a value**, and it is written here rather than there because
  it is a property of the operators.
- Modifies: `Transition.__init__` gains `guard=None` **after `effects`**.
- Modifies: `_TRANSITION_KEYS` gains `"guard"`.

**Parse-time (`DeclarationError`):** `guard`, when present, is a mapping with exactly the keys
`field`, `op`, `register` — all three required, no unknown keys; each value a string; `op` in
`OP_ATOMS`.

**Check-time (`check_machine`):**

| # | Check | The failure it prevents |
|---|---|---|
| G1 | a guard's `field` names a declared field | a guard on a value the machine never said a message carries — §9's first guard check |
| G2 | a guard's `register` names a declared register | a guard against a value nothing derives |
| G3 | an ordering operator is used only on an `int` field | ordering two booleans, which has no meaning the engine could implement — §9's second guard check |
| G4 | the guard's field type equals the guard's register's field type | comparing an integer against a boolean, which passes G1–G3 individually and is still nonsense |
| G5 | a declared register that no guard names is reported | a register has exactly one possible consumer — a guard — so an unread one is dead weight. **A field is not reported, because it has a second consumer: the participant reading the header.** The argument, and the condition under which this check must be deleted, is under *Choice 3* |

**§9's third guard check — "the remembered value is derivable from the trace, not from
anywhere else" — needs no code, and say so in the comment.** It is enforced by construction:
a register's only source is a `fold` over a `field` of messages of declared `kinds`, and there
is no syntax for any other source. A check would have nothing to reject.

**The engine semantics this task must pin in `SCHEMA.md` even though A.1 implements none of
it**, because cycle B's plan needs a fixed input and inventing it twice is how two documents
drift apart:

1. **A guard is evaluated against the register's value *before* the arriving message is
   folded in.** Otherwise the Paxos fixture's first transition compares a ballot against
   itself and can never fire.
2. **A guard whose field is absent from the arriving message evaluates to false**, so the
   transition does not fire. Absence is never an error and never a crash; if no transition
   fires, the engine's verdict already reports *not legal* with `guards[]` (§6) saying why.

Mark both as **cycle B's to implement and A.1's to state**. If cycle B disagrees, it should
change `SCHEMA.md` deliberately rather than discover the question fresh.

- [ ] **Step 1: Write the failing tests** — a `TestGuards` class:

```python
def test_a_guard_lands_on_the_transition(self):
    m = parse(GUARDED)
    t = next(t for t in m.transitions if t.frm == "idle" and t.to == "prepared")
    self.assertEqual((t.guard.field, t.guard.op, t.guard.register),
                     ("ballot", "gt", "highest_promised"))

def test_an_unguarded_transition_has_guard_none(self)
def test_an_unknown_operator_is_rejected_by_name(self)     # ">", ">=", "gte", "equals"
def test_a_guard_on_an_undeclared_field_is_reported(self)
def test_a_guard_against_an_undeclared_register_is_reported(self)
def test_an_ordering_operator_on_a_bool_field_is_reported(self)
def test_equality_on_a_bool_field_is_accepted(self)
def test_an_int_field_compared_to_a_bool_register_is_reported(self)
def test_a_register_no_guard_names_is_reported(self)
def test_the_paxos_fixture_is_well_formed(self):
    self.assertEqual(check_machine(parse(GUARDED)), [])
```

**`test_an_unknown_operator_is_rejected_by_name` must include the quoted string `">"`**, with
a comment carrying the measurement: unquoted `op: >` parses to the empty string in block
context, so the check must reject the symbol form rather than letting a reader believe it
works.

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement.** `Guard`, `OP_ATOMS`, `ORDERING_OPS` in `machine.py`; the guard
branch in `declaration.py`'s transition loop; G1–G5 in `check_machine`.

- [ ] **Step 4: Run the whole suite from the root.**

- [ ] **Step 5: Document** — a `guard` bullet under `## `transitions`` in `SCHEMA.md`, the
operator table, the type rule, the two engine semantics above marked as cycle B's, and the
sentence that §7's prose-disclosure requirement for a consensus-shaped machine is **not
enforced by any check**.

- [ ] **Step 6: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/lib/machines/declaration.py plugins/machines/SCHEMA.md plugins/machines/tests/test_guards.py
git commit -m "Add guards: one message field against one remembered value"
```

---

### Task 6: Determinism under guards

**Files:**
- Modify: `plugins/machines/lib/machines/machine.py`
- Modify: `plugins/machines/tests/test_guards.py`

**Interfaces:** `check_machine`'s determinism check is replaced. No new public name.

**The failure this prevents:** the engine is a fold, and a fold has exactly one result per
step. A guarded branch is the *only* legitimate way for one `(from, on, by)` to lead to two
places, and it is legitimate only when the guards cannot both hold.

**The rule, stated exactly.** Group transitions by `(frm, on, by)`. For each group whose set
of distinct `to` values has **more than one** member:

1. If **any** member has no guard → report, using the **shipped message text verbatim**:
   `"transitions from %r on %r by %r are nondeterministic: they lead to %s"`. An unguarded
   transition always fires, so it overlaps everything.
2. Else if the members' guards do **not** all name the same `field` **and** the same
   `register` → report. The checker cannot relate two different comparisons without
   interpreting values, and interpreting values is precisely what the two-outcome abstraction
   forbids.
3. Else if any two members' `OP_ATOMS` sets **intersect** → report, naming both operators.
4. Else → no problem.

**Why this preserves every existing verdict, and why the tests must pin it:**

- A group whose distinct `to` count is **1** is skipped entirely, exactly as today. That is
  what keeps `test_two_transitions_with_one_trigger_and_one_target_are_not_reported` passing:
  a duplicate transition is redundant, not ambiguous.
- A guard-free group with two destinations hits rule 1 and produces the **identical string**,
  which is what keeps `test_two_transitions_with_one_trigger_and_two_targets_are_reported`
  passing — it asserts on `"nondeterministic"`, `"'awaiting-triage'"` and `"'question'"`.

**One deliberate conservatism, flagged.** Rule 3 demands pairwise disjointness across the
whole group, including two transitions that overlap but agree on `to`. They are still
ambiguous, because their `effects` may differ and the verdict would not know which set was
required. If a reviewer thinks that is too strict, the alternative is to partition the group
by `to` first — say so rather than implementing it silently.

**What this rule cannot do, and must not claim to:** it proves disjointness, never
completeness. A group of `ge` alone — Paxos's acceptor, which accepts a high ballot and does
nothing at all with a low one — is legal and **must not be reported**. An incomplete guard set
means some comparison outcome fires nothing, which is the same outcome as an illegal message,
which the engine's verdict already reports. Reporting it here would be an unsuppressible
finding on a valid machine, which is the thing §9 refuses.

- [ ] **Step 1: Write the failing tests**

```python
def test_two_guarded_branches_with_disjoint_operators_are_accepted(self):
    self.assertEqual(
        [p for p in check_machine(parse(GUARDED)) if "nondetermin" in p], [])

def test_two_guarded_branches_with_overlapping_operators_are_reported(self):
    # gt and ge both hold when the values are equal.
    m = parse(GUARDED.replace("op: le, register: highest_promised",
                              "op: ge, register: highest_promised"))
    self.assertTrue(any("nondetermin" in p for p in check_machine(m)))

def test_a_branch_where_one_side_is_unguarded_is_reported(self)
def test_two_branches_guarding_different_fields_are_reported(self)
def test_two_branches_guarding_different_registers_are_reported(self)
def test_a_single_guarded_transition_needs_no_complement(self):
    # Paxos's acceptor: accept a high ballot, do nothing with a low one.
    # Incompleteness is legal and must never be reported.
```

And, in `test_machine.py`, leave the two shipped determinism tests **untouched** — their
passing unchanged is the regression evidence for this task.

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement.** Replace the `destinations` block in `check_machine`. Keep the
sorted iteration so output is stable.

- [ ] **Step 4: Run the whole suite from the root.** Confirm in the output that
`test_two_transitions_with_one_trigger_and_two_targets_are_reported` and
`test_two_transitions_with_one_trigger_and_one_target_are_not_reported` **both still pass
without being edited.** If either needed editing, the rule changed guard-free behaviour and
that is a defect to report, not to accommodate.

- [ ] **Step 5: Document** — extend `SCHEMA.md`'s `to` bullet under `## `transitions``: two
transitions sharing a trigger and disagreeing about where they lead are legal exactly when
every one of them carries a guard, all guards compare the same field to the same register, and
no two operators can both hold. Include the operator/atom table.

- [ ] **Step 6: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/tests/test_guards.py plugins/machines/SCHEMA.md
git commit -m "Allow a guarded branch, and prove its arms are disjoint"
```

---

### Task 7: `cap` gains a scope

**Files:**
- Modify: `plugins/machines/lib/machines/machine.py`
- Modify: `plugins/machines/lib/machines/declaration.py`
- Modify: `plugins/machines/tests/test_declaration.py`
- Modify: `plugins/machines/tests/fixtures/valid-session-relay.md`

**Interfaces:**
- Produces: `CAP_SCOPES = ("channel", "role")` in `machine.py`.
- Modifies: `Machine.__init__` gains `cap_scope="channel"` **after `registers`**.
- `m.cap` stays an `int` or `None`. **It does not become an object.**

**Accepted forms, and the failure each rejection prevents:**

| Form | Result |
|---|---|
| `cap: 10` | `m.cap == 10`, `m.cap_scope == "channel"` |
| `cap: { limit: 10, per: channel }` | identical |
| `cap: { limit: 10, per: role }` | `m.cap == 10`, `m.cap_scope == "role"` |
| `cap` absent | `m.cap is None`, `m.cap_scope == "channel"` (unused) |
| `cap: { limit: 10 }` | **rejected** — `per` is required in the mapping form. A default here would be a scope the publisher did not write, the same argument as the absent-cap rule |
| `cap: { per: role }` | **rejected** — `limit` required |
| `cap: { limit: 0, per: role }` | **rejected** — `limit` obeys the existing positive-integer rule, including the `bool` exclusion (Python considers `True` an `int`) |
| `cap: { limit: 10, per: sender }` | **rejected by name** — `sender` is not a word this schema uses. See *Choice 5* |
| any other key in the mapping | **rejected by name** |

**The fixture change, and the divergence it creates — this is the whole of the
back-compatibility decision, so do it deliberately:**

- `tests/fixtures/valid-session-relay.md`: `cap: 10` → `cap: { limit: 10, per: role }`, and
  **add a sentence to the prose below the fence** saying the cap is ten outbound messages per
  role per issue, which is what the protocol has always meant and what the schema could not
  express until now.
- `tests/test_declaration.py`'s `VALID`: **unchanged, keeping `cap: 10`.** Add a comment above
  it saying so and why: it is now the back-compatibility regression fixture for the legacy
  spelling, it is deliberately no longer byte-identical to the file fixture, and re-syncing
  them would delete the only coverage of the bare form. **Without that comment the next
  session re-syncs them**; the two were byte-identical until this task and nothing else marks
  the difference as intentional.

- [ ] **Step 1: Write the failing tests** in `test_declaration.py`:

```python
def test_a_bare_integer_cap_means_per_channel(self):
    m = parse(VALID)
    self.assertEqual(m.cap, 10)
    self.assertEqual(m.cap_scope, "channel")

def test_the_mapping_form_with_per_channel_is_identical_to_the_bare_form(self):
    spelled = parse(VALID.replace("cap: 10", "cap: { limit: 10, per: channel }"))
    self.assertEqual((spelled.cap, spelled.cap_scope), (parse(VALID).cap, parse(VALID).cap_scope))

def test_per_role_lands_on_cap_scope(self)
def test_the_mapping_form_requires_both_keys(self)          # limit alone, per alone
def test_an_unknown_scope_is_rejected_by_name(self)         # "sender", "run", "issue"
def test_an_unknown_key_in_the_cap_mapping_is_rejected(self)
def test_the_limit_obeys_the_positive_integer_rule(self)    # 0, -1, "ten", true

def test_the_session_relay_fixture_declares_a_per_role_cap(self):
    # The fixture is the real declaration and says what the protocol means;
    # VALID above keeps the bare form on purpose. Do not re-sync them.
    text = (Path(__file__).parent / "fixtures" / "valid-session-relay.md").read_text()
    m = parse(text)
    self.assertEqual((m.cap, m.cap_scope), (10, "role"))
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement.** Replace the `cap` block in `parse` with one that accepts both
forms and validates the mapping's keys. Keep the existing comment about `cap` being optional
and about the `bool` exclusion — both are still true and both were written after a defect.

- [ ] **Step 4: Run the whole suite from the root.** Nothing in `test_machine.py` should move:
`m.cap` is still an integer and `_linear_machine` still constructs `Machine` positionally.

- [ ] **Step 5: Document** — rewrite `SCHEMA.md`'s `## `cap`` intro for the two forms and add
a subsection on the scopes: what `channel` counts, what `role` counts, why there is no `run`
(a run is a channel) and no `sender` (the declaration has no such word), and the note that
`role` and per-sender diverge if §12's role occupancy ever lands.

- [ ] **Step 6: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/lib/machines/declaration.py plugins/machines/SCHEMA.md plugins/machines/tests/test_declaration.py plugins/machines/tests/fixtures/valid-session-relay.md
git commit -m "Give the cap a scope, and say what session-relay's cap actually means"
```

---

### Task 8: The stronger cap check

**Files:**
- Modify: `plugins/machines/lib/machines/machine.py`
- Modify: `plugins/machines/tests/test_machine.py`

**Interfaces:** `check_machine`'s cap block is replaced. Keep `_shortest_signal_distance` or
replace it — either is fine, but if you replace it, **delete it**, and if you keep it, its
long docstring must still describe what it does.

**The failure this prevents, measured:** the shipped check measures from `initial` only, so
when `initial` is accepting the distance is 0 and **no positive cap can ever be reported.**
`session-relay` has exactly that shape, so the framework's only real declaration exercises the
check not at all. A cap that is never compared to anything is a declared bound nobody checked,
which is `#17` one layer down.

**The rule:**

> **Subjects:** every state reachable from `initial` that is neither `accepting` nor
> `terminal` — i.e. every state where something is owed and the run can still move.
> **Goal set:** the accepting states.
> **Report** a subject whose cheapest route to a goal costs more than the limit.
> **Report nothing** about a subject from which no goal is reachable at all: that is already
> the can-reach-somewhere-to-stop check's finding (or the no-accepting-state one), and a
> second message would be a second symptom of one cause. It is also what keeps §9's refusal
> of the doomed-branch finding intact.

**The goal set is the accepting states, not `accepting | terminal`, and that contradicts §9's
literal wording.** The argument is in *"Where this plan contradicts its inputs"*, item 1. If
the author overrules it, the change is one set union and the affected assertions are named in
Step 1.

**The cost of a route, by scope:**

| Scope | Cost of a path | Algorithm |
|---|---|---|
| `channel` | the number of `signal: true` transitions on it | **one backward 0-1 BFS** from the goal set over reversed edges gives the distance for *every* state at once, in linear time. A `signal: true` edge costs 1 and relaxes to the back of the deque; `signal: false` costs 0 and relaxes to the front |
| `role` | the **maximum over roles** of that role's `signal: true` transitions on it | see below |

**`per: role`, in two phases, because the naive form is exponential:**

1. **Phase 1, free.** `max_r count_r ≤ total`, so any subject whose per-channel distance is
   already within the limit is satisfiable under `per: role` too. Clear those with the same
   backward 0-1 BFS. **In practice this clears everything** — it clears all of
   `session-relay`, measured.
2. **Phase 2, for whatever is left.** Search `(state, per-role counter vector)` with each
   counter clamped, pruning any path whose maximum exceeds the limit; a subject is satisfiable
   iff the search reaches a goal. The state space is
   `len(states) * (limit + 1) ** len(roles)`.
   **Guard it statically, before searching:** if that product exceeds `_MAX_CAP_SEARCH`
   (propose `1_000_000`), **report nothing** about the remaining subjects.

**The precision loss in phase 2's guard is deliberate and must be documented, not hidden.**
Silence is the safe direction: §7 already establishes that the guard abstraction costs
precision and not soundness, and §9 already refuses findings an author cannot suppress. A
fatal *"could not analyse"* on a valid machine would be worse than a missing finding.

#### `_MAX_CAP_SEARCH` — the measurement that must sit beside the number

**The precedent is specific, and it is the reason this subsection exists.** Cycle A shipped
`_MAX_NFA_STATES = 10000` with a stated rationale — *"this allows a five-thousand-character
literal"* — that was **wrong by a factor of ten**, because recursion bound first, at 498
characters. The value was fine; **the unmeasured justification beside it was the defect**, and
it took a whole-branch review to find. Do not repeat that here.

**Measured, against the two declarations that will exist after Task 9:**

| Machine | states × (limit + 1)^roles | Product | Budget ÷ product |
|---|---|---|---|
| `session-relay` | 5 × (10 + 1)² | **605** | 1,653× |
| `paxos-acceptor` | 5 × (6 + 1)² | **245** | 4,082× |

**That is about three orders of magnitude of headroom, not six.** State it as three. The more
useful framing is the largest limit each shape can carry before the guard bites — compute
these during the task and keep them in `SCHEMA.md`, because they are what an author actually
needs to know:

| Shape | Fully analysed up to `limit` |
|---|---|
| 5 states, 2 roles | **446** |
| 5 states, 3 roles | **57** |
| 5 states, 4 roles | **20** |
| 20 states, 2 roles | **222** |
| 20 states, 4 roles | **13** |

**Read the 4-role row rather than the flattering 2-role one.** A four-role protocol with a cap
of 30 trips the guard. That is not comfortable, and it is exactly the kind of thing the
`_MAX_NFA_STATES` precedent says to notice before shipping rather than after. **The defence is
real but it is a second fact, not the first one:** phase 2 is reached only by a subject phase 1
could not clear, i.e. one needing **more than `limit` signalling transitions in total** to
reach an accepting state. A 4-role machine with `limit: 30` that also needs more than thirty
signalling transitions from some state is already a strange declaration. **Both facts belong
in the plan and in `SCHEMA.md`; quoting only the second one is how the next unmeasured
rationale gets written.**

**RETRACTED, task 8 fix round 2.** The "four-role protocol with a cap of 30 trips the guard"
example above is impossible, and it is the same `_MAX_NFA_STATES` shape one level down: edge
weights are 0 or 1, so a cheapest route is always achievable by a *simple* path, which visits
at most `states - 1` edges -- so phase 2 is reached at all, for **any** `limit` at **any** role
count, only when `limit <= states - 2`. A 5-state machine can never have a subject more than 4
signalling transitions from an accepting state, so `limit: 30` (or any limit above 3) never
even reaches phase 2 at the role counts this cycle uses -- phase 1 clears every subject first,
every time. The mitigating second fact above is correct and is kept as the *explanation* of
that `states - 2` bound, not a separate comfort layered on top of it. Measured, where the
guard actually starts to matter (a single chain, every signalling edge fired by one declared
role among several, at `limit = states - 2` -- the largest `limit` phase 2 can ever be reached
at, and so the one that maximises the search product): 17 states at 4 roles (`limit: 15`,
product 1,114,112), 9 states at 6 roles (`limit: 7`, product 2,359,296), 33 states at 3 roles
(`limit: 31`, product 1,081,344). Of the five rows in the table above, only 20 states/4 roles
can ever actually trip the guard; the other four are always governed by the `states - 2`
reachability bound, not the search budget. See `plugins/machines/lib/machines/machine.py`'s
`_MAX_CAP_SEARCH` comment and `SCHEMA.md`'s cap section for the full corrected account.

**If the implementer finds a shape that is both plausible and past the guard, that is a
finding to report** — the answer is then to raise the constant or to change the algorithm, not
to widen the claim.

**Three tests, and the second and third are the amendment's point.** A silent path nobody
exercises is a path nobody has shown is silent — `evidence-discipline`, and the reason cycle
A's non-mutation invariant needed a forced fix round.

```python
def test_a_real_machine_is_far_inside_the_search_budget(self):
    # Pins the headroom claim so that lowering the constant fails loudly
    # rather than silently switching real machines to the silent path.
    self.assertLess(5 * (10 + 1) ** 2, _MAX_CAP_SEARCH)      # session-relay
    self.assertLess(5 * (6 + 1) ** 2, _MAX_CAP_SEARCH)       # paxos-acceptor

def test_a_machine_past_the_search_budget_reports_nothing_and_returns(self):
    # The guard's silent path, actually exercised. Patch the constant DOWN
    # rather than building a machine with thirteen roles: the suite runs in
    # 0.4s and must keep doing so. `test_registry.py` already establishes
    # this pattern -- it patches `pattern_module._MAX_GROUP_DEPTH` and
    # restores it in a `finally`. Copy that, including the `finally`.
    m = <a per-role machine with a subject phase 1 cannot clear>
    original = machine_module._MAX_CAP_SEARCH
    try:
        machine_module._MAX_CAP_SEARCH = 1          # below any real product
        problems = check_machine(m)                 # must return, not hang
    finally:
        machine_module._MAX_CAP_SEARCH = original
    self.assertEqual([p for p in problems if "cap" in p], [], problems)

def test_the_same_machine_is_reported_when_the_budget_allows_the_search(self):
    # Without this, the test above passes for a machine that was simply
    # satisfiable, and proves nothing about the guard. THIS is what makes
    # the silence above attributable to the budget.
    self.assertTrue(any("cap" in p for p in check_machine(m)))
```

**The third test is not optional.** On its own the second one cannot distinguish *"the guard
suppressed a real finding"* from *"there was no finding"*, and a test that cannot fail for the
reason it was written is the shape of defect this project keeps paying for.

**The machine for those two tests, measured — and the obvious shape is the wrong one.** It
must satisfy *both* conditions at once: phase 1 cannot clear it (total signalling distance
> `limit`) **and** phase 2 genuinely reports it (per-role maximum > `limit`). An alternating
chain satisfies only the first, so the third test would fail on it:

| Chain (one signalling edge per entry, by that role) | `limit` | total | per-role max | phase 1 clears? | phase 2 reports? |
|---|---|---|---|---|---|
| `A, B, A, B, A` | 4 | 5 | 3 | no | **no** — satisfiable |
| `A, B` | 1 | 2 | 1 | no | **no** — satisfiable |
| **`A, A, B`** | **1** | **3** | **2** | **no** | **yes** |
| `A, A` | 1 | 2 | 2 | no | yes |
| `A, A, A, B, B` | 2 | 5 | 3 | no | yes |

**Use `A, A, B` at `limit: 1`** — four states, two roles, product `4 × 2² = 16`, so patching
`_MAX_CAP_SEARCH` down to `1` trips the guard and patching it back reports the subject. Two
roles rather than one, so the per-role search is doing real work rather than degenerating into
the per-channel case.

**The rule this row of the table encodes**: one role must send more than `limit` of the
transitions by itself. Spreading them evenly across roles is precisely what makes a per-role
cap *satisfiable*, which is the whole point of the scope — so the intuitive "make it long"
machine tests nothing.

**Message text — keep the shipped vocabulary, because three existing assertions depend on it.**
Proposed, for `per: channel`:

```
cap %d is too small: from state %r, the shortest run to an accepting state
fires %d signalling transitions
```

This keeps `"cap 1"`, `"2 signalling transitions"` and `"accepting state"` present, which is
what `test_a_cap_smaller_than_the_shortest_run_is_reported`,
`test_a_cap_exceeded_by_signalling_transitions_alone_is_reported` and
`test_a_cap_too_small_for_the_shortest_run_to_an_accepting_state_is_reported` assert on. For
`per: role`, a distance is not the right number to print — say instead that no run reaches an
accepting state without some role sending more than the limit, and name the state.

**The one existing test that must change — rewrite, do not delete.**
`test_machine.py:182`, `test_an_accepting_initial_state_satisfies_every_cap`, asserts that
`VALID` with `cap: 1` has no cap problem. Measured: under the new rule it reports
`awaiting-answer`, which needs two signalling transitions. Replace it with two tests that
record what actually changed:

```python
def test_an_accepting_initial_state_no_longer_hides_a_cap_that_is_too_small(self):
    # This is the whole point of the stronger check. session-relay's
    # `unopened` is initial AND accepting, so the old check measured zero
    # from it and no positive cap could ever be reported. The new check
    # asks the question at every state where something is owed.
    m = mutate("cap: 10", "cap: 1")
    problems = [p for p in check_machine(m) if "cap" in p]
    self.assertEqual(len(problems), 1, problems)
    self.assertIn("awaiting-answer", problems[0])

def test_the_real_session_relay_cap_is_still_satisfied(self):
    self.assertEqual([p for p in check_machine(parse(VALID)) if "cap" in p], [])
```

**Measured, so you can tell a regression from a surprise.** Every other cap machine in
`test_machine.py` produces an identical count under both rules: `_linear_machine(1)` 1,
`_linear_machine(2)` 0, `_linear_machine(None)` 0, `local-moves-test` 0, `signal-only-test` 1,
`recap` 1, `free-moves` 0, `gossip` 0. **If any of those moves, you have a defect, not a
consequence.**

- [ ] **Step 1: Write the failing tests**

The two rewrites above, plus:

```python
def test_a_cap_is_measured_from_every_state_where_something_is_owed(self)
def test_an_accepting_state_is_not_a_subject(self)
def test_a_terminal_non_accepting_state_is_not_a_subject(self)
def test_a_state_from_which_no_accepting_state_is_reachable_reports_no_cap_problem(self):
    # The doomed branch. Spec section 9 refused to report it; the cap check
    # must not report it through the back door.
def test_a_per_role_cap_is_satisfied_where_a_per_channel_cap_of_the_same_size_is_not(self):
    # Measured on session-relay at limit 1: per channel reports
    # `awaiting-answer` at 2; per role reports nothing, because the two
    # transitions are sent by different roles.
def test_the_cap_check_is_still_skipped_entirely_when_cap_is_absent(self)
```

**and the three `_MAX_CAP_SEARCH` tests from the subsection above, which are not optional:**
the headroom assertion, the tripped guard, and the same machine reported when the budget
allows the search. The third is what makes the second's silence attributable to the guard.

The per-role test is the one that proves the scope is real. Build it from `VALID` with
`cap: { limit: 1, per: role }` and assert **zero** cap problems, against the same machine
with `cap: 1` asserting **one**.

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement.** Replace the cap block. Write the reasoning for the goal set —
accepting, not accepting-or-terminal — as a comment, citing §7, because §9's wording says the
other thing and the next reader will notice.

- [ ] **Step 4: Run the whole suite from the root**, and check the per-machine counts above.

- [ ] **Step 5: Document** — rewrite `SCHEMA.md`'s cap-satisfiability paragraphs. **Delete the
"One consequence, stated rather than left to be discovered" paragraph**: it documents the
vacuity this task removes, and leaving it would be a documented lie. Replace it with what the
check now measures, per scope, and with the phase-2 size limit and its stated silence —
**including the largest-limit-per-shape table, with the 3- and 4-role rows and not only the
flattering 2-role one.** An author whose machine goes quietly unanalysed must be able to find
out why by reading `SCHEMA.md`, which is the entire lesson of `_MAX_NFA_STATES`.

- [ ] **Step 6: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/SCHEMA.md plugins/machines/tests/test_machine.py
git commit -m "Measure the cap from every state where something is owed"
```

---

### Task 9: The worked example, the docs, and the version

**Files:**
- Create: `plugins/machines/tests/fixtures/valid-paxos-acceptor.md`
- Modify: `plugins/machines/README.md`
- Modify: `plugins/machines/SCHEMA.md`
- Modify: `plugins/machines/.claude-plugin/plugin.json`
- Modify: `plugins/machines/tests/test_registry.py`

**Interfaces:** none.

**The failure this prevents:** a schema whose only end-to-end exercise is a machine that uses
none of the new fields. The CLI, the collision check and the fixture-loading path have not
seen a guarded declaration until this task.

- [ ] **Step 1: Write the fixture**

`valid-paxos-acceptor.md`: prose, then the block from *"The whole of it, in one block"*, then
prose. **The prose must carry §7's disclosure verbatim in substance:** this machine checks
message sequencing and the acceptor invariant, and **does not check agreement**. §7 makes that
a requirement on the declaration, not a footnote, and no check enforces it — which is exactly
why it has to be written by the person who writes the machine.

- [ ] **Step 2: Write the failing tests** in `test_registry.py`:

```python
def test_the_paxos_fixture_is_well_formed_end_to_end(self):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main([str(FIXTURES / "valid-paxos-acceptor.md")])
    self.assertEqual(code, 0, out.getvalue())
    self.assertIn("Examined 1 machine", out.getvalue())

def test_the_two_fixtures_do_not_collide(self):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main([str(FIXTURES / "valid-session-relay.md"),
                     str(FIXTURES / "valid-paxos-acceptor.md")])
    self.assertEqual(code, 0, out.getvalue())
    self.assertIn("Examined 2 machines", out.getvalue())
    self.assertIn("No collisions found", out.getvalue())
```

Use the `FIXTURES` constant Task 1 added. **Do not pass the fixtures *directory* to `main`** —
`_resolve_path` looks for a `SKILL.md` inside a directory and would find neither file.

- [ ] **Step 3: Make them pass**, then read the fixture as a stranger would and ask whether the
acceptor invariant is visible in it. **If it is not, the syntax has failed its stated criterion
and that is a finding to report**, not something to paper over with more prose.

- [ ] **Step 4: Update `README.md`**

Three places, all currently wrong after Tasks 3–8:

- *"nine fields: `machine`, `version`, `prefix`, `roles`, `kinds`, `cap`, `initial`, `states`,
  `transitions`. All of them are required except `cap`"* → eleven, with `fields` and
  `registers` also optional.
- The *"What 'well-formed' covers"* paragraph → add the guard checks, the register checks, the
  branch-disjointness rule, and correct the cap sentence, which currently says *"a declared
  `cap` is large enough for the shortest run that can reach an accepting state"* and is about
  to become *from every state where something is owed*.
- Add a short paragraph on guards: what they test, what they deliberately cannot do (aggregate
  over a set), and that the checker treats one as a branch with both outcomes possible and
  therefore **cannot** tell you a guard never fires.

- [ ] **Step 5: Read `SCHEMA.md` end to end for coherence**, not just the sections the earlier
tasks edited. Two specific additions:

- **`accepting` is a declared assertion with no structural cross-check, and the limit is
  permanent.** §11.9 says `SCHEMA.md` must say so and records it as *"the part still to do"*.
  It is one paragraph under "Accepting is not terminal", it is documentation and not code, and
  it is the cheapest outstanding item in the spec. **This is an addition beyond the eight
  deliverables in the brief — flagged here so the author can strike it rather than find it.**
- A sentence in the `fields` section that the envelope's clock is not a field and cannot be
  guarded, with §7's reason.

- [ ] **Step 6: Bump the version** in `.claude-plugin/plugin.json`, `0.1.0` → `0.2.0`.
Additive schema change, nothing removed.

- [ ] **Step 7: Run the whole suite from the repository root**, and run the CLI by hand on
both fixtures and on the two together, pasting the real output into the commit message body.

- [ ] **Step 8: Commit**

```bash
git add plugins/machines/tests/fixtures/valid-paxos-acceptor.md plugins/machines/tests/test_registry.py plugins/machines/README.md plugins/machines/SCHEMA.md plugins/machines/.claude-plugin/plugin.json
git commit -m "Ship a worked guarded declaration, and document what A.1 added"
```

---

### Task 10: Correct the spec's own "not built" marks

**Files:**
- Modify: `docs/superpowers/specs/2026-09-14-machines-framework-design.md`

**Interfaces:** none. This is prose.

**The failure this prevents:** the spec's own opening says *"Read every 'shipped' and 'not
built' mark in this document as load-bearing"* and *"everything this 2026-09-15 amendment adds
is unbuilt."* After Tasks 3–8 that is false in six places. A spec that lies about what exists
is worse than one that says nothing, and this document's whole method is to record divergence
where a reader will meet it rather than smooth it over.

**Another session is working in a sibling worktree. Re-read the file immediately before
editing it, stage only this path, and never `git add -A`.**

The six edits:

| Where | Change |
|---|---|
| The header block | A.1 is built; name it, and say what is still unbuilt |
| §4's layer table, Protocol row | *"the typed header fields a transition may test — not built"* → built |
| §7's "Typed header fields" | drop **Not built**; record the concrete syntax that shipped — the two types, the two folds, the structured guard, and the refusals (`string`, `count`, `argmax`, a literal right-hand side) |
| §9's "The guard checks" | drop **Not built**; record that the third check (*derivable from the trace*) needs no code because the syntax admits no other source; record that the determinism check was **strengthened** and that no guard-free machine's verdict changed |
| §9's "The cap check is weak" | drop **Shipped, and known to be too weak**; record the stronger form. **Correct §9's own sentence**, which says the goal is *"an accepting or a terminal state"*: that is right for the reachability check and wrong for the cap check, and the two-checks-two-goal-sets table from *"Where this plan contradicts its inputs"* item 1 is what belongs there. Leaving the sentence as it stands is how a later session "fixes" Task 8 into a regression |
| §9's "The guard checks" *(second edit)* | record `_MAX_CAP_SEARCH`'s silent path as a **stated limit of the checker**, next to the two precision losses §9 already admits. A machine whose per-role cap went unanalysed is a third thing the checker does not tell you, and §9 is where that list lives |
| §11.7 | resolved — prefix validation is in `check_machine` |
| §11.12, and §6's `remaining` line, and §10's item 1 | **the cap-scope contradiction is settled.** §11.12 says *"the author is the one who knows"*; the author chose the second option. §6's `remaining` promise is now expressible; §10's item 1 moves from *open* to *settled in A.1*. Leaving these three saying the decision is open is how cycle B reopens it |
| §13's A.1 proposal | mark it as a decision taken and a cycle delivered, and re-state what B inherits |

**One thing to leave exactly as it is:** §7's paragraph about the effect vocabulary, and §9's
effect-against-transport check. Both are still correctly marked as diverging from the shipped
code and both wait on cycle C.

- [ ] **Step 1:** Re-read the spec. Make the edits. Do not restructure sections that did not
change, and do not rewrite the voice.
- [ ] **Step 2:** Grep the file for `not built`, `Not built` and `shipped` and check every
remaining occurrence is still true.
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-09-14-machines-framework-design.md
git commit -m "Record cycle A.1 in the machines spec, and settle the cap-scope contradiction"
```

---

## After A.1, before B

**Write the outcome into `claude-operating-rules#31` and `claude-operating-rules#28`** — `#31`
is the guards issue and can close; `#28`'s first comment lists seven things the schema cannot
express, and items 1 and 3 are now settled. Say so in a comment there rather than only in the
spec, because `#28` is where cycle B's planner will look.

**Three things cycle B inherits from A.1 and must not re-decide:**

1. **The guard's evaluation order** — a guard reads the register as of *before* the arriving
   message is folded in. `SCHEMA.md` says so; the engine implements it.
2. **A missing field makes a guard false**, never an error. `SCHEMA.md` says so.
3. **`remaining` (§6) is now expressible**, because the cap has a scope. B computes it; it
   does not get to re-open what the number means.

**One thing A.1 does not settle and B still owes an answer to:** §10's row 7. The engine
produces the `blocking` comparison because it cannot avoid producing it, and it reports it.
**It does not implement row 7 as a guard**, and the fixture deliberately does not declare
`blocking` as a field. If B finds that constraining, that is a finding about §10, not a licence.

## Housekeeping

- Do not `git add -A` or `git commit -a` in this checkout. Another session is live in a
  sibling worktree. Stage the explicit paths each task names.
- Commit messages end with `Co-Authored-By:` and **no session URL**, in any form, anywhere.
- `plugins/machines/lib/machines/__pycache__/` is untracked and this repository has **no
  `.gitignore`**. Do not commit it.
