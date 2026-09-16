import unittest

from machines.declaration import parse
from machines.errors import DeclarationError
from machines.machine import (Field, Guard, Machine, State, Transition,
                               check_machine)
from tests.test_declaration import VALID  # the known-good declaration


# `GUARDED` grew across three tasks of this cycle, the way `VALID`
# (test_declaration.py) stays fixed but `test_machine.py`'s tests mutate
# copies of it: Task 3 added `fields`; Task 5 added a `guard:` mapping to
# four of the transitions below; Task 7 converted the bare `cap: 6` to the
# mapping form `cap: { limit: 6, per: role }`. That growth is now
# finished -- this is, from here on, the same declaration
# `valid-paxos-acceptor.md` (a fixture Task 9 creates) carries, and
# nothing after this task changes it further.
#
# `GUARDED` and the Paxos fixture are deliberately NOT allowed to diverge
# the way `VALID` and `tests/fixtures/valid-session-relay.md` do (see the
# comment above `VALID` in test_declaration.py): that pair keeps one
# bare-form regression fixture on purpose, but nothing here wants a
# second diverged pair, and Task 9's fixture is meant to be the same
# declaration as this constant, byte for byte where it matters.
#
# Ruling B -- four of the seven transitions below carry `guard:`. Left
# unguarded, this declaration has two genuinely nondeterministic groups
# (`idle` on `prepare` by `proposer`, and `promised` on `accept-request`
# by `proposer`); the determinism rule in `check_machine` treats a
# disjoint guarded branch as legal, which is why `test_the_paxos_fixture_is_well_formed`
# below reports no problems for this declaration.
GUARDED = """
The paxos-acceptor protocol carries a single Paxos ballot number as a
declared header field, and one register -- `highest_promised` -- that
folds it by `max` over `prepare` messages. Four transitions below guard
on it: a `prepare` is only a promise when its ballot beats the highest
one already promised, and an `accept-request` is only honoured at the
ballot the acceptor promised, never another.

```machine
machine: paxos-acceptor
version: v1
prefix: "paxos:v1 "
roles:
  proposer: session
  acceptor: session
kinds: [prepare, promise, accept-request, accepted, rejected]
fields:
  ballot: int
registers:
  highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }
cap: { limit: 6, per: role }
initial: idle
states:
  - { name: idle,     holder: proposer, accepting: true }
  - { name: prepared, holder: acceptor }
  - { name: promised, holder: proposer, accepting: true }
  - { name: proposed, holder: acceptor }
  - { name: decided,  terminal: true, accepting: true }
transitions:
  - { from: idle, on: prepare, by: proposer, to: prepared, signal: true,
      guard: { field: ballot, op: gt, register: highest_promised } }
  - { from: idle, on: prepare, by: proposer, to: idle, signal: true,
      guard: { field: ballot, op: le, register: highest_promised } }
  - { from: prepared, on: promise, by: acceptor, to: promised, signal: true }
  - { from: promised, on: accept-request, by: proposer, to: proposed, signal: true,
      guard: { field: ballot, op: eq, register: highest_promised } }
  - { from: promised, on: accept-request, by: proposer, to: idle, signal: true,
      guard: { field: ballot, op: ne, register: highest_promised } }
  - { from: proposed, on: accepted, by: acceptor, to: decided, signal: true }
  - { from: proposed, on: rejected, by: acceptor, to: idle, signal: true }
```
"""


def _splice_once(text, old, new):
    # Assert the splice landed on exactly the text intended -- the same
    # discipline `test_machine.py`'s `mutate()` applies to `VALID` (see
    # tests/test_machine.py:7-15), strengthened one step further. A
    # `str.replace` whose `old` no longer occurs in `text` returns it
    # unchanged, so a test that only inspects the parse result would go
    # on checking the unmodified declaration and pass while testing
    # nothing -- that is what `old in text` alone catches. But `old`
    # occurring *more than once* is its own silent failure: `str.replace`
    # rewrites every occurrence, so a caller who means to touch one
    # register's `field: ballot` and forgets that `GUARDED`'s prose above
    # the fence also says "declared header field" would splice text the
    # test never meant to touch, with no error anywhere -- a defect this
    # module's own history has already produced once. Counting `old`'s
    # occurrences and requiring exactly one closes that gap for every
    # caller, not just the one that tripped over it.
    #
    # Takes `text` rather than always reading `GUARDED` so a test that
    # needs more than one substitution -- progressively mutating the same
    # string -- can chain calls (splice `GUARDED` once, then splice the
    # result again) and keep the same exactly-once guarantee at every
    # step, instead of falling back to a raw, unguarded `str.replace`
    # once the text in hand is no longer literally `GUARDED`.
    # `splice_guarded`, below, is the common case (splicing `GUARDED`
    # itself) built on top of this.
    count = text.count(old)
    assert count == 1, (
        "splice(%r, ...) matched %d times, not exactly once -- pick a "
        "more specific target" % (old, count))
    return text.replace(old, new)


def splice_guarded(old, new):
    return _splice_once(GUARDED, old, new)


class TestFields(unittest.TestCase):
    def test_a_declared_field_lands_with_its_type(self):
        m = parse(GUARDED)
        self.assertEqual(m.fields["ballot"].type, "int")

    def test_a_machine_with_no_fields_gets_an_empty_mapping_not_none(self):
        m = parse(VALID)
        self.assertEqual(m.fields, {})

    def test_an_explicit_empty_fields_mapping_is_also_empty(self):
        # "absent or empty" -- VALID (no `fields` key at all) covers absent;
        # this covers a publisher who writes the key with nothing under it.
        m = parse(splice_guarded("fields:\n  ballot: int", "fields: {}"))
        self.assertEqual(m.fields, {})

    def test_an_unknown_type_is_rejected_by_name(self):
        for bad in ("integer", "number", "string", "float"):
            with self.subTest(bad=bad):
                with self.assertRaises(DeclarationError) as ctx:
                    parse(splice_guarded("ballot: int", "ballot: " + bad))
                self.assertEqual(ctx.exception.field, "fields")

    def test_a_non_string_type_word_is_rejected(self):
        # `fields: {ballot: 3}` -- the brief's own motivating failure: an
        # integer reaching the guard's type check instead of a type word.
        with self.assertRaises(DeclarationError) as ctx:
            parse(splice_guarded("ballot: int", "ballot: 3"))
        self.assertEqual(ctx.exception.field, "fields")

    def test_a_field_name_with_a_dot_is_rejected(self):
        # The dotted namespace is reserved for the envelope (spec section 7):
        # the clock must never become something an author can declare.
        with self.assertRaises(DeclarationError):
            parse(splice_guarded("ballot: int", "envelope.clock: int"))

    def test_a_bool_field_is_accepted(self):
        m = parse(splice_guarded(
            "ballot: int", "ballot: int\n  blocking: bool"))
        self.assertEqual(m.fields["blocking"].type, "bool")


class TestCap(unittest.TestCase):
    def test_the_paxos_declaration_declares_a_per_role_cap(self):
        m = parse(GUARDED)
        self.assertEqual((m.cap, m.cap_scope), (6, "role"))


class TestRegisters(unittest.TestCase):
    def test_a_register_lands_with_its_fold_field_kinds_and_initial(self):
        r = parse(GUARDED).registers["highest_promised"]
        self.assertEqual(r.fold, "max")
        self.assertEqual(r.field, "ballot")
        self.assertEqual(r.on, ["prepare"])
        self.assertEqual(r.initial, 0)

    def test_an_unknown_fold_is_rejected(self):
        # `count` is the fold that invites "how many promises have I
        # collected" -- which is quorum, which is aggregation over a set
        # of messages, which the spec forbids a register from expressing.
        # Refusing it here costs nothing and removes the temptation to
        # reach for it as the readable-looking way to smuggle quorum
        # counting past that restriction one message at a time.
        #
        # `argmax` needs a second remembered value (which message, or
        # which of its other fields, produced the maximum) alongside the
        # scalar -- a second thing to remember, not a bigger fold over
        # the one a register holds. See the fold/argmax boundary comment
        # next to the R1-R4 checks in `check_machine`.
        for bad in ("count", "argmax", "sum", "min", "first"):
            with self.subTest(bad=bad):
                with self.assertRaises(DeclarationError) as ctx:
                    parse(splice_guarded("fold: max", "fold: " + bad))
                self.assertEqual(ctx.exception.field, "registers")

    def test_an_empty_on_list_is_rejected(self):
        with self.assertRaises(DeclarationError) as ctx:
            parse(splice_guarded("on: [prepare]", "on: []"))
        self.assertEqual(ctx.exception.field, "registers")

    def test_a_register_on_an_undeclared_field_is_reported(self):
        # `"field: ballot"` alone now occurs five times once guards exist
        # (the register's own declaration plus four guards that also name
        # `field: ballot`) -- `_splice_once` would refuse it. `"fold: max,
        # field: ballot"` is the register's own declaration line and
        # nowhere else, so it stays a single, specific target.
        m = parse(splice_guarded("fold: max, field: ballot", "fold: max, field: nope"))
        problems = check_machine(m)
        self.assertTrue(
            any("highest_promised" in p and "nope" in p for p in problems),
            problems)

    def test_a_register_fed_by_an_undeclared_kind_is_reported(self):
        m = parse(splice_guarded("on: [prepare]", "on: [shouting]"))
        problems = check_machine(m)
        self.assertTrue(
            any("highest_promised" in p and "shouting" in p
                for p in problems),
            problems)

    def test_a_bool_initial_on_an_int_field_is_reported(self):
        m = parse(splice_guarded("initial: 0", "initial: true"))
        problems = check_machine(m)
        self.assertTrue(
            any("highest_promised" in p for p in problems), problems)

    def test_an_int_initial_on_a_bool_field_is_reported(self):
        # Two splices, chained: add a bool field, then point the register
        # at it, leaving `initial: 0` (an int) untouched. Both go through
        # `_splice_once`, so each carries the same exactly-once guarantee
        # `splice_guarded` gives `GUARDED` itself -- there is no raw,
        # unguarded `str.replace` against `GUARDED` or text derived from
        # it anywhere in this file.
        # Same retargeting as test_a_register_on_an_undeclared_field_is_reported,
        # and for the same reason: `"field: ballot"` alone is no longer
        # unique once guards exist.
        text = _splice_once(
            GUARDED, "fields:\n  ballot: int",
            "fields:\n  ballot: int\n  blocking: bool")
        text = _splice_once(text, "fold: max, field: ballot", "fold: max, field: blocking")
        m = parse(text)
        problems = check_machine(m)
        # Not just `any("highest_promised" in p for p in problems)`: once
        # the register's field is `blocking` (bool), all four guards --
        # which still compare a `ballot` (int) field against this register
        # -- also trip G4, each message naming `highest_promised` too.
        # Naming "initial" as well pins this assertion to R3, the problem
        # this test is actually about; deleting R3 from `check_machine`
        # would leave the untightened assertion green on G4 messages
        # alone.
        self.assertTrue(
            any("highest_promised" in p and "initial" in p for p in problems),
            problems)

    def test_a_register_sharing_a_name_with_a_field_is_reported(self):
        # `highest_promised` occurs many times in GUARDED now that guards
        # exist -- the prose, the registers key, and every guard's
        # `register: highest_promised` -- so `old` has to be the unique
        # `registers:` line itself, not the bare name.
        #
        # This splice renames only the registers *key*, not the guards'
        # `register:` references, so it also leaves every guard naming an
        # undeclared register (G2) and the renamed register unguarded
        # (G5) -- both real, both additional. The assertion below only
        # asks whether the field-collision problem (R4) this test is
        # actually about is among them, which it still is.
        m = parse(splice_guarded(
            "registers:\n  highest_promised:", "registers:\n  ballot:"))
        problems = check_machine(m)
        self.assertTrue(
            any("ballot" in p and "field" in p for p in problems), problems)


class TestGuards(unittest.TestCase):
    def test_a_guard_lands_on_the_transition(self):
        m = parse(GUARDED)
        t = next(t for t in m.transitions if t.frm == "idle" and t.to == "prepared")
        self.assertEqual((t.guard.field, t.guard.op, t.guard.register),
                         ("ballot", "gt", "highest_promised"))

    def test_an_unguarded_transition_has_guard_none(self):
        # `prepared` on `promise` is the one transition Ruling B left
        # unguarded.
        m = parse(GUARDED)
        t = next(t for t in m.transitions if t.frm == "prepared" and t.to == "promised")
        self.assertIsNone(t.guard)

    def test_an_unknown_operator_is_rejected_by_name(self):
        # Measured against the shipped `MachineSafeLoader`: in block
        # context, an unquoted `op: >` parses to the empty string with no
        # error raised anywhere, because `>` is YAML's block-scalar
        # indicator, not a comparison symbol reaching this check.
        # `GUARDED`'s own guard mappings are flow-style (`{ field: ...,
        # op: ..., register: ... }`), where an unquoted `op: >` instead
        # raises a YAML `ScannerError` immediately -- a different, but
        # still wrong, failure mode; `op: !=` fails with a YAML error
        # about a tag (`!`) in either style. None of that reaches
        # `_guard_field`'s `op not in OP_ATOMS` check as the string a
        # publisher meant. Quoting each candidate below is what makes it
        # arrive as the plain string it looks like, so the test is
        # actually exercising this module's rejection rather than YAML's
        # -- which is the whole reason the operator vocabulary is spelled
        # out as words instead of symbols.
        for bad in (">", ">=", "gte", "equals"):
            with self.subTest(bad=bad):
                with self.assertRaises(DeclarationError) as ctx:
                    parse(splice_guarded("op: gt", 'op: "%s"' % bad))
                self.assertEqual(ctx.exception.field, "guard")

    def test_a_guard_on_an_undeclared_field_is_reported(self):
        # "field: ballot, op: gt" (not the bare "field: ballot", which
        # now matches five times) is the one guard using `gt`, so this
        # touches only the `idle`-to-`prepared` guard.
        m = parse(splice_guarded("field: ballot, op: gt", "field: nope, op: gt"))
        problems = check_machine(m)
        self.assertTrue(any("nope" in p for p in problems), problems)

    def test_a_guard_against_an_undeclared_register_is_reported(self):
        m = parse(splice_guarded(
            "op: gt, register: highest_promised", "op: gt, register: nope"))
        problems = check_machine(m)
        self.assertTrue(any("nope" in p for p in problems), problems)

    def test_an_ordering_operator_on_a_bool_field_is_reported(self):
        text = _splice_once(
            GUARDED, "fields:\n  ballot: int",
            "fields:\n  ballot: int\n  blocking: bool")
        # Retargets the `gt` guard's field to the new bool field, leaving
        # its register (still folding an `int`) untouched -- this also
        # trips G4 (field/register type mismatch), which is fine: the
        # assertion below only asks for the ordering-specific problem.
        text = _splice_once(text, "field: ballot, op: gt", "field: blocking, op: gt")
        m = parse(text)
        problems = check_machine(m)
        self.assertTrue(any("ordering" in p for p in problems), problems)

    def test_equality_on_a_bool_field_is_accepted(self):
        text = _splice_once(
            GUARDED, "fields:\n  ballot: int",
            "fields:\n  ballot: int\n  blocking: bool")
        text = _splice_once(
            text,
            "highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }",
            "highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }\n"
            "  blocking_last: { fold: last, field: blocking, on: [prepare], initial: false }")
        # Retargets the `eq` guard (the only one) to the new bool field
        # and its matching bool register, so this exercises equality on a
        # bool with nothing else about the fixture disturbed.
        text = _splice_once(
            text, "field: ballot, op: eq, register: highest_promised",
            "field: blocking, op: eq, register: blocking_last")
        m = parse(text)
        problems = check_machine(m)
        self.assertFalse(any("blocking" in p for p in problems), problems)

    def test_an_int_field_compared_to_a_bool_register_is_reported(self):
        text = _splice_once(
            GUARDED, "fields:\n  ballot: int",
            "fields:\n  ballot: int\n  blocking: bool")
        text = _splice_once(
            text,
            "highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }",
            "highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }\n"
            "  blocking_last: { fold: last, field: blocking, on: [prepare], initial: false }")
        # Retargets the `ne` guard's *register* only, leaving its field
        # `ballot` (int) untouched, so only G4 (not G3 -- `ne` is not an
        # ordering operator) is exercised.
        text = _splice_once(
            text, "op: ne, register: highest_promised",
            "op: ne, register: blocking_last")
        m = parse(text)
        problems = check_machine(m)
        self.assertTrue(
            any("blocking_last" in p and "bool" in p for p in problems), problems)

    def test_a_register_no_guard_names_is_reported(self):
        text = _splice_once(
            GUARDED,
            "highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }",
            "highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }\n"
            "  unused: { fold: last, field: ballot, on: [prepare], initial: 0 }")
        m = parse(text)
        problems = check_machine(m)
        self.assertTrue(any("unused" in p for p in problems), problems)

    def test_the_paxos_fixture_is_well_formed(self):
        self.assertEqual(check_machine(parse(GUARDED)), [])


class TestDeterminismUnderGuards(unittest.TestCase):
    """A guarded branch is the only legitimate way for one (frm, on, by) to
    lead to more than one `to`, and only when the guards prove the branches
    can never both fire: every member carries a guard, all guards compare
    the same `field` to the same `register`, and no two of their `OP_ATOMS`
    sets intersect. See the determinism comment in `check_machine` for the
    rule stated in full.
    """

    def test_two_guarded_branches_with_disjoint_operators_are_accepted(self):
        self.assertEqual(
            [p for p in check_machine(parse(GUARDED)) if "nondetermin" in p], [])

    def test_two_guarded_branches_with_overlapping_operators_are_reported(self):
        # `gt` accepts only `GT`; `ge` accepts `EQ` or `GT`. Retargeting the
        # `idle`-to-`idle` branch from `le` to `ge` puts it back in the
        # group next to the `idle`-to-`prepared` branch's `gt`, and their
        # atom sets now share `GT`: both hold whenever the field is
        # strictly greater than the register, not merely when they are
        # equal.
        m = parse(splice_guarded("op: le, register: highest_promised",
                                 "op: ge, register: highest_promised"))
        problems = check_machine(m)
        self.assertTrue(any("nondetermin" in p for p in problems), problems)

    def test_a_branch_where_one_side_is_unguarded_is_reported(self):
        # Drop the `gt` guard from the `idle`-to-`prepared` branch, leaving
        # it unconditional. An unconditional transition always fires, so it
        # overlaps the `le`-guarded `idle`-to-`idle` branch regardless of
        # what that guard says.
        text = _splice_once(
            GUARDED,
            "to: prepared, signal: true,\n"
            "      guard: { field: ballot, op: gt, register: highest_promised } }",
            "to: prepared, signal: true }")
        problems = check_machine(parse(text))
        self.assertTrue(any("nondetermin" in p for p in problems), problems)

    def test_two_branches_guarding_different_fields_are_reported(self):
        # Retarget the `le` guard to a second, newly declared field. Two
        # guards naming different fields cannot be related without
        # interpreting the values they compare, so the group is reported
        # regardless of what either operator is.
        text = _splice_once(GUARDED, "fields:\n  ballot: int",
                            "fields:\n  ballot: int\n  blocking: bool")
        text = _splice_once(
            text, "field: ballot, op: le, register: highest_promised",
            "field: blocking, op: le, register: highest_promised")
        problems = check_machine(parse(text))
        self.assertTrue(any("nondetermin" in p for p in problems), problems)

    def test_two_branches_guarding_different_registers_are_reported(self):
        # A second register, folding the same field, gives the `le` guard
        # somewhere else to point. Two guards naming different registers
        # are exactly as unrelatable as two naming different fields.
        text = _splice_once(
            GUARDED,
            "highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }",
            "highest_promised: { fold: max, field: ballot, on: [prepare], initial: 0 }\n"
            "  highest_promised2: { fold: max, field: ballot, on: [prepare], initial: 0 }")
        text = _splice_once(text, "op: le, register: highest_promised",
                            "op: le, register: highest_promised2")
        problems = check_machine(parse(text))
        self.assertTrue(any("nondetermin" in p for p in problems), problems)

    def test_a_single_guarded_transition_needs_no_complement(self):
        # Paxos's acceptor: accept a high ballot, do nothing with a low one.
        # Dropping the `le`-guarded `idle`-to-`idle` branch entirely leaves
        # the `gt`-guarded `idle`-to-`prepared` branch alone in its group --
        # a single `to`, so the determinism check never even considers it.
        # Incompleteness is legal and must never be reported: some
        # comparison outcome now fires no transition, which is the same
        # outcome as an illegal message, and the engine's verdict already
        # reports that.
        text = _splice_once(
            GUARDED,
            "  - { from: idle, on: prepare, by: proposer, to: idle, signal: true,\n"
            "      guard: { field: ballot, op: le, register: highest_promised } }\n",
            "")
        self.assertEqual(
            [p for p in check_machine(parse(text)) if "nondetermin" in p], [])

    def test_an_operator_outside_op_atoms_is_reported_not_crashed(self):
        # Not reachable through `parse` -- `_guard_field` (declaration.py)
        # validates `op` against `OP_ATOMS` before a `Guard` is ever built.
        # But a hand-built `Machine` is a first-class caller of
        # `check_machine` too (cycle B's engine constructs exactly this),
        # and this determinism check used to index `OP_ATOMS[op]` on the
        # assumption `parse` had already guaranteed it, crashing with a
        # raw `KeyError` on a `Guard` carrying an operator `parse` would
        # never have let through. An operator this check cannot relate to
        # anything must be reported, not silently treated as disjoint
        # from every other guard in the group -- the safe direction.
        m = Machine(
            "bogus-op-test", "v1", "x",
            {"role": "party"}, {"step1"}, None,
            "start",
            {
                "start": State("start"),
                "middleA": State("middleA", terminal=True, accepting=True),
                "middleB": State("middleB", terminal=True, accepting=True),
            },
            [
                Transition("start", "step1", "role", "middleA", signal=True,
                           guard=Guard("f", "gt", "g")),
                Transition("start", "step1", "role", "middleB", signal=True,
                           guard=Guard("f", "bogus", "g")),
            ],
            fields={"f": Field("f", "int")},
        )
        problems = check_machine(m)
        self.assertTrue(any("nondetermin" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
