# Paxos Acceptor Protocol

This document describes the paxos-acceptor protocol: the acceptor half of Paxos, declared as a
guarded state machine. It carries a single Paxos ballot number as a declared header field, and
one register — `highest_promised` — that folds it by `max` over `prepare` messages. Four of the
seven transitions below guard on that register: a `prepare` is only a promise when its ballot
beats the highest one already promised, and an `accept-request` is only honoured at the ballot
the acceptor promised, never another.

```machine
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

A run begins in `idle`, held by the proposer. A `prepare` carrying a ballot higher than
`highest_promised` is a promise: the acceptor moves to `prepared`, on its way to answering
`promise`, and the ballot becomes the new `highest_promised`. A `prepare` carrying a ballot no
higher than what is already promised is the guarded `idle`-to-`idle` self-transition — the
acceptor stays exactly where it was, because Paxos's actual rule for a stale `prepare` is
silence, not a new state or a reply that would itself be a message.

Once promised, an `accept-request` at the ballot the acceptor promised moves the run to
`proposed`, on its way to `decided`. An `accept-request` at any other ballot returns to `idle`:
some other proposer's `prepare` has since promised a different ballot, and this request is
stale.

This machine checks two things: message sequencing — that a `promise` cannot arrive before its
`prepare`, that an `accept-request` cannot arrive before its `promise`, and so on for every
state's declared exits — and the acceptor invariant the four guards above encode directly: a
`prepare` is honoured only above the highest ballot already promised, and an `accept-request` is
honoured only at exactly that ballot, never above it or below it. **It does not check
agreement.** Nothing here confirms that a majority of
acceptors settle on one value, that a proposer waits for a quorum of promises before issuing an
`accept-request`, or that two proposers cannot each believe they have won. Agreement is a
property of the whole cluster — every acceptor and every proposer, taken together, over a run
of many machines exchanging messages — and this declaration is one acceptor's own rules for its
own register; it has no way to see the others, and no field or register in this schema could
name them. A reader who needs agreement checked needs a different kind of check than this one
provides.

The cap is six outbound messages per role per run — the proposer's own budget of six and the
acceptor's own budget of six, drawn from separate pools rather than one shared total — which is
what `cap: { limit: 6, per: role }` means here.
