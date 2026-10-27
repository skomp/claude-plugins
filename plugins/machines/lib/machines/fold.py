"""The fold: a channel's recorded trace, turned into a current state.

This is the pure part of the engine. It reads a machine and a trace and
returns a `Fold`; it opens no file, reads no clock and performs no effect.
A refused message is a fact about the trace, not the end of the fold: it
does not advance the state, does not feed a register, does not consume the
clock, and the fold carries on with the next message.

The ordering that matters most: a guard reads its register as of BEFORE the
arriving message is folded into it (SCHEMA.md, the `guard` bullet). Fold
first and `ballot gt highest_promised` becomes `5 > 5`, the `le` branch
fires, and the paxos machine never leaves `idle` -- silently, nothing raises.
"""

from machines.machine import OP_ATOMS

# An engine-side limit on ONE fold: a defence of the engine against a trace
# somebody hands it, and NOT a bound on the protocol. The framework does not
# require a protocol to terminate and an absent `cap` means no bound
# (SCHEMA.md); nothing here is declared, and no publisher fills anything in.
# A fold that reaches the limit stops, sets `Fold.truncated`, and the verdict
# built from it is not legal (engine.py): a verdict about a fold that did not
# finish is not a verdict about the channel.
#
# Measured on the real `fold` on 2026-10-26 (Raspberry Pi, CPython 3, best of
# 3, `limit` raised out of the way), a one-state machine with a guarded
# self-loop, one sender, clocks 1..n, every message accepted:
#     1,001 messages 0.016 s; 10,001 0.173 s; 100,001 1.86 s;
#     1,000,001 21.5 s                      (16 to 22 us per message)
# and every message refused ("undeclared kind"): 1,001 0.002 s; 10,001
# 0.025 s; 100,001 0.29 s; 1,000,001 4.1 s  (2 to 4 us per message).
# This DISAGREES with the plan's anchor of about 6 us per message from a
# reference implementation: the shipped fold is about three times slower.
# The per-message cost is not constant in the number of DISTINCT senders,
# though: `max(clocks.values())` and the concurrency scan walk every sender
# seen, so a trace in which every message has a new sender is quadratic:
# 1,001 messages 0.095 s; 3,001 0.74 s; 10,001 8.7 s (867 us per message).
# To repeat it: build a `Trace` of n `Message`s with
# `Envelope(i + 1, sender)` and time `fold(m, trace, limit=10**9)`.
#
# Which bound governs: at 10,000 steps the realistic cost (a few senders) is
# 0.2 s at most, and the hostile all-distinct-senders trace is 8.7 s, the
# worst the limit permits. A real channel (one issue thread, a handful of
# senders) is hundreds of messages, so the plausible channel length is far
# below the limit and the limit governs only hostile or runaway input; the
# time cost, not channel length, is what fixes the number. 100,000 would
# allow the quadratic case to run for minutes.
MAX_FOLD_STEPS = 10000

_PYTHON_TYPE = {"int": int, "bool": bool}

# SPEC section 6's four order values, exactly, as one vocabulary. Where each
# one actually appears: "ok" and "concurrent" are the only values a `Step`
# (and so `Verdict.order`) ever holds, because a refused message makes no
# Step. "duplicate" and "out-of-order" appear only as a `Refusal.reason`. A
# clock above max(seen) + 1 is reported as "out-of-order" with the gap named
# in the refusal's detail: the author kept four values rather than add a
# fifth. No production code reads this tuple; it documents the vocabulary.
ORDERS = ("ok", "duplicate", "out-of-order", "concurrent")


class WorldReadRecord(object):
    def __init__(self, index, verb, result):
        self.index = index
        self.verb = verb
        self.result = result


class GuardReading(object):
    """One guard, as evaluated. `atom` is "LT", "EQ" or "GT", or None when the
    field was absent from the message (or the guard could not be evaluated, in
    which case `note` says why). Both compared values are kept: a guard that
    fired must be as readable afterwards as an effect that fired."""

    def __init__(self, index, transition_id, field, op, register,
                 field_value, register_value, atom, fired, note=None):
        self.index = index
        self.transition_id = transition_id
        self.field = field
        self.op = op
        self.register = register
        self.field_value = field_value
        self.register_value = register_value
        self.atom = atom
        self.fired = fired
        self.note = note


class Step(object):
    def __init__(self, index, transition, frm, to, order, concurrent_with=()):
        self.index = index
        # The other senders whose accepted high-water clock is >= this
        # message's clock; non-empty exactly when order == "concurrent".
        self.concurrent_with = tuple(concurrent_with)
        self.transition = transition
        self.frm = frm
        self.to = to
        self.order = order


class Refusal(object):
    def __init__(self, index, reason, state, detail=None):
        self.index = index
        self.reason = reason
        self.state = state
        self.detail = detail


class Fold(object):
    def __init__(self, state, registers, spent, clocks, fired, refusals,
                 guards, world_reads, truncated, steps, outbound_clock):
        self.state = state
        self.registers = registers
        self.spent = spent
        self.clocks = clocks
        self.fired = tuple(fired)
        self.refusals = tuple(refusals)
        self.guards = tuple(guards)
        self.world_reads = tuple(world_reads)
        self.truncated = truncated
        self.steps = steps
        # max(every accepted clock, over ALL senders) + 1; 1 for an empty
        # trace. The engine reads this and never recomputes it.
        self.outbound_clock = outbound_clock


def transition_id(t):
    return (t.frm, t.on, t.by, t.to)


def _atom(a, b):
    return "LT" if a < b else ("EQ" if a == b else "GT")


def _wrong_type(m, fields):
    """The first declared field carried with the wrong Python type, or None.
    `bool` is an `int` in Python, so it is refused against `int` explicitly:
    `True < 5` succeeds and would be a silent wrong comparison."""
    for name in sorted(fields):
        declared = m.fields.get(name)
        if declared is None:
            continue
        want = _PYTHON_TYPE.get(declared.type)
        value = fields[name]
        if want is bool:
            ok = isinstance(value, bool)
        elif want is int:
            ok = isinstance(value, int) and not isinstance(value, bool)
        else:
            ok = False
        if not ok:
            return "field %r is declared %s but carries %r (%s)" % (
                name, declared.type, value, type(value).__name__)
    return None


def _read_guard(index, t, msg, registers):
    g = t.guard
    tid = transition_id(t)
    value = msg.fields.get(g.field)
    if g.register in registers:
        current = registers[g.register]
    else:
        current = None
    if g.op not in OP_ATOMS:
        return GuardReading(index, tid, g.field, g.op, g.register, value,
                            current, None, False,
                            "operator %r is not in the vocabulary" % (g.op,))
    if g.register not in registers:
        return GuardReading(index, tid, g.field, g.op, g.register, value,
                            None, None, False,
                            "register %r is not declared" % (g.register,))
    if g.field not in msg.fields:
        # Absence is never an error and never a crash: the guard is false.
        return GuardReading(index, tid, g.field, g.op, g.register, None,
                            current, None, False)
    atom = _atom(value, current)
    return GuardReading(index, tid, g.field, g.op, g.register, value,
                        current, atom, atom in OP_ATOMS[g.op])


def fold(m, trace, limit=MAX_FOLD_STEPS):
    state = m.initial
    registers = {name: r.initial for name, r in m.registers.items()}
    spent = {role: 0 for role in m.roles}
    clocks = {}
    fired, refusals, guards, world_reads = [], [], [], []
    # `steps` counts messages CONSUMED, refused ones included: a refused
    # message still cost a fold step, and the limit is a cost limit.
    steps = 0
    truncated = False

    for index, msg in enumerate(trace.messages):
        if steps >= limit:
            truncated = True
            break
        steps += 1
        for wr in msg.world_reads:
            world_reads.append(WorldReadRecord(index, wr.verb, wr.result))

        def refuse(reason, detail=None):
            refusals.append(Refusal(index, reason, state, detail))

        if msg.kind not in m.kinds:
            refuse("undeclared kind", "kind %r" % (msg.kind,))
            continue
        if msg.by not in m.roles:
            refuse("undeclared role", "role %r" % (msg.by,))
            continue
        wrong = _wrong_type(m, msg.fields)
        if wrong is not None:
            refuse("field type", wrong)
            continue

        # The clock verdict. It comes before the transition lookup, so a
        # repeated message is a "duplicate" and not "no transition". Clocks are
        # keyed by SENDER; the cap (spent) is keyed by ROLE. Never one key.
        sender = msg.envelope.sender
        clock = msg.envelope.clock
        order = "ok"
        if sender in clocks and clock <= clocks[sender]:
            if clock == clocks[sender]:
                refuse("duplicate", "clock %d from %r repeats its high-water "
                       "mark" % (clock, sender))
            else:
                refuse("out-of-order", "clock %d from %r is below its "
                       "high-water mark %d" % (clock, sender, clocks[sender]))
            continue
        # The gap rule needs something seen to measure against: the first
        # accepted message sets the baseline, whatever its clock (test_fold
        # pins first clocks of 7 and 9).
        highest = max(clocks.values()) if clocks else None
        if highest is not None and clock > highest + 1:
            refuse("out-of-order", "clock %d follows nothing seen; highest "
                   "seen is %d" % (clock, highest))
            continue
        concurrent_with = tuple(sorted(
            s for s, c in clocks.items() if s != sender and c >= clock))
        if concurrent_with:
            order = "concurrent"

        # Candidates in declaration order, for a stable `guards` sequence;
        # every one is evaluated, because "more than one fires" is a refusal.
        firing = []
        for t in m.transitions:
            if t.frm != state or t.on != msg.kind or t.by != msg.by:
                continue
            if t.guard is None:
                firing.append(t)
                continue
            reading = _read_guard(index, t, msg, registers)
            guards.append(reading)
            if reading.fired:
                firing.append(t)

        if not firing:
            refuse("no transition",
                   "nothing fires from %r on %r by %r" % (state, msg.kind,
                                                          msg.by))
            continue
        if len(firing) > 1:
            refuse("ambiguous", "%d transitions fire: %s" % (
                len(firing),
                "; ".join(repr(transition_id(t)) for t in firing)))
            continue

        t = firing[0]
        # Guards have all been read; only now does the message feed the
        # registers.
        for name, r in m.registers.items():
            if msg.kind in r.on and r.field in msg.fields:
                value = msg.fields[r.field]
                if r.fold == "max":
                    registers[name] = max(registers[name], value)
                elif r.fold == "last":
                    registers[name] = value
        if t.signal and t.by in spent:
            spent[t.by] += 1
        clocks[sender] = max(clocks.get(sender, 0), clock)
        fired.append(Step(index, t, state, t.to, order, concurrent_with))
        state = t.to

    outbound = max(clocks.values()) + 1 if clocks else 1
    return Fold(state, registers, spent, clocks, fired, refusals, guards,
                world_reads, truncated, steps, outbound)
