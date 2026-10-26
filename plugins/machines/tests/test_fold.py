import unittest
from pathlib import Path

from machines.declaration import parse
from machines.envelope import Envelope, Message, Trace, load_trace
from machines.fold import MAX_FOLD_STEPS, fold
from machines.machine import (Field, Guard, Machine, Register, State,
                              Transition, check_machine)

FIXTURES = Path(__file__).parent / "fixtures"


def _msg(kind, by, sender, clock, fields=None, world_reads=()):
    return Message(kind, by, Envelope(clock, sender), fields, world_reads)


def _trace(messages):
    return Trace("c", "m", "v1", True, messages)


def _paxos():
    return parse((FIXTURES / "valid-paxos-acceptor.md").read_text())


def _machine(transitions, registers=None, fields=None, kinds=("step",),
             roles=("r",), states=("a", "b")):
    return Machine(
        "m", "v1", "m:v1 ", {r: "session" for r in roles}, list(kinds), None,
        states[0],
        {s: State(s, accepting=True) for s in states}, transitions,
        fields=fields, registers=registers)


def _ge_only_machine():
    return _machine(
        [Transition("a", "step", "r", "b", guard=Guard("n", "ge", "reg"))],
        registers={"reg": Register("reg", "max", "n", ["step"], 5)},
        fields={"n": Field("n", "int")})


class FixtureFolds(unittest.TestCase):
    def test_the_session_relay_fixture_folds_to_concluded(self):
        m = parse((FIXTURES / "valid-session-relay.md").read_text())
        f = fold(m, load_trace(FIXTURES / "trace-session-relay.json"))
        self.assertEqual(f.state, "concluded")
        self.assertEqual(f.refusals, ())
        self.assertEqual(f.spent, {"initiator": 2, "responder": 2})
        self.assertEqual(f.clocks, {"repo-a": 3, "repo-b": 4})
        self.assertEqual(f.outbound_clock, 5)
        self.assertEqual([s.order for s in f.fired], ["ok"] * 4)

    def test_the_paxos_fixture_folds_to_decided_and_remembers_the_ballot(self):
        m = _paxos()
        f = fold(m, load_trace(FIXTURES / "trace-paxos-acceptor.json"))
        self.assertEqual(f.state, "decided")
        self.assertEqual(f.registers, {"highest_promised": 5})
        self.assertEqual(f.spent, {"proposer": 2, "acceptor": 2})
        self.assertEqual(f.clocks, {"p1": 3, "a1": 4})

    def test_an_empty_trace_is_the_initial_state_and_clock_one(self):
        f = fold(_paxos(), _trace([]))
        self.assertEqual((f.state, f.outbound_clock, f.steps, f.truncated),
                         ("idle", 1, 0, False))
        self.assertEqual(f.registers, {"highest_promised": 0})

    def test_the_limit_constant_exists(self):
        self.assertIsInstance(MAX_FOLD_STEPS, int)


class Ordering(unittest.TestCase):
    def test_a_guard_reads_the_register_before_the_arriving_message_is_folded_in(self):
        f = fold(_paxos(), _trace([_msg("prepare", "proposer", "p1", 1,
                                        {"ballot": 5})]))
        self.assertEqual(f.state, "prepared")  # NOT "idle": 5 > 5 is False
        self.assertEqual(f.registers, {"highest_promised": 5})
        reading = next(g for g in f.guards if g.op == "gt")
        self.assertEqual((reading.field_value, reading.register_value,
                          reading.atom, reading.fired), (5, 0, "GT", True))


class GuardRefusals(unittest.TestCase):
    def test_a_prepare_without_its_ballot_field_is_refused_because_both_guards_are_false(self):
        f = fold(_paxos(), _trace([_msg("prepare", "proposer", "p1", 1, {})]))
        self.assertEqual(f.state, "idle")
        self.assertEqual([r.reason for r in f.refusals], ["no transition"])
        self.assertEqual([g.fired for g in f.guards], [False, False])
        self.assertEqual([g.atom for g in f.guards], [None, None])

    def test_an_incomplete_guard_set_refuses_the_outcome_it_omits(self):
        f = fold(_ge_only_machine(), _trace([_msg("step", "r", "s1", 1,
                                                   {"n": 3})]))
        self.assertEqual([r.reason for r in f.refusals], ["no transition"])
        self.assertEqual(f.guards[0].atom, "LT")

    def test_a_refusal_does_not_advance_state_registers_spent_or_clock(self):
        m = _paxos()
        f = fold(m, _trace([_msg("prepare", "proposer", "p1", 7, {}),
                            _msg("prepare", "proposer", "p1", 8,
                                 {"ballot": 2})]))
        self.assertEqual(f.state, "prepared")
        self.assertEqual(f.clocks, {"p1": 8})
        self.assertEqual(f.refusals[0].index, 0)
        self.assertEqual(f.fired[0].index, 1)

    def test_an_operator_outside_the_vocabulary_does_not_fire_and_does_not_raise(self):
        m = _machine(
            [Transition("a", "step", "r", "b", guard=Guard("n", "bogus", "reg"))],
            registers={"reg": Register("reg", "max", "n", ["step"], 0)},
            fields={"n": Field("n", "int")})
        f = fold(m, _trace([_msg("step", "r", "s", 1, {"n": 1})]))
        self.assertEqual([r.reason for r in f.refusals], ["no transition"])
        self.assertFalse(f.guards[0].fired)
        self.assertIn("bogus", f.guards[0].note)

    def test_a_guard_naming_an_undeclared_register_does_not_fire_and_does_not_raise(self):
        m = _machine(
            [Transition("a", "step", "r", "b", guard=Guard("n", "gt", "nope"))],
            fields={"n": Field("n", "int")})
        f = fold(m, _trace([_msg("step", "r", "s", 1, {"n": 1})]))
        self.assertEqual([r.reason for r in f.refusals], ["no transition"])


class OtherRefusals(unittest.TestCase):
    def test_an_undeclared_kind_is_refused_by_name_not_a_key_error(self):
        f = fold(_paxos(), _trace([_msg("gossip", "proposer", "p1", 1)]))
        self.assertEqual([r.reason for r in f.refusals], ["undeclared kind"])
        self.assertEqual(f.state, "idle")

    def test_an_undeclared_role_is_refused_by_name(self):
        f = fold(_paxos(), _trace([_msg("prepare", "learner", "p1", 1,
                                        {"ballot": 1})]))
        self.assertEqual([r.reason for r in f.refusals], ["undeclared role"])

    def test_a_message_whose_by_is_not_the_states_holder_fires_nothing(self):
        f = fold(_paxos(), _trace([_msg("prepare", "acceptor", "a1", 1,
                                        {"ballot": 1})]))
        self.assertEqual([r.reason for r in f.refusals], ["no transition"])
        self.assertEqual(f.state, "idle")
        self.assertEqual(f.registers, {"highest_promised": 0})

    def test_a_bool_in_an_int_field_is_refused_rather_than_compared(self):
        f = fold(_paxos(), _trace([_msg("prepare", "proposer", "p1", 1,
                                        {"ballot": True})]))
        self.assertEqual([r.reason for r in f.refusals], ["field type"])
        self.assertEqual(f.guards, ())
        self.assertEqual(f.state, "idle")

    def test_an_int_in_a_bool_field_is_refused(self):
        m = _machine([Transition("a", "step", "r", "b")],
                     fields={"flag": Field("flag", "bool")})
        f = fold(m, _trace([_msg("step", "r", "s", 1, {"flag": 1})]))
        self.assertEqual([r.reason for r in f.refusals], ["field type"])

    def test_two_transitions_that_differ_only_in_effects_are_refused_as_ambiguous(self):
        m = _machine([
            Transition("a", "step", "r", "b", signal=True,
                       effects=["label.add:one"]),
            Transition("a", "step", "r", "b", signal=True,
                       effects=["label.add:two"])])
        self.assertEqual(check_machine(m), [])  # the checker passes it
        f = fold(m, _trace([_msg("step", "r", "s", 1)]))
        self.assertEqual([r.reason for r in f.refusals], ["ambiguous"])
        self.assertEqual(f.state, "a")
        self.assertEqual(f.fired, ())
        self.assertEqual(f.spent, {"r": 0})
        self.assertEqual(f.refusals[0].detail.count("('a', 'step', 'r', 'b')"), 2)

    def test_overlapping_guards_are_ambiguous_and_every_guard_is_read(self):
        m = _machine(
            [Transition("a", "step", "r", "b", guard=Guard("n", "ge", "reg")),
             Transition("a", "step", "r", "a", guard=Guard("n", "le", "reg"))],
            registers={"reg": Register("reg", "max", "n", ["step"], 5)},
            fields={"n": Field("n", "int")})
        f = fold(m, _trace([_msg("step", "r", "s", 1, {"n": 5})]))
        self.assertEqual([r.reason for r in f.refusals], ["ambiguous"])
        self.assertEqual([g.fired for g in f.guards], [True, True])
        self.assertEqual(f.registers, {"reg": 5})


class Registers(unittest.TestCase):
    def _reg_machine(self, fold_kind, on=("step",), initial=0):
        return _machine(
            [Transition("a", "step", "r", "a"),
             Transition("a", "other", "r", "a")],
            registers={"reg": Register("reg", fold_kind, "n", list(on),
                                       initial)},
            fields={"n": Field("n", "int")}, kinds=("step", "other"))

    def test_max_keeps_the_highest_value_seen_and_last_keeps_the_most_recent(self):
        msgs = [_msg("step", "r", "s", i + 1, {"n": v})
                for i, v in enumerate([3, 9, 4])]
        self.assertEqual(fold(self._reg_machine("max"), _trace(msgs))
                         .registers, {"reg": 9})
        self.assertEqual(fold(self._reg_machine("last"), _trace(msgs))
                         .registers, {"reg": 4})

    def test_a_register_is_untouched_by_a_kind_not_in_its_on_list(self):
        f = fold(self._reg_machine("last"),
                 _trace([_msg("other", "r", "s", 1, {"n": 8})]))
        self.assertEqual(f.registers, {"reg": 0})

    def test_a_register_holds_its_declared_initial_before_any_matching_message(self):
        f = fold(self._reg_machine("max", initial=7), _trace([]))
        self.assertEqual(f.registers, {"reg": 7})

    def test_a_register_whose_field_is_absent_from_a_matching_message_is_untouched(self):
        f = fold(self._reg_machine("last", initial=7),
                 _trace([_msg("step", "r", "s", 1, {})]))
        self.assertEqual(f.registers, {"reg": 7})
        self.assertEqual(f.refusals, ())


class Bookkeeping(unittest.TestCase):
    def test_the_outbound_clock_is_the_max_over_all_senders_plus_one(self):
        f = fold(_paxos(), _trace([
            _msg("prepare", "proposer", "p1", 9, {"ballot": 1}),
            _msg("promise", "acceptor", "a1", 2)]))
        self.assertEqual(f.clocks, {"p1": 9, "a1": 2})
        self.assertEqual(f.outbound_clock, 10)

    def test_world_reads_are_recorded_and_opaque(self):
        from machines.envelope import WorldRead
        f = fold(_paxos(), _trace([_msg("prepare", "proposer", "p1", 1,
                                        {"ballot": 1},
                                        [WorldRead("gh", {"x": [1]})])]))
        self.assertEqual([(w.index, w.verb, w.result) for w in f.world_reads],
                         [(0, "gh", {"x": [1]})])


if __name__ == "__main__":
    unittest.main()
