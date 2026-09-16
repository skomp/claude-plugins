import unittest
from pathlib import Path
from machines.declaration import extract_block, parse
from machines.errors import DeclarationError
from machines.machine import FIELDS, REQUIRED

ONE = "intro\n\n```machine\nmachine: x\n```\n\ntrailing prose\n"
NONE = "intro only, no block\n"
TWO = "```machine\na: 1\n```\ntext\n```machine\nb: 2\n```\n"
OTHER_FENCE = "```yaml\nmachine: x\n```\n"

class TestExtractBlock(unittest.TestCase):
    def test_returns_block_contents_without_the_fences(self):
        self.assertEqual(extract_block(ONE), "machine: x\n")

    def test_no_block_raises(self):
        with self.assertRaises(DeclarationError):
            extract_block(NONE)

    def test_two_blocks_raises(self):
        with self.assertRaises(DeclarationError):
            extract_block(TWO)

    def test_a_yaml_fence_is_not_a_machine_fence(self):
        with self.assertRaises(DeclarationError):
            extract_block(OTHER_FENCE)

# `cap: 10` below is the bare legacy spelling, kept unchanged on purpose.
# `tests/fixtures/valid-session-relay.md` was byte-identical to this
# declaration until `cap` gained a scope and moved to the mapping form
# (`cap: { limit: 10, per: role }`) there -- VALID did not move with it.
# From here on VALID is the back-compatibility regression
# fixture for the bare-integer spelling, and the *only* place that
# spelling is still exercised: re-syncing the two would delete that
# coverage. See `test_the_session_relay_fixture_declares_a_per_role_cap`
# below, which carries the same note against the fixture side.
VALID = """
```machine
machine: session-relay
version: v1
prefix: "session-relay:v1 "
roles:
  initiator: repository
  responder: repository
kinds: [triage, question, answer, conclusion, stalemate]
cap: 10
initial: unopened
states:
  - { name: unopened, holder: initiator, accepting: true }
  - { name: awaiting-triage, holder: responder }
  - { name: awaiting-answer, holder: initiator }
  - { name: concluded, terminal: true, accepting: true }
  - { name: stalled, terminal: true }
transitions:
  - { from: unopened, on: triage, by: initiator, to: awaiting-triage, signal: true,
      effects: ["label.add:session-relay:open"] }
  - { from: awaiting-triage, on: question, by: responder, to: awaiting-answer, signal: true }
  - { from: awaiting-answer, on: answer, by: initiator, to: awaiting-triage, signal: true }
  - { from: awaiting-triage, on: conclusion, by: responder, to: concluded, signal: true,
      effects: ["label.remove:session-relay:open"] }
  - { from: awaiting-triage, on: stalemate, by: responder, to: stalled, signal: true,
      effects: ["label.remove:session-relay:open", "label.add:session-relay:stalled", "escalate"] }
```
"""

class TestParse(unittest.TestCase):
    def test_parses_every_declared_field(self):
        m = parse(VALID)
        self.assertEqual(m.name, "session-relay")
        self.assertEqual(m.version, "v1")
        self.assertEqual(m.prefix, "session-relay:v1 ")
        self.assertEqual(m.cap, 10)
        self.assertEqual(m.initial, "unopened")
        self.assertEqual(set(m.roles), {"initiator", "responder"})
        self.assertEqual(len(m.states), 5)
        self.assertEqual(len(m.transitions), 5)

    def test_transition_fields_land_on_the_right_attributes(self):
        m = parse(VALID)
        t = m.transitions[1]
        self.assertEqual(t.frm, "awaiting-triage")
        self.assertEqual(t.on, "question")
        self.assertEqual(t.by, "responder")
        self.assertEqual(t.to, "awaiting-answer")
        self.assertTrue(t.signal)
        self.assertEqual(t.effects, [])

    def test_terminal_state_is_terminal_and_others_are_not(self):
        m = parse(VALID)
        self.assertTrue(m.states["concluded"].terminal)
        self.assertFalse(m.states["awaiting-triage"].terminal)

    def test_accepting_is_parsed_and_defaults_to_false(self):
        # The default is the conservative one on purpose: an author who
        # declares nothing accepting gets a machine the checker rejects,
        # rather than one where stopping anywhere is silently fine.
        m = parse(VALID)
        self.assertTrue(m.states["unopened"].accepting)
        self.assertTrue(m.states["concluded"].accepting)
        self.assertFalse(m.states["awaiting-triage"].accepting)
        self.assertFalse(m.states["awaiting-answer"].accepting)

    def test_accepting_and_terminal_are_independent(self):
        # `stalled` carries `terminal: true` and no `accepting`, and comes
        # back terminal and not accepting. A parser that derived one from
        # the other would flatten the fixture's error state into an
        # ordinary conclusion.
        m = parse(VALID)
        self.assertTrue(m.states["stalled"].terminal)
        self.assertFalse(m.states["stalled"].accepting)

    def test_accepting_must_be_an_actual_boolean(self):
        # Same hazard as `terminal` and `signal`: with the resolver
        # narrowed, `accepting: yes` is the string "yes", and Python
        # truthiness would happily make that True.
        for written in ("yes", "1", '"true"'):
            with self.subTest(written=written):
                bad = VALID.replace(
                    "- { name: unopened, holder: initiator, accepting: true }",
                    "- { name: unopened, holder: initiator, accepting: %s }" % written)
                with self.assertRaises(DeclarationError) as ctx:
                    parse(bad)
                self.assertEqual(ctx.exception.field, "accepting")

    def test_cap_may_be_absent_entirely(self):
        # The field is optional, and absent means "this protocol declares
        # no bound" -- not zero, not a sentinel, not a default the author
        # never asked for. A protocol with no reason to terminate must be
        # able to say nothing about a cap rather than invent one.
        m = parse(VALID.replace("cap: 10\n", ""))
        self.assertIsNone(m.cap)
        # `cap_scope` still carries its default even with no cap to scope
        # -- unused, but present, the same reasoning `fields`/`registers`
        # default to `{}` rather than `None`.
        self.assertEqual(m.cap_scope, "channel")

    def test_a_bare_integer_cap_means_per_channel(self):
        m = parse(VALID)
        self.assertEqual(m.cap, 10)
        self.assertEqual(m.cap_scope, "channel")

    def test_the_mapping_form_with_per_channel_is_identical_to_the_bare_form(self):
        spelled = parse(VALID.replace("cap: 10", "cap: { limit: 10, per: channel }"))
        self.assertEqual(
            (spelled.cap, spelled.cap_scope),
            (parse(VALID).cap, parse(VALID).cap_scope))

    def test_per_role_lands_on_cap_scope(self):
        m = parse(VALID.replace("cap: 10", "cap: { limit: 10, per: role }"))
        self.assertEqual(m.cap, 10)
        self.assertEqual(m.cap_scope, "role")

    def test_the_mapping_form_requires_both_keys(self):
        with self.assertRaises(DeclarationError) as ctx:
            parse(VALID.replace("cap: 10", "cap: { limit: 10 }"))
        self.assertEqual(ctx.exception.field, "per")
        with self.assertRaises(DeclarationError) as ctx:
            parse(VALID.replace("cap: 10", "cap: { per: role }"))
        self.assertEqual(ctx.exception.field, "limit")

    def test_an_unknown_scope_is_rejected_by_name(self):
        # `sender` is not a word this schema uses -- there is no per-sender
        # scope, and the declaration itself has no field named `sender`
        # for one to mean. `run` is rejected too: a run is a channel under
        # a different name, not a separate scope.
        for bad in ("sender", "run", "issue"):
            with self.subTest(bad=bad):
                with self.assertRaises(DeclarationError) as ctx:
                    parse(VALID.replace(
                        "cap: 10", "cap: { limit: 10, per: %s }" % bad))
                self.assertEqual(ctx.exception.field, "cap")

    def test_an_unknown_key_in_the_cap_mapping_is_rejected(self):
        with self.assertRaises(DeclarationError) as ctx:
            parse(VALID.replace(
                "cap: 10", "cap: { limit: 10, per: role, extra: 1 }"))
        self.assertEqual(ctx.exception.field, "extra")

    def test_the_limit_obeys_the_positive_integer_rule(self):
        # Same rule as the bare form's, including the `bool` exclusion --
        # `per: role` does not relax what counts as a real count.
        for value in ("0", "-1", '"ten"', "true"):
            with self.subTest(value=value):
                with self.assertRaises(DeclarationError) as ctx:
                    parse(VALID.replace(
                        "cap: 10", "cap: { limit: %s, per: role }" % value))
                self.assertEqual(ctx.exception.field, "cap")

    def test_the_session_relay_fixture_declares_a_per_role_cap(self):
        # The fixture is the real declaration and says what the protocol
        # means; VALID above keeps the bare form on purpose -- see the
        # comment above VALID's definition. Do not re-sync the two: doing
        # so would delete the only coverage this suite has of the legacy
        # bare-integer spelling.
        text = (Path(__file__).parent / "fixtures" / "valid-session-relay.md").read_text()
        m = parse(text)
        self.assertEqual((m.cap, m.cap_scope), (10, "role"))

    def test_unknown_top_level_field_raises_and_names_it(self):
        bad = VALID.replace("cap: 10", "cap: 10\ncaps: 12")
        with self.assertRaises(DeclarationError) as ctx:
            parse(bad)
        self.assertEqual(ctx.exception.field, "caps")

    def test_missing_required_field_raises_and_names_it(self):
        # `initial`, not `cap`: `cap` became optional when the framework
        # stopped requiring protocols to terminate, so its absence is no
        # longer a missing-field error and cannot stand in for one here.
        bad = VALID.replace("initial: unopened\n", "")
        with self.assertRaises(DeclarationError) as ctx:
            parse(bad)
        self.assertEqual(ctx.exception.field, "initial")

    def test_cap_when_present_must_be_a_positive_integer(self):
        # Optional does not mean unvalidated. Every one of these is a
        # written cap, and none of them is a count.
        for value in ("0", "-1", '"ten"', "true", "false"):
            with self.subTest(value=value):
                with self.assertRaises(DeclarationError) as ctx:
                    parse(VALID.replace("cap: 10", "cap: " + value))
                self.assertEqual(ctx.exception.field, "cap")

    def test_fields_is_accepted_but_not_required(self):
        # `fields` and `registers` are both optional top-level fields.
        # VALID carries neither, and has always parsed -- assert that on
        # purpose, rather than let the suite stay green by accident if a
        # future change made either required.
        self.assertIn("fields", FIELDS)
        self.assertIn("registers", FIELDS)
        # The full value, not just two memberships: a membership check
        # alone would not catch some future change accidentally adding a
        # third optional name to FIELDS without also excluding it here.
        self.assertEqual(
            REQUIRED,
            ("machine", "version", "prefix", "roles", "kinds",
             "initial", "states", "transitions"))
        m = parse(VALID)
        self.assertEqual(m.fields, {})

    def test_duplicate_state_name_raises(self):
        bad = VALID.replace(
            "- { name: concluded, terminal: true, accepting: true }",
            "- { name: awaiting-triage, terminal: true }",
        )
        with self.assertRaises(DeclarationError):
            parse(bad)


class TestBooleanTokenWordsStayStrings(unittest.TestCase):
    """PyYAML's default resolver treats yes/no/on/off (and case variants)
    as booleans in *any* scalar position -- a mapping key as much as a
    value. A publisher choosing one of those words as an ordinary name
    must get that name back, not a Python bool, in every position the
    schema exposes: a kind, a state name, a role name, a transition's
    `on`, and a `holder`. A test that only covers the `on:` key leaves
    the other four positions exactly as exposed as before.
    """

    def test_kind_named_with_a_boolean_token_word_stays_a_string(self):
        bad = VALID.replace(
            "kinds: [triage, question, answer, conclusion, stalemate]",
            "kinds: [yes, question, answer, conclusion, stalemate]",
        )
        m = parse(bad)
        self.assertIn("yes", m.kinds)
        self.assertNotIn(True, m.kinds)

    def test_state_named_with_a_boolean_token_word_stays_a_string(self):
        bad = VALID.replace(
            "- { name: stalled, terminal: true }",
            "- { name: yes, terminal: true }",
        )
        m = parse(bad)
        self.assertIn("yes", m.states)
        self.assertEqual(m.states["yes"].name, "yes")

    def test_role_named_with_a_boolean_token_word_stays_a_string(self):
        bad = VALID.replace("initiator: repository", "yes: repository")
        m = parse(bad)
        self.assertIn("yes", m.roles)

    def test_transition_on_a_boolean_token_word_stays_a_string(self):
        bad = VALID.replace("on: question", "on: yes")
        m = parse(bad)
        self.assertEqual(m.transitions[1].on, "yes")

    def test_holder_set_to_a_boolean_token_word_stays_a_string(self):
        bad = VALID.replace("holder: responder", "holder: yes")
        m = parse(bad)
        self.assertEqual(m.states["awaiting-triage"].holder, "yes")

    def test_signal_no_longer_accepts_yes_as_true(self):
        # The cost of narrowing the resolver: `signal: yes` is now the
        # string "yes", not the boolean True, and this field requires an
        # actual boolean rather than falling back to Python truthiness.
        bad = VALID.replace("signal: true", "signal: yes", 1)
        with self.assertRaises(DeclarationError):
            parse(bad)


_STATES_BLOCK = """states:
  - { name: unopened, holder: initiator, accepting: true }
  - { name: awaiting-triage, holder: responder }
  - { name: awaiting-answer, holder: initiator }
  - { name: concluded, terminal: true, accepting: true }
  - { name: stalled, terminal: true }
"""

_TRANSITIONS_BLOCK = """transitions:
  - { from: unopened, on: triage, by: initiator, to: awaiting-triage, signal: true,
      effects: ["label.add:session-relay:open"] }
  - { from: awaiting-triage, on: question, by: responder, to: awaiting-answer, signal: true }
  - { from: awaiting-answer, on: answer, by: initiator, to: awaiting-triage, signal: true }
  - { from: awaiting-triage, on: conclusion, by: responder, to: concluded, signal: true,
      effects: ["label.remove:session-relay:open"] }
  - { from: awaiting-triage, on: stalemate, by: responder, to: stalled, signal: true,
      effects: ["label.remove:session-relay:open", "label.add:session-relay:stalled", "escalate"] }
"""

class TestMalformedListShapedFields(unittest.TestCase):
    def test_kinds_that_is_not_a_list_raises_and_names_it(self):
        bad = VALID.replace(
            "kinds: [triage, question, answer, conclusion, stalemate]",
            "kinds: yes",
        )
        with self.assertRaises(DeclarationError) as ctx:
            parse(bad)
        self.assertEqual(ctx.exception.field, "kinds")

    def test_states_that_is_not_a_list_raises_and_names_it(self):
        bad = VALID.replace(_STATES_BLOCK, "states: not-a-list\n")
        with self.assertRaises(DeclarationError) as ctx:
            parse(bad)
        self.assertEqual(ctx.exception.field, "states")

    def test_transitions_that_is_not_a_list_raises_and_names_it(self):
        bad = VALID.replace(_TRANSITIONS_BLOCK, "transitions: not-a-list\n")
        with self.assertRaises(DeclarationError) as ctx:
            parse(bad)
        self.assertEqual(ctx.exception.field, "transitions")


_ROLES_BLOCK = """roles:
  initiator: repository
  responder: repository
"""

_A_STATE = "- { name: stalled, terminal: true }"
_A_TRANSITION = ("  - { from: awaiting-triage, on: question, by: responder, "
                 "to: awaiting-answer, signal: true }")
_AN_EFFECTS_LIST = 'effects: ["label.remove:session-relay:open"] }'


class TestMalformedInputIsRejectedByNameNotByTraceback(unittest.TestCase):
    """Every one of these inputs is a plausible hand-written declaration,
    and every one of them used to reach the caller as a raw Python
    traceback -- ValueError, KeyError, TypeError, AttributeError -- from
    `parse`, from `check_machine`, or from `check_all`.

    That is not a cosmetic complaint. `machines-check` has three exit
    codes on purpose: 1 is "I checked, and found a problem", 2 is "I could
    not check at all". An uncaught exception exits 1 with a traceback,
    which reports the tool's own crash as a finding about the publisher's
    machine. The whole contract of this tool is to name the field that is
    wrong, so each case here asserts on `exception.field`, not merely that
    something was raised.

    One row is worse than a crash and is the reason the list-shape guards
    were not enough: `effects: escalate` never raised at all. A string is
    iterable, so the effect-vocabulary check walked it character by
    character and reported eight problems -- 'e', 's', 'c', 'a', 'l', ...
    -- eight confident wrong answers where a crash would at least have
    been visible.
    """

    def assert_rejected(self, field, old, new):
        self.assertIn(old, VALID, "the splice anchor %r is stale" % old)
        with self.assertRaises(DeclarationError) as ctx:
            parse(VALID.replace(old, new))
        self.assertEqual(ctx.exception.field, field)

    # -- containers --

    def test_roles_that_is_a_scalar_is_rejected(self):
        self.assert_rejected("roles", _ROLES_BLOCK, "roles: nobody\n")

    def test_roles_that_is_a_list_is_rejected(self):
        self.assert_rejected("roles", _ROLES_BLOCK, "roles: [a, b]\n")

    def test_a_role_key_that_is_not_a_string_is_rejected(self):
        # `check_machine` sorts `m.roles` to build `role_index` for the
        # per-role cap search (machine.py, `role_index = {r: i for i, r
        # in enumerate(sorted(m.roles))}`). A non-string role key sails
        # past the `isinstance(roles, dict)` check and used to reach
        # that sort as a raw `TypeError: '<' not supported between
        # instances of 'str' and 'int'` -- the shipped CLI exiting 1
        # with a Python traceback instead of naming the field.
        self.assert_rejected(
            "roles", _ROLES_BLOCK,
            "roles:\n  1: repository\n  responder: repository\n")

    def test_a_states_entry_that_is_not_a_mapping_is_rejected(self):
        self.assert_rejected("states", _A_STATE, "- 5")

    def test_a_transitions_entry_that_is_not_a_mapping_is_rejected(self):
        self.assert_rejected("transitions", _A_TRANSITION, "  - 5")

    # -- missing sub-fields --

    def test_a_states_entry_without_a_name_is_rejected(self):
        self.assert_rejected("name", _A_STATE, "- { terminal: true }")

    def test_a_transitions_entry_without_a_to_is_rejected(self):
        self.assert_rejected("to", ", to: awaiting-answer, signal: true }",
                             ", signal: true }")

    # -- scalars the schema documents as strings --

    def test_a_non_string_machine_is_rejected(self):
        self.assert_rejected("machine", "machine: session-relay", "machine: 5")

    def test_a_non_string_version_is_rejected(self):
        self.assert_rejected("version", "version: v1", "version: 1")

    def test_a_non_string_initial_is_rejected(self):
        self.assert_rejected("initial", "initial: unopened", "initial: 5")

    def test_a_non_string_state_name_is_rejected(self):
        self.assert_rejected("name", _A_STATE, "- { name: 5, terminal: true }")

    def test_a_non_string_holder_is_rejected(self):
        self.assert_rejected("holder", "holder: responder", "holder: 5")

    def test_a_non_string_transition_field_is_rejected(self):
        for field, old, new in (
            ("from", "from: unopened,", "from: 5,"),
            ("on", "on: triage,", "on: 5,"),
            ("by", "by: initiator, to: awaiting-triage", "by: 5, to: awaiting-triage"),
            ("to", "to: awaiting-triage, signal", "to: 5, signal"),
        ):
            with self.subTest(field=field):
                self.assert_rejected(field, old, new)

    def test_a_non_string_prefix_is_rejected(self):
        # This one never crashed in `parse` at all: `prefix: 5` parsed
        # cleanly and then failed with `TypeError: object of type 'int'
        # has no len()` out of the pattern compiler, one module and one
        # public entry point away from the field that caused it.
        for written in ("5", "", "2.0"):
            with self.subTest(prefix=written):
                self.assert_rejected(
                    "prefix", 'prefix: "session-relay:v1 "', "prefix: " + written)

    def test_a_401_character_prefix_is_rejected(self):
        # A literal this long parses and compiles cleanly on its own -- no
        # metacharacter anywhere in it -- but a bare literal past 498
        # characters blows the stack with an uncaught RecursionError deep
        # in the NFA compiler (reached via check_machine's prefix_problem,
        # in machine.py), not a DeclarationError. 401 is one past the
        # declared 400-character limit, well short of where recursion
        # actually fails, so this exercises the guard rather than the
        # crash it exists to prevent.
        self.assert_rejected(
            "prefix", 'prefix: "session-relay:v1 "',
            'prefix: "%s"' % ("a" * 401))

    def test_a_400_character_prefix_is_accepted(self):
        # The boundary, in the direction that matters: exactly the stated
        # limit must parse, not be off-by-one rejected.
        m = parse(VALID.replace(
            'prefix: "session-relay:v1 "', 'prefix: "%s"' % ("a" * 400)))
        self.assertEqual(len(m.prefix), 400)

    # -- list entries --

    def test_a_non_string_kinds_entry_is_rejected(self):
        self.assert_rejected(
            "kinds", "kinds: [triage, question, answer, conclusion, stalemate]",
            "kinds: [5]")

    def test_a_non_string_effects_entry_is_rejected(self):
        self.assert_rejected("effects", _AN_EFFECTS_LIST, "effects: [5] }")

    def test_a_scalar_effects_field_is_rejected(self):
        self.assert_rejected("effects", _AN_EFFECTS_LIST, "effects: 5 }")

    def test_a_bare_string_effects_field_is_rejected_not_iterated(self):
        # The row that did not crash: eight problems, one per character of
        # "escalate", every one of them wrong.
        self.assert_rejected("effects", _AN_EFFECTS_LIST, "effects: escalate }")


if __name__ == "__main__":
    unittest.main()
