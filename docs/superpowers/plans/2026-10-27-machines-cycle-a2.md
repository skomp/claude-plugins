# `machines` Cycle A.2 — Structured Effects — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An effect stops being a string and becomes a shape — a `verb` and typed `args` — so
that a verb taking more than one argument is expressible without inventing an escaping grammar.
The checker then validates each effect's verb, arity and argument types. The vocabulary stays
the three built-in verbs; **opening it is cycle C.2 and is not this cycle's work.**

**Architecture:** One new value type, `Effect(verb, args)`, beside `Field`, `Register` and
`Guard` in `machine.py`. `declaration.py` parses the new shape; `check_machine` validates it
against a built-in verb table that C.2 will replace with the transport's declaration;
`Transition.effects` and therefore `Verdict.effects` carry `Effect` objects instead of strings.
Nothing else about the declaration language moves.

**Tech Stack:** Python 3 (stdlib + PyYAML), `unittest`. Nothing new.

**Spec:** `docs/superpowers/specs/2026-10-27-machines-transport-declaration-design.md` §7 — the
decision, its argument, and what A.2 is for. Also
`docs/superpowers/specs/2026-09-14-machines-framework-design.md` §7 (*"The effect vocabulary is
the transport's, not the framework's"*), which is the divergence this cycle half-closes.

**Issue:** `claude-plugins#28` carries the cycle list. This cycle also closes the
highest-value item of `claude-plugins#55` — see Task 2.

---

## Read this before you write a line

**All code in this plan is a PROPOSAL, not a requirement.** The contracts — names, signatures,
types, and the failure each thing must prevent — are the binding part. The bodies are a sketch.
Cycle A's plan produced seven defects of its own and cycle B's produced two more, every one of
them in code that had been reasoned out rather than run.

**Be sceptical. Report defects rather than fixing them silently.** If you conclude something
here is wrong, say so with evidence rather than implementing something you believe is incorrect.

**Two things you must not do:**

1. **Do not open the vocabulary.** `label.add`, `label.remove` and `escalate` stay the only
   verbs a machine may name. This cycle changes the *shape* of an effect, not the *set* of
   verbs. Opening it needs a transport declaration, which is cycle C.1.
2. **Do not change `FIELD_TYPES`.** It is `("int", "bool")` and it governs a message's header
   fields, not a verb's arguments. A verb argument may also be a string, so the argument types
   are their own vocabulary. Conflating the two would couple two unrelated languages.

---

## Global Constraints

- **Python 3 stdlib + PyYAML only.** No new dependency.
- **Run the suite from `plugins/machines`:**
  `PYTHONPATH=lib:. python3 -m unittest discover -s tests -t .`
- **Baseline: 407 tests pass at `2fb41b3`.** If your starting count differs, stop and report it.
- **Every new test must be seen to fail under a mutation of the code it covers**, named with its
  verbatim failure in the commit body. A test that has only ever passed is not evidence.
- **A same-size edit restored within the same second lets Python reuse the mutated `.pyc`**, so a
  restored file can keep failing and the evidence inverts. `touch` the file after every mutation
  and restore, or run `python3 -B`. **Mutate a copy under `/tmp`**, never the checkout.
- **Tests will be edited in this cycle, and that is expected** — this is a schema change, so
  tests that pin the old shape are describing the old schema. **Editing a test to make new code
  pass is a different thing from editing a test because the schema changed**, and a reviewer will
  judge every edit on which one it was. Say in your report, for each edited test, what it pinned
  before and why that expectation is now wrong.
- **Do not `git add -A` or `git commit -a`.** Stage the explicit paths each task names. Never
  stage `.claude/` or `.superpowers/`.
- Commit trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` and nothing after it.
  **No `claude.ai/code/session_*` URL anywhere.**

---

## Measurements — already taken, do not re-derive

Every row was produced by running a command in this checkout at `2fb41b3` on 2026-10-27.

| Fact | How |
|---|---|
| **407 tests pass.** | the command above |
| `plugins/machines` is at version **0.6.0**, in `plugin.json` and the marketplace entry | `grep '"version"'` |
| `scripts/sync-manifests.py --check` is clean; `claude plugin validate .` passes with one pre-existing `tone-roulette` advisory that is not ours | both commands |

**The code that changes, quoted from the source.**

`declaration.py`'s `_effects_field` (around line 387) is the whole of the current parse:

```python
def _effects_field(raw):
    """`effects` is an optional list of strings. ..."""
    if "effects" not in raw:
        return []
    effects = raw["effects"]
    if not isinstance(effects, list):
        raise DeclarationError("effects must be a list of strings, not %r" % (effects,),
                               field="effects")
    for effect in effects:
        _require_string(effect, "effects", "each entry of ")
    return effects
```

`machine.py`'s effect check (around line 503) is the whole of the current validation:

```python
    for t in m.transitions:
        for effect in t.effects:
            if effect == "escalate":
                continue
            prefix = next(
                (p for p in ("label.add:", "label.remove:") if effect.startswith(p)),
                None,
            )
            if prefix is None or len(effect) == len(prefix):
                problems.append("effect %r is not in the vocabulary "
                                "(label.add:<name>, label.remove:<name>, escalate)"
                                % effect)
```

**The repeat key, around line 594 of `machine.py`**, which `tuple(t.effects)` makes
string-dependent today:

```python
            key = (t.to, t.signal, tuple(t.effects),
                   None if t.guard is None
                   else (t.guard.field, t.guard.op, t.guard.register))
```

**The closed vocabularies that exist now** — `FIELD_TYPES = ("int", "bool")`,
`FOLDS = ("max", "last")`, `CAP_SCOPES = ("channel", "role")`,
`ROLE_KINDS = ("repository", "session")`, `NAME = ^[a-z][a-z0-9_-]*$`. **`NAME` rejects a dot**,
so a verb name is *not* `NAME`-shaped: `label.add` contains one. A verb name needs its own
pattern.

**The only fixture with effects** is `plugins/machines/tests/fixtures/valid-session-relay.md`,
with exactly three lists:

```yaml
      effects: ["label.add:session-relay:open"]
      effects: ["label.remove:session-relay:open"]
      effects: ["label.remove:session-relay:open", "label.add:session-relay:stalled", "escalate"]
```

`valid-paxos-acceptor.md` declares no effects at all.

**Where `effects` appears in the test suite**, by `grep -c`: `test_declaration.py` 15,
`test_machine.py` 14, `test_engine.py` 13, `test_fold.py` 7. No other test file mentions it.

**Where `SCHEMA.md` describes effects**: line 18 (*"`effects` must be lists of strings"*), the
`effects` bullet under the transition fields (around line 722), the determinism `to` bullet
(around 713), and the engine section's unclassified-list paragraph (around 846).

**The one argument that decides this cycle's shape, measured in the fixture above:**
`label.add:session-relay:open` is one verb and **one argument that itself contains a colon**.
Any colon-separated multi-argument grammar is ambiguous on the first real declaration this
project has.

---

## The contract

```python
# machine.py
ARG_TYPES = ("string", "int", "bool")
VERB = re.compile(r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)*$")

BUILTIN_VERBS = {
    "label.add":    {"name": "string"},
    "label.remove": {"name": "string"},
    "escalate":     {},
}

class Effect(object):
    __init__(self, verb, args)        # verb: str; args: dict[str, str | int | bool]
```

```yaml
# the declaration, after this cycle
effects:
  - verb: label.add
    args: { name: "session-relay:open" }
  - verb: escalate
```

- **`verb`** is required, a string, and must match `VERB`. A dotted name is the point: the
  existing verbs are dotted and `NAME` forbids a dot.
- **`args`** is optional and defaults to `{}`. Omitting it and writing `args: {}` mean the same
  thing, and `escalate` is why: requiring an empty mapping on every argument-free verb is noise
  a reader has to skip. **An argument's value is never defaulted** — a default is a value nobody
  wrote that the checker would then validate as though they had.
- **Exactly two keys.** Any other key on an effect entry is a `DeclarationError` naming it, the
  way every other mapping in this language already behaves.

**The failure `Effect` must prevent:** an effect that names a verb its performer does not offer,
or supplies it with the wrong arity or the wrong types, reaching run time. Today that is a
run-time failure halfway through a conversation; after this cycle it is an install error.

**What `check_machine` must report**, each as its own problem string:

| When | Report |
|---|---|
| `verb` is not in `BUILTIN_VERBS` | the verb, and the vocabulary that exists |
| an argument the verb does not declare | the argument's name and the verb |
| a declared argument missing | the argument's name and the verb |
| an argument of the wrong type | the argument, the declared type, and what arrived |
| **a `bool` where `int` is declared** | the same wrong-type problem. `isinstance(True, int)` is `True`, so this is the default behaviour unless it is guarded — the trap `declaration.py` already guards for `cap: true` |

---

## File Structure

```
plugins/machines/
  lib/machines/
    machine.py        MODIFY  Effect, ARG_TYPES, VERB, BUILTIN_VERBS; the effect check;
                              the repeat key
    declaration.py    MODIFY  _effects_field parses the new shape
    engine.py         MODIFY  only if the verdict's effects need it — see Task 3
    fold.py           UNCHANGED (it copies what the transition carries)
  tests/
    test_declaration.py  MODIFY  the parse tests
    test_machine.py      MODIFY  the checker tests
    test_engine.py       MODIFY  the verdict's effects assertions
    test_fold.py         MODIFY  the step's effects assertions
    fixtures/valid-session-relay.md   MODIFY  three effect lists -- in TASK 1, not Task 4,
                              because the parser change makes the old shape unparseable
  SCHEMA.md           MODIFY  four places, named in Measurements
  .claude-plugin/plugin.json   MODIFY  0.6.0 -> 0.7.0
.claude-plugin/marketplace.json  MODIFY  the machines entry, same bump
```

---

## Tasks

Each task ends with an independently testable deliverable, a whole-suite run, and a commit.
**Every dispatch must carry:** *"the code here is a proposal, not a requirement — be sceptical,
and report defects rather than fixing them silently."*

---

### Task 1: `Effect`, the parser that builds one, and every declaration that must still parse

**Files:** `lib/machines/machine.py`, `lib/machines/declaration.py`,
`tests/test_declaration.py`, `tests/fixtures/valid-session-relay.md`

**Measured before dispatch, and it sets this task's scope:** the old effect shape appears in
four places that other test files parse — `test_declaration.py`'s `VALID` (line 56 onward), a
second declaration block in the same file (line 343 onward), the splice helper
`_AN_EFFECTS_LIST` (line 383), and the fixture `valid-session-relay.md`. `VALID` is imported by
`test_machine.py`, `test_guards.py` and `test_registry.py`, and the fixture is read by
`test_fold.py`, `test_engine.py` and `test_registry.py`. **So the parser change makes all of
them unparseable the moment it lands, and rewriting them is part of this task rather than of
Task 4.** A `DeclarationError` from a fixture is not a failing assertion about effects; it is
every test that touches that declaration erroring out, which would bury Task 2's and Task 3's
real signal.

**Interfaces:** produces `Effect`, `ARG_TYPES`, `VERB`; `_effects_field` returns
`list[Effect]`. Task 2 consumes all of it. **`BUILTIN_VERBS` belongs to Task 2** — this task
parses a shape and validates nothing about *which* verb it names.

**The failure this prevents:** a shape that looks parsed but is not — an effect entry that is a
string, a bare verb with no mapping around it, an `args` that is a list, an argument value that
is `None` or a float.

- [ ] **Step 1: Write the failing tests** in `test_declaration.py`. Name them for the input.
  At minimum: an entry that is a string is refused by name; `verb` absent is refused; a `verb`
  with a space, a capital or a leading dot is refused; an unknown key on the entry is refused
  **naming the key**; `args` that is a list is refused; an argument whose value is a float or
  `None` is refused; `args` omitted parses to `{}`; `args: {}` parses the same; a string, an
  `int` and a `bool` argument all parse and keep their Python types.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** `Effect` in `machine.py` beside `Guard`; `VERB` and `ARG_TYPES` as
  module constants; `_effects_field` rewritten. Follow `_guard_field`'s shape — it is the
  closest existing thing and it already rejects an unknown key by name.
- [ ] **Step 4: Rewrite the four old-shape declarations** named above, into the new shape,
  keeping every value exactly as it is — `session-relay:open` and `session-relay:stalled` are
  that protocol's own label names and this cycle does not touch them. `_AN_EFFECTS_LIST` is a
  splice helper: whatever replaces it must still splice, and `test_machine.py`'s `mutate` helper
  asserts a splice landed before replacing, which is the discipline to copy.
- [ ] **Step 5: Run the whole suite.** Nothing may fail with a `DeclarationError` any more. What
  remains failing are assertions in `test_machine.py`, `test_engine.py` and `test_fold.py` that
  compare effects as strings — **do not fix those here**; Tasks 2 and 3 own them. Record the
  count, the files, and that every remaining failure is an assertion rather than a parse error.
- [ ] **Step 6: See one new test fail under a mutation.** Drop the unknown-key rejection from the
  effect branch; the unknown-key test must fail. Restore, `touch`, confirm.
- [ ] **Step 7: Commit** `machine.py`, `declaration.py`, `test_declaration.py` and the fixture.

**Note:** the suite is red at the end of this task, and every remaining failure must be an
assertion about an effect's string form. That is the one place in this plan where red is
allowed, because the schema change and its consequences cannot land in one commit without the
commit being unreviewable. **A parse error at the end of this task means a declaration was
missed**, which is a different thing and is this task's own defect. Task 2 and Task 3 make the
suite green again.

---

### Task 2: The checker validates verb, arity and types — and the repeat key stops being hand-written

**Files:** `lib/machines/machine.py`, `tests/test_machine.py`

**Interfaces:** produces `BUILTIN_VERBS`. Consumes Task 1's `Effect` and `ARG_TYPES`.

**The failure this prevents:** two of them. The one in the contract table above — a bad effect
reaching run time — and a second that `claude-plugins#55` names as its highest-value item:

> `machine.py`'s repeat key hand-enumerates the fields of `Transition` and `Guard`. The
> enumeration is complete today. **If a later cycle adds a field to either class and does not
> update that key, two transitions that differ only in the new field are collapsed into one
> "declared twice" report** — the checker would say a declaration repeats itself where it holds
> two rivals, and the engine would then refuse the message at run time as `ambiguous`.

**This cycle is that later cycle.** It changes what `effects` holds, and the key reads
`tuple(t.effects)`. Fix the trap rather than stepping in it: derive the key from the objects'
own fields so that adding a field to `Transition`, `Guard` or `Effect` either updates the key or
fails a test.

- [ ] **Step 1: Write the failing tests** in `test_machine.py`: an unknown verb is reported with
  the vocabulary; an unknown argument is reported naming it; a missing argument is reported
  naming it; a `string` where `int` is declared and an `int` where `string` is declared are each
  reported; **a `bool` where `int` is declared is reported**; `escalate` with an argument is
  reported; `escalate` with no `args` is accepted. Then one test for the key: a field added to
  `Effect` is reflected in the key — assert it from the class's own fields, not from a literal.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** Replace the effect loop with one that reads `BUILTIN_VERBS`. Replace
  the key's `tuple(t.effects)` and its hand-written guard triple with a derivation.
- [ ] **Step 4: Run the whole suite.** `test_declaration.py` and `test_machine.py` must now be
  green. `test_engine.py` and `test_fold.py` may still fail; Task 3 owns them.
- [ ] **Step 5: Two mutations.** Accept a `bool` for an `int` argument — the bool test must fail.
  Then restore the hand-written key — the key test must fail. Each with a `touch`, each restored.
- [ ] **Step 6: Commit** `machine.py`, `test_machine.py`.

---

### Task 3: The verdict carries effects as data

**Files:** `lib/machines/engine.py` (if needed), `tests/test_engine.py`, `tests/test_fold.py`

**Interfaces:** `Verdict.effects` is a `tuple[Effect, ...]`. `fold.py` is expected to need **no
change** — it copies what a transition carries — and if it does need one, say why in the report.

**The failure this prevents:** a verdict whose effects a reader cannot act on. §6 of the
framework design: *"The engine performs neither. It requires, and something else performs."* A
required set that has to be re-parsed from a string by whoever performs it is the same defect in
a different place.

- [ ] **Step 1: Update the assertions.** Every `effects` assertion in `test_engine.py` and
  `test_fold.py` compares values, so it must now compare `(verb, args)` pairs rather than
  strings. **Do not weaken one into a length check or a truthiness check** — the measured values
  are in Measurements and they stay the subject.
- [ ] **Step 2: Run the whole suite.** It must be green: 407 plus everything Tasks 1 and 2 added.
- [ ] **Step 3: One mutation.** Make `Verdict.effects` always empty; the fixture verdict tests
  must fail. Restore, `touch`, confirm.
- [ ] **Step 4: Commit.**

---

### Task 4: The document

**Files:** `SCHEMA.md`

**The failure this prevents:** a publisher-facing document describing a language the code no
longer accepts. This project has caught that three times in two cycles, and twice it was in
`SCHEMA.md`.

- [ ] **Step 1: Read `SCHEMA.md` end to end**, then change the four places named in
  Measurements. The `effects` bullet gets the new shape, the two keys, the argument types, the
  built-in verb table with its arities, and the sentence that this vocabulary is the framework's
  only until a transport declares its own (cycle C.1). **Keep the paragraph explaining why an
  effect is inert data** — it is the reason the shape is closed, and it is still true.
- [ ] **Step 2: Grep for claims that are now false:**
  `grep -niE "list of strings|vocabulary|label\.add:" plugins/machines/SCHEMA.md plugins/machines/README.md`
  Every surviving hit must still be true.
- [ ] **Step 3: Run the whole suite**, and `PYTHONPATH=lib ./bin/machines-check` on both fixtures.
- [ ] **Step 4: Commit.**

---

### Task 5: The version, the manifests, and the record

**Files:** `plugins/machines/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, the
three generated manifests, and two issues.

- [ ] **Step 1: Bump `0.6.0` → `0.7.0`** in both source manifests. A declaration that parsed will
  not parse, so this is not additive.
- [ ] **Step 2: Run** `python3 scripts/sync-manifests.py`, then `--check` (silent, exit 0), then
  `claude plugin validate .` ("Validation passed"; the `tone-roulette` advisory is pre-existing).
  **Never edit a generated manifest by hand.**
- [ ] **Step 3: Write the outcome into the issues.** `claude-plugins#28`: tick A.2 and say what
  cycle C.1 now inherits. `claude-plugins#55`: the repeat-key trap is closed by Task 2 — say how,
  and leave the rest of that issue open.
- [ ] **Step 4: Run the whole suite one last time** and put the real count in the commit body.
- [ ] **Step 5: Commit.**

---

## Where this plan contradicts its inputs

**1. The framework design's §7 says the vocabulary is the transport's. After this cycle it is
still the framework's.** A.2 changes the shape and keeps the three built-in verbs, so §7's
divergence is half-closed, not closed. **Whoever writes cycle C.1's plan must not read a
structured effect as evidence that the vocabulary opened.** `SCHEMA.md` has to say the same
thing, in Task 4, for the same reason.

**2. The repeat-key fix belongs to `claude-plugins#55`, not to this cycle's charter.** It is here
because this cycle is the one that changes what the key reads, and stepping in a trap that is
already written down would be worse than widening the cycle by one step.

---

## Decisions this plan makes, which nobody agreed to

Each is the controller's, taken on 2026-10-27, and each is cheap to reverse before the task that
depends on it.

1. **`args` is optional and defaults to `{}`.** The alternative is requiring `args: {}` on every
   argument-free verb, which is noise. *Cost: one branch in the parser.*
2. **A verb name gets its own pattern, `VERB`, not `NAME`.** Measured: `NAME` rejects a dot and
   every existing verb has one. *Cost: one constant.*
3. **Argument types are `string`, `int`, `bool` — their own vocabulary, not `FIELD_TYPES`.**
   A header field may not be a string; a verb argument must be. *Cost: one constant, and a
   reader has two lists to keep straight, which Task 4 must make obvious.*
4. **`Verdict.effects` carries `Effect` objects, not rendered strings.** The engine emits data
   and something else performs. *Cost: the assertions in two test files, done in Task 3.*
5. **Task 1 rewrites the fixture and the three in-test declarations, not Task 4.** Found by a
   pre-dispatch scan of this plan: `VALID` is imported by three test files and the fixture is
   read by three more, so leaving them in the old shape would turn Tasks 2 and 3 into a wall of
   parse errors. *Cost: Task 1 is bigger and Task 4 is smaller.*
6. **The suite is red between Task 1 and Task 2.** The alternative is one unreviewable commit.
   *Cost: a reviewer must read Task 1's report to know the red was expected.*
