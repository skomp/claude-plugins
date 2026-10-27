"""The verdict: a fold, turned into something a reader and a caller can act on.

This module emits a verdict and never an action. It performs no effect,
writes no file, calls nothing out, reads no clock and no environment:
`escalate` is a word in a tuple. It reads a `Fold` and a `Machine` and
nothing else about a trace; it does not re-walk the messages, and the
outbound clock is `Fold.outbound_clock`, read, never recomputed.

`Verdict` is built by `_build`, so that `gate` (which answers "may I send
this") can reuse it rather than inline a second copy.
"""

from machines.fold import MAX_FOLD_STEPS, candidates, fold, wrong_type


class Offer(object):
    """One transition leaving the current state. `guard` is the declared
    `machine.Guard` or None, named and NOT evaluated: no message exists yet,
    so the engine cannot know whether the guard will pass."""

    def __init__(self, kind, by, to, guard):
        self.kind = kind
        self.by = by
        self.to = to
        self.guard = guard


class Remaining(object):
    """`spent` and `headroom` each map every declared role to an int.
    Under `per: channel` every role's headroom is the one shared budget, so
    the numbers are equal on purpose and must never be summed."""

    def __init__(self, limit, scope, spent, headroom):
        self.limit = limit
        self.scope = scope
        self.spent = spent
        self.headroom = headroom


class Verdict(object):
    def __init__(self, legal, reason, state, holder, accepting, terminal,
                 may_send, remaining, effects, order, concurrent_with,
                 guards, world_reads, outbound_clock, refusals, truncated):
        self.legal = legal
        self.reason = reason
        self.state = state
        self.holder = holder
        self.accepting = accepting
        self.terminal = terminal
        self.may_send = tuple(may_send)
        self.remaining = remaining
        # ONE unclassified list. What separates transport effects from agent
        # effects is the transport declaration, which is cycle C.
        self.effects = tuple(effects)
        self.order = order
        self.concurrent_with = tuple(concurrent_with)
        self.guards = tuple(guards)
        self.world_reads = tuple(world_reads)
        self.outbound_clock = outbound_clock
        self.refusals = tuple(refusals)
        self.truncated = truncated


def _remaining(m, spent):
    if m.cap is None:
        return None  # no cap declared: no bound, and no default substituted
    if m.cap_scope == "role":
        headroom = {role: m.cap - spent.get(role, 0) for role in m.roles}
    else:
        shared = m.cap - sum(spent.values())
        headroom = {role: shared for role in m.roles}
    return Remaining(m.cap, m.cap_scope,
                     {role: spent.get(role, 0) for role in m.roles}, headroom)


def _may_send(m, state):
    return tuple(Offer(t.on, t.by, t.to, t.guard)
                 for t in m.transitions if t.frm == state)


def _refusal_reason(refusals):
    r = refusals[0]
    text = "message %d refused: %s" % (r.index, r.reason)
    if r.detail:
        text += " (%s)" % (r.detail,)
    if len(refusals) > 1:
        text += "; %d further refusals" % (len(refusals) - 1)
    return text


def _build(m, f, legal, reason, effects=None, extra_guards=()):
    """Assemble a Verdict from a Fold. Shared by `verdict` and `gate`.
    `effects` and `extra_guards` are for `gate`: the effects of the transition
    it would fire (or () on a refusal), and the guards it read outbound. The
    order of an outbound message is "ok" with no peers: its clock is stamped
    above every clock seen."""
    st = m.states[f.state]
    last = f.fired[-1] if f.fired else None
    if effects is None:
        effects = tuple(last.transition.effects) if last else ()
        order = last.order if last else "ok"
        concurrent = last.concurrent_with if last else ()
    else:
        order, concurrent = "ok", ()
    return Verdict(
        legal=legal,
        reason=reason,
        state=f.state,
        holder=None if st.terminal else st.holder,
        accepting=st.accepting,
        terminal=st.terminal,
        may_send=_may_send(m, f.state),
        remaining=_remaining(m, f.spent),
        effects=effects,
        order=order,
        concurrent_with=concurrent,
        guards=tuple(f.guards) + tuple(extra_guards),
        world_reads=f.world_reads,
        outbound_clock=f.outbound_clock,
        refusals=f.refusals,
        truncated=f.truncated)


def _truncated_reason(f):
    return ("fold truncated after %d steps: the trace is longer than the "
            "engine's fold limit, so no verdict about the channel is "
            "given" % (f.steps,))


def _overspend_reason(m, f):
    """A reason when the fold already spent more than the declared cap, else
    None. The fold has no cap rule, so a trace past the cap folds cleanly;
    this is the check that stops `verdict` calling it a legal run. It does
    not say WHICH message overspent: who busted a cap counted per role and
    per channel is a design question left to a later cycle."""
    remaining = _remaining(m, f.spent)
    if remaining is None:
        return None
    for role in m.roles:
        room = remaining.headroom[role]
        if room < 0:
            if remaining.scope == "role":
                return ("cap exceeded: role %r spent %d of a cap of %d "
                        "(%d over)" % (role, remaining.spent[role],
                                       remaining.limit, -room))
            return ("cap exceeded: the channel's roles spent %d of a shared "
                    "cap of %d (%d over; seen from role %r)" % (
                        sum(remaining.spent.values()), remaining.limit,
                        -room, role))
    return None


def verdict(m, trace, limit=MAX_FOLD_STEPS):
    f = fold(m, trace, limit)
    if f.truncated:
        return _build(m, f, False, _truncated_reason(f))
    if f.refusals:
        return _build(m, f, False, _refusal_reason(f.refusals))
    over = _overspend_reason(m, f)
    if over is not None:
        return _build(m, f, False, over)
    return _build(m, f, True, None)


def gate(m, trace, outbound, limit=MAX_FOLD_STEPS):
    """May `outbound` be sent now? Answered before the message exists.

    `legal` is judged against the folded state alone. It does NOT inherit
    `verdict`'s meaning: a refusal in the trace's history is reported in
    `refusals` and never by itself refuses an outbound message, or one old
    refused message would silence the channel for ever.

    The gate reads `outbound.by` and `outbound.fields`. `outbound.sender` is
    the caller's; `outbound.kind` is the kind to send. Any clock the caller
    put in `outbound.envelope` is DISCARDED and never validated: the engine
    stamps `outbound_clock` (the fold's, max seen + 1) and a sender cannot
    choose it. Nothing is performed: `effects` names what the transition
    that would fire requires, and is () on a refusal.

    `outbound.world_reads` is dropped: the gate answers from the channel's
    recorded state and the outbound fields alone, and never reads, carries or
    branches on a world read of the outbound message. The world reads of the
    trace's own messages are kept in the verdict, as `verdict` keeps them.

    There are five refusal reasons. In the order they are checked:
    the truncation refusal (the trace outran the engine's limit; the reason
    names the truncation, `truncated` is true, and nothing is judged against
    the partial state); "terminal state"; "not permitted here" (nothing
    fires on (kind, by) under the guards and these fields, including a field
    carried with the wrong type); "ambiguous" (more than one fires, as in
    the fold: none is picked); "cap exhausted" (headroom <= 0 and the
    transition that would fire has signal: true; a signal: false transition
    is a local move and is never counted).
    """
    f = fold(m, trace, limit)
    if f.truncated:
        # The state is partial: nothing may be judged against it.
        return _build(m, f, False, _truncated_reason(f), ())
    if m.states[f.state].terminal:
        return _build(m, f, False, "terminal state", ())
    if (outbound.kind not in m.kinds or outbound.by not in m.roles
            or wrong_type(m, outbound.fields) is not None):
        return _build(m, f, False, "not permitted here", ())
    index = len(trace.messages)
    found = candidates(m, f.state, outbound, f.registers, index)
    firing, readings = found.firing, found.readings
    if not firing:
        return _build(m, f, False, "not permitted here", (), readings)
    if found.ambiguous:
        return _build(m, f, False, "ambiguous", (), readings)
    t = firing[0]
    remaining = _remaining(m, f.spent)
    if (t.signal and remaining is not None
            and remaining.headroom[outbound.by] <= 0):
        return _build(m, f, False, "cap exhausted", (), readings)
    return _build(m, f, True, None, tuple(t.effects), readings)
