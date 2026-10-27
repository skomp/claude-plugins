import inspect
import re
import unittest
from pathlib import Path

import machines.engine
from machines.declaration import parse
from machines.engine import Offer, Remaining, Verdict, gate, verdict
from machines.envelope import Envelope, Message, Trace, load_trace
from machines.machine import (Effect, Field, Guard, Machine, Register, State,
                              Transition, check_machine)

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
                   effects=[Effect("escalate")])]
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


def _out(kind, by, sender, fields=None, clock=None):
    return Message(kind, by, Envelope(clock, sender), fields)


def _loop(cap, scope, signal=True, roles=("r",)):
    """One state, a self-loop `step` for each role in `roles`."""
    return _machine(cap, scope,
                    states={"a": State("a", holder="r", accepting=True)},
                    transitions=[Transition("a", "step", r, "a", signal=signal,
                                            effects=[Effect("escalate")])
                                 for r in roles])


def _spend(by, sender, n, start=1):
    return [_msg("step", by, sender, start + i) for i in range(n)]


class Gate(unittest.TestCase):
    def test_the_gate_refuses_a_kind_the_current_state_does_not_permit(self):
        trace = _trace(load_trace(
            FIXTURES / "trace-session-relay.json").messages[:1])
        v = gate(SESSION_RELAY, trace, _out("answer", "initiator", "repo-a"))
        self.assertFalse(v.legal)  # state is awaiting-triage
        self.assertEqual(v.reason, "not permitted here")
        self.assertEqual(v.effects, ())

    def test_the_gate_admits_a_kind_the_current_state_permits(self):
        trace = _trace(load_trace(
            FIXTURES / "trace-session-relay.json").messages[:1])
        v = gate(SESSION_RELAY, trace, _out("question", "responder", "repo-b"))
        self.assertTrue(v.legal)
        self.assertIsNone(v.reason)
        self.assertEqual(v.outbound_clock, 2)

    def test_the_gate_refuses_an_outbound_message_past_the_cap(self):
        m = _loop(10, "role")
        nine = gate(m, _trace(_spend("r", "x", 9)), _out("step", "r", "x"))
        self.assertTrue(nine.legal)  # the tenth is the last one allowed
        v = gate(m, _trace(_spend("r", "x", 10)), _out("step", "r", "x"))
        self.assertFalse(v.legal)  # item 6's "11 of 10", refused
        self.assertEqual(v.reason, "cap exhausted")
        self.assertEqual(v.remaining.headroom["r"], 0)
        self.assertEqual(v.effects, ())

    def test_an_overspent_role_is_exhausted_not_admitted(self):
        m = _loop(1, "role")
        v = gate(m, _trace(_spend("r", "x", 2)), _out("step", "r", "x"))
        self.assertEqual(v.remaining.headroom["r"], -1)
        self.assertEqual((v.legal, v.reason), (False, "cap exhausted"))

    def test_a_role_at_its_cap_does_not_block_the_other_role(self):
        m = _loop(2, "role", roles=("r", "s"))
        trace = _trace(_spend("r", "x", 2))
        self.assertEqual(gate(m, trace, _out("step", "r", "x")).reason,
                         "cap exhausted")
        self.assertTrue(gate(m, trace, _out("step", "s", "y")).legal)

    def test_under_per_channel_scope_one_budget_is_shared(self):
        m = _loop(2, "channel", roles=("r", "s"))
        trace = _trace(_spend("r", "x", 2))
        self.assertEqual(gate(m, trace, _out("step", "s", "y")).reason,
                         "cap exhausted")

    def test_a_machine_with_no_cap_is_never_exhausted(self):
        m = _loop(None, "channel")
        v = gate(m, _trace(_spend("r", "x", 50)), _out("step", "r", "x"))
        self.assertTrue(v.legal)
        self.assertIsNone(v.remaining)

    def test_a_local_move_does_not_count_against_the_cap(self):
        m = _loop(1, "role", signal=False)
        v = gate(m, _trace(_spend("r", "x", 3)), _out("step", "r", "x"))
        self.assertEqual(v.remaining.spent["r"], 0)
        self.assertTrue(v.legal)
        # headroom gone but the transition is a local move: still admitted
        m2 = _machine(1, "role", states={
            "a": State("a", holder="r", accepting=True)}, transitions=[
            Transition("a", "step", "r", "a", signal=True),
            Transition("a", "note", "r", "a", signal=False)])
        m2.kinds.append("note")
        trace = _trace(_spend("r", "x", 1))
        self.assertEqual(gate(m2, trace, _out("step", "r", "x")).reason,
                         "cap exhausted")
        self.assertTrue(gate(m2, trace, _out("note", "r", "x")).legal)

    def test_the_gate_refuses_everything_from_a_terminal_state(self):
        trace = _trace(_spend("r", "x", 1))
        m = _machine(None)
        for kind, by in (("step", "r"), ("step", "s"), ("nope", "r")):
            v = gate(m, trace, _out(kind, by, "x"))
            self.assertEqual((v.legal, v.reason, v.terminal),
                             (False, "terminal state", True))

    def test_the_gate_refuses_more_than_one_firing_transition(self):
        m = _machine(None, states={
            "a": State("a", holder="r", accepting=True),
            "b": State("b", accepting=True),
            "c": State("c", accepting=True)}, transitions=[
            Transition("a", "step", "r", "b"),
            Transition("a", "step", "r", "c")])
        v = gate(m, _trace([]), _out("step", "r", "x"))
        self.assertEqual((v.legal, v.reason), (False, "ambiguous"))
        self.assertEqual(v.effects, ())

    def test_the_ambiguous_refusal_is_a_backstop_for_a_hand_built_machine(
            self):
        # The checker reports a transition declared twice, so a declaration
        # that `parse` accepted can never reach this refusal; it stays for a
        # hand-built `Machine`, which skips the parser. Do not delete it as
        # dead code: the engine cannot tell a repeat from a rival.
        m = _machine(None, states={
            "a": State("a", holder="r", accepting=True),
            "b": State("b", accepting=True)}, transitions=[
            Transition("a", "step", "r", "b"),
            Transition("a", "step", "r", "b")])
        self.assertTrue(any("declared twice" in p for p in check_machine(m)))
        v = gate(m, _trace([]), _out("step", "r", "x"))
        self.assertEqual((v.legal, v.reason), (False, "ambiguous"))

    def test_a_refusal_in_the_history_does_not_refuse_an_outbound_message(
            self):
        trace = _trace([_msg("answer", "initiator", "repo-a", 1)])
        self.assertFalse(verdict(SESSION_RELAY, trace).legal)
        v = gate(SESSION_RELAY, trace, _out("triage", "initiator", "repo-a"))
        self.assertTrue(v.legal)
        self.assertEqual([r.reason for r in v.refusals], ["no transition"])

    def test_the_gate_overwrites_a_caller_supplied_clock(self):
        v = gate(SESSION_RELAY, _trace([]),
                 _out("triage", "initiator", "repo-a", clock=99))
        self.assertEqual(v.outbound_clock, 1)
        trace = _trace(_spend("r", "x", 3))
        v = gate(_loop(None, "channel"), trace,
                 _out("step", "r", "x", clock=1))
        self.assertEqual(v.outbound_clock, 4)

    def test_the_gate_evaluates_a_guard_against_the_outbound_messages_own_fields(
            self):
        # promised at ballot 5: ballot 5 honours the promise, any other ballot
        # is the stale branch, and a message with no ballot fires neither
        trace = _trace([_msg("prepare", "proposer", "p1", 1, {"ballot": 5}),
                        _msg("promise", "acceptor", "a1", 2)])
        for fields, fired in (({"ballot": 5}, "eq"), ({"ballot": 6}, "ne")):
            v = gate(PAXOS, trace,
                     _out("accept-request", "proposer", "p1", fields))
            self.assertTrue(v.legal)
            self.assertEqual([(g.op, g.field_value, g.register_value)
                              for g in v.guards if g.fired and g.index == 2],
                             [(fired, fields["ballot"], 5)])
        v = gate(PAXOS, trace, _out("accept-request", "proposer", "p1"))
        self.assertEqual((v.legal, v.reason), (False, "not permitted here"))

    def test_the_gate_refuses_a_guarded_field_of_the_wrong_type(self):
        v = gate(PAXOS, _trace([]),
                 _out("prepare", "proposer", "p1", {"ballot": True}))
        self.assertEqual((v.legal, v.reason), (False, "not permitted here"))

    def test_the_gate_performs_no_effect_and_only_names_the_required_set(
            self):
        v = gate(SESSION_RELAY, _trace([]),
                 _out("triage", "initiator", "repo-a"))
        self.assertEqual(v.effects, ("label.add:session-relay:open",))


if __name__ == "__main__":
    unittest.main()


class OverspentTrace(unittest.TestCase):
    """The fold has no cap rule, so a trace past the cap folds without a
    refusal. `verdict` must still not call it a legal run."""

    def test_a_trace_past_a_per_role_cap_is_not_a_legal_run(self):
        m = _loop(3, "role")
        v = verdict(m, _trace(_spend("r", "x", 7)))
        self.assertEqual(v.refusals, ())
        self.assertEqual(v.remaining.headroom, {"r": -4, "s": 3})
        self.assertFalse(v.legal)
        self.assertIn("'r'", v.reason)
        self.assertIn("7 of a cap of 3", v.reason)
        self.assertIn("4 over", v.reason)

    def test_a_trace_past_a_shared_cap_is_not_a_legal_run(self):
        m = _loop(3, "channel", roles=("r", "s"))
        v = verdict(m, _trace(_spend("r", "x", 5)))
        self.assertFalse(v.legal)
        self.assertIn("5 of a shared cap of 3", v.reason)
        self.assertIn("2 over", v.reason)

    def test_a_trace_exactly_at_its_cap_is_still_legal(self):
        v = verdict(_loop(3, "role"), _trace(_spend("r", "x", 3)))
        self.assertEqual((v.legal, v.reason), (True, None))
        self.assertEqual(v.remaining.headroom["r"], 0)

    def test_the_gate_still_says_cap_exhausted_at_zero_and_below(self):
        m = _loop(3, "role")
        for n in (3, 7):
            v = gate(m, _trace(_spend("r", "x", n)), _out("step", "r", "x"))
            self.assertEqual((v.legal, v.reason), (False, "cap exhausted"))
        two = gate(m, _trace(_spend("r", "x", 2)), _out("step", "r", "x"))
        self.assertTrue(two.legal)


class GateWorldReads(unittest.TestCase):
    def _trace_with(self, reads):
        from machines.envelope import WorldRead
        rs = [WorldRead(v, r) for v, r in reads]
        return _trace([Message("step", "r", Envelope(i + 1, "x"), None, rs)
                       for i in range(2)])

    def test_the_gate_is_identical_however_a_world_read_turned_out(self):
        m = _loop(10, "role")
        a = gate(m, self._trace_with([("db", {"rows": 3})]),
                 _out("step", "r", "x"))
        b = gate(m, self._trace_with([("db", {"rows": 99999, "z": [1]})]),
                 _out("step", "r", "x"))
        for name in ("legal", "reason", "state", "holder", "accepting",
                     "terminal", "may_send", "order", "concurrent_with",
                     "outbound_clock", "truncated", "refusals", "effects",
                     "guards"):
            self.assertEqual(vars_of(getattr(a, name)),
                             vars_of(getattr(b, name)), name)
        self.assertEqual(vars_of(a.remaining), vars_of(b.remaining))
        self.assertTrue(a.legal)
        self.assertNotEqual([w.result for w in a.world_reads],
                            [w.result for w in b.world_reads])

    def test_the_gate_drops_the_outbound_messages_own_world_reads(self):
        from machines.envelope import WorldRead
        m = _loop(10, "role")
        out = Message("step", "r", Envelope(None, "x"), None,
                      [WorldRead("db", {"rows": 3})])
        v = gate(m, self._trace_with([]), out)
        self.assertTrue(v.legal)
        self.assertEqual(v.world_reads, ())


def vars_of(value):
    if isinstance(value, (list, tuple)):
        return tuple(vars_of(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, vars_of(v)) for k, v in value.items()))
    if hasattr(value, "__dict__"):
        return tuple(sorted((k, vars_of(v)) for k, v in vars(value).items()))
    return value


class TruncatedFold(unittest.TestCase):
    def test_a_truncated_fold_is_reported_and_is_not_legal(self):
        v = verdict(_loop(None, "channel"), _trace(_spend("r", "x", 50)),
                    limit=10)
        self.assertTrue(v.truncated)
        self.assertFalse(v.legal)
        self.assertIn("truncated", v.reason)

    def test_a_fold_inside_its_limit_is_legal_and_not_truncated(self):
        v = verdict(_loop(None, "channel"), _trace(_spend("r", "x", 5)),
                    limit=10)
        self.assertEqual((v.truncated, v.legal, v.reason),
                         (False, True, None))

    def test_the_gate_refuses_on_a_truncated_fold(self):
        v = gate(_loop(None, "channel"), _trace(_spend("r", "x", 50)),
                 _out("step", "r", "x"), limit=10)
        self.assertTrue(v.truncated)
        self.assertFalse(v.legal)
        self.assertIn("truncated", v.reason)
        self.assertEqual(v.effects, ())

    def test_the_gate_still_admits_inside_the_limit(self):
        v = gate(_loop(None, "channel"), _trace(_spend("r", "x", 5)),
                 _out("step", "r", "x"), limit=10)
        self.assertEqual((v.truncated, v.legal), (False, True))
