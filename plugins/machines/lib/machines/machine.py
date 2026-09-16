import re
from collections import deque

from .pattern import PatternError, compile_pattern

# Every top-level field the parser accepts, and the subset of them a
# declaration must actually carry. `cap` is the one that is accepted and
# not required: a protocol that has no reason to terminate has no bound to
# declare, and forcing one would make its author write a number nobody
# believes -- which is the failure this framework exists to answer, not one
# it should cause. Absent means "this protocol declares no bound"; it does
# not mean zero, and there is no default.
#
# `fields` and `registers` are optional the same way: a protocol with
# nothing to guard on declares neither, and gets an empty mapping rather
# than a required field it never wanted.
FIELDS = ("machine", "version", "prefix", "roles", "kinds", "fields",
          "registers", "cap", "initial", "states", "transitions")
REQUIRED = tuple(f for f in FIELDS if f not in ("cap", "fields", "registers"))

_INFINITY = float("inf")

# A declared header field's name, reused unchanged for register names:
# both live in the same namespace a publisher writes into, and both must
# stay out of the dotted `envelope.*` namespace a later cycle reserves for
# the message envelope itself (the Lamport clock among it) -- forbidding
# `.` here is what keeps a declared field from ever colliding with it.
NAME = re.compile(r"^[a-z][a-z0-9_-]*$")

# The closed set of types a declared field may carry. Closed on purpose:
# an open type word (`integer`, `number`, ...) would let a publisher write
# something the engine's guard comparison (cycle B) cannot evaluate, and
# the failure would surface far from the declaration that caused it.
# Deliberately no `string` -- a guard compares a register's fold to a
# field by equality or order (cycle B), and every comparison this schema
# can express is arithmetic or boolean; there is no string fold or string
# ordering defined anywhere in the spec for one to compare against.
FIELD_TYPES = ("int", "bool")


class Field(object):
    """A declared header field: a name and its type, nothing else.

    `type` is one of `FIELD_TYPES`. There is no default and no value here
    -- a `Field` describes what a header position must contain, not what
    any one message carries in it.
    """

    def __init__(self, name, type):
        self.name = name
        self.type = type


# The closed set of ways a register may fold a field's value across a
# trace. Closed for the same reason `FIELD_TYPES` is: an open fold word
# would let a publisher declare a register that cycle B's engine (the
# fold itself is cycle B's job; this schema only declares its shape)
# cannot evaluate, and the failure would surface far from the declaration
# that caused it. See the comment on the R1-R4 checks in `check_machine`
# for the fold/argmax boundary this set is drawn at, and SCHEMA.md's
# `registers` section for why `min`, `first`, `count` and `sum` are not
# here either.
FOLDS = ("max", "last")


class Register(object):
    """A declared register: one remembered scalar, folded from the trace.

    `fold` is one of `FOLDS`. `field` names the declared header field
    (see `Field`, above) whose value is read on every matching message.
    `on` is the non-empty list of kinds that feed the register -- a
    message of any other declared kind leaves it untouched. `initial` is
    the value the register holds before any matching message has arrived,
    an `int` or a `bool`, and (once a machine has passed `check_machine`)
    the same Python type as the field it folds.

    This class only declares the fold; it does not perform one. Nothing
    in cycle A reads a channel, folds a trace, or evaluates a guard --
    that is cycle B's engine. A `Register` is what a guard (cycle B) will
    compare a field against once one exists.
    """

    def __init__(self, name, fold, field, on, initial):
        self.name = name
        self.fold = fold
        self.field = field
        self.on = on
        self.initial = initial


# A guard's operator vocabulary, spelled as words rather than symbols --
# see declaration.py's `_guard_field` for the measurement that makes a
# symbol form actively unsafe, not merely a style choice.
#
# `LT`, `EQ`, `GT` are the three possible outcomes of comparing two values
# of a totally ordered type -- there are no others. Every operator below
# is the union of the outcomes that make it true: `eq` accepts only `EQ`,
# `ne` accepts everything that is not `EQ`, and the four ordering
# operators each accept one or two of the three. This table is what makes
# a guard's truth decidable from which atom a comparison produced,
# without a check ever interpreting the compared values themselves --
# it only has to know which of `LT`/`EQ`/`GT` two values produced, once,
# and this table answers every operator from that one fact.
OP_ATOMS = {
    "eq": frozenset(["EQ"]),
    "ne": frozenset(["LT", "GT"]),
    "lt": frozenset(["LT"]),
    "le": frozenset(["LT", "EQ"]),
    "gt": frozenset(["GT"]),
    "ge": frozenset(["EQ", "GT"]),
}

# The operators that require an ordering, not merely an equality test.
# `eq`/`ne` are meaningful on any totally ordered type, `bool` included
# (there are only two values, so equal-or-not is all there is to ask);
# the four here ask "which is bigger", which a `bool` field has no
# declared meaning for. See G3 in `check_machine`.
ORDERING_OPS = ("lt", "le", "gt", "ge")


class Guard(object):
    """A transition's guard: one declared field compared to one declared
    register's remembered value, by one operator.

    `field` names a declared header field (see `Field`, above); `register`
    names a declared `Register`; `op` is one of `OP_ATOMS`'s six keys.

    This class only declares the comparison. Nothing in cycle A evaluates
    one -- comparing a guard against an arriving message and a register's
    current value, and deciding whether the transition fires, is cycle
    B's engine, the same boundary `Register`'s docstring draws for a fold.
    """

    def __init__(self, field, op, register):
        self.field = field
        self.op = op
        self.register = register


class State(object):
    """A state, with two independent properties that are easy to conflate.

    `accepting` -- nothing further is *required*. It is fine for the
    conversation to stop here, with nothing owed to anybody.

    `terminal` -- nothing further is *possible*. No transition leaves.

    All four combinations are meaningful. A conclusion is both. A responder
    sitting idle, willing to answer another question but owing nobody
    anything, is accepting and not terminal. A session that has just sent a
    message and is waiting for the reply is neither. And an abort -- a
    protocol violation, a peer that went away -- is terminal and *not*
    accepting: the conversation ended while something was still owed, and
    saying so is the whole point of the state.

    `accepting` defaults to False, which is the conservative direction: an
    author who declares nothing accepting gets a machine the checker
    rejects by name, rather than one where stopping anywhere is silently
    fine.
    """

    def __init__(self, name, holder=None, terminal=False, accepting=False):
        self.name = name
        self.holder = holder
        self.terminal = terminal
        self.accepting = accepting


class Transition(object):
    def __init__(self, frm, on, by, to, signal=False, effects=None, guard=None):
        self.frm = frm
        self.on = on
        self.by = by
        self.to = to
        self.signal = signal
        self.effects = list(effects or [])
        # `Guard` or `None`. `None` means this transition fires
        # unconditionally -- there is no empty `Guard` standing in for
        # "no guard", the same reasoning `Register`'s absence-is-`None`
        # comment gives for `fields`/`registers` on `Machine`.
        self.guard = guard


# The closed set of things a declared `cap` counts over. Closed for the
# same reason `FIELD_TYPES` and `FOLDS` are: an open scope word would let
# a publisher write something the cap-satisfiability check has no meaning
# for. `channel` is what a bare `cap: N` has always meant -- the cap
# bounds outbound messages across the one run as a whole -- and stays the
# default both when `per` is written as `channel` and when the mapping
# form is not used at all. `role` bounds each declared role's own
# outbound messages separately: the same limit applied once per role
# rather than once for the whole run. There is no `run` scope, because a
# run is a channel under a different name, and no per-sender scope, because
# the declaration has no word for a message's sender -- see SCHEMA.md.
CAP_SCOPES = ("channel", "role")


class Machine(object):
    def __init__(self, name, version, prefix, roles, kinds, cap,
                 initial, states, transitions, fields=None, registers=None,
                 cap_scope="channel"):
        self.name = name
        self.version = version
        self.prefix = prefix
        self.roles = roles
        self.kinds = kinds
        self.cap = cap
        # What `cap` counts over -- one of `CAP_SCOPES`. Meaningful only
        # when `cap` is not `None`; carries the default `"channel"` even
        # when there is no cap to scope, the same way `fields`/`registers`
        # default to `{}` rather than requiring a caller to check for
        # `None` first.
        self.cap_scope = cap_scope
        self.initial = initial
        self.states = states
        self.transitions = transitions
        # Dict[str, Field], keyed by field name. Defaults to `{}`, not
        # `None`: a machine with no declared fields still has something
        # iterable and indexable, the same reasoning `Transition.effects`
        # already applies to `effects=None`.
        self.fields = fields if fields is not None else {}
        # Dict[str, Register], keyed by register name. Defaults to `{}`
        # for the same reason `fields` does.
        self.registers = registers if registers is not None else {}


# `prefix` is not just a string -- it is source text pattern.py compiles to
# an NFA. `_parse_cat` (the recursive-descent parser's grammar production
# for concatenation) is an iterative loop, not per-character recursion, so
# parsing itself survives a long bare literal; but it builds a left-deep
# `Cat(Cat(Cat(...), Lit), Lit)` tree, one level per character, and the
# Thompson NFA compiler's `_compile_cat` walks that tree by recursing into
# `node.left` -- so a long enough literal exhausts Python's call stack
# during *compilation*, with no `(`, `|`, or repetition operator anywhere
# in it, and nothing about the parse stage itself at fault.
#
# Measured: a 498-character literal prefix compiles; 499 raises
# `RecursionError` out of `compile_pattern`, reached via `check_machine`
# (see `prefix_problem` below) or via `declaration.parse` (see
# declaration.py's `_require_prefix_length`, which enforces this same
# limit at parse time, before a `Machine` even exists), past every shape
# guard above, as an uncaught traceback -- exit 1 from `machines-check`
# for a crash, not a finding.
#
# 400 is the limit for *this* route: two orders of magnitude above
# `session-relay:v1 ` (17 characters) or any other plausible protocol
# prefix, comfortably under the 498 where a bare literal's recursion
# fails, checked both here and in declaration.py's `_require_prefix_length`
# before the pattern parser ever sees the text, so a publisher -- or, for
# a hand-built `Machine` that skipped the parser, a caller of
# `check_machine` -- gets a named field and a stated limit instead of a
# stack trace for that shape of input.
#
# CORRECTION: an earlier version of this comment called 498 "the exact
# failure this module's shape guards otherwise exist to prevent" -- true
# only for a bare literal. A prefix built from nested `(...)` groups
# recurses in the *parser*, not just the compiler, and hits it far
# shallower: `'(' * 199 + 'a' + ')' * 199` is 399 characters -- under this
# 400-character guard -- and still raised an uncaught `RecursionError`
# through the shipped CLI. This length guard bounds the concatenation-
# chain route (a long flat Cat/Alt tree, whatever it's built from --
# literals, `|` branches, or short reps) and nothing else; it was never a
# bound on nesting depth. Nesting depth has its own guard now
# (`_MAX_GROUP_DEPTH` in pattern.py, checked in `_parse_group`), and
# whatever either guard misses is caught as a last resort by
# `prefix_problem`'s `RecursionError` handler, rather than propagating as
# a traceback.
#
# This constant used to live only in declaration.py, and so did the check
# against it: a `Machine` built by `declaration.parse` could never carry
# an over-length prefix, because `_require_prefix_length` raises before
# one is constructed. But `prefix_problem` exists precisely so a
# hand-built `Machine` -- one that skipped the parser and its shape
# guards entirely, the same case the module docstring on `check_all`
# already names for `TypeError` -- gets the same answer `check_machine`
# gives everyone else. Defined here, once, and imported into
# declaration.py, so the two enforcement points share one number rather
# than risking two.
_MAX_PREFIX_LENGTH = 400


# Phase 2 of the per-role cap check (see the cap block in `check_machine`,
# below) searches `(state, per-role counter vector)`, one counter per
# declared role, each ranging over `0..limit`, once for every subject
# phase 1 could not already clear -- this guards ONE such search's state
# space before it ever runs, the same way `_MAX_PREFIX_LENGTH` (above) and
# pattern.py's `_MAX_NFA_STATES` guard their own searches before running
# them. It does not bound `check_machine`'s total work on a machine with
# more than one unresolved subject: the search below runs once per such
# subject, so a machine with many of them costs a multiple of this bound,
# not the bound itself -- still finite, still returns, just not "this
# many states visited, once."
#
# The precedent that makes the number below non-negotiable without a
# measurement beside it: pattern.py's `_MAX_NFA_STATES` shipped with the
# rationale "this allows a five-thousand-character literal", which was
# wrong by a factor of ten -- recursion bound the real limit first, at 498
# characters. The value was fine; the unmeasured claim beside it was the
# defect. So, measured here (Python 3.11.9), against the two declarations
# this cycle ships (`m.states`, `limit`, and `m.roles` read straight off
# each): session-relay is 5 states, `limit: 10`, 2 roles --
# `5 * (10 + 1) ** 2 = 605`; paxos-acceptor is 5 states, `limit: 6`,
# 2 roles -- `5 * (6 + 1) ** 2 = 245`. Against a budget of 1,000,000 that
# is 1,653x headroom for session-relay and 4,082x for paxos-acceptor --
# about three orders of magnitude, not six, which is the number an
# unmeasured "the budget is a million and the real machines are in the
# hundreds" reflex would have written.
#
# **A second, sharper bound applies before this one even gets consulted,
# and an earlier version of this comment missed it -- the same
# `_MAX_NFA_STATES` shape one level down, this time in the comment rather
# than the code.** Edge weights are 0 or 1, so a cheapest route is always
# achievable by some *simple* path (repeating a state only adds cost), and
# a simple path visits at most `len(states)` states, i.e. at most
# `len(states) - 1` edges. So no subject's channel-scope distance can ever
# exceed `len(states) - 1`, and phase 2 is reached at all -- for any
# `limit`, at any role count -- only when `limit <= len(states) - 2`.
# `len(states) - 2` is also the `limit` at which the phase-2 product,
# `states * (limit + 1) ** roles`, is LARGEST (it only grows with `limit`
# over that range) -- which is exactly why the boundary construction below
# fixes `limit` there: it is the worst case, not merely a reachable one.
#
# Whether that worst case still clears the budget depends on states AND
# roles together, not on states alone -- a blanket "this guard is
# irrelevant to small machines at any role count" would itself be false:
# a 5-state machine's product at its largest reachable `limit`, 3, first
# exceeds the budget at 9 declared roles (`5 * 4 ** 9 = 1,310,720`). For
# the role counts this cycle's declarations and the table below actually
# use (2-4), though, it holds: a 5-state machine can never have a subject
# more than 4 signalling transitions from an accepting state, so
# `limit: 30` (or any limit above 3) never even reaches phase 2 at 2, 3 or
# 4 declared roles -- phase 1 clears every subject first, every time.
# Measured, both bounds together (states, roles, the largest `limit`
# phase 2 is ever reached at, the largest `limit` this guard would still
# permit if reached):
#
#   states   roles   reachable-at-all bound (states-2)   budget bound   binds?
#        5       2                                    3            446   no -- reachability wins
#        5       3                                    3             57   no -- reachability wins
#        5       4                                    3             20   no -- reachability wins
#       20       2                                   18            222   no -- reachability wins
#       20       4                                   18             13   YES -- budget wins
#
# Only the 20-state, 4-role row can ever actually trip this guard; the
# other four never reach a `limit` where the budget bound is the tighter
# one. Where silence genuinely begins, measured by finding the smallest
# machine (a single chain, every signalling edge fired by one declared
# role among several, `limit = states - 2` -- the LARGEST `limit` at
# which phase 2 is reached at all, so the one most likely to trip the
# guard) whose product first exceeds budget:
# 17 states at 4 roles (`limit: 15`, product 1,114,112), 9 states at 6
# roles (`limit: 7`, product 2,359,296), 33 states at 3 roles (`limit:
# 31`, product 1,081,344). Below each of those state counts, at its own
# role count, this guard is provably never consulted, however large
# `limit` is written -- phase 1 clears everything first.
#
# The fact that still matters, restated correctly rather than dropped:
# phase 2 is only ever reached by a subject phase 1 could not already
# clear -- one whose shortest run to an accepting state needs *more than
# `limit`* signalling transitions in total, counting every role together.
# That is the explanation of the `states - 2` bound above (a route that
# long needs that many states to walk through), not a separate comfort
# layered on top of it. Both facts belong in this comment and in
# SCHEMA.md; publishing a number without checking which bound actually
# governs it is the exact defect `_MAX_NFA_STATES` shipped once already.
_MAX_CAP_SEARCH = 1_000_000


def prefix_problem(prefix):
    """Check a prefix pattern for whether a `Machine` can actually use it:
    whether it is short enough, and whether it will compile.

    Returns None when `prefix` is fine; otherwise a human-readable problem
    string naming the field, `"prefix pattern %r: ..."`. This is a
    property of one machine's own declaration, not of a set of them, and
    used to be checked only in `registry.py`'s `check_all` (compilation)
    and `declaration.py`'s `_require_prefix_length` (length, at parse
    time, before a `Machine` exists) -- which meant a caller that used
    `check_machine` directly on a hand-built `Machine` (the documented
    answer to "is this machine well-formed", and exactly what cycle B's
    engine does) got no prefix validation at all. It is called from
    `check_machine` below for exactly that reason, and from `check_all` to
    decide whether a machine is fit to compare against others for a
    collision -- a pattern that will not compile cannot be intersected
    with anything.

    The length check first: over `_MAX_PREFIX_LENGTH` characters is
    rejected by name before `compile_pattern` is even called, the same as
    declaration.py's `_require_prefix_length` does at parse time -- see
    that constant, above, for the measurement and reasoning. A `Machine`
    built by `declaration.parse` can never reach here with an over-length
    prefix (that function already raised), so this cannot double-report
    against a parsed machine; it only ever fires for a hand-built one.

    Then `compile_pattern` itself, which catches `PatternError` -- from an
    unparseable prefix, or one that is nullable (matches the empty string,
    and would therefore claim every message; see pattern.py's
    `compile_pattern`) -- and nothing else, except one backstop.

    A prefix nested deep enough in `(...)` groups is named by `PatternError`
    too -- pattern.py's parser tracks nesting depth and rejects past 100
    levels, well short of where it would recurse into a raw
    `RecursionError`. That guard is the ordinary case; `RecursionError`
    itself is also caught here, alongside `PatternError`, as a backstop --
    converted to the same kind of named problem -- for whatever AST shape
    (if any) reaches a deep stack some other way, in either the parser or
    the compiler. See pattern.py's `_MAX_GROUP_DEPTH` for the measurement
    and reasoning; the handler below stays trivial on purpose (no
    formatting that calls back into pattern code, no further recursion),
    since `RecursionError` fires with the stack nearly exhausted. This
    backstop is what keeps SCHEMA.md's promise that nothing a publisher
    writes reaches them as a Python traceback true of a bad prefix
    specifically, and it must move with the compile call rather than stay
    behind in `registry.py` -- a raw 399-character nested prefix reached an
    uncaught traceback through the shipped CLI before this guard existed.
    """
    if len(prefix) > _MAX_PREFIX_LENGTH:
        return ("prefix pattern %r: prefix is %d characters long; the "
                "limit is %d characters"
                % (prefix, len(prefix), _MAX_PREFIX_LENGTH))
    try:
        compile_pattern(prefix)
    except PatternError as exc:
        # Name the field. Every other `check_machine` message says which
        # field it is about; without the prefix here, a publisher reads
        # `unclosed group starting at position 0` and has to guess which
        # of eleven fields is a pattern at all.
        return "prefix pattern %r: %s" % (prefix, exc)
    except RecursionError:
        return "prefix pattern %r: too deeply nested to analyse" % (prefix,)
    return None


def check_machine(m):
    """Check a machine for well-formedness.

    Returns a list of human-readable problems. An empty list means the
    machine is well-formed. This returns problems rather than raising,
    because a publisher wants every problem at once, not the first one.

    **This no longer checks that the machine terminates, and that is
    deliberate.** An earlier version required `cap`, required at least one
    terminal state, and required every state to reach one -- which writes
    "a protocol terminates" into the framework as a law. It is not one. It
    is a property of some protocols, and requiring it of all of them forces
    an author with a continuous protocol to declare a bound they do not
    mean. A declared bound nobody believes is the exact failure this
    framework exists to answer.

    What is checked instead is that nobody is ever owed something forever
    with no exit: at least one state must be somewhere nothing is owed, and
    every state where something *is* owed must be able to reach somewhere a
    run may legitimately stop -- an accepting state, or a terminal one.
    Stopping badly is still an exit, and a protocol that stops badly on
    purpose, with effects that tell the peers, is doing its job.
    """
    problems = []

    bad_prefix = prefix_problem(m.prefix)
    if bad_prefix is not None:
        problems.append(bad_prefix)

    names = set(m.states)

    initial_declared = m.initial in names
    if not initial_declared:
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
            if effect == "escalate":
                continue
            prefix = next(
                (p for p in ("label.add:", "label.remove:") if effect.startswith(p)),
                None,
            )
            if prefix is None or len(effect) == len(prefix):
                problems.append("effect %r is not in the vocabulary "
                                "(label.add:<name>, label.remove:<name>, escalate)"
                                % effect)

    terminals = set(n for n, s in m.states.items() if s.terminal)
    accepting = set(n for n, s in m.states.items() if s.accepting)

    # At least one place where nothing is owed. This is the one property of
    # the old termination requirement worth keeping, restated: a protocol
    # with no state in which the conversation may rest is a protocol that
    # is never in a good state. It is not the same as "must terminate" --
    # an accepting state may have any number of transitions out of it --
    # and a machine with no terminal state at all satisfies it happily.
    #
    # Note this is *not* redundant with the reachability check below, and
    # deleting it would not be caught there: a machine whose every state is
    # non-accepting but which does have terminal states passes reachability
    # (everything can reach a terminal state) and would sail through with
    # nowhere for a run to rest.
    if not accepting:
        problems.append("no state is accepting; at least one state must be "
                        "a place the conversation may rest with nothing owed")

    for t in m.transitions:
        if t.frm in terminals:
            problems.append("terminal state %r has an outgoing transition" % t.frm)

    # Determinism, with a guarded branch as the one legitimate exception.
    # Two transitions sharing (frm, on, by) with different `to` states
    # leave the machine with a choice no declaration resolves, unless a
    # guard on every one of them proves the choice is never actually
    # offered. The engine is specified as a fold over the message trace,
    # and a fold is a function: it has exactly one result per (state,
    # message). A nondeterministic declaration therefore cannot be run at
    # all, and nothing else here says so -- every other check passes on it.
    #
    # The rule, in the order it is checked, for each group whose distinct
    # `to` values number more than one (a group with only one is a
    # duplicate, not an ambiguity, and is skipped entirely, same as
    # before):
    #
    #   1. Any member with no guard -- an unguarded transition always
    #      fires, so it overlaps everything else in the group. Reported.
    #   2. The members' guards do not all compare the same `field` to the
    #      same `register` -- two different comparisons cannot be related
    #      to each other without interpreting the values they compare,
    #      which is precisely what the two-outcome abstraction (`OP_ATOMS`,
    #      above) exists to avoid needing to do. Reported.
    #   3. Any two members' `OP_ATOMS` sets intersect -- both guards can
    #      hold for the same comparison outcome, so the branch they guard
    #      is still a choice. Reported, naming both operators. Checked
    #      pairwise across the *whole* group, including two members that
    #      happen to agree on `to`: they may still disagree on `effects`,
    #      and the verdict has no way to know which set was required.
    #   4. Otherwise: the guards partition the comparison's outcomes, so
    #      exactly one member fires for any value the field and register
    #      can produce. Not reported.
    #
    # What this proves, and what it does not: disjointness, never
    # completeness. A group of `ge` alone -- an acceptor that accepts a
    # high ballot and does nothing at all with a low one -- is legal: an
    # incomplete guard set means some outcome fires no transition, which is
    # the same outcome as an illegal message, and the engine's verdict
    # already reports that. Reporting it here too would be an
    # unsuppressible finding on a valid machine, which is the thing §9
    # refuses.
    groups = {}
    for t in m.transitions:
        groups.setdefault((t.frm, t.on, t.by), []).append(t)
    for trigger in sorted(groups):
        members = groups[trigger]
        targets = set(t.to for t in members)
        if len(targets) <= 1:
            continue
        problem = (
            "transitions from %r on %r by %r are nondeterministic: they "
            "lead to %s" % (trigger[0], trigger[1], trigger[2],
                            ", ".join(repr(x) for x in sorted(targets))))
        if any(t.guard is None for t in members):                      # 1
            problems.append(problem)
            continue
        fields = set(t.guard.field for t in members)
        registers = set(t.guard.register for t in members)
        if len(fields) > 1 or len(registers) > 1:                      # 2
            problems.append(problem)
            continue
        overlap = None
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                op_i, op_j = members[i].guard.op, members[j].guard.op
                # `op` is validated against `OP_ATOMS` by `parse`
                # (`_guard_field` in declaration.py), but a hand-built
                # `Machine` is a first-class caller here too -- that is
                # exactly what cycle B's engine constructs -- and does
                # not go through `parse`. An operator outside `OP_ATOMS`
                # cannot be related to anything: report the group as
                # nondeterministic rather than indexing `OP_ATOMS` and
                # raising `KeyError`, and rather than `.get(op,
                # frozenset())`, which would silently treat the unknown
                # operator as disjoint from every other guard and let a
                # malformed machine pass this check clean. Unprovable
                # disjointness is not disjointness; reporting is the
                # safe direction.
                if op_i not in OP_ATOMS or op_j not in OP_ATOMS:        # 3
                    overlap = (op_i, op_j)
                    break
                if OP_ATOMS[op_i] & OP_ATOMS[op_j]:                     # 3
                    overlap = (op_i, op_j)
                    break
            if overlap is not None:
                break
        if overlap is not None:
            problems.append(
                "%s (guards %r and %r overlap)" % (problem, overlap[0], overlap[1]))
        # else: rule 4 -- the guards partition the outcomes; not reported.

    # Holder agreement. A state's `holder` and a transition's `by` both
    # answer "who acts next" -- the channel-layer property the design makes
    # checkable. Declared twice and never reconciled, they can disagree:
    # a state held by `initiator` whose only exits are `by: responder` says
    # the initiator must act and that only the responder can.
    #
    # Terminal states are exempt (nobody acts next), and so is a state with
    # no `holder` at all, which is optional: with nothing declared there is
    # nothing to contradict. A non-terminal state with no outgoing
    # transition agrees vacuously; if something is owed there, the
    # can-a-run-stop check below reports it, and if nothing is owed there
    # (it is accepting) it is a resting place that simply happens not to be
    # declared terminal, which is not a defect.
    #
    # Accepting states are *not* exempt. Accepting says nothing is
    # *required* next, not that nothing can happen next: an accepting state
    # with outgoing transitions still has a role who acts if anyone does,
    # and `holder` naming a different one is still a contradiction.
    outgoing_by = {}
    for t in m.transitions:
        outgoing_by.setdefault(t.frm, set()).add(t.by)
    for name in sorted(names):
        s = m.states[name]
        if s.terminal or s.holder is None:
            continue
        disagreeing = sorted(a for a in outgoing_by.get(name, ()) if a != s.holder)
        if disagreeing:
            problems.append(
                "state %r declares holder %r but has outgoing transitions by %s"
                % (name, s.holder, ", ".join(repr(a) for a in disagreeing)))

    # An unused kind. A kind nobody fires on is vocabulary a publisher
    # believes is part of the protocol and that the protocol cannot
    # receive: the declaration says the machine understands it, and no
    # state does anything with it.
    fired_on = set(t.on for t in m.transitions)
    for kind in sorted(set(m.kinds) - fired_on):
        problems.append("kind %r is declared but no transition fires on it" % kind)

    # Registers: R1-R4. `declaration.parse` already enforced everything
    # about a register's own shape (a mapping, a `NAME`-shaped key,
    # exactly the four keys `fold`/`field`/`on`/`initial`, `fold` in
    # `FOLDS`, `on` a non-empty list of strings, `initial` an `int` or a
    # `bool`); what is left is cross-referencing one register's
    # declaration against `fields` and `kinds`, both declared elsewhere
    # in the same document, which is exactly what a parser -- reading one
    # key at a time -- cannot do.
    #
    # R3 is skipped for a register whose `field` is itself undeclared
    # (R1 already fired): there is no field type left to compare
    # `initial` against, the same reason the reachability and cap checks
    # below are skipped when `initial` (the state) is undeclared.
    #
    # The fold/argmax boundary, recorded here because a later session
    # reaching for `argmax` will look here first. A register remembers
    # one scalar, seeded at `initial`, and updated by exactly one field
    # read per matching step: conceptually, `register = fold(register,
    # message.field)` for every message whose kind is in `on`. `max` and
    # `last` both fit that shape, and both keep the register's value the
    # same Python type as the field across every step -- `max` because
    # comparing two values of the same type produces one of that same
    # type, `last` because it never combines anything, it only replaces.
    # That is what makes R3's type check ("`initial`'s type matches the
    # field's declared type") a promise that holds for the register's
    # entire life, not just at the start.
    #
    # `argmax` does not fit the shape: "the message that produced the
    # maximum" is a second value remembered alongside the scalar -- which
    # message, or which of its other fields -- and that second value is
    # not in general an `int` or a `bool` either. Admitting `argmax`
    # would mean admitting a second remembered value and a second type
    # for it, which is a different, larger feature than a bigger fold
    # over the one scalar this schema declares. `FOLDS` stays closed to
    # `max` and `last` until that is designed on purpose, not backed into
    # by one more string in a tuple.
    #
    # A third property, easy to read past: `FIELD_TYPES` is closed to
    # `int` and `bool`, so there is nothing a register could ever hold
    # that is a *payload* -- only a value a guard can order or test for
    # equality. Paxos's own next step needs exactly a payload: once a
    # proposer holds a quorum's worth of promises, it must propose the
    # *value* one of them already carried, not just the ballot that won.
    # That value is content, and content has no declarable field to carry
    # it in -- so no fold over this schema's fields, `max`, `last`, or a
    # future `argmax`, can ever be the register that remembers it.
    #
    # Nor can two registers forge it. `highest_ballot: max(ballot)`
    # alongside `chosen: last(value)` looks like it tracks both halves,
    # but `value` is content with no field to name it in the first place,
    # and even granting one, `last` remembers the *most recent* reading,
    # not the one paired with the maximum -- the two folds run
    # independently and go out of step on the first message that arrives
    # out of order. The forgery is not merely outside the vocabulary; it
    # computes the wrong answer, silently, the first time it matters.
    for name in sorted(m.registers):
        r = m.registers[name]
        field_declared = r.field in m.fields
        if not field_declared:                                        # R1
            problems.append(
                "register %r names undeclared field %r" % (name, r.field))
        for kind in r.on:                                              # R2
            if kind not in m.kinds:
                problems.append(
                    "register %r is fed by undeclared kind %r"
                    % (name, kind))
        if field_declared:                                             # R3
            field_type = m.fields[r.field].type
            initial_type = "bool" if isinstance(r.initial, bool) else "int"
            if initial_type != field_type:
                problems.append(
                    "register %r has initial %r, which is %s, but field "
                    "%r is declared %s"
                    % (name, r.initial, initial_type, r.field, field_type))
        if name in m.fields:                                           # R4
            problems.append(
                "register %r shares its name with a declared field"
                % (name,))

    # Guards: G1-G5. `declaration.parse` already enforced everything about
    # a guard's own shape (a mapping, exactly the three keys
    # `field`/`op`/`register`, each a string, `op` in `OP_ATOMS`); what is
    # left is cross-referencing a guard's `field` and `register` against
    # `fields` and `registers`, both declared elsewhere in the same
    # document, the same split the R1-R4 comment above draws for a
    # register's own `field` and `on`.
    #
    # G3 and G4 are both skipped when a name they would need is itself
    # undeclared -- G1/G2 already fired for that name, or (G4 only) the
    # register's own `field` is undeclared and R1 already fired for it --
    # the same reason R3 above is skipped for a register whose `field` is
    # undeclared: there is no field type left to compare against.
    #
    # One check named in the design this schema follows has no code here
    # on purpose: that the value a guard compares against is derivable
    # from the trace and nowhere else. It is enforced by construction, not
    # by a check that could fail -- a register's only source is a `fold`
    # over a `field` of messages of declared `kinds` (see `Register`,
    # above), and there is no syntax anywhere in this schema for a
    # register to come from anything else. A check here would have
    # nothing to reject.
    guarded_registers = set()
    for t in m.transitions:
        g = t.guard
        if g is None:
            continue
        # Identified by all four of (frm, on, by, to), not just the first
        # three: two transitions sharing (frm, on, by) but landing in
        # different states is exactly the case a guard exists to
        # disambiguate, so a guard message that dropped `to` would make
        # two distinct guards on that pair produce byte-identical
        # problems -- silently losing one report to any caller that
        # de-duplicates, on the declaration's own motivating case.
        where = "guard on transition from %r on %r by %r to %r" % (t.frm, t.on, t.by, t.to)
        field_declared = g.field in m.fields
        if not field_declared:                                        # G1
            problems.append("%s names undeclared field %r" % (where, g.field))
        register_declared = g.register in m.registers
        if not register_declared:                                     # G2
            problems.append("%s names undeclared register %r" % (where, g.register))
        else:
            guarded_registers.add(g.register)
        if field_declared and g.op in ORDERING_OPS:                    # G3
            field_type = m.fields[g.field].type
            if field_type != "int":
                problems.append(
                    "%s uses ordering operator %r on field %r, which is "
                    "declared %s, not int -- ordering has no meaning the "
                    "engine could implement for a non-int field"
                    % (where, g.op, g.field, field_type))
        if field_declared and register_declared:                       # G4
            register_field = m.registers[g.register].field
            if register_field in m.fields:
                field_type = m.fields[g.field].type
                register_field_type = m.fields[register_field].type
                if field_type != register_field_type:
                    problems.append(
                        "%s compares field %r (%s) against register %r "
                        "(%s)" % (where, g.field, field_type, g.register,
                                 register_field_type))

    for name in sorted(m.registers):                                   # G5
        if name not in guarded_registers:
            problems.append(
                "register %r is declared but no guard names it" % (name,))

    # The reachability and cap checks both need a declared `initial` to
    # mean anything: with an undeclared initial state, forward-flooding
    # from it reaches nothing, which would report every other declared
    # state as unreachable *and* as unable to stop -- N+2 derivative
    # problems burying the one real one. Skip them and let the `initial`
    # message stand alone; the publisher re-runs after fixing `initial`,
    # which is cheap.
    if initial_declared:
        forward = {}
        backward = {}
        for t in m.transitions:
            forward.setdefault(t.frm, set()).add(t.to)
            backward.setdefault(t.to, set()).add(t.frm)

        reachable = _flood({m.initial}, forward)
        for name in sorted(names - reachable):
            problems.append("state %r is not reachable from the initial state" % name)

        # Nobody is owed something forever with no exit. The property is
        # "can this run ever stop", not "does this run terminate", so the
        # goal set is every state where a run may legitimately stop: an
        # accepting state (nothing further required) *or* a terminal one
        # (nothing further possible).
        #
        # Terminal non-accepting states must be seeds, not subjects. Such a
        # state is an error state -- an abort, a protocol violation, a peer
        # that went away -- and reaching it on purpose, with effects that
        # notify the peers, is a protocol doing its job. It can reach
        # nothing at all, by construction, so asking it to reach an
        # accepting state would report every error state in every protocol
        # as a defect. Seeding it instead says the right thing: arriving
        # there is a way for the conversation to stop.
        #
        # Accepting states are seeds for the same structural reason -- a
        # state a run may rest in owes no path onward.
        #
        # This is a seed change from the check it replaces (which flooded
        # backwards from `terminals` alone), not an algorithm change:
        # `_flood` takes its starting set as an argument and assumes
        # nothing about what the members are.
        can_stop = _flood(terminals | accepting, backward)
        for name in sorted(reachable - can_stop):
            problems.append(
                "state %r cannot reach a state where a run may stop; it owes "
                "a response and can reach no accepting state and no terminal "
                "state" % name)

        # Cap satisfiability, and only when a cap was declared at all.
        # `cap` is optional: absent means this protocol states no bound,
        # and there is then nothing to compare the machine against. Skipped
        # entirely rather than defaulted, because inventing a bound here
        # would put a number in front of the publisher that they never
        # wrote.
        #
        # `cap` bounds the outbound messages one run may emit -- the
        # transitions it fires with `signal: true`, not every transition
        # it fires. A `signal: false` move is purely local: it is not an
        # outbound message and does not cost against the cap (see
        # SCHEMA.md's `cap` and `signal` sections).
        #
        # Subjects: every state reachable from `initial` that is neither
        # accepting nor terminal -- every state where something is owed
        # and the run can still move. Measuring only from `initial` (the
        # check this replaces) is why a cap on `session-relay` was never
        # exercised: `unopened` is initial and accepting, so that check's
        # one measurement was always zero. Neither an accepting state nor
        # a terminal non-accepting one is ever asked the question here:
        # an accepting state's own distance to the goal set below is
        # itself, i.e. zero, so no cap could ever be too small for it, and
        # a terminal non-accepting state (an abort) can reach nothing at
        # all, by construction, so it would only ever hit the
        # no-accepting-state-reachable case a few paragraphs down. A
        # subject this check can ever name is exactly a state the answer
        # is genuinely open for.
        #
        # Goal set: the accepting states, and only the accepting states --
        # deliberately narrower than `terminals | accepting`, the goal set
        # the can-a-run-stop check above uses. The two checks ask
        # different questions, and §7 is where that split is drawn: the
        # check above asks whether a run can escape limbo at all, and an
        # abort escapes it, so `terminals | accepting` is the right goal
        # set there. This check asks whether the declared budget buys
        # somewhere *good* -- a state where nothing is owed on purpose,
        # not a state the run gave up in -- and an abort is not somewhere
        # good. A cap that only reaches the error state is a cap that
        # cannot be satisfied, and saying so is this check's job, not a
        # case to paper over by widening the goal set to match §9's
        # literal (and, for this check, incorrect) wording.
        #
        # Cost of a route, by `m.cap_scope` (one of `CAP_SCOPES`):
        #
        #   channel -- the number of `signal: true` transitions on the
        #   route, however many roles fire them. One backward 0-1 BFS
        #   (`_signal_distances`, below) from the goal set, over every
        #   transition reversed, gives every state's distance to the
        #   nearest accepting state at once, in linear time.
        #
        #   role -- the *maximum over roles* of that role's own
        #   `signal: true` transitions on the route, computed in two
        #   phases because the naive per-role search is exponential in
        #   the role count:
        #
        #     1. Free. `max_r count_r <= total`, so any subject whose
        #        channel-scope distance already fits under the cap is
        #        satisfiable under `role` scope too -- the same backward
        #        0-1 BFS above clears it, no further search needed. In
        #        practice this clears every subject of every declaration
        #        in this cycle.
        #     2. For whatever phase 1 could not clear: search
        #        `(state, per-role counter vector)` forward from the
        #        subject (`_role_cap_satisfiable`, below), clamping every
        #        counter at `limit` and pruning any move that would push
        #        one over it. The subject is satisfiable under `role`
        #        scope iff that search reaches an accepting state. The
        #        state space is `len(m.states) * (limit + 1) **
        #        len(m.roles)` -- see `_MAX_CAP_SEARCH`, above
        #        `check_machine`, for the guard on it and the numbers
        #        measured beside that guard. Past the guard, nothing is
        #        reported for the remaining subjects: silence is the safe
        #        direction, the same as it is for the guard abstraction
        #        generally (§7) and for every unsuppressible finding this
        #        design already refuses (§9) -- a fatal "could not
        #        analyse" on a valid machine would be worse than a missing
        #        finding.
        #
        # Nothing is reported for a subject from which no accepting state
        # is reachable at all: that is already the reachability check's
        # finding (or the no-accepting-state one), and a cap message on
        # top of it would be a second symptom of one cause.
        if m.cap is not None:
            reversed_signal = {}
            for t in m.transitions:
                reversed_signal.setdefault(t.to, []).append(
                    (t.frm, 1 if t.signal else 0))
            channel_distance = _signal_distances(accepting, reversed_signal)

            if m.cap_scope == "role":
                forward_by_role = {}
                for t in m.transitions:
                    forward_by_role.setdefault(t.frm, []).append(
                        (t.to, t.by, 1 if t.signal else 0))
                role_index = {r: i for i, r in enumerate(sorted(m.roles))}
                # A `by` this loose is already reported by the
                # transition-validity loop at the top of this function
                # ("transition by names undeclared role"); phase 2 cannot
                # index a search space by a role that was never declared,
                # so it is skipped entirely for this machine rather than
                # guessed at -- the same reasoning R3, G3 and G4 already
                # apply above: skip the analysis a prerequisite it needs
                # cannot support, rather than crash on it or fabricate an
                # answer. Checked here, once, rather than inside
                # `_role_cap_satisfiable`'s search loop, so a machine with
                # an undeclared `by` costs one pass over `m.transitions`,
                # not a `KeyError` the first time the search reaches that
                # edge.
                role_names_valid = all(
                    t.by in role_index for t in m.transitions if t.signal)
                search_affordable = role_names_valid and (
                    len(m.states) * (m.cap + 1) ** len(m.roles)
                    <= _MAX_CAP_SEARCH)

            for name in sorted(reachable - accepting - terminals):
                d = channel_distance.get(name)
                if d is None:
                    continue
                if m.cap_scope != "role":
                    if d > m.cap:
                        problems.append(
                            "cap %d is too small: from state %r, the "
                            "shortest run to an accepting state fires %d "
                            "signalling transitions"
                            % (m.cap, name, d))
                    continue
                if d <= m.cap:
                    continue  # phase 1: cleared for free
                if not search_affordable:
                    continue  # too big for the guard, or an undeclared
                              # `by` phase 2 cannot index -- report nothing
                if not _role_cap_satisfiable(
                        name, accepting, forward_by_role, role_index, m.cap):
                    problems.append(
                        "cap %d is too small: from state %r, no run "
                        "reaches an accepting state without some role "
                        "sending more than %d signalling transitions"
                        % (m.cap, name, m.cap))

    return problems


def _signal_distances(goals, graph):
    """0-1 BFS distances from every member of `goals` to every node that
    can reach one, over `graph`, where `graph[node]` is a list of
    `(neighbour, weight)` edges and `weight` is 1 for a `signal: true`
    transition, 0 for `signal: false`. Returns `{node: distance}`; a node
    absent from the result cannot reach any member of `goals` at all.

    Called with `graph` already reversed (built from `t.to` to
    `(t.frm, weight)`, not the other way around) and `goals` as the
    accepting states: `dist[s]` after this call is then the cost of the
    cheapest *forward* run from `s` to some accepting state -- the
    quantity the cap check bounds -- for every state at once, rather than
    once per subject. Every member of `goals` seeds the search at distance
    0, the same "zero hops away", not "shortest cycle back to it" reading
    a single source would get; multi-source 0-1 BFS is exactly
    single-source with more than one node seeded before the loop starts,
    the algorithm does not otherwise distinguish them.

    0-1 BFS, not plain BFS: a graph with only 0/1 edge weights has a
    shortest-path structure plain (unweighted) BFS cannot compute
    correctly, because a 0-weight edge can make a "farther" node (by hop
    count) actually cheaper. A deque keeps the frontier ordered by
    distance without a heap: relaxing a node along a weight-0 edge pushes
    it to the *front* (it belongs at the current distance), and along a
    weight-1 edge pushes it to the *back* (it belongs one distance further
    out) -- so the deque is popped in non-decreasing distance order, same
    as plain BFS's FIFO queue is when every edge costs 1.
    """
    dist = {}
    frontier = deque()
    for g in goals:
        dist[g] = 0
        frontier.append(g)
    while frontier:
        node = frontier.popleft()
        d = dist[node]
        for target, weight in graph.get(node, ()):
            candidate = d + weight
            if candidate < dist.get(target, _INFINITY):
                dist[target] = candidate
                if weight == 0:
                    frontier.appendleft(target)
                else:
                    frontier.append(target)
    return dist


def _role_cap_satisfiable(start, goals, forward, role_index, limit):
    """Phase 2 of the per-role cap search (see the cap block in
    `check_machine`, above): can some run from `start` reach a member of
    `goals` without any single role firing more than `limit` `signal:
    true` transitions along the way?

    `forward[state]` is a list of `(target, by, weight)` edges (`weight`
    1 for `signal: true`, 0 for `signal: false`), and `role_index` maps a
    declared role name to its position in a per-role counter vector.
    Searches `(state, counters)` forward from `start`, incrementing the
    firing role's own counter on every `signal: true` edge and refusing to
    take an edge that would push a counter past `limit` -- so no counter
    in any node this search ever visits exceeds `limit`, and the space it
    can explore is bounded by `len(states) * (limit + 1) ** len(roles)`,
    the same product `_MAX_CAP_SEARCH` guards before this function is ever
    called.

    Plain reachability, not a shortest-path search: phase 1 (the caller's
    `_signal_distances`) already answered "is there a cheap enough route
    measured across every role together"; clamping each role's count and
    asking only "does some route keep every one of them under the limit"
    turns the question into reachability once the clamp is folded into
    the state, not a distance to minimise.
    """
    zero = (0,) * len(role_index)
    seen = {(start, zero)}
    stack = [(start, zero)]
    while stack:
        state, counters = stack.pop()
        for target, by, weight in forward.get(state, ()):
            if weight:
                i = role_index[by]
                if counters[i] >= limit:
                    continue  # this role would exceed the limit -- pruned
                next_counters = counters[:i] + (counters[i] + 1,) + counters[i + 1:]
            else:
                next_counters = counters
            if target in goals:
                return True
            node = (target, next_counters)
            if node not in seen:
                seen.add(node)
                stack.append(node)
    return False


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
