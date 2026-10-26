import inspect
import re
import unittest
from pathlib import Path

import machines.engine
import machines.envelope
import machines.fold
from machines.declaration import parse
from machines.envelope import Envelope, Message, Trace
from machines.fold import ORDERS, fold
from machines.machine import Machine, State, Transition

FIXTURES = Path(__file__).parent / "fixtures"


def _msg(kind, by, sender, clock, fields=None):
    return Message(kind, by, Envelope(clock, sender), fields)


def _trace(messages):
    return Trace("c", "m", "v1", True, messages)


PAXOS = parse((FIXTURES / "valid-paxos-acceptor.md").read_text())


def _loop(roles=("r",)):
    """A machine whose every message is accepted: one state, a self-loop per
    role, each counting against the cap."""
    return Machine(
        "m", "v1", "m:v1 ", {r: "session" for r in roles}, ["step"], None,
        "a", {"a": State("a", accepting=True)},
        [Transition("a", "step", r, "a", signal=True) for r in roles])


def _prepare_promise(promise_clock, promise_sender="a1"):
    return _trace([_msg("prepare", "proposer", "p1", 1, {"ballot": 5}),
                   _msg("promise", "acceptor", promise_sender, promise_clock)])


class Orders(unittest.TestCase):
    def test_there_are_exactly_four_order_values(self):
        self.assertEqual(
            ORDERS, ("ok", "duplicate", "out-of-order", "concurrent"))

    def test_a_clock_that_does_not_increase_from_one_sender_is_refused_as_a_duplicate(self):
        f = fold(PAXOS, _trace([
            _msg("prepare", "proposer", "p1", 1, {"ballot": 5}),
            _msg("promise", "acceptor", "a1", 2),
            _msg("promise", "acceptor", "a1", 2)]))
        self.assertEqual([(r.index, r.reason) for r in f.refusals],
                         [(2, "duplicate")])
        self.assertEqual(f.state, "promised")
        self.assertEqual(f.clocks["a1"], 2)

    def test_a_lower_clock_from_the_same_sender_is_refused_as_out_of_order(self):
        f = fold(_loop(), _trace([_msg("step", "r", "s", 2),
                                  _msg("step", "r", "s", 3),
                                  _msg("step", "r", "s", 2)]))
        self.assertEqual([(r.index, r.reason) for r in f.refusals],
                         [(2, "out-of-order")])
        self.assertEqual(f.clocks, {"s": 3})
        self.assertEqual(f.spent, {"r": 2})

    def test_two_senders_with_an_equal_clock_are_concurrent_and_neither_is_refused(self):
        f = fold(PAXOS, _prepare_promise(1))
        self.assertEqual(f.refusals, ())
        self.assertEqual(f.state, "promised")
        self.assertEqual([s.order for s in f.fired], ["ok", "concurrent"])

    def test_a_concurrent_step_names_the_other_senders(self):
        f = fold(_loop(), _trace([_msg("step", "r", "s1", 1),
                                  _msg("step", "r", "s2", 2),
                                  _msg("step", "r", "s3", 2),
                                  _msg("step", "r", "s4", 3)]))
        self.assertEqual(f.refusals, ())
        self.assertEqual([s.order for s in f.fired],
                         ["ok", "ok", "concurrent", "ok"])
        self.assertEqual([s.concurrent_with for s in f.fired],
                         [(), (), ("s2",), ()])

    def test_a_clock_below_another_senders_is_concurrent_too(self):
        f = fold(_loop(), _trace([_msg("step", "r", "s1", 1),
                                  _msg("step", "r", "s1", 2),
                                  _msg("step", "r", "s2", 1)]))
        self.assertEqual(f.refusals, ())
        self.assertEqual(f.fired[2].order, "concurrent")
        self.assertEqual(f.fired[2].concurrent_with, ("s1",))

    def test_a_clock_above_the_highest_seen_plus_one_is_refused_as_out_of_order(self):
        f = fold(_loop(), _trace([_msg("step", "r", "s1", 5),
                                  _msg("step", "r", "s1", 6),
                                  _msg("step", "r", "s2", 9)]))
        self.assertEqual([(r.index, r.reason) for r in f.refusals],
                         [(2, "out-of-order")])
        self.assertEqual(f.refusals[0].detail,
                         "clock 9 follows nothing seen; highest seen is 6")
        self.assertNotIn("s2", f.clocks)

    def test_a_repeated_message_is_a_duplicate_not_no_transition(self):
        # The paxos machine has no promise transition from `promised`, so the
        # clock verdict must be reached before the transition lookup.
        f = fold(PAXOS, _trace([
            _msg("prepare", "proposer", "p1", 1, {"ballot": 5}),
            _msg("promise", "acceptor", "a1", 2),
            _msg("promise", "acceptor", "a1", 2)]))
        self.assertEqual(f.refusals[0].reason, "duplicate")


class Keys(unittest.TestCase):
    def test_one_sender_acting_in_two_roles_keeps_one_clock_and_two_role_counts(self):
        f = fold(_loop(("r", "q")), _trace([_msg("step", "r", "x", 1),
                                            _msg("step", "q", "x", 2)]))
        self.assertEqual(f.refusals, ())
        self.assertEqual(f.clocks, {"x": 2})
        self.assertEqual(f.spent, {"r": 1, "q": 1})

    def test_two_senders_sharing_a_role_keep_two_clocks_and_one_role_count(self):
        f = fold(_loop(), _trace([_msg("step", "r", "s1", 1),
                                  _msg("step", "r", "s2", 2)]))
        self.assertEqual(f.refusals, ())
        self.assertEqual(f.clocks, {"s1": 1, "s2": 2})
        self.assertEqual(f.spent, {"r": 2})

    def test_a_refused_lower_clock_cannot_lower_a_senders_high_water_mark(self):
        # The per-sender rule refuses every clock at or below the mark, so an
        # accepted clock is always above it: `max(old, new)` and `new` cannot
        # differ, and no trace can pin the `max` itself. What is pinned here is
        # the observable half: a refused lower clock leaves the mark alone, and
        # the next clock is judged against the mark, not the refused message.
        f = fold(_loop(), _trace([_msg("step", "r", "s1", 1),
                                  _msg("step", "r", "s1", 2),
                                  _msg("step", "r", "s1", 1),
                                  _msg("step", "r", "s1", 2)]))
        self.assertEqual([r.reason for r in f.refusals],
                         ["out-of-order", "duplicate"])
        self.assertEqual(f.clocks, {"s1": 2})


class Outbound(unittest.TestCase):
    def test_the_outbound_clock_is_one_above_the_highest_clock_on_the_channel(self):
        f = fold(PAXOS, _trace([
            _msg("prepare", "proposer", "p1", 9, {"ballot": 1}),
            _msg("promise", "acceptor", "a1", 2)]))
        self.assertEqual(f.outbound_clock, 10)

    def test_the_outbound_clock_of_an_empty_trace_is_one(self):
        self.assertEqual(fold(PAXOS, _trace([])).outbound_clock, 1)

    def test_a_refused_message_does_not_raise_the_outbound_clock(self):
        f = fold(_loop(), _trace([_msg("step", "r", "s1", 1),
                                  _msg("step", "r", "s1", 2),
                                  _msg("step", "r", "s2", 9),
                                  _msg("step", "r", "s1", 1)]))
        self.assertEqual(len(f.refusals), 2)
        self.assertEqual(f.outbound_clock, 3)


class NoSeq(unittest.TestCase):
    def test_a_clock_is_never_called_seq_anywhere_in_the_engine(self):
        for mod in (machines.envelope, machines.fold, machines.engine):
            src = inspect.getsource(mod)
            self.assertIsNone(re.search(r"\bseq\b|\bseq_|_seq\b", src),
                              "%s names seq; #48 decision 1 forbids it"
                              % mod.__name__)
