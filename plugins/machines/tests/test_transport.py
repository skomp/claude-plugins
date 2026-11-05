import os
import tempfile
import unittest
from pathlib import Path

from machines.errors import DeclarationError
from machines.machine import ARG_TYPES
from machines.transport import (PERFORMERS, RETURNS, TOUCHES, Transport,
                                TransportError, Verb, load_transport,
                                parse_transport)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "transport-fake"
FIXTURE = FIXTURE_DIR / "transport" / "transport.yaml"

HEAD = """\
transport: t
version: v1
channel:
  total_order: true
"""

LIST = """\
  channel.list:
    touches: channel-read
    performer: transport
    args: {}
    returns: messages
"""

APPEND = """\
  channel.append:
    touches: channel-write
    performer: transport
    args: { body: string }
"""


def doc(head=HEAD, verbs=LIST + APPEND):
    return head + "verbs:\n" + verbs


def refused(test, text, *needles):
    with test.assertRaises(TransportError) as cm:
        parse_transport(text)
    for needle in needles:
        test.assertIn(needle, cm.exception.message)
    return cm.exception


class TestFixture(unittest.TestCase):
    def setUp(self):
        self.t = parse_transport(FIXTURE.read_text())

    def test_top_level_fields(self):
        t = self.t
        self.assertEqual(t.name, "transport-fake")
        self.assertEqual(t.version, "v1")
        self.assertIs(t.total_order, True)
        self.assertEqual(t.channel_id, "a fake channel, for tests")
        self.assertIsNone(t.root)
        self.assertEqual(list(t.verbs), [
            "channel.list", "channel.append", "signal.send", "label.add",
            "label.remove", "escalate"])

    def test_every_verb_by_value(self):
        want = {
            "channel.list": Verb("channel.list", "channel-read", "transport",
                                 {}, "messages"),
            "channel.append": Verb("channel.append", "channel-write",
                                   "transport", {"body": "string"}, None),
            "signal.send": Verb("signal.send", "channel-write", "transport",
                                {"to": "string", "text": "string"}, None),
            "label.add": Verb("label.add", "world-write", "transport",
                              {"name": "string"}, None),
            "label.remove": Verb("label.remove", "world-write", "transport",
                                 {"name": "string"}, None),
            "escalate": Verb("escalate", "world-write", "agent", {}, None),
        }
        self.assertEqual(self.t.verbs, want)
        for name, verb in want.items():
            got = self.t.verbs[name]
            self.assertEqual(
                (got.name, got.touches, got.performer, got.args, got.returns),
                (verb.name, verb.touches, verb.performer, verb.args,
                 verb.returns))

    def test_verb_equality_is_by_every_field(self):
        base = Verb("a", "world-write", "agent", {"x": "int"}, None)
        self.assertEqual(base, Verb("a", "world-write", "agent", {"x": "int"}, None))
        for other in (Verb("b", "world-write", "agent", {"x": "int"}, None),
                      Verb("a", "world-read", "agent", {"x": "int"}, None),
                      Verb("a", "world-write", "transport", {"x": "int"}, None),
                      Verb("a", "world-write", "agent", {"x": "bool"}, None),
                      Verb("a", "world-write", "agent", {"x": "int"}, "messages")):
            self.assertNotEqual(base, other)

    def test_constants(self):
        self.assertEqual(TOUCHES, ("channel-read", "channel-write",
                                   "world-read", "world-write"))
        self.assertEqual(PERFORMERS, ("transport", "agent"))
        self.assertEqual(RETURNS, ("messages",))

    def test_error_is_a_declaration_error(self):
        self.assertTrue(issubclass(TransportError, DeclarationError))


class TestLoad(unittest.TestCase):
    def test_load_file_sets_root(self):
        t = load_transport(str(FIXTURE))
        self.assertEqual(t.root, str(FIXTURE.parent))
        self.assertEqual(t.name, "transport-fake")

    def test_load_directory_containing_transport_yaml(self):
        t = load_transport(str(FIXTURE.parent))
        self.assertEqual(t.root, str(FIXTURE.parent))

    def test_load_missing_is_an_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(OSError):
                load_transport(d)
            with self.assertRaises(OSError):
                load_transport(os.path.join(d, "transport.yaml"))

    def test_load_refuses_a_bad_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "transport.yaml")
            Path(p).write_text("transport: t\n")
            with self.assertRaises(TransportError):
                load_transport(p)


class TestTopLevel(unittest.TestCase):
    def test_minimal_parses(self):
        t = parse_transport(doc())
        self.assertEqual((t.name, t.version, t.total_order, t.channel_id),
                         ("t", "v1", True, None))

    def test_not_a_mapping(self):
        refused(self, "- a\n- b\n", "mapping")
        refused(self, "", "mapping")

    def test_bad_yaml(self):
        refused(self, "transport: [\n")

    def test_unknown_key_named(self):
        e = refused(self, doc() + "colour: red\n", "colour")
        self.assertEqual(e.field, "colour")

    def test_run_is_just_an_unknown_key(self):
        e = refused(self, doc() + "run: ./go.sh\n", "run")
        self.assertEqual(e.field, "run")
        self.assertIn("unknown", e.message)
        for key in ("cmd", "shell"):
            self.assertEqual(refused(self, doc() + key + ": x\n", key).field, key)

    def test_each_required_key_is_required(self):
        for key in ("transport", "version", "channel", "verbs"):
            lines = []
            skip = False
            for line in doc().splitlines():
                top = line and not line[0].isspace()
                if top:
                    skip = line.startswith(key + ":")
                if not skip:
                    lines.append(line)
            e = refused(self, "\n".join(lines) + "\n", key)
            self.assertEqual(e.field, key)

    def test_name_must_be_name_shaped(self):
        refused(self, doc().replace("transport: t", "transport: Bad_Name"),
                "transport", "Bad_Name")
        refused(self, doc().replace("transport: t", "transport: 5"), "transport")

    def test_version_must_not_be_empty(self):
        e = refused(self, doc().replace("version: v1", 'version: ""'),
                    "version", "empty")
        self.assertEqual(e.field, "version")

    def test_version_must_be_a_string(self):
        e = refused(self, doc().replace("version: v1", "version: 1"), "version")
        self.assertEqual(e.field, "version")


class TestChannel(unittest.TestCase):
    def test_total_order_false_is_fine(self):
        t = parse_transport(doc(HEAD.replace("true", "false")))
        self.assertIs(t.total_order, False)

    def test_channel_must_be_a_mapping(self):
        refused(self, doc("transport: t\nversion: v1\nchannel: 3\n"), "channel")

    def test_total_order_absent_has_no_default(self):
        e = refused(self, doc("transport: t\nversion: v1\nchannel:\n  id: x\n"),
                    "total_order", "no default")
        self.assertEqual(e.field, "total_order")

    def test_total_order_yes_is_refused(self):
        e = refused(self, doc(HEAD.replace("true", "yes")), "total_order")
        self.assertEqual(e.field, "total_order")

    def test_total_order_quoted_true_is_refused(self):
        refused(self, doc(HEAD.replace("true", '"true"')), "total_order")

    def test_total_order_int_is_refused(self):
        refused(self, doc(HEAD.replace("true", "1")), "total_order")

    def test_channel_unknown_key_named(self):
        e = refused(self, doc(HEAD + "  order: total\n"), "order")
        self.assertEqual(e.field, "order")

    def test_id_must_be_a_string(self):
        e = refused(self, doc(HEAD + "  id: 4\n"), "id")
        self.assertEqual(e.field, "id")

    def test_id_is_kept(self):
        t = parse_transport(doc(HEAD + "  id: some prose\n"))
        self.assertEqual(t.channel_id, "some prose")


class TestVerbShape(unittest.TestCase):
    def test_verbs_must_be_a_non_empty_mapping(self):
        refused(self, HEAD + "verbs: {}\n", "verbs")
        refused(self, HEAD + "verbs: [a]\n", "verbs")
        refused(self, HEAD + "verbs:\n", "verbs")

    def test_verb_name_must_look_like_a_verb(self):
        refused(self, doc(verbs=LIST + APPEND +
                          "  Bad Verb:\n    touches: world-write\n"
                          "    performer: agent\n    args: {}\n"), "Bad Verb")

    def test_verb_entry_must_be_a_mapping(self):
        refused(self, doc(verbs=LIST + APPEND + "  x: 3\n"), "x")

    def test_each_verb_key_is_required(self):
        for key in ("touches", "performer", "args"):
            body = "".join(l + "\n" for l in APPEND.splitlines()
                           if not l.strip().startswith(key + ":"))
            e = refused(self, doc(verbs=LIST + body), key, "channel.append",
                        "is missing required field")
            self.assertEqual(e.field, key)

    def test_verb_unknown_key_named(self):
        e = refused(self, doc(verbs=LIST + APPEND + "    run: ./x\n"),
                    "run", "channel.append")
        self.assertEqual(e.field, "run")

    def test_touches_must_be_in_touches(self):
        e = refused(self, doc(verbs=LIST + APPEND.replace(
            "channel-write", "world-maybe")), "touches", "world-maybe",
            "channel.append")
        self.assertEqual(e.field, "touches")

    def test_performer_must_be_in_performers(self):
        e = refused(self, doc(verbs=LIST + APPEND.replace(
            "performer: transport", "performer: human")), "performer", "human")
        self.assertEqual(e.field, "performer")

    def test_args_must_be_a_mapping(self):
        e = refused(self, doc(verbs=LIST + APPEND.replace(
            "{ body: string }", "[body]")), "args", "channel.append")
        self.assertEqual(e.field, "args")

    def test_arg_name_must_be_name_shaped(self):
        refused(self, doc(verbs=LIST + APPEND.replace(
            "body: string", "Body: string")), "Body", "channel.append")

    def test_arg_type_word_outside_arg_types(self):
        for word in ("integer", "float", "list"):
            e = refused(self, doc(verbs=LIST + APPEND.replace(
                "body: string", "body: " + word)), word, "channel.append")
            self.assertEqual(e.field, "args")
        refused(self, doc(verbs=LIST + APPEND.replace(
            "body: string", "body: 3")), "channel.append")

    def test_the_fixture_transport_uses_only_words_the_checker_can_test(self):
        # Reads the YAML directly, not through parse_transport, so that a
        # word dropped from ARG_TYPES fails this test and not only the
        # parser. Replaces test_every_builtin_type_word_is_one_the_checker_can_test.
        import yaml
        from machines.machine import arg_type
        raw = yaml.safe_load(FIXTURE.read_text())
        samples = {"string": "x", "int": 1, "bool": True}
        used = {w for v in raw["verbs"].values() for w in v["args"].values()}
        self.assertTrue(used)
        for word in used:
            self.assertIn(word, ARG_TYPES)
            self.assertEqual(arg_type(samples[word]), word)

    def test_every_arg_type_word_is_accepted(self):
        for word in ARG_TYPES:
            t = parse_transport(doc(verbs=LIST + APPEND.replace(
                "body: string", "body: " + word)))
            self.assertEqual(t.verbs["channel.append"].args, {"body": word})


class TestReturns(unittest.TestCase):
    def test_channel_read_requires_returns(self):
        text = doc(verbs=LIST.replace("    returns: messages\n", "") + APPEND)
        e = refused(self, text, "returns", "channel.list")
        self.assertEqual(e.field, "returns")

    def test_returns_value_must_be_in_returns(self):
        e = refused(self, doc(verbs=LIST.replace("messages", "threads") + APPEND),
                    "returns", "threads")
        self.assertEqual(e.field, "returns")

    def test_returns_refused_on_other_touches(self):
        e = refused(self, doc(verbs=LIST + APPEND + "    returns: messages\n"),
                    "returns", "channel.append")
        self.assertEqual(e.field, "returns")
        wr = ("  w:\n    touches: world-read\n    performer: transport\n"
              "    args: {}\n    returns: messages\n")
        refused(self, doc(verbs=LIST + APPEND + wr), "returns", "w")


class TestRequiredVerbs(unittest.TestCase):
    def test_channel_list_missing(self):
        e = refused(self, doc(verbs=APPEND), "channel.list")
        self.assertEqual(e.field, "verbs")

    def test_channel_append_missing(self):
        e = refused(self, doc(verbs=LIST), "channel.append")
        self.assertEqual(e.field, "verbs")

    def test_two_channel_read_verbs_refused(self):
        second = LIST.replace("channel.list", "channel.peek")
        e = refused(self, doc(verbs=LIST + second + APPEND),
                    "channel-read", "channel.peek")
        self.assertEqual(e.field, "verbs")

    def test_the_only_channel_read_must_be_named_channel_list(self):
        refused(self, doc(verbs=LIST.replace("channel.list", "channel.peek")
                          + APPEND), "channel.list", "channel.peek")

    def test_channel_list_must_be_channel_read(self):
        refused(self, doc(verbs=LIST.replace("channel-read", "world-read")
                          .replace("    returns: messages\n", "") + APPEND),
                "channel.list", "channel-read")

    def test_channel_list_must_take_no_arguments(self):
        e = refused(self, doc(verbs=LIST.replace("args: {}",
                                                 "args: { since: string }")
                              + APPEND), "channel.list", "since")
        self.assertEqual(e.field, "args")

    def test_channel_list_must_be_performed_by_the_transport(self):
        refused(self, doc(verbs=LIST.replace("performer: transport",
                                             "performer: agent") + APPEND),
                "channel.list", "performer")

    def test_channel_append_must_be_channel_write(self):
        refused(self, doc(verbs=LIST + APPEND.replace("channel-write",
                                                      "world-write")),
                "channel.append", "channel-write")

    def test_channel_append_must_be_performed_by_the_transport(self):
        refused(self, doc(verbs=LIST + APPEND.replace("performer: transport",
                                                      "performer: agent")),
                "channel.append", "performer")


class TestAgentVerbs(unittest.TestCase):
    AGENT = ("  x:\n    touches: %s\n    performer: agent\n    args: {}\n")

    def test_agent_may_not_read_or_write_the_channel(self):
        for touches in ("channel-read", "channel-write"):
            extra = self.AGENT % touches
            if touches == "channel-read":
                # Would also be a second channel-read; the agent rule must
                # be the reason named, so check it on its own first.
                extra += "    returns: messages\n"
            e = refused(self, doc(verbs=LIST + APPEND + extra), "x", "agent")
            self.assertIn(touches, e.message)

    def test_agent_may_touch_the_world(self):
        for touches in ("world-read", "world-write"):
            t = parse_transport(doc(verbs=LIST + APPEND + self.AGENT % touches))
            self.assertEqual(t.verbs["x"].performer, "agent")


if __name__ == "__main__":
    unittest.main()
