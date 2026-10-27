# Design — the `machines` transport declaration, and how a verb is called

**Status:** design. Nothing here is built. It is the input to cycle C.

**Scope:** item 5 of §11 in
`docs/superpowers/specs/2026-09-14-machines-framework-design.md` — *"the transport's language
and invocation mechanism"*. What a transport declaration must **contain** was settled there (a
verb set with typed arguments, a mark on every verb that reaches outside the channel, and one
statement of whether the channel gives a total order). **The file format that carries it, and
how a verb is actually called, were not.** This document decides both, and the three
consequences that fall out of them.

**And one thing it did not set out to decide.** Opening the effect vocabulary turned out to
need a change to the frozen declaration language: an effect must name a verb and supply
several typed arguments, and a string cannot carry that without an escaping grammar. §7 has
the argument and the author's ruling. It becomes **cycle A.2**, sequenced before cycle C, the
way A.1 was sequenced before B.

**Author's note on provenance:** these are the controller's decisions, taken on 2026-10-27
after the author declined an interview and said to propose something. Every one is reversible
and each is marked with what it costs if it is wrong. Nothing here was agreed by the author in
conversation.

**Read first:** §5 (layout), §6 (four executables, and the engine that never acts), §7 (the
effect vocabulary is the transport's), §8 (the narrow cut, verb classification, total order)
and §9 (the checks the install runs) of the framework design. This document argues from them
and does not restate them.

---

## 1. Why this is the next thing

Cycle B shipped the engine and left two promises unkept, both for the same reason and both
named in the spec:

1. **The verdict carries one unclassified `effects` list**, not §6's `effects.transport[]` and
   `effects.agent[]`. What classifies a verb is the transport declaration. Until it exists, the
   engine would have to hardcode a classification of the three verbs the checker already
   hardcodes — the generalising-from-one-instance failure §7 names. The cost is stated in §6:
   the *"the machine made me do this"* check that a human reader is supposed to be able to
   perform **is not available**.
2. **`total_order` and `channel_order` are validated and read by nothing.** A trace carries
   them; the engine derives order from the clock alone. §8 says the engine's behaviour differs
   between a channel that gives a total order and one that does not, and today it does not
   differ at all.

A third thing is worse than either, because it is live: **`check_machine` restricts every
effect to `label.add:<name>`, `label.remove:<name>` and `escalate`** —
`plugins/machines/lib/machines/machine.py`, around line 503 — and `SCHEMA.md` documents that
restriction as the rule. §7 calls those three verbs a failure and says whoever lands the
transport declaration must change the checker and `SCHEMA.md` in the same act. **Until then a
machine written to §7 does not install.**

So this is not polish. Three documented divergences between the design and the shipped code all
close on one artefact.

---

## 2. Decision 1 — the declaration is data, in YAML, in the closed-language discipline

`transport/transport.yaml`, beside the publisher's code, inside
`machines/<publisher>/<name>/<version>/` (§5's layout, unchanged).

**YAML, parsed the way `declaration.py` parses a machine:** every key known, an unknown key
rejected **by name**, no expressions, no interpolation, no includes. A reader of the file can
see everything it says, and the installer can print it without running anything.

**Why not a Python module that declares its verbs in a dict.** It would be the shortest path —
the engine is Python, the transport is Python, `import` and read an attribute. It is refused:
importing the publisher's module to find out what the publisher's module claims means executing
the code **before** the consent screen that exists to authorise executing the code. The
installer must be able to show a user what a transport says it does without taking its word by
running it.

**Why not JSON.** The machine declaration is YAML in a fenced block, `SCHEMA.md` documents YAML
hazards the parser already guards (`on: yes` resolving to `true`, `op: >` in block context
parsing to the empty string), and that knowledge transfers. A second syntax for the second half
of one install buys nothing.

*Costs if wrong:* one parser and one document. The format is not load-bearing for anything
below it.

---

## 3. Decision 2 — one executable, one call per verb, JSON in and JSON out

A transport ships **one entry point**: `transport/bin/transport`, executable, invoked with the
verb name as its only argument, the call's JSON on stdin, the result's JSON on stdout.

```
$ transport/bin/transport channel.list <<< '{"channel": "...", "args": {}}'
{"ok": true, "result": {"messages": [ ... ]}}
```

**Why one entry point rather than a command template per verb.** The alternative is a
declaration where each verb names an argv template and the caller substitutes typed arguments.
It is tempting because the consent screen would then show the real command line. It is refused
for two reasons, and the second is the one that decides it:

- **Templating is a new injection surface** owned by us, on a path whose whole point is that the
  publisher's code is the untrusted part. Argument quoting rules would become ours to get right
  for ever.
- **It would dress disclosure as enforcement.** §8 is explicit: *"A transport doing shell
  execution behind a verb named `comment.post` is simply lying; no design stops code from
  lying."* A displayed command line invites a reader to believe they have seen what will run.
  They have seen what the declaration says, which is exactly what one entry point also tells
  them, without the false precision.

**Why not in-process.** The engine must stay what cycle B made it: three modules that open no
file but a trace handed to them, run no subprocess, make no network call, read no clock and no
environment, pinned by tests. Loading a publisher's module into the engine's process ends that
in one line, and the invariance test that proves the engine never branches on a world read
would be proving it about a process that also contains the transport.

**Stateless, by contract.** §8 already says a verb takes JSON, returns JSON, and holds nothing
between calls. One process per call makes that structural rather than promised, the same way
cycle B's trace has no slot for a message body.

**The result envelope**, exactly:

```
{"ok": true,  "result": <verb-specific>}
{"ok": false, "error": "<human-readable>"}
```

**Two exit codes, and they mean what `machines-check`'s mean.** `0` — the transport ran and the
JSON on stdout is its answer, `ok` either way. Non-zero — **the transport could not run**, and
stdout is not an answer. A transport that cannot run must never be read as a verb that failed,
for the same reason a broken install must not read as a failing check.

*Costs if wrong:* a runner and a declaration field. No machine declaration changes.

---

## 4. Decision 3 — a channel read returns exactly what cycle B already parses

A `channel.list` verb's `result` is `{"messages": [...]}`, where each message is what
`plugins/machines/lib/machines/envelope.py`'s `parse_trace` already accepts: `kind`, `by`,
`envelope` (`clock`, `sender`, `channel_order`), `fields`, `world_reads`. Nothing new, and no
second shape to keep in step.

This is the decision that makes cycle C cheap to verify: a trace fixture is already *"the JSON a
transport would have returned"* (the cycle B plan's own words), so the first real transport can
be checked against the fixtures that the engine's 407 tests already use.

**`parse_trace` rejects an unknown key by name**, so a transport that returns a message body
fails at the boundary rather than carrying content into the framework. §4's third row stays
structural.

*Costs if wrong:* the verb's result schema, and whatever translates it.

---

## 5. Decision 4 — a verb declares its performer, which is what unblocks §6

§8 classifies a verb by **what its result touches** — channel read, channel write, world read,
world write. That axis survives untouched. It is not enough to split §6's two effect lists,
because both lists are about **who performs**, and that is a different question: `escalate` is a
world-ish act performed by **Claude**, under the harness's permissions; `label.add` is a world
write performed by **installed code**, under install-time consent.

So a verb declares both:

| Field | Values | Answers |
|---|---|---|
| `touches` | `channel-read`, `channel-write`, `world-read`, `world-write` | what the result touches (§8) — and `world-read` is the mark §8 requires |
| `performer` | `transport`, `agent` | who does it (§6's two performers) |

A `performer: agent` verb's entry declares the shape of what Claude is being asked to do and
**carries no implementation**: the transport's entry point is never called for it. That is what
makes §6's distinction real rather than editorial — the two lists are not a classification we
apply to effect strings, they are a field the publisher filled in, and the installer showed.

**The verdict's two lists then follow mechanically**, and the engine still performs neither.

*Costs if wrong:* one field, and the verdict goes back to one list.

---

## 6. The declaration, field by field

```yaml
transport: github-issues          # name; NAME-shaped, as machine.py's NAME
version: v1                       # string, required
channel:
  total_order: true               # REQUIRED. Absent does not install (§8, §9)
  id: "a GitHub issue URL"        # prose, for the consent screen only
verbs:
  channel.list:
    touches: channel-read
    performer: transport
    args: {}
    returns: messages             # the only channel-read return shape (§4 above)
  channel.append:
    touches: channel-write
    performer: transport
    args: { body: string }
  signal.send:
    touches: channel-write
    performer: transport
    args: { to: string, text: string }
  label.add:
    touches: world-write
    performer: transport
    args: { name: string }
  escalate:
    touches: world-write
    performer: agent
    args: { reason: string }
```

- **`args`** is a name-to-type mapping, and the types are the declaration language's own:
  `string`, `int`, `bool`. **Not a nested schema.** §7 asks for *"a typed argument schema, not
  just a name"* so that a machine naming a verb with the wrong arity or the wrong type fails at
  install; three scalar types do that. A richer schema is a new language to validate, and
  nothing has asked for one. *Costs if wrong: an additive change.*
- **`returns`** is present only on a `channel-read` verb, and its only value today is
  `messages`. It exists so that a second channel-read shape has somewhere to be declared rather
  than being inferred.
- **`total_order` is required and has no default.** §9: *"Absent is not a default; it is a
  declaration that will not install, because the engine's behaviour differs between the two
  cases and guessing would pick one silently."*
- **No `run`, no `cmd`, no `shell`.** The entry point is fixed by decision 2, so the declaration
  has nowhere to put a command. A publisher cannot make one verb run something other than the
  entry point, and a reader does not have to check whether they did.

---

## 7. What the checker must change, in the same act

§7 says it, and it is the part most likely to be deferred and then forgotten:

1. **Delete the hardcoded vocabulary.** `check_machine` currently accepts exactly
   `label.add:<name>`, `label.remove:<name>` and `escalate` and rejects everything else.
2. **Validate a machine's effects against the installed transport's declared verbs** — the verb
   exists, the arity matches, every argument's type matches (§9's worked example).
3. **`SCHEMA.md` changes in the same commit.** It documents the three-verb restriction as the
   rule today. A `SCHEMA.md` that still says so after this lands is the publisher-facing false
   claim this project has now caught three times.
4. **Report a machine that names a `world-read` or `world-write` verb** so the installer can
   show it, and **refuse a transport whose `channel.total_order` is absent.**

**One migration consequence, and it is not optional.** `plugins/machines/tests/fixtures/valid-session-relay.md`
declares `label.add:session-relay:open` and friends under the old vocabulary. Those effect
strings are `verb:argument` run together; the new form names a verb and supplies typed
arguments. **That is a schema change** — the thing cycle A.1 existed to prevent being done
mid-cycle.

### An effect becomes structured, and that is cycle A.2 — the author's decision, 2026-10-27

```yaml
effects:
  - verb: label.add
    args: { name: "session-relay:open" }
  - verb: signal.send
    args: { to: "repo-b", text: "your turn" }
  - verb: escalate
    args: {}
```

**This document first recommended keeping `effects:` a list of strings**, so that the frozen
schema would not move: `label.add:open` read as `label.add(name="open")`. **A builder check
disproved it, and the evidence is already in this repository.** The string form works for one
argument and collapses on two:

- `signal.send(to: string, text: string)` needs a separator, and `text` is free prose.
- the shipped fixture's `label.add:session-relay:open` has a single argument that **itself
  contains a colon**, so it is ambiguous under any colon separator that was ever going to be
  chosen.
- an `int` and a `bool` would need a spelling, and the spelling would need a parser.

**A string needs a parser, and this project has measured what that costs.** Cycle A.1 refused a
string guard (`"ballot > highest_promised"`) for exactly this reason and chose a shape instead;
`pattern.py` is the record of the alternative — 770 lines, a `RecursionError` reachable through
the shipped CLI, and two depth guards plus a backstop, each added after the fact. Inventing an
escaping grammar for effects would be the same decision taken a second time, with the same
outcome available in advance.

So the effect becomes a shape, and because it is a change to the declaration language it gets
its own cycle, sequenced before the one that needs it:

**Cycle A.2 — structured effects.** `effects:` becomes a list of mappings, each with `verb` and
`args`; `declaration.py` parses it; `check_machine` validates each `verb` against the vocabulary
it knows and each `args` against the declared types; `SCHEMA.md`'s effect section is rewritten;
both shipped fixtures are rewritten; the version bumps because a declaration that parsed will
not parse. **It does not need the transport declaration** — A.2 can keep validating against the
three built-in verbs, with the vocabulary opened in C.2 — which is exactly why it can go first
and why C can then be written against a schema that does not move under it. That argument is
A.1's, verbatim, and it held.

*Costs if wrong:* a cycle, and two fixtures rewritten twice.

---

## 8. Who calls a verb, and who never does

This is the boundary cycle C is most likely to blur, because the engine is the thing that knows
what should happen next.

> **The engine never calls a verb.** It emits a verdict. §6's whole first subsection is that
> the engine requires and something else performs, and cycle B's three modules are pinned by
> tests that assert they open no file, run no subprocess and make no network call.

So cycle C ships a **runner** — ours, not the publisher's — that performs one call: resolve the
installed transport for a machine, spawn its entry point, write the call JSON, read the result
JSON, and hand the result back to its caller. It belongs beside the installer in `bin/`, and it
is the only code in this framework that executes a publisher's file.

**Who calls the runner is cycle D's question**, not this document's. Today the answer is "a
test". After cycle D it is the dispatcher, inside a session's turn. Either way the sequence is:
the engine folds a trace and gives a verdict; something reads the verdict; **that something**
asks the runner to perform the writes the verdict says are required, and asks Claude to perform
the `performer: agent` ones under its own permissions.

*Costs if wrong:* nothing structural. The runner is one file and the rule is already in §6.

---

## 9. What the installer shows, and what it asks

§6 says the installer *"shows the code it is about to install and asks for consent"*, and §8
says it must state plainly that a bundle ships code. What that screen contains, decided here:

- **the pinned ref** it cloned, and the repository it came from;
- **every file in `transport/`**, with its size, and the entry point named;
- **the declared verbs**, each with its `touches` and its `performer`, with the
  world-touching ones and the `performer: agent` ones called out rather than listed flat;
- **the total-order statement**;
- **the prefixes the machine claims**, and the verdict of the collision check against every
  machine already installed;
- **the effects the machine requires**, each resolved to the verb that will perform it.

And one sentence that does not hedge: **a transport is code, it runs under your account, and the
declaration above is what it says about itself, not what it has been proven to do.** §8 refuses
sandboxing and refuses a capability allowlist, on the ground that *"disclosure that holds beats
enforcement that does not"* — so the disclosure has to be honest about being disclosure.

---

## 10. Non-goals

- **No sandbox and no capability allowlist.** §8, and the reasoning there is not re-opened.
- **No auto-update.** §11.3: record the installed ref, compare against the remote on a
  timestamp gate, report. Never update by itself.
- **No daemon, no watcher, no poller.** §14. A transport that blocks is publisher code called
  synchronously inside a turn.
- **No second channel kind.** Whether addressing is floor or a second kind of channel is
  §11.11, and it is cycle D's.
- **No change to the declaration language's states, roles, kinds, transitions, guards,
  registers or cap.** The one place this design presses against the schema is §7 above, and it
  says so.

---

## 11. Open, and explicitly not settled

1. **A thread whose machine is uninstalled or upgraded mid-conversation.** §11.2's proposal
   stands — the trace names protocol and version, the registry keeps old versions, a thread pins
   the version it opened with, uninstalling with live threads warns and names them — and this
   document neither extends nor settles it.
2. **What bounds delegation.** §11.4. Untouched, and still unstated.
3. **Whether the engine should use `channel_order` for duplicate detection when
   `total_order` is true.** §8 says it should. Cycle B derives order from the clock alone. This
   design makes the statement available; it does not decide how much of the engine's order logic
   changes, because that is engine work with its own tests and it may deserve its own small
   cycle rather than riding along with an installer.
4. **How a transport is tested by its publisher.** Nothing here says how someone writing the
   second transport finds out whether theirs is correct. A conformance fixture — the trace
   fixtures run back through a real entry point — is the obvious answer and is not designed.

---

## 12. Sequencing — one schema cycle, then three steps, then the installer

| | Delivers | Why here |
|---|---|---|
| **A.2** | structured effects: `effects:` becomes `verb` plus typed `args`, parsed, checked, documented, both fixtures rewritten, version bumped | A change to the declaration language, so it goes before the cycle that reads it, exactly as A.1 went before B. It needs no transport declaration — it keeps the three built-in verbs and only changes their shape |
| **C.1** | the transport declaration parser and its own checks: `transport.yaml`, the closed language, `total_order` required, the verb table with `touches` and `performer` | Needs nothing but A.2's settled effect shape. Runnable against a hand-written file, exactly as cycle A's checker was |
| **C.2** | the vocabulary opened: the hardcoded three verbs deleted, a machine's effects validated against a declared verb set, `SCHEMA.md` rewritten in the same commit | Needs C.1. **The one step that takes something away:** a machine that installs today may not install after it |
| **C.3** | the runner, and the verdict's two effect lists | Needs C.1 for `performer`. The engine still performs nothing; the runner is the only code in this framework that executes a publisher's file |
| **C.4** | the installer, `/machines:install`, `~/.claude-machine/`, the registry and the consent screen | Needs all of the above, **and it needs §11 item 1 settled** — a registry cannot be designed without knowing what a thread pins. It is also the only step with outward-facing behaviour: it writes outside the repository and asks a human for consent |

**C.4 gets its own plan, and probably its own cycle.** A.2 and C.1 to C.3 are one plan's worth
of work with one verification. C.4 is cloning at a pinned ref, a registry format, an upgrade and
uninstall story, the collision check against what is already installed, and a consent flow
inside a slash command — and its data model waits on an item this document does not settle.
Planning it as a row in someone else's table is how it would arrive half-specified.

---

## 13. A builder read this, and what their questions settled

A fresh engineer was asked what they would still have to guess before planning this. Eight
questions came back. One was the author's and is answered in §7. **The other seven are the
controller's calls, recorded here so a reader can see which parts of this design nobody
agreed to.**

1. **What does the checker validate against when no transport is installed?** `machines-check`
   takes an optional `--transport <path>`. **Without one, effect-vocabulary validation does not
   run, and the report says so** — this project's rule is that a check reports only on what it
   examined, so a silent skip is not available. At install a transport is always present, so the
   real check always happens. **A `machine.yaml` does not name its transport:** the bundle is the
   pairing, and adding a field would be a schema change for no gain. The 407 existing tests and
   both fixtures keep passing with no transport.
2. **Does the verdict's shape change, and what does the engine need?** `verdict()` and `gate()`
   gain an **optional** `transport=` argument. `effects` stays exactly as it is, and the two
   classified lists are added **beside** it. Additive, so no existing test moves; with no
   transport passed, the two lists are empty and `effects` is what it is today. The engine still
   performs nothing and still imports nothing of the publisher's.
3. **Must a transport declare particular verbs?** Yes, two, or it does not install: **exactly
   one `channel-read` verb, named `channel.list`, with `returns: messages`**, and a
   `channel.append`. A protocol with no way to read its channel is not a protocol, and the
   runner needs one name to call rather than a heuristic.
4. **Where does `channel` come from, and does the runner bound a call?** Every call carries
   `channel`, supplied by the caller, and it is the same value the trace's `channel` holds.
   **The runner bounds both time and output size**, with the defaults measured and the numbers
   in the comment, as `MAX_FOLD_STEPS` and `_MAX_CAP_SEARCH` already are. **A call that hits
   either bound is a failed call — `{"ok": false}` — never a short result.** A truncated channel
   read handed on as a complete trace would be the cap-bypass §8 warns about, arriving from our
   own code rather than from a hostile transport.
5. **Are the three shipped verbs a breaking change?** Yes, and A.2 is where they break: both
   fixtures are rewritten there, `escalate` with `args: {}`. The alternative — optional or
   defaulted arguments — is refused, because a default argument is a value nobody wrote that the
   checker then validates as if they had.
6. **Does the transport constrain label names?** No. `label.add(name: string)` takes a string;
   that `session-relay`'s own names are prefixed is that protocol's convention, not the
   framework's business. A framework that policed them would be checking meaning.
7. **How big is C.4?** Its own plan. See §12.

**The question the builder could not settle was the right one to escalate**, and it overturned
this document's own recommendation. That is the second time in two cycles that a plan's
reasoned-out proposal was wrong where its measurements were right.
