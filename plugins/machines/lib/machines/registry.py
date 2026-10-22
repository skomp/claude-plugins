"""Check a set of installed machines: each one's own well-formedness, and
whether any two of them can claim the same message.

This is what a person actually reads at install time -- `product.py`'s
`patterns_collide` answers "do these two patterns collide" for a single
pair; this module turns that into a report over every machine that was
handed to it, using `machine.py`'s `check_machine` for each machine's own
well-formedness first.

One thing this module has to do that `patterns_collide` itself does not:

- A prefix that will not compile (unparseable, or nullable -- see
  pattern.py's `compile_pattern`) makes `patterns_collide` raise
  `PatternError`. `check_machine` reports that as one of a machine's own
  problems now (see `machine.py`'s `prefix_problem`, which is where the
  check itself, and the reasoning behind it, live), but this module still
  has to act on it: a machine whose prefix will not compile cannot be
  intersected with anything, so it is excluded from collision checking
  while every other machine is still checked against every other, bad
  machine included on neither side.

- Two machines with the same `name`, the same `publisher` and a
  different `version` are one protocol's history (an installer keeps old
  versions on purpose), not a collision, so that pair is skipped. Two
  absent publishers count as the same publisher, so every declaration
  written before `publisher` existed is skipped or compared exactly as it
  was. Every other pair is compared -- different names, or one name
  chosen by two publishers (one of them possibly absent) -- even when
  their prefixes are written identically: that is the collision this
  module exists to find.

Because a name alone no longer identifies a machine, every place this
module names one -- a `problems` key, each side of a `collisions` pair --
uses `label`: `publisher/name` when a publisher is declared, the bare
`name` when it is not. Otherwise a collision between two publishers'
`session-relay` would read as `session-relay` and `session-relay`.
"""

import itertools

from .machine import check_machine, prefix_problem
from .product import patterns_collide


def label(m):
    """The name a report uses for machine `m`: `publisher/name`, or the
    bare `name` when no publisher is declared. See the module docstring.
    """
    if m.publisher is None:
        return m.name
    return "%s/%s" % (m.publisher, m.name)


class Report(object):
    """The result of `check_all`.

    - `examined`: how many machines were looked at, including zero. A
      report that found no collisions because it was handed no machines
      must not read the same as a report that checked ten machines and
      found them all clean -- see the module-level docstring and
      `check_all` below.
    - `problems`: machine label (see `label`) -> its own list of problems, straight from
      `check_machine` (which includes a prefix that would not compile --
      see `machine.py`'s `prefix_problem`). A machine with no problems of
      its own is absent from this dict, not present with an empty list.
    - `collisions`: pairs of machine labels that can claim the same
      message, each pair as a sorted 2-tuple, each pair listed once, the
      whole list sorted -- so the output is stable across runs.
    """

    def __init__(self, examined, problems, collisions):
        self.examined = examined
        self.problems = problems
        self.collisions = collisions


def check_all(machines):
    """Check every machine in `machines` for its own well-formedness, then
    check every pair of machines that are not one protocol -- not the same
    `name` *and* `publisher` -- against each other for a collision.
    Returns a `Report`.

    A machine's own problems -- including a prefix pattern that will not
    compile -- come straight from `check_machine`; nothing here re-derives
    or re-catches that. See `machine.py`'s `prefix_problem` for what makes
    a prefix fail to compile (an unparseable pattern, a nullable one, or
    one nested too deep in `(...)` groups) and for the `RecursionError`
    backstop that keeps any of that from ever reaching a caller as a raw
    traceback.

    What this function still has to do with that result is decide
    collidability: `prefix_problem` is called again here, not to collect a
    second copy of the same problem, but because a pattern that will not
    compile cannot be intersected with anything -- the machine that
    carries it is left out of collision checking, and every other machine
    is still checked against every other.

    This function is deliberately not described as "never raises": a
    `Machine` constructed by hand, bypassing the parser's shape guards,
    can still carry a non-string `prefix` or a non-iterable `transitions`,
    and a resulting `TypeError` would pass through both `check_machine`
    and this function uncaught. `parse` is what makes that unreachable in
    practice (see declaration.py's shape guards), not a blanket catch here
    -- swallowing arbitrary exceptions would turn a bug in this library
    into a finding about the publisher's machine.
    """
    problems = {}
    collidable = []  # machines fit to compare (prefix compiles); the compiled
                     # pattern is not kept here -- patterns_collide recompiles
                     # both prefixes itself on every call

    for m in machines:
        own_problems = list(check_machine(m))
        if prefix_problem(m.prefix) is None:
            collidable.append(m)
        if own_problems:
            problems[label(m)] = own_problems

    collisions = []
    for a, b in itertools.combinations(collidable, 2):
        if a.name == b.name and a.publisher == b.publisher:
            # Same protocol, different (or, degenerately, the same)
            # version -- kept on purpose, not a collision. Two absent
            # publishers are equal here (`None == None`); one absent and
            # one present are not. See the module docstring.
            continue
        if patterns_collide(a.prefix, b.prefix):
            collisions.append(tuple(sorted((label(a), label(b)))))

    collisions.sort()

    return Report(len(machines), problems, collisions)
