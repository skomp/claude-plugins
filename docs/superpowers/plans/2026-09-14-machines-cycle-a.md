# `machines` Cycle A — Declaration Schema and Checker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the declaration schema for a protocol machine and the checker that
validates one machine and detects collisions between two, so that a protocol can be
declared and checked before any engine, transport or installer exists.

**Architecture:** A declaration is a fenced `machine` block inside a bundle's `SKILL.md`,
written in a closed YAML language. The checker parses it into a `Machine`, validates its
well-formedness and termination, compiles its prefix pattern into an NFA, and decides
whether two machines can claim the same message by intersecting their prefix languages and
testing emptiness. Nothing in this cycle reads a channel, sends a message, or runs a
publisher's code.

**Tech Stack:** Python 3 (stdlib + PyYAML), `unittest`, bash entry point, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-14-machines-framework-design.md` — read §4, §7, §9
and §12 before starting. The plan argues from the spec; both travel together.

---

## Read this before you write a line

**All code in this plan is a PROPOSAL, not a requirement.** It was written by reasoning,
not by running. `writing-plans-and-dispatches` rule 1 records fourteen real defects on one
project, every one of them in code written into a plan and transcribed faithfully because
it arrived looking like requirements.

**Be sceptical. Report defects rather than fixing them silently.** If you conclude something
in this plan is wrong, say so with evidence rather than implementing something you believe
is incorrect. The contracts — names, signatures, types, and the failure each thing must
prevent — are the binding part. The bodies are a sketch.

## Global Constraints

- **Python 3.8+ syntax.** Measured on this machine: Python 3.11.9. Do not use syntax newer
  than 3.8; this runs on other people's machines.
- **Standard library only, plus PyYAML.** Measured: PyYAML 6.0.3 is present here, **pytest
  is not**. Use `unittest` from the stdlib. Do not add a dependency without raising it.
- **PyYAML is not in the standard library.** The entry point must detect its absence and
  fail with the exact install command, never with a traceback. See Task 8.
- **`python3` here is a pyenv shim** (`/Users/robert/.pyenv/shims/python3`). A repository
  carrying a `.python-version` for an uninstalled interpreter makes the shim fail in a way
  that looks like the tool is broken. The entry point must report that clearly.
- **Use `yaml.safe_load`, never `yaml.load`.** A declaration is untrusted input from a
  publisher.
- **No network, no subprocess, no filesystem writes anywhere in this cycle.** The checker
  reads files and prints. That is all it does.
- **One word, one meaning.** `machine` is the declared automaton. `pattern` is the prefix
  expression. `channel` is where a conversation happens. Do not alternate synonyms.
- Every GitHub issue this work creates carries the `created-by-claude` label.

## File Structure

```
plugins/machines/
  .claude-plugin/plugin.json     manifest
  README.md                      what the plugin is, and the schema by example
  SCHEMA.md                      the declaration language, field by field
  bin/machines-check             bash entry point; finds python3, checks PyYAML, runs the CLI
  lib/machines/
    __init__.py                  empty
    errors.py                    DeclarationError, with a file and a field
    declaration.py               SKILL.md → fenced block → dict → Machine
    machine.py                   the Machine dataclass and its well-formedness checks
    pattern.py                   restricted pattern → AST → NFA
    product.py                   intersection emptiness over two NFAs
    registry.py                  many declarations → collision report
    cli.py                       argument handling and human-readable output
  tests/
    __init__.py                  empty, and REQUIRED — Task 3 onward does
                                 `from tests.test_declaration import VALID`,
                                 which needs `tests` to be a package
    test_declaration.py
    test_machine.py
    test_pattern.py
    test_product.py
    test_registry.py
    fixtures/
      valid-session-relay.md     a complete declaration in a SKILL.md
      no-block.md                a SKILL.md carrying no machine block
.github/workflows/machines-tests.yml
```

Each module has one responsibility and no knowledge of the ones above it. `pattern.py` and
`product.py` know nothing about protocols — they are an automaton library, and they are
tested as one.

---

### Task 1: Plugin skeleton and fenced-block extraction

**Files:**
- Create: `plugins/machines/.claude-plugin/plugin.json`
- Create: `plugins/machines/lib/machines/__init__.py` (empty)
- Create: `plugins/machines/lib/machines/errors.py`
- Create: `plugins/machines/lib/machines/declaration.py`
- Create: `plugins/machines/tests/fixtures/valid-session-relay.md`
- Create: `plugins/machines/tests/fixtures/no-block.md`
- Test: `plugins/machines/tests/test_declaration.py`

**Interfaces:**
- Produces: `extract_block(text: str) -> str` — returns the contents of the single
  ```` ```machine ```` fenced block in a SKILL.md. Raises `DeclarationError` when there is
  no block, or more than one.
- Produces: `class DeclarationError(Exception)` with attributes `message: str`,
  `field: Optional[str]`.

**The failure this prevents:** a SKILL.md with two machine blocks, or none, silently
yielding whichever block a naive regex found first. A bundle whose prose and machine
disagree is the drift this format exists to stop; two blocks is that drift in one file.

- [ ] **Step 1: Write the failing test**

```python
# plugins/machines/tests/test_declaration.py
import unittest
from machines.declaration import extract_block
from machines.errors import DeclarationError

ONE = "intro\n\n```machine\nmachine: x\n```\n\ntrailing prose\n"
NONE = "intro only, no block\n"
TWO = "```machine\na: 1\n```\ntext\n```machine\nb: 2\n```\n"
OTHER_FENCE = "```yaml\nmachine: x\n```\n"

class TestExtractBlock(unittest.TestCase):
    def test_returns_block_contents_without_the_fences(self):
        self.assertEqual(extract_block(ONE), "machine: x\n")

    def test_no_block_raises(self):
        with self.assertRaises(DeclarationError):
            extract_block(NONE)

    def test_two_blocks_raises(self):
        with self.assertRaises(DeclarationError):
            extract_block(TWO)

    def test_a_yaml_fence_is_not_a_machine_fence(self):
        with self.assertRaises(DeclarationError):
            extract_block(OTHER_FENCE)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest tests.test_declaration -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'machines'`.

- [ ] **Step 3: Write the minimal implementation**

PROPOSAL — check the fence regex against the test cases yourself before trusting it.

```python
# plugins/machines/lib/machines/errors.py
class DeclarationError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field
```

```python
# plugins/machines/lib/machines/declaration.py
import re
from .errors import DeclarationError

_FENCE = re.compile(r"^```machine[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)

def extract_block(text):
    blocks = _FENCE.findall(text)
    if not blocks:
        raise DeclarationError("no ```machine block found")
    if len(blocks) > 1:
        raise DeclarationError(
            "found %d ```machine blocks; a bundle declares exactly one" % len(blocks)
        )
    return blocks[0]
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest tests.test_declaration -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Write the manifest and the two fixtures**

`plugin.json` follows the shape of `plugins/agent-operations/.claude-plugin/plugin.json` —
copy its keys, change the values. Version `0.1.0`.

`valid-session-relay.md` carries prose plus one machine block. **Use the declaration in
Task 2 Step 1's `VALID` constant** — that is the only complete declaration in this plan —
with the outer Python triple quotes removed and a paragraph of prose above and below the
fence. `no-block.md` carries prose only.

- [ ] **Step 6: Commit**

```bash
git add plugins/machines/.claude-plugin/plugin.json plugins/machines/lib plugins/machines/tests
git commit -m "Add the machines plugin skeleton and fenced-block extraction"
```

---

### Task 2: Parse a declaration into a Machine

**Files:**
- Create: `plugins/machines/lib/machines/machine.py`
- Modify: `plugins/machines/lib/machines/declaration.py`
- Create: `plugins/machines/SCHEMA.md`
- Test: `plugins/machines/tests/test_declaration.py` (extend)

**Interfaces:**
- Consumes: `extract_block`, `DeclarationError` from Task 1.
- Produces: `parse(text: str) -> Machine` — SKILL.md text to a validated `Machine`.
- Produces: `class Machine` with exactly these attributes:
  `name: str`, `version: str`, `prefix: str`, `roles: Dict[str, str]` (role name → what it
  binds to), `kinds: Set[str]`, `cap: int`, `initial: str`,
  `states: Dict[str, State]`, `transitions: List[Transition]`.
- Produces: `class State` with `name: str`, `holder: Optional[str]`, `terminal: bool`.
- Produces: `class Transition` with `frm: str`, `on: str`, `by: str`, `to: str`,
  `signal: bool`, `effects: List[str]`.

**`frm`, not `from`.** `from` is a Python keyword. The YAML field is `from`; the attribute
is `frm`. Do not "fix" this.

**The failure this prevents:** an unknown field being silently ignored. A publisher who
writes `caps: 10` instead of `cap: 10` must be told, not given a machine with a default cap
they never asked for.

- [ ] **Step 1: Write the failing tests**

```python
# append to plugins/machines/tests/test_declaration.py
from machines.declaration import parse

VALID = """
```machine
machine: session-relay
version: v1
prefix: "session-relay:v1 "
roles:
  initiator: repository
  responder: repository
kinds: [triage, question, answer, conclusion, stalemate]
cap: 10
initial: awaiting-triage
states:
  - { name: awaiting-triage, holder: responder }
  - { name: awaiting-answer, holder: initiator }
  - { name: concluded, terminal: true }
  - { name: stalled, terminal: true }
transitions:
  - { from: awaiting-triage, on: question, by: responder, to: awaiting-answer, signal: true }
  - { from: awaiting-answer, on: answer, by: initiator, to: awaiting-triage, signal: true }
  - { from: awaiting-triage, on: conclusion, by: responder, to: concluded, signal: true,
      effects: ["label.remove:session-relay:open"] }
  - { from: awaiting-triage, on: stalemate, by: responder, to: stalled, signal: true,
      effects: ["label.remove:session-relay:open", "label.add:session-relay:stalled", "escalate"] }
```
"""

class TestParse(unittest.TestCase):
    def test_parses_every_declared_field(self):
        m = parse(VALID)
        self.assertEqual(m.name, "session-relay")
        self.assertEqual(m.version, "v1")
        self.assertEqual(m.prefix, "session-relay:v1 ")
        self.assertEqual(m.cap, 10)
        self.assertEqual(m.initial, "awaiting-triage")
        self.assertEqual(set(m.roles), {"initiator", "responder"})
        self.assertEqual(len(m.states), 4)
        self.assertEqual(len(m.transitions), 4)

    def test_transition_fields_land_on_the_right_attributes(self):
        m = parse(VALID)
        t = m.transitions[0]
        self.assertEqual(t.frm, "awaiting-triage")
        self.assertEqual(t.on, "question")
        self.assertEqual(t.by, "responder")
        self.assertEqual(t.to, "awaiting-answer")
        self.assertTrue(t.signal)
        self.assertEqual(t.effects, [])

    def test_terminal_state_is_terminal_and_others_are_not(self):
        m = parse(VALID)
        self.assertTrue(m.states["concluded"].terminal)
        self.assertFalse(m.states["awaiting-triage"].terminal)

    def test_unknown_top_level_field_raises_and_names_it(self):
        bad = VALID.replace("cap: 10", "cap: 10\ncaps: 12")
        with self.assertRaises(DeclarationError) as ctx:
            parse(bad)
        self.assertEqual(ctx.exception.field, "caps")

    def test_missing_required_field_raises_and_names_it(self):
        bad = VALID.replace("cap: 10\n", "")
        with self.assertRaises(DeclarationError) as ctx:
            parse(bad)
        self.assertEqual(ctx.exception.field, "cap")

    def test_cap_must_be_a_positive_integer(self):
        for value in ("0", "-1", '"ten"'):
            with self.assertRaises(DeclarationError):
                parse(VALID.replace("cap: 10", "cap: " + value))

    def test_duplicate_state_name_raises(self):
        bad = VALID.replace(
            "- { name: concluded, terminal: true }",
            "- { name: awaiting-triage, terminal: true }",
        )
        with self.assertRaises(DeclarationError):
            parse(bad)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest tests.test_declaration -v`
Expected: FAIL with `ImportError: cannot import name 'parse'`.

- [ ] **Step 3: Write the implementation**

PROPOSAL. The contract above is binding; this body is a sketch.

```python
# plugins/machines/lib/machines/machine.py
REQUIRED = ("machine", "version", "prefix", "roles", "kinds",
            "cap", "initial", "states", "transitions")

class State(object):
    def __init__(self, name, holder=None, terminal=False):
        self.name = name
        self.holder = holder
        self.terminal = terminal

class Transition(object):
    def __init__(self, frm, on, by, to, signal=False, effects=None):
        self.frm = frm
        self.on = on
        self.by = by
        self.to = to
        self.signal = signal
        self.effects = list(effects or [])

class Machine(object):
    def __init__(self, name, version, prefix, roles, kinds, cap,
                 initial, states, transitions):
        self.name = name
        self.version = version
        self.prefix = prefix
        self.roles = roles
        self.kinds = kinds
        self.cap = cap
        self.initial = initial
        self.states = states
        self.transitions = transitions
```

```python
# add to plugins/machines/lib/machines/declaration.py
import yaml
from .machine import Machine, State, Transition

_STATE_KEYS = {"name", "holder", "terminal"}
_TRANSITION_KEYS = {"from", "on", "by", "to", "signal", "effects"}

def parse(text):
    data = yaml.safe_load(extract_block(text))
    if not isinstance(data, dict):
        raise DeclarationError("a machine block must be a mapping")

    for key in data:
        if key not in REQUIRED:
            raise DeclarationError("unknown field %r" % key, field=key)
    for key in REQUIRED:
        if key not in data:
            raise DeclarationError("missing field %r" % key, field=key)

    cap = data["cap"]
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise DeclarationError("cap must be a positive integer", field="cap")

    states = {}
    for raw in data["states"]:
        _reject_unknown(raw, _STATE_KEYS, "states")
        name = raw["name"]
        if name in states:
            raise DeclarationError("duplicate state %r" % name, field="states")
        states[name] = State(name, raw.get("holder"), bool(raw.get("terminal", False)))

    transitions = []
    for raw in data["transitions"]:
        _reject_unknown(raw, _TRANSITION_KEYS, "transitions")
        transitions.append(Transition(
            raw["from"], raw["on"], raw["by"], raw["to"],
            bool(raw.get("signal", False)), raw.get("effects"),
        ))

    return Machine(
        data["machine"], data["version"], data["prefix"],
        dict(data["roles"]), set(data["kinds"]), cap,
        data["initial"], states, transitions,
    )

def _reject_unknown(raw, allowed, where):
    for key in raw:
        if key not in allowed:
            raise DeclarationError("unknown field %r in %s" % (key, where), field=key)
```

`REQUIRED` lives in `machine.py`; import it in `declaration.py`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest tests.test_declaration -v`
Expected: all PASS.

- [ ] **Step 5: Write `SCHEMA.md`**

One section per field, each giving the type, whether it is required, and **the failure the
field prevents**. The reader must be able to find the cap without reading any code.

- [ ] **Step 6: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/lib/machines/declaration.py plugins/machines/SCHEMA.md plugins/machines/tests/test_declaration.py
git commit -m "Parse a machine declaration into a validated Machine"
```

---

### Task 3: Well-formedness and termination

**Files:**
- Modify: `plugins/machines/lib/machines/machine.py`
- Test: `plugins/machines/tests/test_machine.py`

**Interfaces:**
- Consumes: `Machine`, `State`, `Transition`, `DeclarationError` from Task 2.
- Produces: `check_machine(m: Machine) -> List[str]` — returns a list of human-readable
  problems. **Empty list means well-formed.** It returns problems rather than raising,
  because a publisher wants every problem at once, not the first one.

The checks, each its own test:

1. `initial` names a declared state.
2. Every transition's `from` and `to` name declared states.
3. Every transition's `on` is in `kinds`.
4. Every transition's `by` is a declared role.
5. Every state's `holder`, when set, is a declared role.
6. A terminal state has no outgoing transition.
7. At least one state is terminal.
8. Every state is reachable from `initial`.
9. **Every state can reach a terminal state.** This is the termination property, and it is
   the reason this checker exists.
10. **Every effect is in the fixed vocabulary.** The vocabulary is exactly
    `label.add:<name>`, `label.remove:<name>` and `escalate`. Nothing else.

**The failure this prevents:** check 9 is the one item 6 exercised by hand. A machine with
a state from which no terminal state is reachable is a protocol that can run forever, and
prose cannot detect it.

**Check 10 is what keeps the language closed**, which the spec's §7 calls load-bearing twice
over: it is the restriction that keeps the properties decidable *and* the restriction that
stops an installed machine being a program. An unvalidated `effects` list is a hole straight
through both — a publisher writing `effects: ["run:curl ..."]` would be declaring an action,
and an engine that later grew to honour it would be executing a stranger's instruction. It
must be rejected here, at the only place it can be.

- [ ] **Step 1: Write the failing tests**

```python
# plugins/machines/tests/test_machine.py
import unittest
from machines.declaration import parse
from machines.machine import check_machine
from tests.test_declaration import VALID  # the known-good declaration

def mutate(old, new):
    return parse(VALID.replace(old, new))

class TestCheckMachine(unittest.TestCase):
    def test_the_known_good_machine_has_no_problems(self):
        self.assertEqual(check_machine(parse(VALID)), [])

    def test_initial_must_name_a_declared_state(self):
        m = mutate("initial: awaiting-triage", "initial: nowhere")
        self.assertTrue(any("nowhere" in p for p in check_machine(m)))

    def test_transition_to_an_undeclared_state_is_reported(self):
        m = mutate("to: awaiting-answer, signal: true }",
                   "to: nowhere, signal: true }")
        self.assertTrue(any("nowhere" in p for p in check_machine(m)))

    def test_transition_on_an_undeclared_kind_is_reported(self):
        m = mutate("on: question", "on: shouting")
        self.assertTrue(any("shouting" in p for p in check_machine(m)))

    def test_transition_by_an_undeclared_role_is_reported(self):
        m = mutate("by: responder, to: awaiting-answer",
                   "by: bystander, to: awaiting-answer")
        self.assertTrue(any("bystander" in p for p in check_machine(m)))

    def test_a_terminal_state_with_an_outgoing_transition_is_reported(self):
        # Give the terminal state `concluded` an exit back to a state that
        # already exists. No new state, no YAML indentation splice.
        m = parse(VALID)
        m.transitions.append(type(m.transitions[0])(
            "concluded", "question", "responder", "awaiting-triage"))
        self.assertTrue(any("concluded" in p for p in check_machine(m)))

    def test_a_machine_with_no_terminal_state_is_reported(self):
        m = parse(VALID)
        for s in m.states.values():
            s.terminal = False
        self.assertTrue(any("terminal" in p for p in check_machine(m)))

    def test_an_unreachable_state_is_reported(self):
        m = parse(VALID)
        m.states["orphan"] = type(m.states["concluded"])("orphan", terminal=True)
        self.assertTrue(any("orphan" in p for p in check_machine(m)))

    def test_a_state_that_cannot_reach_a_terminal_state_is_reported(self):
        # Remove both exits from awaiting-triage, leaving a two-state loop.
        m = parse(VALID)
        m.transitions = [t for t in m.transitions
                         if t.on not in ("conclusion", "stalemate")]
        problems = check_machine(m)
        self.assertTrue(any("awaiting-triage" in p and "terminal" in p
                            for p in problems))

    def test_an_effect_outside_the_vocabulary_is_reported(self):
        m = mutate('"label.add:session-relay:stalled"', '"run:curl example.com"')
        self.assertTrue(any("run:curl" in p for p in check_machine(m)))

    def test_each_permitted_effect_form_is_accepted(self):
        for effect in ("escalate", "label.add:anything", "label.remove:anything"):
            m = mutate('"escalate"', '"%s"' % effect)
            self.assertEqual(check_machine(m), [], effect)
```

- [ ] **Step 2: Run and confirm failure**

Run: `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest tests.test_machine -v`
Expected: FAIL with `ImportError: cannot import name 'check_machine'`.

- [ ] **Step 3: Implement `check_machine`**

PROPOSAL. Check 9 is a backward reachability from the terminal set — build the reverse
graph, flood from every terminal state, and report any state not reached.

```python
# add to plugins/machines/lib/machines/machine.py
def check_machine(m):
    problems = []
    names = set(m.states)

    if m.initial not in names:
        problems.append("initial state %r is not declared" % m.initial)

    for t in m.transitions:
        for label, value in (("from", t.frm), ("to", t.to)):
            if value not in names:
                problems.append("transition %s names undeclared state %r"
                                % (label, value))
        if t.on not in m.kinds:
            problems.append("transition on names undeclared kind %r" % t.on)
        if t.by not in m.roles:
            problems.append("transition by names undeclared role %r" % t.by)

    for s in m.states.values():
        if s.holder is not None and s.holder not in m.roles:
            problems.append("state %r has undeclared holder %r" % (s.name, s.holder))

    for t in m.transitions:
        for effect in t.effects:
            if effect != "escalate" and not (
                effect.startswith("label.add:") or effect.startswith("label.remove:")
            ):
                problems.append("effect %r is not in the vocabulary "
                                "(label.add:<name>, label.remove:<name>, escalate)"
                                % effect)

    terminals = set(n for n, s in m.states.items() if s.terminal)
    if not terminals:
        problems.append("no state is terminal; the machine cannot terminate")

    for t in m.transitions:
        if t.frm in terminals:
            problems.append("terminal state %r has an outgoing transition" % t.frm)

    forward = {}
    backward = {}
    for t in m.transitions:
        forward.setdefault(t.frm, set()).add(t.to)
        backward.setdefault(t.to, set()).add(t.frm)

    reachable = _flood({m.initial}, forward)
    for name in sorted(names - reachable):
        problems.append("state %r is not reachable from the initial state" % name)

    can_finish = _flood(terminals, backward)
    for name in sorted(reachable - can_finish):
        problems.append("state %r cannot reach a terminal state" % name)

    return problems

def _flood(seeds, graph):
    seen = set()
    stack = list(seeds)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, ()))
    return seen
```

- [ ] **Step 4: Run and confirm all pass**

Run: `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest tests.test_machine -v`

- [ ] **Step 5: Commit**

```bash
git add plugins/machines/lib/machines/machine.py plugins/machines/tests/test_machine.py
git commit -m "Check a machine for well-formedness and termination"
```

---

### Task 4: The restricted pattern language

**Files:**
- Create: `plugins/machines/lib/machines/pattern.py`
- Test: `plugins/machines/tests/test_pattern.py`

**Interfaces:**
- Produces: `parse_pattern(src: str) -> Node` — an AST.
- Produces: `class PatternError(DeclarationError)`.
- Node types: `Lit(chars: FrozenSet[Tuple[int,int]])` (a set of inclusive codepoint
  ranges), `Cat(left, right)`, `Alt(left, right)`, `Star(node)`, `Empty()`.

**The grammar, which is the whole point of the restriction:**

```
pattern := alt
alt     := cat ('|' cat)*
cat     := rep*
rep     := atom ('*' | '+' | '?')?
atom    := literal | '.' | class | '(' alt ')'
class   := '[' '^'? item+ ']'
item    := char '-' char | char
literal := any char except | * + ? ( ) [ ] . \  — or '\' followed by one of those
```

**Nothing else is accepted.** No backreferences, no lookaround, no anchors, no `{n,m}`, no
named groups, no shorthand classes. `+` compiles to `Cat(x, Star(x))` and `?` to
`Alt(x, Empty())`, so the NFA builder in Task 5 handles three operators, not five.

**The failure this prevents:** a publisher writing `(a)\1` and the checker accepting it.
Backreferences are not regular, so a pattern containing one cannot be intersected, and the
install-time guarantee would silently stop holding for that machine. Rejecting at parse time
is the only place this can be caught.

- [ ] **Step 1: Write the failing tests**

```python
# plugins/machines/tests/test_pattern.py
import unittest
from machines.pattern import parse_pattern, PatternError

class TestParsePattern(unittest.TestCase):
    def test_accepts_a_plain_literal(self):
        self.assertIsNotNone(parse_pattern("session-relay:v1 "))

    def test_accepts_the_documented_example(self):
        self.assertIsNotNone(parse_pattern('received from: [^ ]*, type: "force"'))

    def test_accepts_alternation_grouping_and_repetition(self):
        for src in ("a|b", "(ab)*", "a+b?", "[a-z0-9]+", "."):
            self.assertIsNotNone(parse_pattern(src), src)

    def test_rejects_a_backreference(self):
        with self.assertRaises(PatternError):
            parse_pattern(r"(a)\1")

    def test_rejects_lookaround(self):
        with self.assertRaises(PatternError):
            parse_pattern("(?=a)b")

    def test_rejects_a_counted_repetition(self):
        with self.assertRaises(PatternError):
            parse_pattern("a{2,3}")

    def test_rejects_an_unclosed_group(self):
        with self.assertRaises(PatternError):
            parse_pattern("(ab")

    def test_rejects_an_unclosed_class(self):
        with self.assertRaises(PatternError):
            parse_pattern("[a-z")

    def test_escaped_metacharacter_is_a_literal(self):
        self.assertIsNotNone(parse_pattern(r"a\*b"))
```

- [ ] **Step 2: Run and confirm failure**

Run: `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest tests.test_pattern -v`

- [ ] **Step 3: Implement a recursive-descent parser**

PROPOSAL. Write it as a class holding `src` and a cursor. Represent a character class as a
frozenset of `(low, high)` inclusive codepoint ranges; `.` is `((0, 0x10FFFF),)`; a negated
class is the complement of its ranges over that same span, computed by sorting and walking
the gaps. Keep the complement helper separate and test it — off-by-one in range complement
is the defect most likely to survive into Task 6, where it becomes a wrong collision verdict
rather than a visible crash.

Reject `(?` outright with a message naming lookaround, and reject `\` followed by a digit
with a message naming backreferences. A generic "bad escape" tells a publisher nothing.

- [ ] **Step 4: Run and confirm all pass**

- [ ] **Step 5: Commit**

```bash
git add plugins/machines/lib/machines/pattern.py plugins/machines/tests/test_pattern.py
git commit -m "Parse the restricted prefix pattern language"
```

---

### Task 5: Compile a pattern to an NFA

**Files:**
- Modify: `plugins/machines/lib/machines/pattern.py`
- Test: `plugins/machines/tests/test_pattern.py` (extend)

**Interfaces:**
- Consumes: `parse_pattern`, the node types from Task 4.
- Produces: `class NFA` with `start: int`, `accept: Set[int]`,
  `moves: Dict[int, List[Tuple[FrozenSet[Tuple[int,int]], int]]]`,
  `epsilon: Dict[int, Set[int]]`.
- Produces: `compile_pattern(src: str) -> NFA`.
- Produces: `NFA.accepts(text: str) -> bool` — **for tests only.** The checker never runs a
  pattern against a string; it only intersects two of them. This method exists so Task 5 can
  be verified without Task 6.

**The failure this prevents:** an NFA that is wrong in a way only intersection reveals.
`accepts` lets Task 5 be tested against strings, where a wrong answer is obvious, rather
than against another automaton, where it is not.

- [ ] **Step 1: Write the failing tests**

```python
# append to plugins/machines/tests/test_pattern.py
from machines.pattern import compile_pattern

class TestCompilePattern(unittest.TestCase):
    def check(self, src, yes, no):
        nfa = compile_pattern(src)
        for s in yes:
            self.assertTrue(nfa.accepts(s), "%r should match %r" % (src, s))
        for s in no:
            self.assertFalse(nfa.accepts(s), "%r should not match %r" % (src, s))

    def test_literal(self):
        self.check("abc", ["abc"], ["ab", "abcd", "", "abd"])

    def test_alternation(self):
        self.check("a|bc", ["a", "bc"], ["b", "abc", ""])

    def test_star_matches_zero_or_more(self):
        self.check("ab*", ["a", "ab", "abbb"], ["b", "", "ba"])

    def test_plus_requires_one(self):
        self.check("ab+", ["ab", "abbb"], ["a", "", "b"])

    def test_question_is_zero_or_one(self):
        self.check("ab?", ["a", "ab"], ["abb", ""])

    def test_class_and_negated_class(self):
        self.check("[a-c]", ["a", "b", "c"], ["d", "", "aa"])
        self.check("[^a-c]", ["d", "z"], ["a", "b", ""])

    def test_dot_matches_one_of_anything(self):
        self.check(".", ["a", "Z", "9"], ["", "ab"])

    def test_the_documented_example(self):
        self.check('received from: [^ ]*, type: "force"',
                   ['received from: alpha, type: "force"',
                    'received from: , type: "force"'],
                   ['received from: two words, type: "force"',
                    'received from: alpha, type: "soft"'])
```

- [ ] **Step 2: Run and confirm failure**

- [ ] **Step 3: Implement Thompson construction**

PROPOSAL. Allocate integer state ids from a counter. `Lit` makes two states and one
charset move. `Cat` joins with an epsilon. `Alt` adds a new start with two epsilons and a
new accept. `Star` adds a new start/accept pair with the four standard epsilons. `Empty`
makes one state that is its own accept.

`accepts` is a subset simulation: epsilon-close the start, then for each character step
every move whose charset contains its codepoint, epsilon-close, and finally test whether the
set meets `accept`. **Match the whole string, not a prefix** — the prefix semantics live in
Task 6, and putting them here too would double-apply them.

- [ ] **Step 4: Run and confirm all pass**

- [ ] **Step 5: Commit**

```bash
git add plugins/machines/lib/machines/pattern.py plugins/machines/tests/test_pattern.py
git commit -m "Compile a restricted pattern to an NFA"
```

---

### Task 6: Do two machines claim the same message?

**Files:**
- Create: `plugins/machines/lib/machines/product.py`
- Test: `plugins/machines/tests/test_product.py`

**Interfaces:**
- Consumes: `NFA`, `compile_pattern` from Task 5.
- Produces: `patterns_collide(a: str, b: str) -> bool`.

**The definition, and it is not "the two patterns are equal".** A machine claims a message
when its pattern matches a **prefix** of that message. So machine `a` claims the set
`L(a)·Σ*`, and two machines collide exactly when

```
L(a)·Σ*  ∩  L(b)·Σ*  ≠  ∅
```

which holds if and only if some string accepted by one is a prefix of some string accepted
by the other. Concretely: append a self-loop over every character to each NFA's accepting
states, then test the intersection for emptiness by an on-the-fly product search over pairs
of epsilon-closed state sets.

**This subsumes the literal case.** `session-relay:` and `session-relay:v1 ` collide under
this definition and would not under string equality — and that pair is the realistic
mistake, because it is what a publisher produces when versioning a prefix.

**The failure this prevents:** two machines installed side by side, both claiming the same
inbound message, with which one wins decided by registry iteration order. That is the
runtime race `#26` says the installation check exists to make impossible.

**Charset intersection is where this goes wrong.** Two moves can be taken together only on
the characters both charsets contain, so the product steps on `ranges_intersect(x, y)` and
skips the pair when that is empty. Write `ranges_intersect` as its own function and test it
directly — including adjacent-but-disjoint ranges such as `(1,5)` against `(6,9)`, which is
the case an off-by-one turns into a false collision.

- [ ] **Step 1: Write the failing tests**

```python
# plugins/machines/tests/test_product.py
import unittest
from machines.product import patterns_collide, ranges_intersect

class TestRangesIntersect(unittest.TestCase):
    def test_overlapping(self):
        self.assertTrue(ranges_intersect(frozenset([(1, 5)]), frozenset([(3, 9)])))

    def test_adjacent_but_disjoint(self):
        self.assertFalse(ranges_intersect(frozenset([(1, 5)]), frozenset([(6, 9)])))

    def test_touching_at_one_codepoint(self):
        self.assertTrue(ranges_intersect(frozenset([(1, 5)]), frozenset([(5, 9)])))

class TestPatternsCollide(unittest.TestCase):
    def test_identical_patterns_collide(self):
        self.assertTrue(patterns_collide("abc", "abc"))

    def test_disjoint_literals_do_not_collide(self):
        self.assertFalse(patterns_collide("abc", "xyz"))

    def test_a_proper_prefix_collides(self):
        self.assertTrue(patterns_collide("session-relay:", "session-relay:v1 "))

    def test_disjoint_classes_do_not_collide(self):
        self.assertFalse(patterns_collide("[a-c]x", "[d-f]x"))

    def test_overlapping_classes_collide(self):
        self.assertTrue(patterns_collide("[a-d]x", "[c-f]x"))

    def test_star_can_reach_the_other_pattern(self):
        self.assertTrue(patterns_collide("a*b", "aab"))

    def test_alternation_collides_when_one_branch_does(self):
        self.assertTrue(patterns_collide("foo|bar", "bar"))
        self.assertFalse(patterns_collide("foo|bar", "baz"))

    def test_two_real_looking_protocol_prefixes_do_not_collide(self):
        self.assertFalse(patterns_collide("session-relay:v1 ", "machines:v1 "))
```

- [ ] **Step 2: Run and confirm failure**

- [ ] **Step 3: Implement the product search**

PROPOSAL. Breadth-first over pairs `(closure_a, closure_b)` of epsilon-closed NFA state
sets, starting from both start closures. A pair is accepting when both sets meet their NFA's
accept set. Successors: for every move out of `closure_a` and every move out of
`closure_b`, if `ranges_intersect(ca, cb)` then step both. Memoise visited pairs as
`(frozenset, frozenset)`; the search terminates because there are finitely many such pairs.

Add the `Σ*` self-loop by inserting, for each accepting state, a move on the full range
`(0, 0x10FFFF)` back to itself, before searching.

- [ ] **Step 4: Run and confirm all pass**

- [ ] **Step 5: Commit**

```bash
git add plugins/machines/lib/machines/product.py plugins/machines/tests/test_product.py
git commit -m "Decide whether two prefix patterns can claim one message"
```

---

### Task 7: The registry and the collision report

**Files:**
- Create: `plugins/machines/lib/machines/registry.py`
- Test: `plugins/machines/tests/test_registry.py`

**Interfaces:**
- Consumes: `parse`, `check_machine`, `patterns_collide`.
- Produces: `check_all(machines: List[Machine]) -> Report`.
- Produces: `class Report` with **three** attributes: `examined: int` (how many machines
  were looked at, including zero), `problems: Dict[str, List[str]]` (machine name → its own
  well-formedness problems) and `collisions: List[Tuple[str, str]]` (pairs of machine names,
  each pair once, in sorted order).

**The failure this prevents:** reporting "no collisions" for a set of machines the checker
failed to load. An empty input must produce a report that says zero machines were examined,
and the caller in Task 8 must print that count. `evidence-discipline`: a check that finds
nothing because it looked at nothing must not read as a pass.

Two machines with the **same name and different versions** are not a collision — they are
one protocol's history, and §11.2 keeps old versions on purpose. Skip the pair.

- [ ] **Step 1: Write the failing tests**

```python
# plugins/machines/tests/test_registry.py
import unittest
from machines.declaration import parse
from machines.registry import check_all
from tests.test_declaration import VALID

def named(name, prefix, version="v1"):
    text = VALID.replace("machine: session-relay", "machine: " + name)
    text = text.replace('prefix: "session-relay:v1 "', 'prefix: "%s"' % prefix)
    return parse(text.replace("version: v1", "version: " + version))

class TestCheckAll(unittest.TestCase):
    def test_no_machines_reports_zero_examined_and_no_collisions(self):
        report = check_all([])
        self.assertEqual(report.collisions, [])
        self.assertEqual(report.examined, 0)

    def test_two_disjoint_machines_do_not_collide(self):
        report = check_all([named("alpha", "alpha:v1 "), named("beta", "beta:v1 ")])
        self.assertEqual(report.collisions, [])
        self.assertEqual(report.examined, 2)

    def test_two_machines_claiming_one_prefix_collide(self):
        report = check_all([named("alpha", "shared:v1 "), named("beta", "shared:v1 ")])
        self.assertEqual(report.collisions, [("alpha", "beta")])

    def test_a_proper_prefix_collides(self):
        report = check_all([named("alpha", "shared:"), named("beta", "shared:v1 ")])
        self.assertEqual(report.collisions, [("alpha", "beta")])

    def test_two_versions_of_one_machine_are_not_a_collision(self):
        report = check_all([named("alpha", "alpha:v1 ", "v1"),
                            named("alpha", "alpha:v1 ", "v2")])
        self.assertEqual(report.collisions, [])

    def test_a_malformed_machine_is_reported_under_its_own_name(self):
        bad = named("alpha", "alpha:v1 ")
        bad.initial = "nowhere"
        report = check_all([bad, named("beta", "beta:v1 ")])
        self.assertIn("alpha", report.problems)
        self.assertNotIn("beta", report.problems)
```

- [ ] **Step 2: Run and confirm failure**

- [ ] **Step 3: Implement `check_all`**

PROPOSAL. Give `Report` an `examined: int`. Run `check_machine` on each machine, keeping
only non-empty problem lists. Then for every unordered pair whose `name` differs, call
`patterns_collide(a.prefix, b.prefix)` and record `tuple(sorted((a.name, b.name)))`.
Sort `collisions` before returning so the output is stable.

- [ ] **Step 4: Run and confirm all pass**

- [ ] **Step 5: Commit**

```bash
git add plugins/machines/lib/machines/registry.py plugins/machines/tests/test_registry.py
git commit -m "Collect machines and report collisions between them"
```

---

### Task 8: The entry point, the README, and CI

**Files:**
- Create: `plugins/machines/lib/machines/cli.py`
- Create: `plugins/machines/bin/machines-check`
- Create: `plugins/machines/README.md`
- Create: `.github/workflows/machines-tests.yml`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md` (the root overview table)

**Interfaces:**
- Consumes: `check_all`, `parse`, `DeclarationError`.
- Produces: `machines-check <path>...` — each path is a `SKILL.md` or a directory searched
  for one. Exit `0` when every machine is well-formed and nothing collides, `1` when a
  problem or collision is found, `2` when the tool could not run at all.

**Three exit codes, not two.** A tool that cannot run must not exit `1`, because `1` reads
as "checked, and found a problem". Missing PyYAML, an unreadable path and a broken pyenv
shim are all `2`.

**The output must state how many machines were examined, always**, including zero. "No
collisions found" after examining nothing is the `evidence-discipline` failure this repo
documents; "Examined 0 machines" cannot be misread.

- [ ] **Step 1: Write the failing test**

```python
# append to plugins/machines/tests/test_registry.py
import io, contextlib
from machines.cli import main

class TestCli(unittest.TestCase):
    def test_no_paths_exits_2_and_says_so(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            code = main([])
        self.assertEqual(code, 2)

    def test_a_missing_path_exits_2(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            code = main(["/nonexistent/SKILL.md"])
        self.assertEqual(code, 2)

    def test_a_valid_fixture_exits_0_and_reports_the_count(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["tests/fixtures/valid-session-relay.md"])
        self.assertEqual(code, 0)
        self.assertIn("Examined 1 machine", out.getvalue())
```

- [ ] **Step 2: Run and confirm failure**

- [ ] **Step 3: Implement `cli.py` and the bash entry point**

PROPOSAL for `bin/machines-check`:

```bash
#!/usr/bin/env bash
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "machines-check: python3 not found on PATH" >&2
  exit 2
fi
if ! python3 -c "import yaml" >/dev/null 2>&1; then
  echo "machines-check: PyYAML is required. Install it with:" >&2
  echo "    python3 -m pip install PyYAML" >&2
  exit 2
fi
PYTHONPATH="$HERE/../lib${PYTHONPATH:+:$PYTHONPATH}" \
  exec python3 -m machines.cli "$@"
```

`cli.py` ends with `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`.

A broken pyenv shim makes `python3 -c "import yaml"` fail with its own message on stderr;
let that through rather than swallowing it, so the user sees the real cause.

- [ ] **Step 4: Run the whole suite and confirm it passes**

Run: `cd plugins/machines && PYTHONPATH=lib:. python3 -m unittest discover -s tests -t . -v`

- [ ] **Step 5: Verify the entry point by hand**

```bash
chmod +x plugins/machines/bin/machines-check
plugins/machines/bin/machines-check plugins/machines/tests/fixtures/valid-session-relay.md
echo "exit=$?"
```
Expected: `Examined 1 machine`, `exit=0`.

- [ ] **Step 6: Add CI, the marketplace entry and the READMEs**

`.github/workflows/machines-tests.yml` follows `tone-roulette-tests.yml`: `on: [push,
pull_request]`, `runs-on: ubuntu-latest`, `actions/checkout@v4`, then
`pip install PyYAML` and the `unittest discover` command from Step 4.

Add a `machines` entry to `.claude-plugin/marketplace.json` beside the existing four, and a
row to the root `README.md` table. Write `plugins/machines/README.md` in the voice of the
other plugin READMEs, and say plainly that cycle A ships **the schema and the checker only**
— no engine, no installer, no dispatcher.

- [ ] **Step 7: Commit**

```bash
git add plugins/machines .github/workflows/machines-tests.yml .claude-plugin/marketplace.json README.md
git commit -m "Add the machines-check entry point, CI and the plugin README"
```

---

## After cycle A, before cycle B

**Walk the seven backport rows from the spec's §10 against this schema, on paper, and write
what you find into `claude-plugins#28`.** The spec says this is the cheapest
defect-finder in the whole design and that cycle B must not start before it. It costs
reading and nothing else.

Two rows are known in advance to need attention:

- **"Four guards in fixed order"** is expected *not* to be expressible; §10 argues that is
  the good kind of defect. Confirm the argument or report that it fails.
- **"The signal and the header can disagree about `blocking`"** is the row that decides
  whether the framework earned its place. The schema above has no way to say it, because
  §10's claim is that the *engine* expresses it by computing both values, not the
  declaration. Cycle A cannot settle it; record that it is deferred to cycle B rather than
  letting it look answered.

## Housekeeping

- `.claude/settings.local.json` in this worktree holds a **throwaway** spike hook. It is
  untracked, this repository has **no `.gitignore`**, and it must not be committed. A fresh
  session loads it and settles the spec's §11.1 trigger question; remove it afterwards.
- Do not `git add -A` or `git commit -a` in this checkout. Stage the explicit paths each
  task names.
