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

# Provisional. Task 7 measures the real figure and owns the enforcement: until
# then `fold` accepts `limit` and does not act on it, and `Fold.truncated`
# stays False.
MAX_FOLD_STEPS = 10000

_PYTHON_TYPE = {"int": int, "bool": bool}

# SPEC section 6's four order values, exactly. A clock above max(seen) + 1 is
# reported as "out-of-order" with the gap named in the refusal's detail: the
# author kept four values rather than add a fifth.
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


def _read_guard(m, index, t, msg, registers):
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
    steps = 0

    for index, msg in enumerate(trace.messages):
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
        concurrent_with = ()
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
            reading = _read_guard(m, index, t, msg, registers)
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
                world_reads, False, steps, outbound)
