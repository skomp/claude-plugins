# Session Relay Protocol

This document describes the session-relay protocol, a state machine that coordinates communication between two repositories in a distributed session management system.

<!-- `cap` below is deliberately the mapping form (`per: role`), not the bare
     `cap: 10` that `tests/test_declaration.py`'s VALID still carries. The
     two were byte-identical until `cap` gained a scope; VALID kept the bare
     spelling on purpose, as the only remaining coverage of it, and this
     fixture moved to the mapping form because it is what the protocol has
     actually always meant. Do not re-sync the two -- see the comment above
     VALID's definition. -->

```machine
machine: session-relay
version: v1
prefix: "session-relay:v1 "
roles:
  initiator: repository
  responder: repository
kinds: [triage, question, answer, conclusion, stalemate]
cap: { limit: 10, per: role }
initial: unopened
states:
  - { name: unopened, holder: initiator, accepting: true }
  - { name: awaiting-triage, holder: responder }
  - { name: awaiting-answer, holder: initiator }
  - { name: concluded, terminal: true, accepting: true }
  - { name: stalled, terminal: true }
transitions:
  - { from: unopened, on: triage, by: initiator, to: awaiting-triage, signal: true,
      effects: ["label.add:session-relay:open"] }
  - { from: awaiting-triage, on: question, by: responder, to: awaiting-answer, signal: true }
  - { from: awaiting-answer, on: answer, by: initiator, to: awaiting-triage, signal: true }
  - { from: awaiting-triage, on: conclusion, by: responder, to: concluded, signal: true,
      effects: ["label.remove:session-relay:open"] }
  - { from: awaiting-triage, on: stalemate, by: responder, to: stalled, signal: true,
      effects: ["label.remove:session-relay:open", "label.add:session-relay:stalled", "escalate"] }
```

The protocol ensures that a session between two repositories progresses through well-defined states, with each transition requiring explicit signals and optional side effects on the system state.

A run begins in `unopened`, held by the initiator: the side that found a cause living in the peer's repository and has not yet filed anything. Filing the downstream issue *is* the `triage` message — the issue body carries the protocol header with `kind=triage` and `seq=1`, and there is no separate first comment — which is why `triage` is a transition here and not something the machine starts after. It is an outbound message the machine emits, so it counts against the cap like every other one.

The cap is ten outbound messages per role per issue — the initiator gets its own ten-message budget and the responder gets its own, rather than the two sharing a single pool — which is what this protocol has always meant and what the bare `cap: 10` form could not say until `cap` gained a scope.
