# `machines` Cycle B — The Engine: the Fold, the Verdict and the Outbound Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the engine. It folds a channel's recorded trace into a current state, remembers
each declared register, evaluates each guard against the arriving message for real, reports the
envelope's clock and what that clock says about order, computes the cap headroom the declared
scope asks for, and gates an outbound message before it is sent — emitting a **verdict** and
never an action. **No transport. No installer. No dispatcher. No schema change.**

**Architecture:** Three new modules, in one dependency direction, on top of the frozen cycle-A.1
schema. `envelope.py` holds the wire shape of a trace and refuses anything that is not channel
or protocol layer — it has no slot for a message body, which is how §4's third row becomes
structural rather than promised. `fold.py` is the pure part: trace in, `Fold` out, no I/O and no
clock of its own. `engine.py` is the presentation and the gate: it turns a `Fold` into a
`Verdict` and answers *"may I send this"*. Nothing in `machine.py`, `declaration.py`,
`registry.py`, `pattern.py` or `product.py` changes.

```
engine.py  ->  fold.py  ->  envelope.py  ->  (stdlib only)
                   \
                    `-> machine.py (read-only: Machine, Guard, OP_ATOMS, CAP_SCOPES)
```

**Tech Stack:** Python 3 (stdlib + PyYAML), `unittest`, bash entry point, GitHub Actions.
Nothing new. Trace fixtures are JSON, read with `json` from the stdlib.

**Spec:** `docs/superpowers/specs/2026-09-14-machines-framework-design.md`. Read, by heading:
§4 *"The three layers"* and both of its subsections (*"The envelope: order belongs to the
channel"*, *"Accepting is not terminal"*); §6 *"Four executables, all ours"* and its
subsections *"The engine emits a verdict, never an action"*, *"What the engine may read, which
is narrower than what the transport may do"* and *"Two performers"*; §7 *"Typed header fields,
and the guards that test them"*; §8 *"Verbs classify by what their result touches"* and *"A
transport declares whether its channel gives a total order"*; §9 *"The guard checks"* and *"The
cap check, strengthened in cycle A.1"*; §10 *"The walk run against the shipped schema"* and
*"`session-relay`'s `seq=` and the envelope's clock are different quantities"*; §11 items 6, 10,
12 and 13; §13's table and *"What B inherits"*. **The plan argues from the spec; both travel
together, and *"Where this plan contradicts its inputs"* below lists six places where the spec,
the ticket or the shipped code contradict themselves or each other.**

**Issues:** `claude-plugins#48` (cycle B — scope, four decisions, acceptance criteria),
`claude-plugins#32` (the clock; **the body is superseded by the third comment** — read both),
`claude-plugins#28` (the parent; **comment 1 is cycle B's input list and comment 4 withdraws
comment 1's "cycle B must add a second bound"**). All read 2026-10-26.

---

## Read this before you write a line

**All code in this plan is a PROPOSAL, not a requirement.** `writing-plans-and-dispatches`
rule 1 records fourteen real defects on one project, every one of them in code written into a
plan and transcribed faithfully because it arrived looking like requirements. Cycle A's plan
produced seven more. **The contracts below — names, signatures, types, and the failure each
thing must prevent — are the binding part. The bodies are a sketch.**

**Be sceptical. Report defects rather than fixing them silently.** If you conclude something
here is wrong, say so with evidence rather than implementing something you believe is
incorrect. This plan was written expecting to be contradicted. Read *"Where this plan
contradicts its inputs"* before you decide a task is wrong.

**Four things you must not do:**

1. **Do not change the schema.** Not `declaration.py`, not `machine.py`'s field lists, not
   `FOLDS`/`OP_ATOMS`/`FIELD_TYPES`/`CAP_SCOPES`/`ROLE_KINDS`, not `SCHEMA.md`'s field
   definitions. §13's whole argument for cycle A.1 was that B needs a schema that does not
   move. If you believe the engine needs a schema change, **stop and report it** — that is a
   finding about §13, not a licence.
2. **Do not name the clock `seq`.** `claude-plugins#48` decision 1, `#32`'s third comment and
   §10 all forbid it. The envelope key is `clock`.
3. **Do not add a second declared bound.** `claude-plugins#48` decision 4 and `#28`'s fourth
   comment. Task 7 adds an engine-side limit on one fold, reported in the verdict. No schema
   field, no new declaration word.
4. **Do not implement the effect vocabulary change or the transport declaration.** §7's open
   verb set and §9's effect-against-transport check are **cycle C**. The shipped
   `check_machine` hardcodes `label.add:<name>`, `label.remove:<name>` and `escalate`; leave it
   exactly as it is, and leave the verdict's effects unclassified (see *contradiction 1*).

---

## Global Constraints

- **Python 3 stdlib + PyYAML only.** No new dependency. Trace fixtures are read with `json`.
- **Run the suite from `plugins/machines`:**
  `PYTHONPATH=lib:. python3 -m unittest discover -s tests -t .`
  This is what `.github/workflows/machines-tests.yml:13` runs (with `-v`).
- **Baseline: 266 tests pass at `118db3d`.** If your starting count differs, stop and report it.
- **No test may lose.** Every one of the 266 keeps passing, unmutated, at every task boundary.
- **Every new test must be seen to fail under a mutation of the code it covers.** Each task
  carries that as an explicit step, naming the mutation. A test that has only ever passed is
  not evidence.
- **The engine emits a verdict, never an action.** Nothing in `envelope.py`, `fold.py` or
  `engine.py` may open a file other than a trace handed to it, run a subprocess, make a network
  call, read the clock, read the environment, or perform an effect. `escalate` is a word in a
  tuple, never a thing that happens.
- **The engine never branches on a world read.** Task 6 pins this with an invariance test, not
  with a comment.
- **No `claude.ai/code/session_*` URL** in a commit message, a code comment, a document, or
  anywhere else. Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
  and nothing after it.
- **Do not `git add -A` or `git commit -a`.** Other sessions may be live in sibling worktrees.
  Stage the explicit paths each task names. `plugins/machines/lib/machines/__pycache__/` is
  untracked and this repository has **no `.gitignore`** — never commit it.

---

## Review Focus

Five input classes the spec implies, that a reasonable person will hand the engine, and that no
task's main deliverable exercises on its own. Each line names the owning task, which carries the
test in its own step style.

1. **An empty trace.** A channel with nothing on it is the normal state of every protocol before
   it starts, and `session-relay`'s `unopened` is *accepting* precisely so that it can be
   described. The verdict for a zero-message trace must be the initial state's verdict, not a
   crash and not `legal: False`. → **Task 4**.
2. **A message naming a kind, role or state the machine does not declare.** The dispatcher that
   filters inbound traffic is cycle D; the engine is handed JSON by whoever calls it, today a
   test. An undeclared kind must be a named refusal, never a `KeyError`. → **Task 2**.
3. **A field value of the wrong Python type.** `{"ballot": true}` against an `int` register, or
   `{"ballot": "5"}`. Python compares `True < 5` happily and raises on `"5" < 5`, so one route
   silently computes a wrong guard and the other crashes. Both are wrong. → **Task 2**.
4. **A clock that is absent, not an integer, negative, or a bool.** The envelope is the one part
   of the wire that no declaration validates, so `envelope.py` is the only place this can be
   caught. → **Task 1**.
5. **Two senders occupying one role, and one sender acting as two roles.** §11.12 records that
   `per: role` and a real per-sender count coincide *only* while exactly one participant holds a
   role, and that every declaration in this cycle assumes it. The cap is counted per role; the
   clock is counted per sender. The engine must not quietly assume the two are the same key.
   → **Task 3** (clock) and **Task 5** (cap).

---

## What cycle B delivers

| | Deliverable | Task |
|---|---|---|
| 1 | the trace and envelope wire shape, with **no slot for a body** | 1 |
| 2 | the fold: state, registers, guard evaluation at run time, per-role spend | 2 |
| 3 | the envelope's clock, and the order verdict | 3 |
| 4 | the verdict | 4 |
| 5 | the outbound gate, and the stamped outbound clock | 5 |
| 6 | the rule that the engine never branches on a world read, pinned by an invariance test | 6 |
| 7 | the engine-side limit on one fold, reported in the verdict (§11.10, settled) | 7 |
| 8 | `SCHEMA.md` and `README.md`: what the engine does, and what it does not check | 8 |
| 9 | the version bump in both manifests, the manifest sync, the spec's "not built" marks | 9 |

### Explicitly out of scope — read this before you add something helpful

- **The installer, the registry and `/machines:install`** — cycle C (§13).
- **The transport declaration file format** — the verb set with typed arguments, the
  world-touching marks and the total-order statement. Cycle C reads and displays it (§13, §11.5).
  Cycle B needs **no transport at all**: a fixture is the JSON a transport would have returned.
- **The dispatcher and the `session-relay` backport** — cycle D (§13). In particular, **do not
  re-express `session-relay`** and do not touch `plugins/session-relay/`.
- **The §11.1 trigger measurement** (whether a hook sees an inbound cross-session message). It
  gates cycle D only. Do not register a hook.
- **The open effect vocabulary and §9's effect-against-transport check** — cycle C (§7, §9).
- **§10's row 7 as a guard.** The engine produces the `blocking` comparison because it cannot
  avoid producing it, and reports it; it is not a declared guard. Neither shipped fixture
  declares `blocking`, and cycle B must not add it (§10, A.1's handover note).
- **§11.10's "redefine the cap to count channel writes"** proposal. It is a checker and schema
  change and depends on §8's classification landing. Task 7 does the engine-side half only.

---

## Measurements — already taken, do not re-derive

Every row was produced by running a command in this worktree at `118db3d` on 2026-10-26, on
Python 3.13 (the `__pycache__` tags read `cpython-313`). The reference-fold rows were produced
by a throwaway script built **only** from the shipped declaration objects and `machine.OP_ATOMS`
— it is not an engine and it decided nothing; it measured what the shipped declarations imply.

### The baseline

| Fact | Command |
|---|---|
| **266 tests pass.** | `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest discover -s tests -t .` |
| `scripts/sync-manifests.py --check` is clean. | `python3 scripts/sync-manifests.py --check` |
| `claude plugin validate .` → **Validation passed** (with one pre-existing `tone-roulette` README warning that is not ours). | `claude plugin validate .` |
| `plugins/machines/.claude-plugin/plugin.json` version is **`0.3.0`**; the `machines` entry in `.claude-plugin/marketplace.json` is **`0.3.0`**. The marketplace `name` is `skomp-plugins`. | `cat`, `python3 -c "import json; …"` |
| The marketplace entry's `description` ends *"Cycle A: the schema and the checker only, no engine, no installer, no dispatcher."* — **false after this cycle.** | same |

### Nothing shipped reads a trace or a message. Stated either way, because it was asked.

`grep -rniE "\btrace\b|\bfold\b|envelope|clock|lamport|\bengine\b|verdict|remaining|world_read"
plugins/machines/lib/ --include=*.py` returns **46 hits, every one of them a comment or a
docstring** describing what cycle B will do. There is no executable line anywhere in
`plugins/machines/lib/` that reads a message, a trace, a clock or a register's run-time value.
`Register`'s docstring says it outright: *"This class only declares the fold; it does not
perform one."* The engine starts from zero.

### The closed vocabularies, read from the source

```
FOLDS        = ('max', 'last')
FIELD_TYPES  = ('int', 'bool')
ORDERING_OPS = ('lt', 'le', 'gt', 'ge')
CAP_SCOPES   = ('channel', 'role')
ROLE_KINDS   = ('repository', 'session')
NAME         = ^[a-z][a-z0-9_-]*$
OP_ATOMS     = {'eq': ['EQ'], 'ne': ['GT','LT'], 'lt': ['LT'], 'le': ['EQ','LT'],
                'gt': ['GT'], 'ge': ['EQ','GT']}
```

**`NAME` forbids `.`, so `envelope.clock` is not a declarable field or register name** —
verified: `NAME.match("envelope.clock")` is `None`. §7's *"do not let a later cycle expose the
clock as a guardable field"* is enforced by the parser today, not by discipline. The engine may
therefore use the dotted `envelope.*` namespace freely without ever colliding with a publisher's
name.

### Signatures and shapes, quoted from the source

```python
# machine.py
def check_machine(m) -> list[str]        # human-readable problems; [] means well-formed
def prefix_problem(prefix) -> str | None

class Field:      __init__(self, name, type)
class Register:   __init__(self, name, fold, field, on, initial)
class Guard:      __init__(self, field, op, register)
class State:      __init__(self, name, holder=None, terminal=False, accepting=False)
class Transition: __init__(self, frm, on, by, to, signal=False, effects=None, guard=None)
class Machine:    __init__(self, name, version, prefix, roles, kinds, cap,
                           initial, states, transitions, fields=None, registers=None,
                           cap_scope="channel", publisher=None)

# declaration.py
def parse(text) -> Machine               # raises DeclarationError
def extract_block(text) -> str

# registry.py
def label(m) -> str                      # "publisher/name", or bare "name"
def check_all(machines) -> Report
class Report:     __init__(self, examined, problems, collisions)
                  # examined: int; problems: dict[label -> list[str]]; collisions: sorted list of 2-tuples

# pattern.py
def compile_pattern(src) -> NFA          # NFA.accepts(text) -> bool; raises PatternError
```

**The container types a `Machine` actually carries, measured** (these bite: three of the four are
not what a reader guesses):

| Attribute | Runtime type | Note |
|---|---|---|
| `m.roles` | `dict[str, str]` | role name → one of `ROLE_KINDS` |
| `m.kinds` | **`set[str]`** | a `set`, not a list — unordered; sort before you print one |
| `m.states` | `dict[str, State]` | keyed by name |
| `m.transitions` | `list[Transition]` | **declaration order, preserved** |
| `m.fields` | `dict[str, Field]` | `{}` when absent, never `None` |
| `m.registers` | `dict[str, Register]` | `{}` when absent, never `None` |
| `m.cap` | `int | None` | `None` means *no bound*; there is no default |
| `m.cap_scope` | `str` | always set, `"channel"` even when `m.cap is None` |
| `Transition.frm` | `str` | the attribute is `frm`; the YAML key is `from` |

### Both shipped fixtures, exactly as they parse

`session-relay` — `check_machine` returns `[]`. `prefix='session-relay:v1 '`, `publisher=None`,
`cap=10`, `cap_scope='role'`, `initial='unopened'`, `fields={}`, `registers={}`,
`roles={'initiator': 'repository', 'responder': 'repository'}`,
`kinds={'triage','question','answer','conclusion','stalemate'}`.

| State | holder | accepting | terminal | exits `(on, by, to, guarded)` |
|---|---|---|---|---|
| `unopened` *(initial)* | initiator | **yes** | no | `(triage, initiator, awaiting-triage, no)` |
| `awaiting-triage` | responder | no | no | `(conclusion, responder, concluded, no)`, `(question, responder, awaiting-answer, no)`, `(stalemate, responder, stalled, no)` |
| `awaiting-answer` | initiator | no | no | `(answer, initiator, awaiting-triage, no)` |
| `concluded` | — | **yes** | **yes** | none |
| `stalled` | — | no | **yes** | none |

Effects, all on `signal: true` transitions: `triage` → `["label.add:session-relay:open"]`;
`conclusion` → `["label.remove:session-relay:open"]`; `stalemate` →
`["label.remove:session-relay:open", "label.add:session-relay:stalled", "escalate"]`. The other
two carry none. **Every one of the five transitions has `signal: true`.**

`paxos-acceptor` — `check_machine` returns `[]`. `prefix='paxos:v1 '`, `cap=6`,
`cap_scope='role'`, `initial='idle'`, `fields={'ballot': 'int'}`,
`registers={'highest_promised': ('max', 'ballot', ['prepare'], 0)}`,
`roles={'proposer': 'session', 'acceptor': 'session'}`.

| State | holder | accepting | terminal | exits `(on, by, to, guard)` |
|---|---|---|---|---|
| `idle` *(initial)* | proposer | **yes** | no | `(prepare, proposer, idle, ballot le highest_promised)`, `(prepare, proposer, prepared, ballot gt highest_promised)` |
| `prepared` | acceptor | no | no | `(promise, acceptor, promised, —)` |
| `promised` | proposer | **yes** | no | `(accept-request, proposer, idle, ballot ne highest_promised)`, `(accept-request, proposer, proposed, ballot eq highest_promised)` |
| `proposed` | acceptor | no | no | `(accepted, acceptor, decided, —)`, `(rejected, acceptor, idle, —)` |
| `decided` | — | **yes** | **yes** | none |

No transition in `paxos-acceptor` carries an effect. All seven have `signal: true`.

### The fold/guard ordering, measured — and it is load-bearing

`SCHEMA.md` already pins it (*"A guard is evaluated against the register's value before the
arriving message is folded into it"*). **It was measured independently, and the shipped paxos
fixture dies on its first message if an implementer gets it backwards.** Reference fold over the
trace `prepare(ballot=5) → promise → accept-request(ballot=5) → accepted`:

| Order | Result |
|---|---|
| **fold the arriving message first, then evaluate the guard** | message 1: `highest_promised` becomes 5, so `ballot gt highest_promised` is `5 > 5` = false and the `le` branch fires — **the run stays in `idle`**. Message 2, `promise`, finds no transition out of `idle`. **The protocol is dead on its first message.** |
| **evaluate the guard, then fold** (the pinned order) | `idle → prepared → promised → proposed → decided`, `highest_promised = 5` |

This is the single most expensive thing to get wrong in this cycle, and it fails *silently* in
the sense that nothing crashes — the machine simply never leaves its initial state.

### Reference verdict values for the two recorded traces

Four-message traces, one per fixture, with the clock assigned `1, 2, 3, 4` and two senders
alternating:

| | `session-relay` | `paxos-acceptor` |
|---|---|---|
| final state | `concluded` | `decided` |
| holder / accepting / terminal | `None` / `True` / `True` | `None` / `True` / `True` |
| exits from the final state | none | none |
| registers | `{}` | `{'highest_promised': 5}` |
| signalling transitions per role | `initiator: 2, responder: 2` | `proposer: 2, acceptor: 2` |
| headroom under `per: role` | `initiator: 8, responder: 8` | `proposer: 4, acceptor: 4` |
| highest clock per sender | `repo-a: 3, repo-b: 4` | `p1: 3, a1: 4` |
| order findings | none | none |

### The three clock cases the acceptance criteria name, measured

| Case | Reference result |
|---|---|
| same sender, clock does not increase (`a1` at 2, then `a1` at 2 again) | `duplicate` at index 2, message **refused**, state unchanged |
| two senders, equal clock (`p1@1` then `a1@1`) | `concurrent` at index 1, **neither message refused**; the fold continues and reaches `promised` |
| a guard that admits nothing | see below |

**Measured, and it changes how acceptance criterion 4 must be met:** `paxos-acceptor`'s two
guarded groups are **complete**, not merely disjoint. `gt`+`le` = `{GT}` ∪ `{LT,EQ}` = every
atom; `eq`+`ne` = `{EQ}` ∪ `{LT,GT}` = every atom. **So no `ballot` value whatsoever can be
refused by a guard on the shipped paxos fixture** — every integer fires exactly one branch. The
two routes that *do* produce a guard refusal, both measured:

1. **The arriving message omits the guard's field.** A `prepare` reaching `idle` with
   `fields: {}` makes both guards false (`SCHEMA.md`'s pinned semantic 2), **no transition
   fires**, and the message is refused. This works on the shipped fixture, unmodified.
2. **An incomplete guard set**, which `SCHEMA.md` says is legal: a lone `ge`-guarded transition
   refuses every `LT` outcome. Needs a machine built in the test file.

Task 2 uses both. Do not spend time looking for a ballot value that paxos refuses; there is none.

### Fold cost, measured — the anchor for Task 7's constant

Reference fold over a `session-relay` trace, timed with `time.perf_counter()`:

| Messages | Time |
|---|---|
| 1,001 | 0.006 s |
| 10,001 | 0.058 s |
| 100,001 | 0.597 s |

Roughly 6 µs per message, linear. **Do not publish a limit without a measurement beside it** —
`pattern.py`'s `_MAX_NFA_STATES` shipped with an unmeasured rationale that was wrong by a factor
of ten, and `machine.py`'s `_MAX_CAP_SEARCH` comment records that defect at length. Task 7
re-measures on the real `fold` and puts the number it measured in the comment.

### A defect in the shipped checker that the engine will meet

**Measured, 2026-10-26.** `check_machine`'s determinism check skips any trigger group whose
members all name one `to` (`if len(targets) <= 1: continue`). So this declaration returns `[]`
from `check_machine`:

```yaml
transitions:
  - { from: a, on: x, by: r, to: b, signal: true, effects: ["label.add:one"] }
  - { from: a, on: x, by: r, to: b, signal: true, effects: ["label.add:two"] }
```

Two candidate transitions, one trigger, **different required effects, and no declared way to
choose.** The same shape with *overlapping* guards (`ge` and `le`, which share the `EQ` atom)
also returns `[]`. `machine.py`'s own comment at rule 3 claims the pairwise operator check runs
*"including two members that happen to agree on `to`: they may still disagree on `effects`, and
the verdict has no way to know which set was required"* — **that comment describes behaviour the
code does not have**, because the `len(targets) <= 1` skip above it means rule 3 is never reached
for such a group. Task 2 handles it in the engine; Task 9 files it as a checker defect.

---

## The contract

### The trace, and why it has no slot for a body

```python
# envelope.py
ENVELOPE_KEYS = ("clock", "sender", "channel_order")   # channel layer
MESSAGE_KEYS  = ("kind", "by", "envelope", "fields", "world_reads")
TRACE_KEYS    = ("channel", "machine", "version", "total_order", "messages")

class WorldRead:  __init__(self, verb, result)         # result is opaque; nothing reads it
class Envelope:   __init__(self, clock, sender, channel_order=None)
class Message:    __init__(self, kind, by, envelope, fields=None, world_reads=())
class Trace:      __init__(self, channel, machine, version, total_order, messages)

def parse_trace(obj) -> Trace                          # raises TraceError
def load_trace(path) -> Trace                          # json.load, then parse_trace
class TraceError(Exception)                            # subclasses machines.errors.DeclarationError
```

**There is no `body` key, and `parse_trace` rejects an unknown key by name** — the same
discipline `declaration.parse` applies to the declaration. §4's third row says the framework
holds no content so it can never *appear* to verify content. In cycle B that stops being a
promise: there is nowhere to put content. A trace carrying `"body"` is a `TraceError`, and the
test for it is the structural statement of the non-goal.

`fields` is `dict[str, int | bool]`, and `parse_trace` enforces exactly that: a value that is
neither `int` nor `bool` is a `TraceError`, named. It cannot check a field against a *declaration*
— `parse_trace` has no `Machine` — so the per-machine type check belongs to the fold (Task 2).

`total_order` is a **required** boolean on the trace. §8 says the transport declares whether its
channel gives a total order and that *absent is not a default*; the transport declaration is
cycle C, so in cycle B the fixture carries the property the transport would have stated. See
*decision 3* for the author.

### `Fold` — the pure part

```python
# fold.py
def fold(m, trace, limit=MAX_FOLD_STEPS) -> Fold

class Fold:
    state:        str                        # the state after the fold
    registers:    dict[str, int | bool]      # every declared register, by name
    spent:        dict[str, int]             # declared role -> signalling transitions it fired
    clocks:       dict[str, int]             # sender -> highest clock accepted from that sender
    fired:        tuple[Step, ...]           # one per accepted message, in trace order
    refusals:     tuple[Refusal, ...]        # one per refused message, in trace order
    guards:       tuple[GuardReading, ...]   # EVERY guard evaluated, in evaluation order
    world_reads:  tuple[WorldReadRecord, ...]
    truncated:    bool                       # the fold hit `limit` (Task 7)
    steps:        int                        # messages consumed

class Step:            __init__(self, index, transition, frm, to, order)
class Refusal:         __init__(self, index, reason, state, detail=None)
class GuardReading:    __init__(self, index, transition_id, field, op, register,
                                field_value, register_value, atom, fired)
class WorldReadRecord: __init__(self, index, verb, result)
```

**`GuardReading` carries both compared values and the atom.** §6: *"`guards[]` is not debugging
output … a guard that fires must be as readable after the fact as an effect that fired."* A
reading with only `fired: False` would hide exactly what §6 says must be visible. `atom` is one
of `"LT"`, `"EQ"`, `"GT"`, or `None` when the field was absent from the message.

**`transition_id`** is the four-tuple `(frm, on, by, to)`. `machine.py` already uses all four for
its guard problem strings, with a recorded reason: three would make two distinct guards on one
trigger produce identical text. Use four here for the same reason.

**The failure `fold` must prevent:** computing a state that the trace does not justify. Four
specific ones, each with a named refusal reason rather than an exception:

| Reason | When |
|---|---|
| `"undeclared kind"` | `msg.kind not in m.kinds` |
| `"undeclared role"` | `msg.by not in m.roles` |
| `"field type"` | a field the machine declares, carried with the wrong Python type — `bool` where `int` is declared, or anything that is neither. **`bool` must be rejected against an `int` field explicitly**: Python's `True < 5` succeeds, so a silent wrong comparison is the default behaviour here, exactly as `declaration.py` already guards `cap: true` |
| `"no transition"` | nothing fires from the current state on `(kind, by)` under the guards |
| `"ambiguous"` | **more than one** transition fires — the shipped-checker defect above. The engine refuses and names both; it does not pick, and it does not union the effects |
| `"duplicate"` / `"out-of-order"` | the clock rules (Task 3) |

A refusal **does not advance the state and does not consume the clock**, and the fold continues
to the next message. A refused message is a fact about the trace, not the end of the fold.

### The clock and the order verdict

```python
ORDERS = ("ok", "duplicate", "out-of-order", "concurrent")   # §6's four, exactly
```

Evaluated in this order, per message, against the fold so far:

1. **Within one sender** (`msg.envelope.sender`): if `clock == clocks[sender]` → `duplicate`;
   if `clock < clocks[sender]` → `out-of-order`. **Both refuse.** (`#32`'s third comment:
   *"Within one sender: a value that does not increase is a duplicate or a message that arrives
   out of order. Refuse it."*)
2. **Across senders:** if any *other* sender's accepted high-water clock is `>= clock`, the
   message is **`concurrent`** with those messages. **Report it. Do not refuse it.** The verdict
   names the other senders. (`#32`'s third comment and `#48` decision 2.)
3. Otherwise `ok`.

`clocks` is keyed by **sender**, never by role. Review-focus item 5: one sender may act in two
roles and two senders may share a role, and the cap (per role) and the clock (per sender) must
not share a key.

**The outbound clock** is `max(every accepted clock on the channel) + 1` — §6: *"the engine
stamps the clock … computed from the trace it has just folded, so a sender cannot forget it and
cannot choose it."* It is `max` over **all** senders, not over the sending sender. Measured
consequence, from §10, which the implementer must not try to "fix": under strict two-party
alternation a sender's tenth message carries a clock of about 19. **That is correct, and it is
why the clock is not `seq` and why `remaining` exists.**

### `Verdict` — the centre of this cycle

```python
# engine.py
def verdict(m, trace, limit=MAX_FOLD_STEPS) -> Verdict
def gate(m, trace, outbound, limit=MAX_FOLD_STEPS) -> Verdict

class Verdict:
    legal:        bool                       # §6 "legal?"
    reason:       str | None                 # None iff legal; the refusal, in words
    state:        str                        # §6: the fold's result
    holder:       str | None                 # §6 "holder" — which role acts next; None at a terminal state
    accepting:    bool                       # §4: nothing further is required
    terminal:     bool                       # §4: nothing further is possible
    may_send:     tuple[Offer, ...]          # §6 "may_send"
    remaining:    Remaining | None           # §6 "remaining"; None iff m.cap is None
    effects:      tuple[str, ...]            # see contradiction 1 — ONE list, unclassified
    order:        str                        # §6 "order?" — one of ORDERS
    concurrent_with: tuple[str, ...]         # senders this message is concurrent with
    guards:       tuple[GuardReading, ...]   # §6 "guards[]" — every guard evaluated
    world_reads:  tuple[WorldReadRecord, ...]# §6 "world_reads[]"
    outbound_clock: int                      # the clock the engine would stamp on the next message
    refusals:     tuple[Refusal, ...]        # every message the fold refused, with its reason
    truncated:    bool                       # the fold hit its limit (Task 7)

class Offer:     __init__(self, kind, by, to, guard)   # guard: machine.Guard | None
class Remaining: __init__(self, limit, scope, spent, headroom)
```

**`Remaining`, named field by field**, because this is where §6 and §7 used to contradict each
other (§11.12) and the plan must not reopen it:

- `limit: int` — `m.cap`.
- `scope: str` — `m.cap_scope`, one of `CAP_SCOPES`.
- `spent: dict[str, int]` — **every declared role**, mapping to the signalling transitions that
  role fired in this fold. `0` for a role that has not acted. Scope-independent raw data.
- `headroom: dict[str, int]` — **every declared role**, mapping to how many further outbound
  messages that role may send. Under `per: role`, `limit - spent[role]`. Under `per: channel`,
  `limit - sum(spent.values())` **for every role**, because the budget is shared — the numbers
  are equal on purpose, and `SCHEMA.md` must say so, or a reader will add them up.

One type in both scopes, no sentinel key, and the gate reads the same line either way:
`headroom[sender_role] > 0`. See *decision 1* for the author.

**`may_send` includes guarded offers, with the guard named and unevaluated.** The engine cannot
know whether a guard will pass before a message exists, and saying so is honest; claiming an
offer is available when a guard will refuse it would be worse than silence. Measured values are
in the fixture tables above — e.g. from `paxos-acceptor`'s `idle`, `may_send` is two offers on
`prepare` by `proposer`, one guarded `gt` and one guarded `le`.

**`effects` is required of something else, performed by nothing here.** §6: *"The engine performs
neither. It requires, and something else performs."* The tuple is the effects of the transition
that `gate` would fire, or of the last transition the fold fired, and it is **data**.

---

## File Structure

```
plugins/machines/
  lib/machines/
    envelope.py                    CREATE  the wire shape; Trace/Message/Envelope/WorldRead,
                                           parse_trace, load_trace, TraceError. No body slot.
    fold.py                        CREATE  fold(); Fold/Step/Refusal/GuardReading/
                                           WorldReadRecord; ORDERS; MAX_FOLD_STEPS
    engine.py                      CREATE  verdict(), gate(); Verdict/Offer/Remaining
    machine.py                     UNCHANGED
    declaration.py                 UNCHANGED
    registry.py                    UNCHANGED
    pattern.py, product.py         UNCHANGED
    errors.py                      UNCHANGED (TraceError subclasses DeclarationError from here)
    cli.py                         UNCHANGED  (no CLI for the engine this cycle — see decision 5)
  tests/
    test_envelope.py               CREATE  Task 1
    test_fold.py                   CREATE  Tasks 2, 6, 7
    test_clock.py                  CREATE  Task 3
    test_engine.py                 CREATE  Tasks 4, 5
    fixtures/trace-session-relay.json   CREATE  Task 1
    fixtures/trace-paxos-acceptor.json  CREATE  Task 1
  SCHEMA.md                        MODIFY  Task 8
  README.md                        MODIFY  Task 8
  .claude-plugin/plugin.json       MODIFY  Task 9  version 0.3.0 -> 0.4.0
  .claude-plugin/plugin.json (codex)       Task 9  written by scripts/sync-manifests.py
.claude-plugin/marketplace.json    MODIFY  Task 9  machines entry 0.3.0 -> 0.4.0, description
.agents/plugins/marketplace.json           Task 9  generated
.github/plugin/marketplace.json            Task 9  generated
docs/superpowers/specs/2026-09-14-machines-framework-design.md  MODIFY  Task 9
```

**Test conventions to copy, measured from the shipped suite:**

- Tests import as `from machines.fold import fold` and `from tests.test_declaration import VALID`;
  the suite runs from `plugins/machines` with `PYTHONPATH=lib:.`.
- `test_machine.py`'s `mutate(old, new)` **asserts the splice landed** before replacing, because a
  `str.replace` whose `old` stopped occurring silently tests the known-good value instead. Copy
  that discipline for any new declaration-text helper.
- `test_registry.py` builds fixture paths from a `FIXTURES` constant. Reuse the pattern; do not
  pass the fixtures *directory* to anything.

---

## Tasks

Each task is dispatchable to a fresh agent that has not read this conversation. Each one ends
with an independently testable deliverable, a whole-suite run, and a commit.

**Every dispatch must carry these two clauses:** *"All code in this plan is a proposal, not a
requirement — be sceptical, and report defects rather than fixing them silently."* and *"If you
conclude one of these findings is wrong, say so with evidence rather than implementing something
you believe is incorrect."*

---

### Task 1: The trace and the envelope — a wire shape with nowhere to put content

**Files:**
- Create: `plugins/machines/lib/machines/envelope.py`
- Create: `plugins/machines/tests/test_envelope.py`
- Create: `plugins/machines/tests/fixtures/trace-session-relay.json`
- Create: `plugins/machines/tests/fixtures/trace-paxos-acceptor.json`

**Interfaces:**
- Produces: `TraceError`, `WorldRead`, `Envelope`, `Message`, `Trace`, `parse_trace(obj) -> Trace`,
  `load_trace(path) -> Trace`, and the three key tuples `TRACE_KEYS`, `MESSAGE_KEYS`,
  `ENVELOPE_KEYS`. Exact attribute names as in *The contract*, above.
- Consumes: `machines.errors.DeclarationError` (as `TraceError`'s base). **Nothing else** —
  `envelope.py` must not import `machine.py`, because a trace is a channel-layer fact and knows
  nothing about any declaration.

**The failure this prevents:** two of them. First, a trace with a slot for a message body, which
would let a later cycle read content and make §4's third row a promise instead of a structure.
Second, an envelope that no validation touches: the declaration validates every protocol field,
and the envelope is the one part of the wire that no declaration describes, so `parse_trace` is
the only place a malformed clock can be caught (review-focus item 4).

**The fixture shape (PROPOSAL — the key names are the contract, the values are a sketch):**

```json
{
  "channel": "https://github.com/skomp/example/issues/1",
  "machine": "session-relay",
  "version": "v1",
  "total_order": true,
  "messages": [
    { "kind": "triage", "by": "initiator",
      "envelope": { "clock": 1, "sender": "repo-a", "channel_order": 101 },
      "fields": {}, "world_reads": [] }
  ]
}
```

Build `trace-session-relay.json` as the four-message trace in *Measurements* —
`triage/initiator/repo-a@1`, `question/responder/repo-b@2`, `answer/initiator/repo-a@3`,
`conclusion/responder/repo-b@4` — and `trace-paxos-acceptor.json` as
`prepare/proposer/p1@1 {ballot: 5}`, `promise/acceptor/a1@2`,
`accept-request/proposer/p1@3 {ballot: 5}`, `accepted/acceptor/a1@4`.

- [ ] **Step 1: Write the failing tests** in `test_envelope.py`.

Name them for the input, not the shape. At minimum:

```python
def test_a_message_carrying_a_body_is_refused_by_name(self):
    with self.assertRaises(TraceError) as caught:
        parse_trace(_one_message(body="hello"))
    self.assertIn("body", str(caught.exception))

def test_an_absent_clock_is_refused(self): ...
def test_a_clock_that_is_a_bool_is_refused(self):      # True is an int in Python
def test_a_clock_that_is_a_string_is_refused(self): ...
def test_a_negative_clock_is_refused(self): ...
def test_an_absent_sender_is_refused(self): ...
def test_an_absent_total_order_is_refused(self):       # §8: absent is not a default
    ...
def test_a_field_value_that_is_a_string_is_refused(self): ...
def test_a_field_value_may_be_an_int_or_a_bool(self): ...
def test_both_shipped_trace_fixtures_load(self):
    for name in ("trace-session-relay.json", "trace-paxos-acceptor.json"):
        trace = load_trace(FIXTURES / name)
        self.assertEqual(len(trace.messages), 4)
        self.assertEqual([msg.envelope.clock for msg in trace.messages], [1, 2, 3, 4])
```

- [ ] **Step 2: Run them and see them fail.**

Run: `PYTHONPATH=lib:. python3 -m unittest tests.test_envelope -v`
Expected: every test errors with `ModuleNotFoundError: No module named 'machines.envelope'`.

- [ ] **Step 3: Implement `envelope.py`.**

Validate by rejecting unknown keys by name, the way `declaration._reject_unknown` does. `clock`
must be an `int`, must not be a `bool`, and must be `>= 1`. Reject a `bool` explicitly:
`isinstance(True, int)` is `True`, which is the same trap `declaration._require_positive_cap`
already guards. `sender` is a non-empty string. `world_reads` entries are
`{"verb": str, "result": <anything>}` — **`result` is opaque and nothing validates it**, which
is the point: Task 6 proves nothing reads it.

- [ ] **Step 4: Run the tests and see them pass.** Then run the whole suite.

Run: `PYTHONPATH=lib:. python3 -m unittest discover -s tests -t .`
Expected: 266 + the new tests, all passing.

- [ ] **Step 5: See the body test fail under a mutation.**

Delete the unknown-key rejection from `parse_trace`'s message branch. Run
`tests.test_envelope`. Expected: `test_a_message_carrying_a_body_is_refused_by_name` **fails**.
Restore the line, re-run, confirm green. Record the mutation and the failure in the commit body.

- [ ] **Step 6: Commit.**

```bash
git add plugins/machines/lib/machines/envelope.py plugins/machines/tests/test_envelope.py plugins/machines/tests/fixtures/trace-session-relay.json plugins/machines/tests/fixtures/trace-paxos-acceptor.json
git commit -m "machines: the trace wire shape, with no slot for a message body"
```

---

### Task 2: The fold — state, registers, and guard evaluation at run time

**Files:**
- Create: `plugins/machines/lib/machines/fold.py`
- Create: `plugins/machines/tests/test_fold.py`

**Interfaces:**
- Consumes: Task 1's `Trace`, `Message`, `Envelope`; `machine.Machine`, `machine.Guard`,
  `machine.OP_ATOMS`; `declaration.parse` (in tests only, to load a fixture declaration).
- Produces: `fold(m, trace, limit=MAX_FOLD_STEPS) -> Fold`, and `Fold`, `Step`, `Refusal`,
  `GuardReading`, `WorldReadRecord`, `MAX_FOLD_STEPS`. Exact attributes as in *The contract*.
  Task 3 extends `fold` with the clock; Task 4 reads `Fold` and nothing else.

**The failure this prevents:** a state the trace does not justify — and, specifically, the one
measured above: evaluating a guard *after* folding the arriving message kills `paxos-acceptor` on
its first message, silently, with nothing raised.

**Three semantics this task must implement and must not re-decide.** `SCHEMA.md` pins the first
two in advance (see its `guard` bullet, *"Two engine semantics cycle B implements"*), and the
third is this plan's answer to the measured checker defect:

1. **A guard reads the register as of before the arriving message is folded in.** Measured, with
   the consequence, in *Measurements*.
2. **A guard whose field is absent from the arriving message is false.** Absence is never an
   error and never a crash. The transition does not fire; if nothing else fires, the message is
   refused with reason `"no transition"`.
3. **More than one transition firing is a refusal, not a choice.** `check_machine` passes a group
   of transitions that share all four of `(frm, on, by, to)` and differ only in `effects` (see
   *Measurements*), so the engine genuinely meets this. Refuse with reason `"ambiguous"`, naming
   every transition that fired. **Do not pick the first, and do not union the effects** — §6
   requires a reader to be able to tell what the protocol demanded, and a union demands something
   no declaration says. See *decision 4*.

**Transition order:** `m.transitions` is a `list` in declaration order (measured). Evaluate
candidates in that order for a stable `guards` sequence, but **do not stop at the first match** —
rule 3 needs to know whether a second one fires.

- [ ] **Step 1: Write the failing tests** in `test_fold.py`.

The two fixture folds — these are the acceptance criteria that name the fixtures by path:

```python
def test_the_session_relay_fixture_folds_to_concluded(self):
    m = parse((FIXTURES / "valid-session-relay.md").read_text())
    f = fold(m, load_trace(FIXTURES / "trace-session-relay.json"))
    self.assertEqual(f.state, "concluded")
    self.assertEqual(f.refusals, ())
    self.assertEqual(f.spent, {"initiator": 2, "responder": 2})

def test_the_paxos_fixture_folds_to_decided_and_remembers_the_ballot(self):
    m = parse((FIXTURES / "valid-paxos-acceptor.md").read_text())
    f = fold(m, load_trace(FIXTURES / "trace-paxos-acceptor.json"))
    self.assertEqual(f.state, "decided")
    self.assertEqual(f.registers, {"highest_promised": 5})
    self.assertEqual(f.spent, {"proposer": 2, "acceptor": 2})
```

The ordering test — **assert the value, not the shape**, and assert the state the wrong order
produces, so a later "simplification" cannot pass it:

```python
def test_a_guard_reads_the_register_before_the_arriving_message_is_folded_in(self):
    m = parse((FIXTURES / "valid-paxos-acceptor.md").read_text())
    f = fold(m, _trace([_msg("prepare", "proposer", "p1", 1, {"ballot": 5})]))
    self.assertEqual(f.state, "prepared")       # NOT "idle": folding first gives 5 > 5 == False
    self.assertEqual(f.registers, {"highest_promised": 5})
    reading = next(g for g in f.guards if g.op == "gt")
    self.assertEqual((reading.field_value, reading.register_value, reading.atom, reading.fired),
                     (5, 0, "GT", True))
```

Guard refusal, by both measured routes — acceptance criterion 4:

```python
def test_a_prepare_without_its_ballot_field_is_refused_because_both_guards_are_false(self):
    m = parse((FIXTURES / "valid-paxos-acceptor.md").read_text())
    f = fold(m, _trace([_msg("prepare", "proposer", "p1", 1, {})]))
    self.assertEqual(f.state, "idle")           # unchanged
    self.assertEqual([r.reason for r in f.refusals], ["no transition"])
    self.assertEqual([g.fired for g in f.guards], [False, False])
    self.assertEqual([g.atom for g in f.guards], [None, None])

def test_an_incomplete_guard_set_refuses_the_outcome_it_omits(self):
    m = _ge_only_machine()                      # one transition, guard: field ge register
    f = fold(m, _trace([_msg("step", "r", "s1", 1, {"n": 3})]))   # register initial 5 -> LT
    self.assertEqual([r.reason for r in f.refusals], ["no transition"])
```

The remaining refusals, review-focus items 2 and 3:

```python
def test_an_undeclared_kind_is_refused_by_name_not_a_key_error(self): ...
def test_an_undeclared_role_is_refused_by_name(self): ...
def test_a_message_whose_by_is_not_the_states_holder_fires_nothing(self): ...
def test_a_bool_in_an_int_field_is_refused_rather_than_compared(self):
    # Python's True < 5 succeeds, so the default behaviour here is a silent wrong guard.
def test_two_transitions_that_differ_only_in_effects_are_refused_as_ambiguous(self):
    # check_machine returns [] for this machine -- measured. The engine is what catches it.
```

Register folding, both folds:

```python
def test_max_keeps_the_highest_value_seen_and_last_keeps_the_most_recent(self): ...
def test_a_register_is_untouched_by_a_kind_not_in_its_on_list(self): ...
def test_a_register_holds_its_declared_initial_before_any_matching_message(self): ...
def test_a_register_whose_field_is_absent_from_a_matching_message_is_untouched(self): ...
```

- [ ] **Step 2: Run them and see them fail.**

Run: `PYTHONPATH=lib:. python3 -m unittest tests.test_fold -v`
Expected: `ModuleNotFoundError: No module named 'machines.fold'`.

- [ ] **Step 3: Implement `fold.py`.**

The atom is the only thing a comparison needs: `"LT"` / `"EQ"` / `"GT"` from one comparison, then
`atom in OP_ATOMS[guard.op]`. `machine.py`'s comment on `OP_ATOMS` explains why that is
sufficient and why nothing need interpret the values further. **Guard against an operator outside
`OP_ATOMS`** the way `check_machine` does — a hand-built `Machine` is a first-class caller — and
treat it as a guard that does not fire, with the reason recorded, rather than raising `KeyError`.

- [ ] **Step 4: Run the tests and see them pass.** Then the whole suite.

- [ ] **Step 5: See the ordering test fail under a mutation.**

Move the register-fold step in `fold` to **before** guard evaluation. Run `tests.test_fold`.
Expected: `test_a_guard_reads_the_register_before_the_arriving_message_is_folded_in` **fails**,
reporting `state == "idle"`, and the two paxos fixture tests fail too. Restore, re-run, confirm
green. Then mutate a second time: make a missing guard field *raise* instead of returning false,
and confirm the absent-field test fails. Record both in the commit body.

- [ ] **Step 6: Commit.**

```bash
git add plugins/machines/lib/machines/fold.py plugins/machines/tests/test_fold.py
git commit -m "machines: fold a channel's trace into a state, and evaluate guards for real"
```

---

### Task 3: The envelope's clock, and the order verdict

**Files:**
- Modify: `plugins/machines/lib/machines/fold.py`
- Create: `plugins/machines/tests/test_clock.py`

**Interfaces:**
- Consumes: Task 2's `fold`, `Fold`, `Refusal`.
- Produces: `ORDERS`, `Fold.clocks`, `Step.order`, `Fold.outbound_clock` (or compute it in
  `engine.py` from `Fold.clocks` — either is fine, but say which in the module docstring and keep
  it in one place). New refusal reasons `"duplicate"` and `"out-of-order"`.

**The failure this prevents:** the `#32`-body rule applied across senders. `#32`'s body says
*"the engine must refuse a message whose sequence number is not greater than the last one from
that sender"*; its **third comment corrects that**: across senders an equal value means the two
messages are concurrent, and refusing either is wrong. A machine with more than two roles meets
concurrent writes on its first one. **The corrections override the body.**

**The rules, in evaluation order:** as in *The contract*, above — per-sender first (`==` is
`duplicate`, `<` is `out-of-order`, both refuse), then cross-sender (`>=` from another sender is
`concurrent`, reported, not refused), else `ok`.

**`clocks` is keyed by sender, never by role.** Review-focus item 5.

- [ ] **Step 1: Write the failing tests** in `test_clock.py`.

The three acceptance criteria that name the clock:

```python
def test_a_clock_that_does_not_increase_from_one_sender_is_refused_as_a_duplicate(self):
    f = fold(PAXOS, _trace([_msg("prepare", "proposer", "p1", 1, {"ballot": 5}),
                            _msg("promise", "acceptor", "a1", 2),
                            _msg("promise", "acceptor", "a1", 2)]))
    self.assertEqual([(r.index, r.reason) for r in f.refusals], [(2, "duplicate")])
    self.assertEqual(f.state, "promised")          # the refusal advanced nothing
    self.assertEqual(f.clocks["a1"], 2)            # and consumed no clock

def test_a_lower_clock_from_the_same_sender_is_refused_as_out_of_order(self): ...

def test_two_senders_with_an_equal_clock_are_concurrent_and_neither_is_refused(self):
    f = fold(PAXOS, _trace([_msg("prepare", "proposer", "p1", 1, {"ballot": 5}),
                            _msg("promise", "acceptor", "a1", 1)]))
    self.assertEqual(f.refusals, ())                        # NEITHER refused
    self.assertEqual(f.state, "promised")                   # the fold continued
    self.assertEqual([s.order for s in f.fired], ["ok", "concurrent"])
```

And the ones the criteria do not name but the spec requires:

```python
def test_one_sender_acting_in_two_roles_keeps_one_clock_and_two_role_counts(self): ...
def test_two_senders_sharing_a_role_keep_two_clocks_and_one_role_count(self): ...
def test_the_outbound_clock_is_one_above_the_highest_clock_on_the_channel(self):
    # max over ALL senders, not over the sender about to write (§6).
def test_the_outbound_clock_of_an_empty_trace_is_one(self): ...
def test_a_clock_is_never_called_seq_anywhere_in_the_engine(self):
    import machines.envelope, machines.fold, machines.engine, inspect
    for mod in (machines.envelope, machines.fold, machines.engine):
        src = inspect.getsource(mod)
        self.assertNotIn("seq", src, "%s names seq; #48 decision 1 forbids it" % mod.__name__)
```

That last test is cheap and pins a decision that is otherwise only prose. If a legitimate
substring collision makes it fail (`sequence`, `consequence`), narrow it to a word-boundary
regex rather than deleting it, and say so in the commit body.

- [ ] **Step 2: Run them and see them fail.** Expected: `AttributeError`/`ImportError` on
`ORDERS` or `Fold.clocks`, and the concurrency test reporting a refusal.

- [ ] **Step 3: Extend `fold` with the clock rules.**

- [ ] **Step 4: Run the tests and see them pass.** Then the whole suite.

- [ ] **Step 5: See the concurrency test fail under a mutation.**

Change the cross-sender branch from *report* to *refuse* — i.e. implement `#32`'s uncorrected
body. Run `tests.test_clock`. Expected:
`test_two_senders_with_an_equal_clock_are_concurrent_and_neither_is_refused` **fails**. Restore,
re-run, confirm green. Then mutate the per-sender comparison from `<=` to `<` and confirm the
duplicate test fails. Record both.

- [ ] **Step 6: Commit.**

```bash
git add plugins/machines/lib/machines/fold.py plugins/machines/tests/test_clock.py
git commit -m "machines: the envelope's clock, and the order verdict it supports"
```

---

### Task 4: The verdict

**Files:**
- Create: `plugins/machines/lib/machines/engine.py`
- Create: `plugins/machines/tests/test_engine.py`

**Interfaces:**
- Consumes: Task 2's and Task 3's `Fold` — **and nothing else about a trace.** `engine.py` reads
  `Fold` and `Machine`; it does not re-walk the messages.
- Produces: `verdict(m, trace, limit=MAX_FOLD_STEPS) -> Verdict`, `Verdict`, `Offer`,
  `Remaining`. Exact fields as in *The contract*. Task 5 adds `gate`.

**The failure this prevents:** a verdict that hides what the protocol demanded. §6 is explicit
that `guards[]` is not debugging output and that a verdict reporting only *"not legal"* would
hide a guard that silently refused a message. The same argument covers `refusals` and the two
performers. And one shape failure: a verdict that *acts*. Nothing in `engine.py` performs an
effect, writes a file, or calls out.

**`remaining`:** read `m.cap` and `m.cap_scope`; `None` when `m.cap is None`, with no default
substituted (§7 — an absent cap means *no bound*). The arithmetic is in *The contract* and the
expected values for both fixture traces are in *Measurements*.

- [ ] **Step 1: Write the failing tests** in `test_engine.py`.

The two acceptance criteria that name a verdict over a fixture:

```python
def test_the_session_relay_fixture_and_its_trace_give_a_verdict(self):
    v = verdict(SESSION_RELAY, load_trace(FIXTURES / "trace-session-relay.json"))
    self.assertTrue(v.legal)
    self.assertIsNone(v.reason)
    self.assertEqual((v.state, v.holder, v.accepting, v.terminal),
                     ("concluded", None, True, True))
    self.assertEqual(v.may_send, ())
    self.assertEqual(v.remaining.scope, "role")
    self.assertEqual(v.remaining.spent, {"initiator": 2, "responder": 2})
    self.assertEqual(v.remaining.headroom, {"initiator": 8, "responder": 8})
    self.assertEqual(v.outbound_clock, 5)
    self.assertEqual(v.order, "ok")

def test_the_paxos_fixture_and_its_trace_give_a_verdict(self):
    v = verdict(PAXOS, load_trace(FIXTURES / "trace-paxos-acceptor.json"))
    self.assertEqual((v.state, v.accepting, v.terminal), ("decided", True, True))
    self.assertEqual(v.remaining.headroom, {"proposer": 4, "acceptor": 4})
    self.assertEqual(v.outbound_clock, 5)
```

Review-focus item 1, and the rest of the verdict's surface:

```python
def test_an_empty_trace_gives_the_initial_states_verdict(self):
    v = verdict(SESSION_RELAY, _trace([]))
    self.assertTrue(v.legal)                       # NOT a refusal, and not a crash
    self.assertEqual((v.state, v.holder, v.accepting, v.terminal),
                     ("unopened", "initiator", True, False))
    self.assertEqual([(o.kind, o.by, o.to) for o in v.may_send],
                     [("triage", "initiator", "awaiting-triage")])
    self.assertEqual(v.remaining.spent, {"initiator": 0, "responder": 0})
    self.assertEqual(v.outbound_clock, 1)

def test_may_send_names_a_guarded_offer_and_does_not_pretend_to_evaluate_it(self):
    v = verdict(PAXOS, _trace([]))
    self.assertEqual(sorted((o.kind, o.by, o.to, o.guard.op) for o in v.may_send),
                     [("prepare", "proposer", "idle", "le"),
                      ("prepare", "proposer", "prepared", "gt")])

def test_the_verdict_reports_every_guard_it_evaluated_with_both_values(self): ...
def test_the_verdict_names_a_refused_message_and_its_reason(self): ...
def test_a_machine_with_no_cap_has_no_remaining_and_no_invented_default(self):
    self.assertIsNone(verdict(_uncapped_machine(), _trace([])).remaining)
def test_under_per_channel_scope_the_headroom_is_the_one_shared_budget(self):
    # every role maps to the same number, on purpose; SCHEMA.md says so
def test_the_verdict_carries_the_effects_of_the_transition_that_fired(self):
    v = verdict(SESSION_RELAY, load_trace(FIXTURES / "trace-session-relay.json"))
    self.assertEqual(v.effects, ("label.remove:session-relay:open",))
def test_the_verdict_names_a_terminal_states_effects_and_performs_nothing(self): ...
```

- [ ] **Step 2: Run them and see them fail.** Expected:
`ModuleNotFoundError: No module named 'machines.engine'`.

- [ ] **Step 3: Implement `verdict` in `engine.py`.**

- [ ] **Step 4: Run the tests and see them pass.** Then the whole suite.

- [ ] **Step 5: See the headroom test fail under a mutation.**

Change the `per: role` branch to use `sum(spent.values())`. Run `tests.test_engine`. Expected:
both fixture verdict tests **fail**, reporting `{'initiator': 6, 'responder': 6}` where 8 was
asserted. Restore, re-run. Then mutate `may_send` to drop guarded offers and confirm the paxos
`may_send` test fails. Record both.

- [ ] **Step 6: Commit.**

```bash
git add plugins/machines/lib/machines/engine.py plugins/machines/tests/test_engine.py
git commit -m "machines: the verdict -- state, holder, may_send, remaining, order, guards"
```

---

### Task 5: The outbound gate, and the clock the engine stamps

**Files:**
- Modify: `plugins/machines/lib/machines/engine.py`
- Modify: `plugins/machines/tests/test_engine.py`

**Interfaces:**
- Consumes: Task 4's `verdict`, `Verdict`, `Remaining`.
- Produces: `gate(m, trace, outbound, limit=MAX_FOLD_STEPS) -> Verdict`, where `outbound` is a
  `Message` **whose envelope the caller may leave incomplete** — see below. Returns a `Verdict`
  with `legal` and `reason` answering *"may I send this"*, and `outbound_clock` carrying the
  clock the engine stamps.

**The failure this prevents:** §6 — *"the engine refusing to emit a message past the cap is the
cap becoming structural. Item 6 showed a competent session doing this by hand; the engine removes
the requirement that the session be competent."* And the stamped clock removes the second half:
*"a sender cannot forget it and cannot choose it."*

**Four refusals the gate must produce, each with its own reason string:**

| Reason | When |
|---|---|
| `"not permitted here"` | no transition out of the folded state fires on `(kind, by)` under the guards and the outbound message's own fields. **This is acceptance criterion 7.** |
| `"cap exhausted"` | `remaining.headroom[outbound.by] <= 0` and the transition that would fire has `signal: true`. A `signal: false` transition is a local move and does not count (§7, §11.6 — *"only signalling transitions"*, settled, recorded so it cannot drift back) |
| `"terminal state"` | the folded state is terminal. Nothing further is possible, and `check_machine` guarantees no transition leaves one |
| `"ambiguous"` | more than one transition fires — Task 2's rule 3, applied outbound |

**The outbound envelope:** the engine **stamps** `clock`, and `gate` must **ignore and overwrite**
any clock the caller supplied rather than validating it. §6's whole point is that the sender
cannot choose it. The gate reads `outbound.by` and `outbound.fields`; the caller supplies
`sender`. Say in the docstring that a caller-supplied clock is discarded, and test it.

- [ ] **Step 1: Write the failing tests**, added to `test_engine.py`.

```python
def test_the_gate_refuses_a_kind_the_current_state_does_not_permit(self):
    trace = _trace(load_trace(FIXTURES / "trace-session-relay.json").messages[:1])
    v = gate(SESSION_RELAY, trace, _out("answer", "initiator", "repo-a"))
    self.assertFalse(v.legal)                       # state is awaiting-triage
    self.assertEqual(v.reason, "not permitted here")

def test_the_gate_admits_a_kind_the_current_state_permits(self):
    trace = _trace(load_trace(FIXTURES / "trace-session-relay.json").messages[:1])
    v = gate(SESSION_RELAY, trace, _out("question", "responder", "repo-b"))
    self.assertTrue(v.legal)
    self.assertEqual(v.outbound_clock, 2)

def test_the_gate_refuses_an_outbound_message_past_the_cap(self):
    # per: role, limit 10. Drive the initiator to 10 signalling transitions, then gate an 11th.
    # This is item 6's "11 of 10" made structural: the cap refuses before the message exists.
def test_a_role_at_its_cap_does_not_block_the_other_role(self):
    # per: role is two budgets, not one -- the property `cap: 10` could not express.
def test_the_gate_refuses_everything_from_a_terminal_state(self): ...
def test_the_gate_overwrites_a_caller_supplied_clock(self):
    v = gate(SESSION_RELAY, _trace([]), _out("triage", "initiator", "repo-a", clock=99))
    self.assertEqual(v.outbound_clock, 1)
def test_the_gate_evaluates_a_guard_against_the_outbound_messages_own_fields(self):
    # paxos: an accept-request at the wrong ballot is refused outbound, not after the fact
def test_the_gate_performs_no_effect_and_only_names_the_required_set(self):
    v = gate(SESSION_RELAY, _trace([]), _out("triage", "initiator", "repo-a"))
    self.assertEqual(v.effects, ("label.add:session-relay:open",))
```

- [ ] **Step 2: Run them and see them fail.** Expected: `ImportError` on `gate`.

- [ ] **Step 3: Implement `gate`.**

- [ ] **Step 4: Run the tests and see them pass.** Then the whole suite.

- [ ] **Step 5: See the cap test fail under a mutation.**

Change the gate's cap comparison from `<= 0` to `< 0` — the off-by-one that produces exactly
item 6's `11 of 10`. Run `tests.test_engine`. Expected:
`test_the_gate_refuses_an_outbound_message_past_the_cap` **fails**, admitting the eleventh
message. Restore, re-run. Then mutate the gate to count `signal: false` transitions against the
cap and confirm a local-move test fails. Record both.

- [ ] **Step 6: Commit.**

```bash
git add plugins/machines/lib/machines/engine.py plugins/machines/tests/test_engine.py
git commit -m "machines: gate the outbound message, and stamp the clock the sender cannot choose"
```

---

### Task 6: The engine never branches on a world read

**Files:**
- Modify: `plugins/machines/lib/machines/fold.py` (if anything is needed at all — it may not be)
- Modify: `plugins/machines/tests/test_fold.py`

**Interfaces:** no new names. `Fold.world_reads` and `Verdict.world_reads` already exist from
Tasks 2 and 4.

**The failure this prevents:** §6 and §14 — *"The engine folds channel reads. It never branches on
a world read."* The reason is replay: the framework has no runtime store, so the trace is the
only record there is, and if a world result could reach the transition function two sessions
folding the same trace would compute different states. §6 calls the rule absolute rather than a
matter of taste, so it needs a test and not a comment.

**How to test an absolute negative, mechanically:** an **invariance** test. Fold a trace; then
fold the same trace with every `world_reads` payload replaced by something wildly different; then
assert that every part of the verdict except `world_reads` is identical. This catches a branch on
a world read however it is written, including one added later by someone who never read this
plan.

- [ ] **Step 1: Write the failing test.**

```python
WORLD = [{"verb": "db.query", "result": {"rows": 3, "status": "green"}}]
OTHER = [{"verb": "db.query", "result": {"rows": 99999, "status": "on fire", "x": [1, 2]}}]

def test_the_verdict_is_identical_however_a_world_read_turned_out(self):
    a = verdict(PAXOS, _trace_with_world_reads(WORLD))
    b = verdict(PAXOS, _trace_with_world_reads(OTHER))
    for name in ("legal", "reason", "state", "holder", "accepting", "terminal",
                 "may_send", "order", "concurrent_with", "outbound_clock",
                 "truncated", "refusals", "effects"):
        self.assertEqual(_norm(getattr(a, name)), _norm(getattr(b, name)), name)
    self.assertEqual(_norm(a.remaining), _norm(b.remaining))
    self.assertEqual([(g.field_value, g.register_value, g.atom, g.fired) for g in a.guards],
                     [(g.field_value, g.register_value, g.atom, g.fired) for g in b.guards])
    self.assertNotEqual(a.world_reads, b.world_reads)   # the inputs really did differ

def test_a_world_read_is_carried_into_the_verdict_naming_the_message_that_brought_it(self):
    v = verdict(PAXOS, _trace_with_world_reads(WORLD))
    self.assertEqual([(w.index, w.verb) for w in v.world_reads], [(0, "db.query")])
```

`_norm` exists because `Verdict` holds value objects: compare them by their attribute tuples, not
by identity. **Do not add `__eq__` to the verdict types just to make this test shorter** — a
hand-rolled `__eq__` that omits a field would make the test pass while testing less, which is the
defect this test exists to prevent.

- [ ] **Step 2: Run them and see them fail.** The second test fails if Task 2 did not carry
`world_reads` through. **If the first test passes immediately, that is expected and good** — the
engine was written not to branch. Do not treat a passing invariance test as nothing: prove it in
Step 4.

- [ ] **Step 3: Carry `world_reads` through if it is not already.**

- [ ] **Step 4: See the invariance test fail under a mutation.** *(This step is the deliverable.)*

Add a single branch on a world read inside `fold` — for instance, skip the register update when
`msg.world_reads` has a `result` whose `rows` exceeds 1000. Run `tests.test_fold`. Expected:
`test_the_verdict_is_identical_however_a_world_read_turned_out` **fails**. Remove the mutation,
re-run, confirm green. **Paste the real failure output into the commit body** — this is the only
evidence that §14's absolute rule is tested rather than asserted.

- [ ] **Step 5: Commit.**

```bash
git add plugins/machines/lib/machines/fold.py plugins/machines/tests/test_fold.py
git commit -m "machines: pin the rule that the engine never branches on a world read"
```

---

### Task 7: The engine-side limit on one fold (§11.10, settled)

**Files:**
- Modify: `plugins/machines/lib/machines/fold.py`
- Modify: `plugins/machines/tests/test_fold.py`

**Interfaces:**
- Produces: `MAX_FOLD_STEPS` (a module constant in `fold.py`), `Fold.truncated`, `Fold.steps`, and
  `Verdict.truncated`, already declared in Task 4's contract.

**The failure this prevents and the one it must not cause.** §11.10 states the uncapped local
loop as a requirement — *"cycle B must add a second bound"* — and `claude-plugins#28`'s **fourth
comment withdraws that**: a local move still needs a message to fire it, the schema has no
epsilon transition, and no transport supplies a waiting verb, so the free loop is **not reachable
from the shipped schema**. `claude-plugins#48` decision 4 carries the withdrawal and names the
replacement: *"an engine-side limit on one fold, reported in the verdict … not a second declared
bound."*

So: **no schema field, no new declaration word, nothing a publisher must fill in.** §4 and §7
spent a correction establishing that the framework does not require a protocol to terminate; a
mandatory second bound would walk that back for every continuous machine. What this task adds is
a refusal to fold for ever over a trace somebody hands the engine — a defence of the engine, not
a bound on the protocol, and `SCHEMA.md` must say which it is.

**Do not publish the number without measuring it.** `pattern.py`'s `_MAX_NFA_STATES` shipped with
an unmeasured rationale that was wrong by a factor of ten, and `machine.py`'s `_MAX_CAP_SEARCH`
comment documents that defect at length as the reason its own number carries a measurement. The
anchor is in *Measurements*: a reference fold ran at about 6 µs per message, 100,001 messages in
0.597 s. **Re-measure on the real `fold`**, with the command in the comment, and pick a number
whose time cost you can state. See *decision 6* on the value and on whether truncation is legal.

- [ ] **Step 1: Write the failing tests.**

```python
def test_a_fold_stops_at_its_limit_and_says_so(self):
    f = fold(SESSION_RELAY, _long_trace(50), limit=10)
    self.assertTrue(f.truncated)
    self.assertEqual(f.steps, 10)

def test_a_fold_inside_its_limit_is_not_marked_truncated(self):
    f = fold(SESSION_RELAY, _long_trace(5), limit=10)
    self.assertFalse(f.truncated)
    self.assertEqual(f.steps, 5)

def test_a_truncated_fold_is_reported_in_the_verdict(self):
    self.assertTrue(verdict(SESSION_RELAY, _long_trace(50), limit=10).truncated)

def test_the_limit_is_an_engine_defence_and_not_a_declared_bound(self):
    # No declaration field changed. Both shipped declarations still parse and check clean,
    # and neither mentions a fold limit.
    for name in ("valid-session-relay.md", "valid-paxos-acceptor.md"):
        m = parse((FIXTURES / name).read_text())
        self.assertEqual(check_machine(m), [])
    self.assertNotIn("fold", set(FIELDS))
```

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Implement the limit, and measure the constant.**

Time the real `fold` at a few sizes, write the command and the numbers into the comment above
`MAX_FOLD_STEPS` the way `_MAX_CAP_SEARCH`'s comment does, and state which bound governs — the
time cost, or a plausible channel length. **If your measurement disagrees with the anchor above,
yours wins; say so in the commit body.**

- [ ] **Step 4: Run the tests and see them pass.** Then the whole suite.

- [ ] **Step 5: See the truncation test fail under a mutation.**

Make `truncated` a constant `False`. Run `tests.test_fold`. Expected:
`test_a_fold_stops_at_its_limit_and_says_so` **fails**. Restore, re-run.

- [ ] **Step 6: Commit.**

```bash
git add plugins/machines/lib/machines/fold.py plugins/machines/tests/test_fold.py
git commit -m "machines: an engine-side limit on one fold, reported in the verdict"
```

---

### Task 8: What the engine does, and what it does not check

**Files:**
- Modify: `plugins/machines/SCHEMA.md`
- Modify: `plugins/machines/README.md`

**Interfaces:** none. This is prose, and it is an acceptance criterion.

**The failure this prevents:** §4's third row and §14's first line — *"the framework does not
check meaning, and no part of it may appear to."* An engine is the first thing in this plugin that
*runs* a protocol, so it is the first thing a reader could mistake for something that verifies
what a conversation means. Until now `README.md` could say *"there is no engine"* and be done.
That sentence is about to be false, and the replacement has to be at least as clear about the
boundary as the sentence it replaces.

**`README.md` — four edits, each currently wrong after Tasks 1–7:**

- *"There is no engine — nothing here runs a machine, advances a state, or emits a message."*
  → there **is** an engine; it advances a state and emits a **verdict**, and it still emits no
  message, because nothing here performs an effect. **Keep "There is no installer" and "There is
  no dispatcher" exactly as they are.**
- The *"What this ships, and what it does not"* opening, which says cycle A and A.1 *"is the
  whole of it"* and that *"anything that talks about a machine actually running is a later
  cycle."* Cycle B is that later cycle. Say so.
- Add a short section on the engine: the fold, the verdict's fields, the outbound gate, the clock,
  and that the engine performs nothing.
- Add the **what the engine does not check** list below.

**The *what the engine does not check* list — the centre of this task.** Both documents carry it;
`SCHEMA.md` in full, `README.md` in short. Every line is a limit this cycle actually has:

1. **Content.** The engine reads the kinds, the roles and the declared fields a declaration names,
   and the envelope. **There is no slot in the trace for a message body** (Task 1) — not a rule
   the engine follows, a shape it cannot express. Whether a draft states a new fact, whether a
   sender set a flag honestly, whether an answer answers the question: none of it is visible here,
   and nothing in this plugin will ever report on it.
2. **Meaning, including `accepting`.** §11.9: *"nothing here can confirm that a state a publisher
   marked accepting really is a fine place for a run to stop"*. The engine reports `accepting`
   because the declaration says so, and that is the whole of its warrant.
3. **Agreement.** A machine that declares anything consensus-shaped — `paxos-acceptor` among them
   — gets its sequencing and its declared invariant checked and **nothing about agreement**. The
   engine folds one acceptor's own register; it cannot see the others and no field in this schema
   could name them. `valid-paxos-acceptor.md` says this in its own prose, as §7 requires.
4. **Whether a guard will fire.** `may_send` names a guarded offer without evaluating it, because
   no message exists yet. The *checker* additionally cannot tell you a guard never fires at all
   (§9's stated precision loss), and the engine does not make up the difference.
5. **Whether the transport told the truth.** §8: a buggy or hostile transport can **misreport
   which messages exist**. It cannot forge a transition, skip the cap or fake a terminal state,
   because the engine is what counts and what decides — but the engine folds the trace it was
   handed, and a trace is only as honest as whoever produced it.
6. **Anything outside the channel.** The engine carries a world read into the verdict and
   **never branches on it** (Task 6). A world read reaches a conversation only as a message
   somebody wrote into the channel.
7. **The clock is not `seq`, and `remaining` is not an ordinal.** §10's table, in short: the clock
   orders and detects duplicates; `remaining` counts against the cap. One sender's tenth message
   can carry a clock of about 19, and that is correct. **Do not render a visible `n of 10` from the
   clock** — that is §2's `11 of 10` finding made worse and made silent.
8. **Whether a declaration is unambiguous.** Measured: `check_machine` passes two transitions that
   share all four of `(from, on, by, to)` and differ only in `effects`. The engine refuses such a
   message as `ambiguous` rather than guessing, which is a refusal a well-formed-looking machine
   can provoke. Name it as a known gap and point at the checker defect Task 9 files.

**`SCHEMA.md` — add one section, change nothing else.** A new top-level section, *"What the engine
does with a declaration"*, after the transition fields: the fold, the two semantics `SCHEMA.md`
already pinned (now implemented — say so, and stop calling them *"cycle B implements"* in the
future tense), the clock and the four order values, `remaining`'s arithmetic in both scopes
**including that `per: channel` headroom is equal across roles and must not be summed**, and the
list above. **Do not touch any field definition.**

- [ ] **Step 1: Read both documents end to end**, not only the paragraphs you intend to change.
`README.md` is 138 lines and `SCHEMA.md` is 786. A document that contradicts itself in a section
nobody edited is the failure this step exists to catch.
- [ ] **Step 2: Make the edits.** Keep the voice. Do not restructure sections that did not change.
- [ ] **Step 3: Grep for the claims that are now false.**

Run: `grep -niE "no engine|nothing here runs|cycle B implements|not built" plugins/machines/README.md plugins/machines/SCHEMA.md`
Expected: every surviving hit is still true. Fix the ones that are not.

- [ ] **Step 4: Run the whole suite.** Documentation changes should not move it; confirm 266 + new.
- [ ] **Step 5: Commit.**

```bash
git add plugins/machines/SCHEMA.md plugins/machines/README.md
git commit -m "machines: document what the engine does, and what it does not check"
```

---

### Task 9: The version, the manifests, the spec's marks, and the issues

**Files:**
- Modify: `plugins/machines/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Generated by script: `plugins/machines/.codex-plugin/plugin.json`,
  `.agents/plugins/marketplace.json`, `.github/plugin/marketplace.json`
- Modify: `docs/superpowers/specs/2026-09-14-machines-framework-design.md`

**Interfaces:** none. This is housekeeping, and three of its four parts are acceptance criteria.

**Why both numbers move together — read the repository's `CLAUDE.md`.** *"An installed plugin is
cached by version, so a change with no bump never reaches an installed copy."* And
`claude plugin validate .` *"reports a marketplace entry whose `version` differs from the plugin's
own `plugin.json`"*, so a bump in one place and not the other is a validation failure, not a
silent drift. **The files under `.claude-plugin/` are the source of truth and the Codex and
Copilot manifests are generated — never edit a generated file by hand.** CI runs
`scripts/sync-manifests.py --check` and fails on a stale file.

- [ ] **Step 1: Bump the version in both places.** `0.3.0` → **`0.4.0`** in
`plugins/machines/.claude-plugin/plugin.json` and in the `machines` entry of
`.claude-plugin/marketplace.json`. Additive: a new engine, no schema change, nothing removed.

- [ ] **Step 2: Correct the marketplace entry's description.** It currently ends *"Cycle A: the
schema and the checker only, no engine, no installer, no dispatcher."* — measured, and false after
this cycle. It becomes the schema, the checker **and the engine**; still no installer and no
dispatcher.

- [ ] **Step 3: Run the sync and the validator.**

```bash
python3 scripts/sync-manifests.py
python3 scripts/sync-manifests.py --check    # must print nothing and exit 0
claude plugin validate .                     # must print "Validation passed"
```

`validate` also emits a pre-existing `tone-roulette` README warning that is **not ours** — leave
it. If anything else appears, stop and report it.

- [ ] **Step 4: Correct the spec's own "not built" marks.**

The spec's opening says *"Read every 'shipped' and 'not built' mark in this document as
load-bearing"* and *"There is still no clock, no verb classification and no engine in
`plugins/machines/`."* After Tasks 1–7 that is false in these places. A spec that lies about what
exists is worse than one that says nothing.

| Where | Change |
|---|---|
| the header block | cycle B is built; say what is still unbuilt (the transport declaration and the verb classification, cycle C; the dispatcher and the backport, cycle D) |
| §4's layer table, **Channel** row | *"the envelope's clock … — not built"* → built |
| §4's *"The envelope"* subsection | drop **Not built. Cycle B.**; record the clock's name (`clock`, never `seq`), the four order values, and that an equal value across senders is reported as concurrent and refused for neither |
| §6's *"The engine emits a verdict, never an action"* | drop **Not built**; record the verdict's shipped field names, and **record that `effects.transport[]` / `effects.agent[]` shipped as one unclassified list** because the classifier is the transport declaration (cycle C). See *contradiction 1* — do not quietly drop the two-list promise, record why it waits |
| §6's *"What the engine may read"* | drop **Not built**; record that the rule is pinned by an invariance test, naming it |
| §11.10 | **settled**: the engine-side fold limit shipped; no second declared bound; the cap-counts-channel-writes proposal is still open and still cycle C's precondition |
| §13's table, row B | mark B delivered, and restate what C and D inherit |

**Two things to leave exactly as they are:** §7's paragraph on the effect vocabulary and §9's
effect-against-transport check. Both are still correctly marked as diverging from the shipped code
and both wait on cycle C. Also leave §11.1 (the trigger measurement) and §11.11 (addressing)
untouched — both are cycle D's.

**Another session may be live in a sibling worktree.** Re-read the spec immediately before editing
it, stage only this path, and never `git add -A`.

- [ ] **Step 5: Grep the spec for marks that are now stale.**

Run: `grep -niE "not built|unbuilt|no engine" docs/superpowers/specs/2026-09-14-machines-framework-design.md`
Expected: every surviving hit is still true.

- [ ] **Step 6: Run the whole suite one last time**, from `plugins/machines`, and paste the real
count into the commit body.

- [ ] **Step 7: Commit.**

```bash
git add plugins/machines/.claude-plugin/plugin.json plugins/machines/.codex-plugin/plugin.json .claude-plugin/marketplace.json .agents/plugins/marketplace.json .github/plugin/marketplace.json docs/superpowers/specs/2026-09-14-machines-framework-design.md
git commit -m "machines: ship the engine at 0.4.0, and record cycle B in the spec"
```

- [ ] **Step 8: Write the outcome into the issues.** Not only into the spec —
`claude-plugins#48` is where a reader will look, `#32` says *"this issue stays open until the
engine carries the clock"* and can now close, and `#28`'s first comment lists seven things the
schema cannot express, of which **item 2's `seq=` half is now settled** (the clock took the
ordering job, the verdict's `remaining` took the counting job). Items 4 and 6 stay open.

**File the checker defect measured in this plan** as its own issue, with the `created-by-claude`,
`plugin:machines` and `severity:medium` labels this repository requires: `check_machine`'s
determinism check skips a trigger group whose members all share one `to`, so two transitions
differing only in `effects` pass, and `machine.py`'s rule-3 comment describes a check that does
not run for that shape. Include the reproducing declaration from *Measurements*. **Do not fix it
in this cycle** — it is a checker change, and cycle B does not touch the checker.

---

## Where this plan contradicts its inputs

Six places. Read these before deciding a task is wrong.

### 1. §6 promises two effect lists; this plan ships one, because the classifier does not exist

§6's verdict carries `effects.transport[]` (*"required of installed code, under install-time
consent"*) and `effects.agent[]` (*"required of Claude, under its own tool permissions"*), and the
*"Two performers"* subsection makes the split load-bearing: *"a reader of a thread who cannot
separate what the protocol demanded from what Claude chose has lost the boundary that stops the
framework appearing to check meaning."*

**Nothing in cycle B can perform that split.** What classifies a verb is the **transport
declaration** — the verb set with typed arguments and the world-touching marks — and §13 puts it
in **cycle C** because the installer is what reads and displays it. The shipped `check_machine`
hardcodes three verbs (`label.add:<name>`, `label.remove:<name>`, `escalate`), which §7 itself
calls *"the generalising-from-one-instance failure `#26`'s body warns about"*. So the only way to
split the two lists today is to hardcode a classification of those three verbs — which is that
same failure, committed deliberately, in the verdict this time.

**This plan ships `effects: tuple[str, ...]`, one unclassified list**, and Task 9 records in §6
why the two-list promise waits for C rather than deleting it. The cost is real and stated: the
*"the machine made me do this"* check §6 wants a human reader to be able to perform is **not
available in cycle B**, and `README.md` must not imply it is.

### 2. `claude-plugins#48`'s guard-refusal criterion cannot be met on the paxos fixture as it stands

Acceptance criterion: *"A test shows that the engine refuses a message when a guard fails."*
**Measured:** `paxos-acceptor`'s two guarded groups are complete, not merely disjoint —
`gt`+`le` and `eq`+`ne` each cover all three of `LT`/`EQ`/`GT` — so **no ballot value is refused
by a guard there**; every integer fires exactly one branch. The criterion is met by the two routes
Task 2 uses: a `prepare` that omits `ballot` (both guards false, on the shipped fixture
unmodified) and a machine with an incomplete guard set built in the test file. **The criterion is
satisfied; the fixture simply is not the place a ballot value gets refused**, and an implementer
who goes looking for one will not find it.

### 3. `#28`'s first comment requires a second bound; its fourth comment withdraws that

Comment 1: *"Cycle B must add a second bound. The cap limits the conversation. A second bound must
limit the run."* Comment 4: *"That overstates the problem … A machine cannot loop for free today …
It is not a separate task for cycle B to remember."* **The correction overrides the earlier
comment**, `claude-plugins#48` decision 4 carries the correction, and §11.10 agrees. Task 7
implements the engine-side limit on one fold and **no declared field**. If a reviewer objects that
the plan ignores comment 1, that is the reviewer reading the withdrawn version.

### 4. The shipped checker passes a declaration the engine cannot run deterministically

Measured, with the reproducing declaration, in *Measurements*. `check_machine` returns `[]` for two
transitions sharing all four of `(from, on, by, to)` and differing only in `effects`, because the
determinism check skips any group with one distinct `to`. `SCHEMA.md`'s `to` bullet says a fold
*"has exactly one result per step, so a machine with that choice in it cannot be run at all"* —
and this is such a machine, passing. Worse, `machine.py`'s own rule-3 comment claims the check
covers *"two members that happen to agree on `to`"*, which it does not.

**This plan handles it in the engine** (refuse with reason `"ambiguous"`, naming both
transitions, Task 2 rule 3) and **files it as a checker defect** (Task 9 step 8) rather than
fixing the checker in a cycle that is not allowed to touch it. See *decision 4* for the other two
options.

### 5. §4 requires a fifth order condition that §6's four-value enumeration has no word for

§4: *"What the engine refuses is a message from a sender whose clock did not advance past that
sender's own last message, **and a message claiming to follow something the receiver has not
seen**."* The second is a clock above `max(seen) + 1` — the sender folded in a message the
engine's trace does not contain. §6 enumerates exactly four order values (`ok`, `duplicate`,
`out-of-order`, `concurrent`), and none of them is that. `claude-plugins#48`'s acceptance criteria
do not mention it at all.

**This plan keeps §6's four values** and reports the condition as `out-of-order` with the gap
named in the refusal's `detail`. See *decision 2* — this is the one place the plan may have picked
wrong, and it is cheap to change either way before Task 3 ships.

### 6. §8 says the total-order property is declared by the transport, which cycle B does not have

§8: *"the transport states whether its channel gives a total order. Absent is not a default; it is
a declaration that will not install."* The transport declaration's **file format** is explicitly
open (§11.5) and explicitly cycle C's. So cycle B has the property to honour and nowhere to read
it from. **This plan puts `total_order` on the trace fixture as a required boolean** — the trace
is *"the JSON a transport would have returned"*, and this is a channel fact that came back with
it, not the transport's declaration file. See *decision 3*.

---

## Decisions this plan could not make — all six settled on 2026-10-26

**Every recommendation below was accepted. Implement the recommendation, not the alternative.**

- **Decisions 1 and 2 are the author's**, answered on 2026-10-26. Decision 1: the headroom is a
  mapping over every declared role, in both cap scopes. Decision 2: a clock above `max(seen) + 1`
  reports `order: "out-of-order"` and names the gap in the refusal's detail, for example
  `"clock 9 follows nothing seen; highest seen is 6"`.
- **Decisions 3, 4, 5 and 6 are the controller's**, taken as recommended on the same day.

The questions and the reasoning are kept below exactly as the plan asked them, because a reader
who meets the answer in the code needs to see what the alternative was and what it cost.

Each is stated as a question, with a recommendation, and each is cheap to change before the task
that depends on it.

1. **Is `remaining.headroom` a mapping over every role, or one integer for the role that acts
   next?** §6's wording is *"cap headroom for this sender on this channel"*, which reads like one
   number. **Recommendation: a mapping over every declared role, in both scopes** — one type
   regardless of scope, no `Optional[int]` when a terminal state has no holder, and the gate reads
   `headroom[by] > 0` identically either way. The cost: under `per: channel` the numbers are equal
   across roles and must not be summed, so `SCHEMA.md` has to say so. (Task 4.)

2. **A clock above `max(seen) + 1` — report it as `out-of-order`, or add a fifth order value?**
   §4 requires the refusal; §6 fixes four values. **Recommendation: report `out-of-order` and name
   the gap in the refusal's detail.** A fifth value is clearer but contradicts §6's enumeration,
   and the wire format is permanent once comments carry it. (Task 3; *contradiction 5*.)

3. **Where does `total_order` come from in cycle B?** **Recommendation: a required boolean on the
   trace fixture**, with §8's declaration left to cycle C. The alternative — defer every
   server-order question to C and have the engine rebuild order from the clock alone — is simpler
   but leaves the GitHub-issues case (the one §8 says is free) untested until C. (Task 1;
   *contradiction 6*.)

4. **The same-`(from,on,by,to)`-different-effects ambiguity: refuse, union, or first-wins?**
   **Recommendation: refuse, with reason `"ambiguous"`, naming both transitions**, and file the
   checker defect without fixing it. A union demands effects no declaration asked for; first-wins
   makes the verdict depend on YAML ordering, which nothing documents. (Task 2;
   *contradiction 4*.)

5. **Does cycle B ship a CLI for the engine?** `bin/machines-check` and `cli.py` serve the
   checker. §6 lists four executables and the engine is one of them, but nothing in
   `claude-plugins#48` asks for a command and the engine's only caller until cycle D is a test.
   **Recommendation: no CLI this cycle.** A command whose only user is a test is surface to
   maintain for nobody, and cycle D is what knows how it should be invoked.

6. **`MAX_FOLD_STEPS`'s value, and is a truncated fold legal?** **Recommendation: measure it on
   the real `fold` and put the measurement in the comment** (the anchor is about 6 µs per message,
   100,001 messages in 0.597 s), and make a truncated fold **`legal: False`** with
   `truncated: True` — a verdict computed from a fold that did not finish is not a verdict about
   the channel, and reporting it as legal would be the quiet wrong answer this framework exists
   to prevent. (Task 7.)

---

## Housekeeping

- **Do not `git add -A` or `git commit -a`.** Stage the explicit paths each task names.
  `plugins/machines/lib/machines/__pycache__/` is untracked and ignored by
  `plugins/machines/.gitignore`; the repository root has no `.gitignore` of its own.
- **Run `git status --short` before every commit** and confirm nothing unexpected is staged.
- **Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`** and nothing
  after it. **No `claude.ai/code/session_*` URL** in a commit message, a code comment, a document
  or an issue body — it is a hard rule in this repository and it is only removable from history by
  a force-push.
- **Every issue this cycle creates carries `created-by-claude`, one `plugin:` label
  (`plugin:machines`) and one `severity:` label.**
- **If a file changes under you and you cannot account for the change, stop and report it.** Do
  not revert it, do not stash it, do not `git checkout` it. The stash stack is shared across
  worktrees.
