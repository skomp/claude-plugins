# `machines` Cycle C.1–C.3 — the transport declaration, the open vocabulary, the runner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A transport declares its verbs in a `transport.yaml`. The checker validates a
machine's effects against those verbs instead of a hardcoded table. A runner calls a
transport's entry point and enforces bounds on each call. The verdict splits its effects into
the ones installed code performs and the ones Claude performs.

**Architecture:** One new parser module, `transport.py`, written in the closed-language
discipline of `declaration.py`. `check_machine` stops reading `BUILTIN_VERBS` and takes the
declared verbs as an argument. A new `runner.py` is the only code in the framework that spawns
a publisher's file. The engine gains an optional `transport=` and still performs nothing.
**Out of scope: C.4, the installer.** It gets its own plan, and it is blocked on §11 item 1 of
the transport design.

**Tech Stack:** Python 3 (stdlib + PyYAML), `unittest`, `subprocess`. Nothing new.

**Spec:** `docs/superpowers/specs/2026-10-27-machines-transport-declaration-design.md`, §2–§8,
§12 rows C.1–C.3 and §13. Read §13 in full: it holds seven decisions that this plan applies
without re-arguing them. Also `docs/superpowers/specs/2026-09-14-machines-framework-design.md`
§6–§9.

**Issues:** `claude-plugins#28` carries the cycle list. Task 0 works off `claude-plugins#55`,
which asks to be done "at the start of cycle C".

---

## Read this before you write a line

**All code in this plan is a PROPOSAL, not a requirement.** The binding part is the contracts:
names, signatures, types, and the failure each piece must prevent. Every plan for this plugin so
far has carried defects in code that was reasoned out rather than run.

**Be sceptical. Report defects rather than fixing them silently.** If you conclude something
here is wrong, say so with evidence rather than implementing something you believe is incorrect.

**Three things you must not do:**

1. **The engine never calls a verb.** `engine.py`, `fold.py` and `envelope.py` must still
   import nothing that could act. `test_the_engine_module_imports_nothing_that_could_act` pins
   this. The runner is a separate module, and the engine never imports it.
2. **Never import or execute a publisher's file in order to read its declaration.**
   `transport.yaml` is parsed as data. Only `runner.py` runs `bin/transport`, and only to
   perform a call.
3. **Never hand a short result on as a complete one.** A call that hits the time bound or the
   output bound returns `{"ok": false, ...}`. A truncated channel read would be the cap bypass
   that §8 warns about.

---

## Global Constraints

- **Python 3 stdlib + PyYAML only.**
- **Run the suite from `plugins/machines`:**
  `PYTHONPATH=lib:. python3 -m unittest discover -s tests -t .`
- **Baseline: 443 tests pass at `d07675b`** (main after `PR: claude-plugins#58`). If your
  starting count differs, stop and report it.
- **Every new test must be seen to fail under a mutation of the code it covers.** Put the
  mutation and its verbatim failure in the commit body.
- **Mutate a copy under `/tmp`**, never the checkout:
  `git archive HEAD | tar -x -C /tmp/<dir>`. Run the mutated copy with `python3 -B`, or
  `touch` the file after every mutation and every restore. If you skip this, a same-second
  same-size restore reuses the mutated `.pyc`.
- **Stage explicit paths.** Never `git add -A` or `git commit -a`. Another agent may be live.
- **Commit subject style:** `machines: <what changed> (cycle C, task N)`.
- **Commit trailer:** `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
  **Never a `Claude-Session:` line**, and never a `claude.ai/code/session_` URL anywhere.
- **A constant ships with its measurement beside it**: the command, the number and the host.
- **`SCHEMA.md` and `README.md` change in the same commit as the behaviour they describe.**
- Error messages name the offending key or value, as `declaration.py`'s do.

## Already measured — do not re-derive

| What | Value | How |
|---|---|---|
| Suite at `d07675b` | 443 tests, OK, 5.3 s | the command above |
| Largest trace message, as JSON | 152 bytes (paxos fixture), 142 bytes (session-relay fixture) | `len(json.dumps(m))` over `tests/fixtures/trace-*.json` |
| `MAX_FOLD_STEPS` | 10000 | `fold.py:48` |
| One `gh api …/issues/28/comments?per_page=100` | 0.64 s and 0.65 s | Python `time.monotonic()` around `subprocess.run`, 2026-11-05, Raspberry Pi, aarch64, 4 cores |
| One `gh issue view 28 --comments --json comments` | 1.31 s, 2.03 s, 1.37 s | same host and method |
| YAML booleans | `MachineSafeLoader` in `declaration.py` resolves only `true`/`false`; `yes`/`on` stay strings | read the class |
| Parts of `claude-plugins#55` already done | `wrong_type`, `read_guard` and `candidates` are public in `fold.py`, and `engine.py` imports those names (commits `c1e28d0`, `96ff98d`) | `grep -n "^def " lib/machines/fold.py` |

**Proposed bounds for the runner, derived from the table** (record the derivation in the
comment beside each constant):

- `MAX_OUTPUT_BYTES = 8 * 1024 * 1024`. 10000 messages × 152 bytes ≈ 1.5 MB is a channel at
  the fold limit. A factor of about 5 leaves room for longer header fields. Above this, the
  fold would truncate anyway.
- `CALL_TIMEOUT_SECONDS = 120`. A channel at the fold limit is 100 pages × about 0.65 s, which
  is about 65 s. Double it. A `session-relay` thread is one page, about 0.65–2 s.

## Review Focus

These are the inputs most likely to bite a real user that no task's happy-path tests reach.
Each one has a test in the task named after it.

1. **`total_order: yes`, `total_order: "true"` or `total_order` absent.** Each one is refused
   by name, never coerced. → Task 1
2. **An entry point that is missing, not executable, or exits non-zero after printing valid
   JSON.** This is "the transport could not run" (`TransportCannotRun`), never `ok: false`, and
   the stdout is discarded. → Task 3
3. **A transport that hangs, or that floods stdout, including through a child process it
   spawned.** The call returns `{"ok": false}` within the bound, and no process stays alive.
   → Task 3
4. **A `channel.list` that returns a message with a `body` key, or a message missing `envelope`.**
   `parse_trace` refuses it by name, at the boundary. → Task 3
5. **A machine that names a verb the transport declares with `performer: agent`.** It checks
   clean, it is reported as an agent effect, and the runner refuses to call the entry point for
   it. → Tasks 2, 3, 4

---

## File map

| File | Change | Task |
|---|---|---|
| `lib/machines/fold.py`, `engine.py`, tests, docs | the `claude-plugins#55` tidy-up | 0 |
| `lib/machines/transport.py` | **new**: `Verb`, `Transport`, `parse_transport`, `load_transport` | 1 |
| `tests/test_transport.py` | **new** | 1 |
| `tests/fixtures/transport-fake/transport/transport.yaml` | **new**: the fixture transport's declaration | 1 |
| `tests/fixtures/transport-fake/transport/bin/transport` | **new**: an executable Python script that serves the trace fixtures | 3 |
| `lib/machines/machine.py` | `BUILTIN_VERBS` deleted; `check_machine(m, verbs=None)`; `arg_type` made public | 2 |
| `lib/machines/registry.py` | `check_all(machines, transport=None)`; `Report` gains two fields | 2 |
| `lib/machines/cli.py`, `bin/machines-check` | `--transport <path>` | 2 |
| `lib/machines/runner.py` | **new**: `call`, `read_channel`, `TransportCannotRun` | 3 |
| `tests/test_runner.py` | **new** | 3 |
| `lib/machines/engine.py` | `transport=` on `verdict` and `gate`; two classified lists | 4 |
| `SCHEMA.md`, `README.md` | in the same commit as each behaviour | 1–4 |
| `.claude-plugin/plugin.json`, marketplace, generated manifests | 0.7.0 → 0.8.0 | 5 |

---

### Task 0: The `claude-plugins#55` tidy-up

**Files:** whatever each item names. Mostly `lib/machines/fold.py`, `lib/machines/engine.py`,
`tests/test_*.py`, `SCHEMA.md` and `README.md`.

**Interfaces:** none. Behaviour must not change. A test whose expected value changes is a
behaviour change: stop and report it.

- [ ] **Step 1:** Read the body of `claude-plugins#55`
  (`gh issue view 55 --repo skomp/claude-plugins`). For each bullet, check whether it still
  holds at `HEAD`. The two "shortest fuse" items look done already (see the measured table).
  Confirm that with `grep`, then record each one as done, citing the commit that did it.
- [ ] **Step 2:** Fix each code-tidying item, each test-hygiene item and each
  documentation-precision item that still holds. If an item should stand, write one sentence
  saying why. Each changed test must still be able to fail: one mutation per changed test, in
  the commit body. Move the test classes that sit below `if __name__ == "__main__"` above it,
  and give `test_clock.py` the block. Then run each of the three files directly with
  `python3 tests/test_x.py`, and confirm that each one reports its full count.
- [ ] **Step 3:** **Do not decide the four design questions.** For "a misspelled field name is
  silently ignored", file a separate issue. Load the `ticket-craft:tracking-work` skill first.
  Labels: `created-by-claude`, `plugin:machines`, `severity:medium`. Leave the other three
  where they are and record them as deferred.
- [ ] **Step 4:** Run the suite. Expect 443 tests or more, OK. Commit in one or more commits,
  each staged by explicit path.
- [ ] **Step 5:** Post a comment on `claude-plugins#55`. It names each item as fixed (with its
  commit), stands (with the reason) or deferred (with the new issue, written as
  `claude-plugins#N`). **Do not close the issue.** The controller closes it after the merge.

---

### Task 1 (C.1): The transport declaration parser

**Files:**
- Create: `lib/machines/transport.py`
- Create: `tests/test_transport.py`
- Create: `tests/fixtures/transport-fake/transport/transport.yaml`
- Modify: `SCHEMA.md`. Add a "The transport declaration" section after the effects section.

**Interfaces — Produces:**

```python
TOUCHES = ("channel-read", "channel-write", "world-read", "world-write")
PERFORMERS = ("transport", "agent")
RETURNS = ("messages",)          # the only channel-read return shape (spec §4)

class Verb:                      # plain value object; __eq__ by fields
    name: str                    # matches machine.VERB
    touches: str                 # in TOUCHES
    performer: str               # in PERFORMERS
    args: dict                   # arg name (matches machine.NAME) -> word in machine.ARG_TYPES
    returns: str | None          # in RETURNS; present iff touches == "channel-read"

class Transport:
    name: str                    # matches machine.NAME
    version: str
    total_order: bool
    channel_id: str | None       # prose for the consent screen; never interpreted
    verbs: dict                  # verb name -> Verb
    root: str | None             # directory holding transport.yaml; None from parse_transport

class TransportError(DeclarationError)   # .field names the offending key

def parse_transport(text: str) -> Transport          # raises TransportError
def load_transport(path: str) -> Transport           # path is transport.yaml, or a directory
                                                     # containing it; sets .root; OSError passes through
```

**The rules. Each one gets a test that names the offending key in the message:**

- YAML loaded with `declaration.MachineSafeLoader`. Import it. Do not copy it.
- Top level: exactly `transport`, `version`, `channel`, `verbs`. Every key except `channel.id`
  is required. An unknown key is refused by name. The keys `run`, `cmd` and `shell` are not
  special: they are unknown keys like any other. Put a test on `run:` so a reader sees this.
- `channel`: exactly `total_order` (required, a real `bool`) and `id` (optional string).
  `total_order: yes` parses as the string `"yes"`, so it is refused. The string `"true"` is
  refused. An absent `total_order` is refused with a message that says it has no default.
- `verbs`: a non-empty mapping. Each entry has exactly `touches`, `performer`, `args` (required,
  may be `{}`) and `returns`.
- `returns` is required when `touches: channel-read` and refused otherwise.
- **The required verbs (§13.3):** exactly one `channel-read` verb, it is named `channel.list`,
  with `returns: messages` and `performer: transport`. A `channel.append` exists with
  `touches: channel-write` and `performer: transport`. Two `channel-read` verbs are refused.
- An argument type word outside `ARG_TYPES` is refused, and the message names the word and the
  verb.
- A verb with `performer: agent` must not be `channel-read` or `channel-write`. The channel is
  the transport's to read and write. If you think this rule is wrong, report it rather than
  dropping it. It is the controller's call and is not in the spec.

**The fixture `transport-fake/transport/transport.yaml`** declares `channel.list`,
`channel.append(body: string)`, `signal.send(to: string, text: string)`,
`label.add(name: string)`, `label.remove(name: string)` (all `performer: transport`), and
`escalate(reason: string)` with `touches: world-write` and `performer: agent`.
`total_order: true`.

> **Watch this:** spec §6 gives `escalate` an argument `reason: string`. Both shipped machine
> fixtures write `escalate` with no args. Under the fixture transport they will therefore fail
> the arity check in Task 2. **Declare `escalate` with `args: {}` in the fixture**, and
> report the mismatch with spec §6 as a finding in your report. Do not rewrite the machine
> fixtures.

- [ ] Steps: write the failing tests (one per rule above, plus parsing the fixture and checking
  every field of every `Verb` by value); run them and see them fail; implement; run them and
  see them pass; mutation evidence for each rule; write the `SCHEMA.md` section; commit.

---

### Task 2 (C.2): Open the vocabulary

**This is the one step that takes something away. Read spec §7 and §13.1 again before
starting.**

**Files:** `lib/machines/machine.py`, `lib/machines/registry.py`, `lib/machines/cli.py`,
`bin/machines-check` (usage text only), `tests/test_machine.py`, `tests/test_registry.py`, the
CLI tests, `SCHEMA.md`, `README.md`.

**Interfaces — Consumes:** `transport.Transport`, `Verb` and `load_transport` from Task 1.

**Interfaces — Produces:**

```python
# machine.py
def arg_type(value) -> str          # was _arg_type; renamed public, behaviour unchanged
def check_machine(m, verbs=None) -> list[str]
    # verbs: dict verb-name -> Verb (Transport.verbs), or None.
    # None: effect-vocabulary validation does NOT run. Every other check runs.
    # BUILTIN_VERBS is deleted, and nothing in lib/ names it.

# registry.py
class Report:
    examined, problems, collisions           # unchanged
    vocabulary_checked: bool                 # True iff a transport was supplied
    world_effects: dict                      # versioned_label(m) -> sorted list of
                                             # (verb, touches) for every effect whose verb
                                             # touches world-read or world-write; {} when
                                             # vocabulary_checked is False
def check_all(machines, transport=None) -> Report
```

**The CLI (`machines-check [--transport <path>] <path>...`):**

- `--transport` takes a `transport.yaml` or a directory containing one. If it is missing or
  unreadable, exit 2. If it fails to parse, exit 1 and print the `TransportError`, prefixed
  with the path.
- **Without `--transport`, print exactly this line** after `Examined N machines`:
  `Effect vocabulary not checked: no --transport given`. A silent skip is not available
  (§13.1).
- With `--transport`, print one line per world-touching effect:
  `<label>: effect <verb> touches <touches>`. These lines are disclosures. They are not
  problems and never change the exit code.

**What happens to the existing tests:**

- The `BUILTIN_VERBS` tests in `test_machine.py` (around line 228–263) move to verb tables
  built in the test. `_with_verb` builds a `{"probe": Verb(...)}` table and passes it as
  `verbs=`. It no longer mutates module state.
- `test_the_vocabulary_is_not_opened_by_a_structured_effect` is deleted, because it pins what
  this task removes. Replace it with a test asserting that `machine` has no `BUILTIN_VERBS`
  attribute, so the table cannot quietly return.
- Add a test that `check_machine(m)` with no verbs passes an effect naming an unknown verb.
  Add a test that the same machine with the fixture's verbs reports it.
- **Both machine fixtures must check clean against the fixture transport.** Add that test.
- A test pins `ARG_TYPES` against the type words used in the fixture transport. This replaces
  `test_every_builtin_type_word_is_one_the_checker_can_test`.

**Docs, in the same commit:** `SCHEMA.md` loses the three-verb table and the sentence "the
vocabulary is still the framework's three verbs". It gains: effects are validated against the
transport's declared verbs; without a transport they are not validated, and the CLI says so.
`README.md` gets the `--transport` flag. Then grep both files and the spec for `BUILTIN_VERBS`
and for "three verbs", and fix every hit in `plugins/machines/`.

- [ ] Steps: failing tests; see them fail; implement; see them pass; mutation evidence
  (including one where `verbs=None` wrongly validates, and one where the CLI line is dropped);
  docs; commit.

---

### Task 3 (C.3a): The runner

**Files:**
- Create: `lib/machines/runner.py`, `tests/test_runner.py`
- Create: `tests/fixtures/transport-fake/transport/bin/transport`. A Python 3 script with
  mode 0755, committed with its executable bit (`git update-index --chmod=+x` if needed).

**Interfaces — Consumes:** `Transport` and `Verb` (Task 1), `machine.arg_type` (Task 2), and
`envelope.parse_trace`.

**Interfaces — Produces:**

```python
CALL_TIMEOUT_SECONDS = 120          # with the derivation from "Already measured"
MAX_OUTPUT_BYTES = 8 * 1024 * 1024  # likewise

class TransportCannotRun(Exception)  # the entry point could not run; stdout is not an answer

def call(transport, verb, channel, args, timeout=CALL_TIMEOUT_SECONDS,
         max_output=MAX_OUTPUT_BYTES) -> dict
    # Returns the envelope exactly: {"ok": True, "result": ...} or {"ok": False, "error": str}.
    # Raises ValueError, before spawning anything, if: transport.root is None; verb is undeclared;
    #   verb.performer == "agent"; args do not match verb.args by name, arity and arg_type.
    # Spawns <root>/bin/transport <verb>, writes {"channel": channel, "args": args} on stdin.
    # Raises TransportCannotRun if: the entry point is missing or not executable; the exit code
    #   is non-zero (stdout discarded); stdout at exit 0 is not JSON or is not exactly one of the
    #   two envelope shapes (an unknown key, a non-bool ok, or both result and error present).
    # Returns {"ok": False, "error": ...} naming the bound if the time bound or the output bound
    #   is hit. The process group is killed in both cases.

def read_channel(transport, machine, channel, **bounds) -> "envelope.Trace"
    # call(transport, "channel.list", channel, {}); on ok:false, see the decision below.
    #   On ok:true builds {"channel": channel, "machine": machine.name,
    #   "version": machine.version, "total_order": transport.total_order,
    #   "messages": result["messages"]} and returns parse_trace(that). TraceError passes through.
```

**One decision is left to you. Report what you chose:** what `read_channel` does when
`channel.list` answers `ok: false`. The proposal is a new `ChannelReadFailed(Exception)`
carrying the error text. It must not return an empty trace. An empty trace is the
short-result failure in "three things you must not do".

**Process handling:** use `subprocess.Popen(..., start_new_session=True)`. On a bound, call
`os.killpg`. Read stdout in chunks, and stop at `max_output + 1` bytes. Do not use
`communicate()` with no limit, because that reads everything first. Do not pass a shell. The
argv is exactly `[<root>/bin/transport, verb]`.

**The fixture entry point** reads the verb from argv and the call from stdin. It behaves
according to `channel`, so a test chooses the behaviour without any extra declared argument:

| `channel` | Behaviour |
|---|---|
| `session-relay` or `paxos-acceptor` | `channel.list` prints `{"ok": true, "result": {"messages": <the messages of tests/fixtures/trace-<channel>.json>}}`. Other verbs print `{"ok": true, "result": {}}` |
| `sleep` | sleeps 30 s |
| `flood` | writes about 2 × `max_output` bytes. The test passes a small `max_output` |
| `child-sleeps` | spawns `sleep 30` as a child, prints nothing and waits |
| `exit-3` | prints a valid ok envelope, then exits 3 |
| `not-json`, `extra-key`, `both` | malformed envelopes |
| `body` | `channel.list` returns one message with a `"body"` key added |
| `refuse` | prints `{"ok": false, "error": "refused"}` |

Tests that hit a bound pass a small `timeout` (for example 0.5 s) or a small `max_output`.
Never wait 120 s in the suite. The `child-sleeps` test must show that no process from the
group is still alive afterwards (`os.killpg(pgid, 0)` raises `ProcessLookupError`). For that,
`call` must make the pgid observable: record it on the exception or in a module-level hook
for tests. Report what you chose.

**Required tests (Review Focus 2–5 among them):** every row of the table above; missing entry
point; a non-executable entry point; `performer: agent` is refused before any spawn (prove it
with a root whose entry point does not exist and the `ValueError` still raised); args
mismatch by name, arity and type; `read_channel` on both trace fixtures yields a `Trace` equal
by value to `load_trace` of the same fixture, `total_order` included; `read_channel` with
`body` raises `TraceError` naming `body`; and the engine purity test still passes, unchanged.

- [ ] Steps: failing tests; see them fail; implement; see them pass; one mutation per bound and
  per `TransportCannotRun` cause; `README.md` gets a short "The runner" section saying the
  runner is the only code in the framework that executes a publisher's file; commit.

---

### Task 4 (C.3b): The verdict's two effect lists

**Files:** `lib/machines/engine.py`, `tests/test_engine.py`, `SCHEMA.md` (the verdict section,
which says "`effects` stays one tuple until it exists"), and `README.md`.

**Interfaces — Consumes:** `Transport.verbs` and `Verb.performer`. The engine must not import
`machines.transport` or `machines.runner`. It reads attributes of the object it is handed.
Add a test pinning that neither module name appears in `engine.py`'s source.

**Interfaces — Produces:**

```python
def verdict(m, trace, limit=MAX_FOLD_STEPS, transport=None) -> Verdict
def gate(m, trace, outbound, limit=MAX_FOLD_STEPS, transport=None) -> Verdict
class Verdict:
    effects             # unchanged: every effect, one tuple, in declared order
    transport_effects   # tuple of the effects whose verb has performer "transport"; () if transport is None
    agent_effects       # tuple of the effects whose verb has performer "agent";     () if transport is None
```

- The two lists partition `effects` and keep its order. Test it on a transition whose effects
  interleave the performers.
- If an effect names a verb the transport does not declare, raise `ValueError` naming the verb.
  `check_machine(m, verbs=transport.verbs)` would have refused that machine, so reaching this
  is a caller's error. Do not return an empty or partial classification.
- **No existing test moves** (§13.2). If one has to, stop and report it.
- `SCHEMA.md`'s verdict section and `README.md`'s "verdict" bullet describe the two lists and
  state that the engine still performs neither.

- [ ] Steps: failing tests; see them fail; implement; see them pass; mutations (swap the two
  performers; drop the `ValueError`); docs; commit.

---

### Task 5: Release and the record

**Files:** `plugins/machines/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
the generated manifests, `README.md` (the version, and what cycles shipped).

- [ ] Bump `machines` to `0.8.0` in `plugin.json` and in the marketplace entry. Change the
  marketplace description to say "Cycles A, A.1, A.2, B and C.1–C.3" and "no installer, no
  dispatcher".
- [ ] Run `python3 scripts/sync-manifests.py` and commit the generated files with the change.
  Then run `python3 scripts/sync-manifests.py --check` and `claude plugin validate .`, both
  from the repository root.
- [ ] Run the full suite and record the count.
- [ ] Commit with the subject `machines: 0.8.0 (cycle C, task 5)`.

The controller does the following after the whole-branch review: push, open the PR, and post
the outcome comment on `claude-plugins#28` (what C.1–C.3 delivered, and what C.4 still waits
on).

---

## Self-review against the spec

| Spec item | Task |
|---|---|
| §2: YAML, closed language, unknown key refused by name, no execution to read it | 1 |
| §3: one entry point, one call per verb, JSON in and out, exit codes, stateless | 3 |
| §4: `channel.list` returns what `parse_trace` accepts; a body is refused at the boundary | 3 |
| §5: `touches` and `performer`; an agent verb is never called | 1, 3 |
| §6: the field-by-field declaration; `total_order` required; no `run`/`cmd`/`shell` | 1 |
| §7.1–7.3: delete the hardcoded vocabulary, validate against declared verbs, `SCHEMA.md` in the same commit | 2 |
| §7.4: report world-touching effects; refuse an absent `total_order` | 2, 1 |
| §8: the engine never calls; the runner is the only executor | 3, 4 (purity tests) |
| §11.3: `total_order` made available; engine order logic unchanged | 3 (`read_channel`), deliberately nothing in the engine |
| §13.1: optional `--transport`, and the report says when vocabulary was not checked | 2 |
| §13.2: optional `transport=`, lists added beside `effects` | 4 |
| §13.3: `channel.list` and `channel.append` are required | 1 |
| §13.4: bounds on time and output; a hit is `ok: false` | 3 |
| §9, C.4: the installer and the consent screen | **not this plan** |
