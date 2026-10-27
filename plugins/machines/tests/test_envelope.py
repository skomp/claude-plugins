import copy
import tempfile
import unittest
from pathlib import Path

from machines.envelope import (ENVELOPE_KEYS, MESSAGE_KEYS, TRACE_KEYS,
                               TraceError, load_trace, parse_trace)
from machines.errors import DeclarationError

FIXTURES = Path(__file__).parent / "fixtures"


def _trace(**top):
    obj = {"channel": "c", "machine": "m", "version": "v1",
           "total_order": True, "messages": []}
    obj.update(top)
    return obj


def _one_message(envelope=None, **extra):
    env = {"clock": 1, "sender": "repo-a"}
    if envelope is not None:
        env = envelope
    msg = {"kind": "k", "by": "r", "envelope": env}
    msg.update(extra)
    return _trace(messages=[msg])


def _env(**changes):
    env = {"clock": 1, "sender": "repo-a"}
    env.update(changes)
    return env


def _without(obj, *path):
    obj = copy.deepcopy(obj)
    node = obj
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return obj


class TraceRefusalTests(unittest.TestCase):
    def test_a_message_carrying_a_body_is_refused_by_name(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(_one_message(body="hello"))
        self.assertIn("body", str(caught.exception))

    def test_an_envelope_carrying_a_body_is_refused_by_name(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(_one_message(envelope=_env(body="hello")))
        self.assertIn("body", str(caught.exception))

    def test_a_trace_carrying_a_body_is_refused_by_name(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(_trace(body="hello"))
        self.assertIn("body", str(caught.exception))

    def test_a_world_read_carrying_a_body_is_refused_by_name(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(_one_message(world_reads=[
                {"verb": "v", "result": 1, "body": "x"}]))
        self.assertIn("body", str(caught.exception))

    def test_a_trace_error_is_a_declaration_error(self):
        self.assertTrue(issubclass(TraceError, DeclarationError))

    def test_an_absent_clock_is_refused(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(_one_message(envelope={"sender": "a"}))
        self.assertIn("clock", str(caught.exception))

    def test_an_absent_envelope_is_refused(self):
        obj = _trace(messages=[{"kind": "k", "by": "r"}])
        with self.assertRaises(TraceError) as caught:
            parse_trace(obj)
        self.assertIn("envelope", str(caught.exception))

    def test_a_clock_that_is_a_bool_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(envelope=_env(clock=True)))

    def test_a_clock_that_is_a_string_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(envelope=_env(clock="1")))

    def test_a_clock_that_is_a_float_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(envelope=_env(clock=1.0)))

    def test_a_negative_clock_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(envelope=_env(clock=-1)))

    def test_a_zero_clock_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(envelope=_env(clock=0)))

    def test_an_absent_sender_is_refused(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(_one_message(envelope={"clock": 1}))
        self.assertIn("sender", str(caught.exception))

    def test_an_empty_sender_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(envelope=_env(sender="")))

    def test_a_channel_order_that_is_a_bool_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(envelope=_env(channel_order=True)))

    def test_an_absent_total_order_is_refused(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(_without(_trace(), "total_order"))
        self.assertIn("total_order", str(caught.exception))

    def test_a_total_order_that_is_not_a_bool_is_refused(self):
        for bad in (1, "true", None):
            with self.subTest(bad=bad), self.assertRaises(TraceError):
                parse_trace(_trace(total_order=bad))

    def test_an_absent_top_level_key_is_refused(self):
        for key in ("channel", "machine", "version", "messages"):
            with self.subTest(key=key), self.assertRaises(TraceError):
                parse_trace(_without(_trace(), key))

    def test_a_trace_that_is_not_a_mapping_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace([])

    def test_messages_that_are_not_a_list_are_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_trace(messages={}))

    def test_a_field_value_that_is_a_string_is_refused(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(_one_message(fields={"ballot": "5"}))
        self.assertIn("ballot", str(caught.exception))

    def test_a_field_value_that_is_a_float_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(fields={"ballot": 5.5}))

    def test_a_field_value_that_is_none_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(fields={"ballot": None}))

    def test_a_world_read_without_a_verb_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(world_reads=[{"result": 1}]))

    def test_a_world_read_without_a_result_is_refused(self):
        with self.assertRaises(TraceError):
            parse_trace(_one_message(world_reads=[{"verb": "v"}]))


class TraceAcceptanceTests(unittest.TestCase):
    def test_a_field_value_may_be_an_int_or_a_bool(self):
        trace = parse_trace(_one_message(fields={"ballot": 5, "flag": True}))
        self.assertEqual(trace.messages[0].fields, {"ballot": 5, "flag": True})

    def test_a_world_read_result_is_opaque(self):
        for result in ("text", None, 1.5, {"a": [1]}, [1, "x"]):
            with self.subTest(result=result):
                trace = parse_trace(_one_message(
                    world_reads=[{"verb": "v", "result": result}]))
                self.assertEqual(trace.messages[0].world_reads[0].result,
                                 result)

    def test_fields_and_world_reads_and_channel_order_default(self):
        msg = parse_trace(_one_message()).messages[0]
        self.assertEqual(msg.fields, {})
        self.assertEqual(msg.world_reads, ())
        self.assertIsNone(msg.envelope.channel_order)

    def test_an_empty_trace_loads(self):
        self.assertEqual(parse_trace(_trace()).messages, ())

    def test_the_key_tuples_are_the_contract(self):
        self.assertEqual(ENVELOPE_KEYS, ("clock", "sender", "channel_order"))
        self.assertEqual(MESSAGE_KEYS, ("kind", "by", "envelope", "fields",
                                        "world_reads"))
        self.assertEqual(TRACE_KEYS, ("channel", "machine", "version",
                                      "total_order", "messages"))

    def test_both_shipped_trace_fixtures_load(self):
        for name in ("trace-session-relay.json", "trace-paxos-acceptor.json"):
            trace = load_trace(FIXTURES / name)
            self.assertEqual(len(trace.messages), 4)
            self.assertEqual([m.envelope.clock for m in trace.messages],
                             [1, 2, 3, 4])

    def test_the_session_relay_fixture_is_the_named_trace(self):
        trace = load_trace(FIXTURES / "trace-session-relay.json")
        self.assertEqual(
            [(m.kind, m.by, m.envelope.sender) for m in trace.messages],
            [("triage", "initiator", "repo-a"),
             ("question", "responder", "repo-b"),
             ("answer", "initiator", "repo-a"),
             ("conclusion", "responder", "repo-b")])

    def test_the_paxos_fixture_is_the_named_trace(self):
        trace = load_trace(FIXTURES / "trace-paxos-acceptor.json")
        self.assertEqual(
            [(m.kind, m.by, m.envelope.sender, m.fields)
             for m in trace.messages],
            [("prepare", "proposer", "p1", {"ballot": 5}),
             ("promise", "acceptor", "a1", {}),
             ("accept-request", "proposer", "p1", {"ballot": 5}),
             ("accepted", "acceptor", "a1", {})])

    def test_load_trace_refuses_a_file_that_is_not_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            handle.write("{nope")
            handle.flush()
            with self.assertRaises(ValueError):
                load_trace(handle.name)


if __name__ == "__main__":
    unittest.main()
