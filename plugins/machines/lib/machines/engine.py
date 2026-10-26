"""The verdict: a fold, turned into something a reader and a caller can act on.

This module emits a verdict and never an action. It performs no effect,
writes no file, calls nothing out, reads no clock and no environment:
`escalate` is a word in a tuple. It reads a `Fold` and a `Machine` and
nothing else about a trace; it does not re-walk the messages, and the
outbound clock is `Fold.outbound_clock`, read, never recomputed.

`Verdict` is built by `_build`, so that `gate` (which answers "may I send
this") can reuse it rather than inline a second copy.
"""

from machines.fold import MAX_FOLD_STEPS, fold


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


def _build(m, f, legal, reason):
    """Assemble a Verdict from a Fold. Shared by `verdict` and (Task 5) `gate`."""
    st = m.states[f.state]
    last = f.fired[-1] if f.fired else None
    return Verdict(
        legal=legal,
        reason=reason,
        state=f.state,
        holder=None if st.terminal else st.holder,
        accepting=st.accepting,
        terminal=st.terminal,
        may_send=_may_send(m, f.state),
        remaining=_remaining(m, f.spent),
        effects=tuple(last.transition.effects) if last else (),
        order=last.order if last else "ok",
        concurrent_with=last.concurrent_with if last else (),
        guards=f.guards,
        world_reads=f.world_reads,
        outbound_clock=f.outbound_clock,
        refusals=f.refusals,
        truncated=f.truncated)


def verdict(m, trace, limit=MAX_FOLD_STEPS):
    f = fold(m, trace, limit)
    if f.refusals:
        return _build(m, f, False, _refusal_reason(f.refusals))
    return _build(m, f, True, None)
