import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from machines import runner
from machines.declaration import parse
from machines.envelope import TraceError, load_trace
from machines.runner import (CALL_TIMEOUT_SECONDS, MAX_OUTPUT_BYTES,
                             ChannelReadFailed, TransportCannotRun, call,
                             read_channel)
from machines.transport import Transport, Verb, load_transport

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_DIR = FIXTURES / "transport-fake" / "transport"
FAKE = load_transport(str(FAKE_DIR))
ENTRY = FAKE_DIR / "bin" / "transport"
SESSION_RELAY = parse((FIXTURES / "valid-session-relay.md").read_text())
PAXOS = parse((FIXTURES / "valid-paxos-acceptor.md").read_text())

# Must match FLOOD_BYTES in the fixture's entry point.
FLOOD_BYTES = 128 * 1024
SHORT = 0.5  # seconds: the time bound a test that hits it passes


def _fake_at(root, entry_mode=None):
    """A copy of the fake transport at `root`. `entry_mode` None leaves the
    entry point out; otherwise it is copied there with that mode."""
    os.makedirs(os.path.join(root, "bin"))
    shutil.copy(FAKE_DIR / "transport.yaml", root)
    if entry_mode is not None:
        entry = os.path.join(root, "bin", "transport")
        shutil.copy(ENTRY, entry)
        os.chmod(entry, entry_mode)
    return load_transport(root)


def _trace_fields(trace):
    return (trace.channel, trace.machine, trace.version, trace.total_order,
            [(m.kind, m.by, m.envelope.clock, m.envelope.sender,
              m.envelope.channel_order, m.fields,
              [(w.verb, w.result) for w in m.world_reads])
             for m in trace.messages])


class Bounds(unittest.TestCase):
    def test_the_bounds_are_the_derived_values(self):
        self.assertEqual(CALL_TIMEOUT_SECONDS, 120)
        self.assertEqual(MAX_OUTPUT_BYTES, 8 * 1024 * 1024)


class Refused(unittest.TestCase):
    """Every ValueError is raised before anything is spawned. Each test uses
    a transport whose entry point does not exist, so a spawn would raise
    TransportCannotRun instead."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.missing = _fake_at(os.path.join(self.tmp, "t"))

    def assertRefused(self, transport, verb, args, *named):
        with mock.patch.object(runner.subprocess, "Popen",
                               side_effect=AssertionError("spawned")) as popen:
            with self.assertRaises(ValueError) as cm:
                call(transport, verb, "echo", args)
        popen.assert_not_called()
        for word in named:
            self.assertIn(word, str(cm.exception))

    def test_a_transport_with_no_root_is_refused(self):
        unrooted = Transport(FAKE.name, FAKE.version, FAKE.total_order,
                             FAKE.channel_id, FAKE.verbs)
        self.assertRefused(unrooted, "channel.list", {}, "root")

    def test_an_undeclared_verb_is_refused(self):
        self.assertRefused(self.missing, "comment.post", {}, "comment.post")

    def test_a_verb_the_agent_performs_is_refused(self):
        self.assertEqual(self.missing.verbs["escalate"].performer, "agent")
        self.assertRefused(self.missing, "escalate", {}, "escalate", "agent")

    def test_the_agent_refusal_is_not_a_failed_spawn(self):
        # Without the Popen mock: a missing entry point would raise
        # TransportCannotRun, which is not a ValueError.
        with self.assertRaises(ValueError) as cm:
            call(self.missing, "escalate", "echo", {})
        self.assertNotIsInstance(cm.exception, TransportCannotRun)
        self.assertIn("agent", str(cm.exception))

    def test_an_argument_with_the_wrong_name_is_refused(self):
        self.assertRefused(self.missing, "label.add", {"title": "x"}, "title")

    def test_a_missing_argument_is_refused(self):
        self.assertRefused(self.missing, "signal.send", {"to": "a"}, "text")

    def test_an_extra_argument_is_refused(self):
        self.assertRefused(self.missing, "label.add",
                           {"name": "x", "colour": "red"}, "colour")

    def test_an_argument_of_the_wrong_type_is_refused(self):
        self.assertRefused(self.missing, "label.add", {"name": 3},
                           "name", "int", "string")

    def test_a_bool_is_not_an_int_and_not_a_string(self):
        self.assertRefused(self.missing, "label.add", {"name": True},
                           "name", "bool")

    def test_args_that_are_not_a_mapping_are_refused(self):
        self.assertRefused(self.missing, "label.add", [("name", "x")], "args")


class CannotRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_a_missing_entry_point_cannot_run(self):
        t = _fake_at(os.path.join(self.tmp, "t"))
        with self.assertRaises(TransportCannotRun) as cm:
            call(t, "channel.list", "refuse", {})
        self.assertIn(os.path.join(t.root, "bin", "transport"),
                      str(cm.exception))

    def test_an_entry_point_that_is_not_executable_cannot_run(self):
        t = _fake_at(os.path.join(self.tmp, "t"), entry_mode=0o644)
        with self.assertRaises(TransportCannotRun):
            call(t, "channel.list", "refuse", {})

    def test_a_non_zero_exit_discards_a_valid_answer(self):
        with self.assertRaises(TransportCannotRun) as cm:
            call(FAKE, "channel.list", "exit-3", {})
        self.assertIn("3", str(cm.exception))

    def test_each_malformed_envelope_cannot_run(self):
        for channel in ("not-json", "extra-key", "both", "ok-not-bool",
                        "ok-only", "not-object", "error-not-string"):
            with self.subTest(channel=channel):
                with self.assertRaises(TransportCannotRun):
                    call(FAKE, "channel.list", channel, {})

    def test_an_unknown_key_is_named(self):
        with self.assertRaises(TransportCannotRun) as cm:
            call(FAKE, "channel.list", "extra-key", {})
        self.assertIn("extra", str(cm.exception))


class Calls(unittest.TestCase):
    def test_the_call_protocol(self):
        out = call(FAKE, "label.add", "echo", {"name": "x"})
        self.assertEqual(out["ok"], True)
        self.assertEqual(out["result"]["argv"],
                         [os.path.join(FAKE.root, "bin", "transport"),
                          "label.add"])
        self.assertEqual(out["result"]["call"],
                         {"channel": "echo", "args": {"name": "x"}})

    def test_ok_false_is_returned_exactly(self):
        self.assertEqual(call(FAKE, "channel.list", "refuse", {}),
                         {"ok": False, "error": "refused"})

    def test_ok_true_is_returned_exactly(self):
        self.assertEqual(call(FAKE, "label.add", "session-relay",
                              {"name": "x"}),
                         {"ok": True, "result": {}})

    def test_output_of_exactly_max_output_is_read(self):
        size = len(json.dumps({"ok": False, "error": "refused"})) + 1
        self.assertEqual(call(FAKE, "channel.list", "refuse", {},
                              max_output=size),
                         {"ok": False, "error": "refused"})
        out = call(FAKE, "channel.list", "refuse", {}, max_output=size - 1)
        self.assertEqual(out["ok"], False)
        self.assertIn("max_output", out["error"])


def _group_members(pgid):
    members = 0
    for name in os.listdir("/proc"):
        if name.isdigit():
            try:
                if os.getpgid(int(name)) == pgid:
                    members += 1
            except (ProcessLookupError, PermissionError):
                pass
    return members


class BoundsHit(unittest.TestCase):
    def setUp(self):
        self.pgids = []
        patcher = mock.patch.object(runner, "_on_spawn", self.pgids.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertGroupGone(self):
        self.assertEqual(len(self.pgids), 1)
        with self.assertRaises(ProcessLookupError):
            os.killpg(self.pgids[0], 0)

    def test_the_time_bound(self):
        start = time.monotonic()
        out = call(FAKE, "channel.list", "sleep", {}, timeout=SHORT)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(out["ok"], False)
        self.assertEqual(set(out), {"ok", "error"})
        self.assertIn("timeout", out["error"])
        self.assertIn(str(SHORT), out["error"])
        self.assertGroupGone()

    def test_the_time_bound_holds_after_stdout_closes(self):
        # The leader closes stdout and keeps running: the bound must cover
        # the wait for its exit, not only the read.
        start = time.monotonic()
        out = call(FAKE, "channel.list", "closes-stdout", {}, timeout=SHORT)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(out["ok"], False)
        self.assertIn("timeout", out["error"])
        self.assertGroupGone()

    def test_the_output_bound(self):
        out = call(FAKE, "channel.list", "flood", {},
                   max_output=FLOOD_BYTES // 2)
        self.assertEqual(out["ok"], False)
        self.assertEqual(set(out), {"ok", "error"})
        self.assertIn("max_output", out["error"])
        self.assertIn(str(FLOOD_BYTES // 2), out["error"])
        self.assertGroupGone()

    def test_the_time_bound_kills_the_whole_group(self):
        # Watch the group from a thread: the test is vacuous unless `sleep`
        # was alive in it before the bound.
        seen = []
        done = threading.Event()

        def watch():
            while not done.is_set():
                if self.pgids:
                    seen.append(_group_members(self.pgids[0]))
                time.sleep(0.05)

        watcher = threading.Thread(target=watch)
        watcher.start()
        try:
            out = call(FAKE, "channel.list", "child-sleeps", {}, timeout=1.5)
        finally:
            done.set()
            watcher.join()
        self.assertEqual(out["ok"], False)
        self.assertIn("timeout", out["error"])
        self.assertGreaterEqual(max(seen), 2)
        self.assertGroupGone()


class ReadChannel(unittest.TestCase):
    def test_both_trace_fixtures_round_trip(self):
        for machine, name in ((SESSION_RELAY, "session-relay"),
                              (PAXOS, "paxos-acceptor")):
            with self.subTest(name=name):
                expected = load_trace(FIXTURES / ("trace-%s.json" % name))
                got = read_channel(FAKE, machine, expected.channel)
                self.assertEqual(_trace_fields(got),
                                 _trace_fields(expected))

    def test_total_order_comes_from_the_transport(self):
        unordered = load_transport(str(FAKE_DIR))
        unordered.total_order = False
        got = read_channel(unordered, SESSION_RELAY, "session-relay")
        self.assertIs(got.total_order, False)

    def test_machine_and_version_come_from_the_machine(self):
        got = read_channel(FAKE, PAXOS, "session-relay")
        self.assertEqual((got.channel, got.machine, got.version),
                         ("session-relay", "paxos-acceptor", PAXOS.version))

    def test_a_message_body_is_refused_by_name(self):
        with self.assertRaises(TraceError) as cm:
            read_channel(FAKE, SESSION_RELAY, "body")
        self.assertIn("body", str(cm.exception))

    def test_ok_false_raises_and_never_reads_as_empty(self):
        with self.assertRaises(ChannelReadFailed) as cm:
            read_channel(FAKE, SESSION_RELAY, "refuse")
        self.assertEqual(cm.exception.error, "refused")
        self.assertIn("refused", str(cm.exception))

    def test_a_result_with_another_key_is_refused_by_name(self):
        with mock.patch.object(runner, "call", return_value={
                "ok": True, "result": {"messages": [], "next": "p2"}}):
            with self.assertRaises(TraceError) as cm:
                read_channel(FAKE, SESSION_RELAY, "x")
        self.assertIn("next", str(cm.exception))

    def test_a_result_with_no_messages_is_refused(self):
        with mock.patch.object(runner, "call",
                               return_value={"ok": True, "result": {}}):
            with self.assertRaises(TraceError) as cm:
                read_channel(FAKE, SESSION_RELAY, "x")
        self.assertIn("messages", str(cm.exception))

    def test_a_result_that_is_not_a_mapping_is_refused(self):
        with mock.patch.object(runner, "call",
                               return_value={"ok": True,
                                             "result": ["messages"]}):
            with self.assertRaises(TraceError) as cm:
                read_channel(FAKE, SESSION_RELAY, "x")
        self.assertIn("mapping", str(cm.exception))

    def test_bounds_are_passed_to_the_call(self):
        with self.assertRaises(ChannelReadFailed) as cm:
            read_channel(FAKE, SESSION_RELAY, "sleep", timeout=SHORT)
        self.assertIn("timeout", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
