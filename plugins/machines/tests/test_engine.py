import inspect
import re
import unittest
from pathlib import Path

import machines.engine
from machines.declaration import parse
from machines.engine import Offer, Remaining, Verdict, verdict
from machines.envelope import Envelope, Message, Trace, load_trace
from machines.machine import (Field, Guard, Machine, Register, State,
                              Transition)

FIXTURES = Path(__file__).parent / "fixtures"
SESSION_RELAY = parse((FIXTURES / "valid-session-relay.md").read_text())
PAXOS = parse((FIXTURES / "valid-paxos-acceptor.md").read_text())


def _msg(kind, by, sender, clock, fields=None):
    return Message(kind, by, Envelope(clock, sender), fields)


def _trace(messages):
    return Trace("c", "m", "v1", True, messages)


def _machine(cap, cap_scope="channel", transitions=None, states=None):
    states = states or {"a": State("a", holder="r", accepting=True),
                        "b": State("b", terminal=True, accepting=True)}
    transitions = transitions if transitions is not None else [
        Transition("a", "step", "r", "b", signal=True,
                   effects=["escalate"])]
    return Machine("m", "v1", "m:v1 ", {"r": "session", "s": "session"},
                   ["step"], cap, "a", states, transitions,
                   cap_scope=cap_scope)


class FixtureVerdicts(unittest.TestCase):
    def test_the_session_relay_fixture_and_its_trace_give_a_verdict(self):
        v = verdict(SESSION_RELAY,
                    load_trace(FIXTURES / "trace-session-relay.json"))
        self.assertTrue(v.legal)
        self.assertIsNone(v.reason)
        self.assertEqual((v.state, v.holder, v.accepting, v.terminal),
                         ("concluded", None, True, True))
        self.assertEqual(v.may_send, ())
        self.assertEqual(v.remaining.scope, "role")
        self.assertEqual(v.remaining.spent, {"initiator": 2, "responder": 2})
        self.assertEqual(v.remaining.headroom,
                         {"initiator": 8, "responder": 8})
        self.assertEqual(v.outbound_clock, 5)
        self.assertEqual(v.order, "ok")

    def test_the_paxos_fixture_and_its_trace_give_a_verdict(self):
        v = verdict(PAXOS, load_trace(FIXTURES / "trace-paxos-acceptor.json"))
        self.assertEqual((v.state, v.accepting, v.terminal),
                         ("decided", True, True))
        self.assertEqual(v.remaining.headroom, {"proposer": 4, "acceptor": 4})
        self.assertEqual(v.outbound_clock, 5)

    def test_the_verdict_carries_the_effects_of_the_transition_that_fired(self):
        v = verdict(SESSION_RELAY,
                    load_trace(FIXTURES / "trace-session-relay.json"))
        self.assertEqual(v.effects, ("label.remove:session-relay:open",))


class EmptyTrace(unittest.TestCase):
    def test_an_empty_trace_gives_the_initial_states_verdict(self):
        v = verdict(SESSION_RELAY, _trace([]))
        self.assertTrue(v.legal)
        self.assertEqual((v.state, v.holder, v.accepting, v.terminal),
                         ("unopened", "initiator", True, False))
        self.assertEqual([(o.kind, o.by, o.to) for o in v.may_send],
                         [("triage", "initiator", "awaiting-triage")])
        self.assertEqual(v.remaining.spent, {"initiator": 0, "responder": 0})
        self.assertEqual(v.outbound_clock, 1)
        self.assertEqual((v.effects, v.order, v.concurrent_with, v.guards,
                          v.refusals), ((), "ok", (), (), ()))


class MaySend(unittest.TestCase):
    def test_may_send_names_a_guarded_offer_and_does_not_pretend_to_evaluate_it(
            self):
        v = verdict(PAXOS, _trace([]))
        self.assertEqual(
            sorted((o.kind, o.by, o.to, o.guard.op) for o in v.may_send),
            [("prepare", "proposer", "idle", "le"),
             ("prepare", "proposer", "prepared", "gt")])
        self.assertTrue(all(isinstance(o, Offer) for o in v.may_send))


class Guards(unittest.TestCase):
    def test_the_verdict_reports_every_guard_it_evaluated_with_both_values(
            self):
        v = verdict(PAXOS, _trace([_msg("prepare", "proposer", "p1", 1,
                                        {"ballot": 5})]))
        self.assertEqual(v.state, "prepared")
        self.assertEqual(len(v.guards), 2)
        by_op = {g.op: g for g in v.guards}
        self.assertEqual((by_op["gt"].field_value, by_op["gt"].register_value,
                          by_op["gt"].atom, by_op["gt"].fired),
                         (5, 0, "GT", True))
        self.assertEqual((by_op["le"].field_value, by_op["le"].register_value,
                          by_op["le"].atom, by_op["le"].fired),
                         (5, 0, "GT", False))

    def test_an_unevaluable_guard_keeps_its_note(self):
        m = _machine(None, transitions=[
            Transition("a", "step", "r", "b",
                       guard=Guard("n", "eq", "nope"))])
        v = verdict(m, _trace([_msg("step", "r", "x", 1)]))
        self.assertEqual(len(v.guards), 1)
        self.assertIn("not declared", v.guards[0].note)


class Refusals(unittest.TestCase):
    def test_the_verdict_names_a_refused_message_and_its_reason(self):
        v = verdict(SESSION_RELAY,
                    _trace([_msg("answer", "initiator", "a", 1)]))
        self.assertFalse(v.legal)
        self.assertEqual(len(v.refusals), 1)
        self.assertEqual((v.refusals[0].index, v.refusals[0].reason),
                         (0, "no transition"))
        self.assertIn("no transition", v.reason)
        self.assertIn("message 0", v.reason)
        self.assertEqual(v.state, "unopened")

    def test_a_clean_trace_has_no_reason(self):
        v = verdict(_machine(None), _trace([]))
        self.assertTrue(v.legal)
        self.assertIsNone(v.reason)


class Remainings(unittest.TestCase):
    def test_a_machine_with_no_cap_has_no_remaining_and_no_invented_default(
            self):
        self.assertIsNone(verdict(_machine(None), _trace([])).remaining)

    def test_under_per_channel_scope_the_headroom_is_the_one_shared_budget(
            self):
        m = _machine(5, "channel", states={
            "a": State("a", holder="r", accepting=True),
            "b": State("b", holder="s", accepting=True)},
            transitions=[Transition("a", "step", "r", "b", signal=True),
                         Transition("b", "step", "s", "a", signal=True)])
        v = verdict(m, _trace([_msg("step", "r", "x", 1),
                               _msg("step", "s", "y", 2),
                               _msg("step", "r", "x", 3)]))
        self.assertEqual(v.remaining.scope, "channel")
        self.assertEqual(v.remaining.spent, {"r": 2, "s": 1})
        self.assertEqual(v.remaining.headroom, {"r": 2, "s": 2})
        self.assertIsInstance(v.remaining, Remaining)

    def test_under_per_role_scope_each_role_has_its_own_headroom(self):
        m = _machine(5, "role")
        v = verdict(m, _trace([_msg("step", "r", "x", 1)]))
        self.assertEqual(v.remaining.headroom, {"r": 4, "s": 5})


class Effects(unittest.TestCase):
    def test_the_verdict_names_a_terminal_states_effects_and_performs_nothing(
            self):
        v = verdict(_machine(None), _trace([_msg("step", "r", "x", 1)]))
        self.assertEqual((v.state, v.terminal, v.holder), ("b", True, None))
        self.assertEqual(v.effects, ("escalate",))
        self.assertEqual(v.may_send, ())
        self.assertIsInstance(v, Verdict)

    def test_the_engine_module_imports_nothing_that_could_act(self):
        src = inspect.getsource(machines.engine)
        for pattern in (r"^\s*import (os|sys|time|subprocess|socket|"
                        r"shutil|pathlib|urllib|datetime|random)\b",
                        r"^\s*from (os|time|subprocess|socket|pathlib|"
                        r"datetime) import",
                        r"\bopen\(", r"\bos\.environ\b"):
            self.assertIsNone(re.search(pattern, src, re.M), pattern)


class Order(unittest.TestCase):
    def test_a_concurrent_last_step_is_reported_with_its_peers(self):
        m = _machine(None, states={
            "a": State("a", holder="r", accepting=True)},
            transitions=[Transition("a", "step", "r", "a"),
                         Transition("a", "step", "s", "a")])
        v = verdict(m, _trace([_msg("step", "r", "x", 1),
                               _msg("step", "s", "y", 1)]))
        self.assertTrue(v.legal)
        self.assertEqual((v.order, v.concurrent_with), ("concurrent", ("x",)))


if __name__ == "__main__":
    unittest.main()
