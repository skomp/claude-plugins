import unittest
import machines.machine as machine_module
from machines.declaration import parse
from machines.machine import (Machine, State, Transition, check_machine,
                               _MAX_PREFIX_LENGTH)
from tests.test_declaration import VALID  # the known-good declaration
from tests.test_guards import GUARDED  # the known-good guarded declaration

def mutate(old, new):
    # Assert the splice landed. A `str.replace` whose `old` no longer
    # occurs in VALID returns VALID unchanged, so the test would go on
    # checking the known-good machine and pass while testing nothing --
    # which is exactly what happened to two of these when VALID's
    # `initial` changed.
    assert old in VALID, "mutate(%r, ...) matched nothing in VALID" % old
    return parse(VALID.replace(old, new))


def _linear_machine(cap):
    """start -(signal)-> middle -(signal)-> done, and only `done` accepts.

    Two signalling transitions to the one place a run may legitimately
    stop, so the shortest signalling distance to an accepting state is
    exactly 2 and the cap check has a boundary to be right or wrong about.
    """
    return Machine(
        "linear-test", "v1", "x",
        {"role": "party"}, {"step1", "step2"}, cap,
        "start",
        {
            "start": State("start"),
            "middle": State("middle"),
            "done": State("done", terminal=True, accepting=True),
        },
        [
            Transition("start", "step1", "role", "middle", signal=True),
            Transition("middle", "step2", "role", "done", signal=True),
        ],
    )


def _phase2_machine(limit):
    """`A, A, B` at `limit`, per role -- four states, two roles, one
    signalling edge per entry by that role: `s0` needs role `a` to fire
    twice (`s0` -> `s1` -> `s2`) before role `b` fires once (`s2` -> `s3`).

    This is the shape that actually exercises phase 2: an alternating
    chain spreads its signalling transitions evenly across roles, which
    is precisely what makes a per-role cap *satisfiable*, so it would
    prove nothing about the search. Here role `a` alone exceeds `limit`
    on the only route out of `s0`, so phase 1 (the free per-channel
    clearance) cannot clear `s0` -- its channel-scope distance is 3,
    `limit` is 1 -- and phase 2 must actually search to find that no
    route keeps role `a`'s own count at or under `limit` either.

    Product for the `_MAX_CAP_SEARCH` guard: `len(states) * (limit + 1) **
    len(roles)` = `4 * (limit + 1) ** 2`; at `limit=1` that is `4 * 4 =
    16`, comfortably searchable, and comfortably tripped by patching the
    guard down in a test.
    """
    return Machine(
        "phase2-test", "v1", "x",
        {"a": "party", "b": "party"}, {"step1", "step2"}, limit,
        "s0",
        {
            "s0": State("s0", holder="a"),
            "s1": State("s1", holder="a"),
            "s2": State("s2", holder="b"),
            "s3": State("s3", terminal=True, accepting=True),
        },
        [
            Transition("s0", "step1", "a", "s1", signal=True),
            Transition("s1", "step1", "a", "s2", signal=True),
            Transition("s2", "step2", "b", "s3", signal=True),
        ],
        cap_scope="role",
    )


class TestCheckMachine(unittest.TestCase):
    def test_the_known_good_machine_has_no_problems(self):
        self.assertEqual(check_machine(parse(VALID)), [])

    def test_initial_must_name_a_declared_state(self):
        m = mutate("initial: unopened", "initial: nowhere")
        self.assertTrue(any("nowhere" in p for p in check_machine(m)))

    def test_transition_to_an_undeclared_state_is_reported(self):
        m = mutate("to: awaiting-answer, signal: true }",
                   "to: nowhere, signal: true }")
        self.assertTrue(any("nowhere" in p for p in check_machine(m)))

    def test_transition_from_an_undeclared_state_is_reported(self):
        m = mutate("from: awaiting-triage, on: question",
                   "from: nowhere, on: question")
        self.assertTrue(any("nowhere" in p for p in check_machine(m)))

    def test_transition_on_an_undeclared_kind_is_reported(self):
        m = mutate("on: question", "on: shouting")
        self.assertTrue(any("shouting" in p for p in check_machine(m)))

    def test_transition_by_an_undeclared_role_is_reported(self):
        m = mutate("by: responder, to: awaiting-answer",
                   "by: bystander, to: awaiting-answer")
        self.assertTrue(any("bystander" in p for p in check_machine(m)))

    def test_a_state_with_an_undeclared_holder_is_reported(self):
        m = mutate("holder: responder", "holder: bystander")
        self.assertTrue(any("bystander" in p for p in check_machine(m)))

    def test_a_terminal_state_with_an_outgoing_transition_is_reported(self):
        # Give the terminal state `concluded` an exit back to a state that
        # already exists. No new state, no YAML indentation splice.
        m = parse(VALID)
        m.transitions.append(type(m.transitions[0])(
            "concluded", "question", "responder", "awaiting-triage"))
        self.assertTrue(any("concluded" in p for p in check_machine(m)))

    def test_an_unreachable_state_is_reported(self):
        m = parse(VALID)
        m.states["orphan"] = type(m.states["concluded"])(
            "orphan", terminal=True, accepting=True)
        self.assertTrue(any("orphan" in p for p in check_machine(m)))

    def test_an_effect_outside_the_vocabulary_is_reported(self):
        m = mutate('"label.add:session-relay:stalled"', '"run:curl example.com"')
        self.assertTrue(any("run:curl" in p for p in check_machine(m)))

    def test_each_permitted_effect_form_is_accepted(self):
        for effect in ("escalate", "label.add:anything", "label.remove:anything"):
            m = mutate('"escalate"', '"%s"' % effect)
            self.assertEqual(check_machine(m), [], effect)

    def test_a_label_effect_with_an_empty_name_is_reported(self):
        for effect in ("label.add:", "label.remove:"):
            m = mutate('"escalate"', '"%s"' % effect)
            self.assertTrue(
                any(repr(effect) in p for p in check_machine(m)), effect)

    def test_an_undeclared_initial_does_not_cascade_into_reachability_noise(self):
        # A typo in `initial` should not amplify into one "not reachable"
        # problem per declared state plus a spurious "cannot reach a
        # terminal state" -- only check 1's message should appear.
        m = mutate("initial: unopened", "initial: nowhere")
        problems = check_machine(m)
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(any("nowhere" in p for p in problems))

    def test_a_prefix_that_will_not_compile_is_reported_by_check_machine(self):
        m = _linear_machine(cap=2)
        m.prefix = "a*"          # nullable: claims every message
        problems = check_machine(m)
        self.assertTrue(any("prefix" in p for p in problems), problems)

    def test_a_compiling_prefix_adds_no_problem(self):
        self.assertEqual(check_machine(_linear_machine(cap=2)), [])

    def test_a_prefix_over_the_length_limit_is_reported_by_check_machine(self):
        # `declaration.parse` rejects this before a Machine ever exists
        # (see declaration.py's `_require_prefix_length`), so this only
        # exercises a hand-built Machine -- exactly the case check_machine
        # is now the sole gate for.
        m = _linear_machine(cap=2)
        m.prefix = "a" * (_MAX_PREFIX_LENGTH + 1)
        problems = check_machine(m)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("prefix", problems[0])

    def test_a_prefix_at_the_length_limit_adds_no_problem(self):
        m = _linear_machine(cap=2)
        m.prefix = "a" * _MAX_PREFIX_LENGTH
        self.assertEqual(check_machine(m), [])


class TestChecksNoTaskOwned(unittest.TestCase):
    """Four properties the schema documents, the design says are checked at
    install, and nothing checked: every one of these machines returned `[]`
    from `check_machine`.

    A declared, documented, inert field reads as checked to every publisher
    who writes one. That is the failure this whole framework exists to
    answer, and it had appeared inside the framework: `cap` was parsed,
    validated as a positive integer, documented as "what makes termination
    checkable at all", and then compared to nothing.
    """

    def test_two_transitions_with_one_trigger_and_two_targets_are_reported(self):
        # Same (from, on, by), different `to`. The engine is specified as a
        # fold over the trace, and a fold has exactly one result per step,
        # so this machine cannot be run at all -- while every other check
        # passes on it.
        m = parse(VALID)
        m.transitions.append(type(m.transitions[0])(
            "awaiting-triage", "question", "responder", "stalled"))
        problems = check_machine(m)
        self.assertTrue(any("nondeterministic" in p for p in problems), problems)
        self.assertTrue(any("'awaiting-triage'" in p and "'question'" in p
                            for p in problems), problems)

    def test_two_transitions_with_one_trigger_and_one_target_are_not_reported(self):
        # A duplicate transition is redundant, not ambiguous: the fold
        # still has one result. Only a *divergent* target is a problem.
        m = parse(VALID)
        m.transitions.append(type(m.transitions[0])(
            "awaiting-triage", "question", "responder", "awaiting-answer"))
        self.assertEqual(
            [p for p in check_machine(m) if "nondeterministic" in p], [])

    def test_a_holder_contradicting_every_outgoing_by_is_reported(self):
        # `holder` and `by` both answer "who acts next". Declared twice,
        # never reconciled: this state says the initiator holds it and
        # that only the responder can move out of it.
        m = parse(VALID)
        m.states["awaiting-triage"].holder = "initiator"
        problems = check_machine(m)
        self.assertTrue(any("awaiting-triage" in p and "holder" in p
                            for p in problems), problems)

    def test_a_terminal_state_holder_is_not_required_to_agree(self):
        # Nobody acts next in a terminal state, so there is nothing for a
        # `holder` there to contradict.
        m = parse(VALID)
        m.states["concluded"].holder = "initiator"
        self.assertEqual(check_machine(m), [])

    def test_a_cap_smaller_than_the_shortest_run_is_reported(self):
        # start -> middle -> done is two signalling transitions to the only
        # accepting state, so cap 1 makes settling and staying under the cap
        # mutually exclusive. `m.cap` was read by nothing before this check.
        #
        # This used to be `mutate("cap: 10", "cap: 1")` against VALID, and
        # it cannot be any more: `unopened` is now accepting, and it is also
        # `initial`, so VALID's shortest signalling run to an accepting
        # state is zero transitions long and *every* positive cap satisfies
        # it. That is the correct answer under the accepting-state model --
        # a session-relay run may legitimately stop before filing anything,
        # having emitted nothing -- but it means VALID no longer exercises
        # this check at all, so the check needs a machine of its own.
        m = _linear_machine(cap=1)
        problems = check_machine(m)
        self.assertTrue(any("cap 1" in p for p in problems), problems)

    def test_a_cap_exactly_equal_to_the_shortest_run_is_not_reported(self):
        # The boundary, in the direction that matters: a cap of 2 permits
        # the two-transition run, so it must not be reported. An off-by-one
        # here would reject machines that are perfectly runnable.
        self.assertEqual(check_machine(_linear_machine(cap=2)), [])

    def test_an_accepting_initial_state_no_longer_hides_a_cap_that_is_too_small(self):
        # This is the whole point of the stronger check. session-relay's
        # `unopened` is initial AND accepting, so the old check measured zero
        # from it and no positive cap could ever be reported. The new check
        # asks the question at every state where something is owed.
        m = mutate("cap: 10", "cap: 1")
        problems = [p for p in check_machine(m) if "cap" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("awaiting-answer", problems[0])

    def test_the_real_session_relay_cap_is_still_satisfied(self):
        self.assertEqual([p for p in check_machine(parse(VALID)) if "cap" in p], [])

    def test_local_moves_on_the_shortest_run_do_not_count_against_the_cap(self):
        # The re-reviewer's own machine: two purely-local moves
        # (`signal: false`) followed by one signalling move, and cap 1.
        # `cap` bounds outbound *messages*, and a local move emits none --
        # so this run costs 1, not 3, and cap 1 must accept it. Counting
        # every transition (the pre-fix behaviour) wrongly rejected this
        # exact shape.
        m = Machine(
            "local-moves-test", "v1", "x",
            {"role": "party"}, {"step1", "step2", "step3"}, 1,
            "start",
            {
                "start": State("start"),
                "middle": State("middle"),
                "late": State("late"),
                "done": State("done", terminal=True, accepting=True),
            },
            [
                Transition("start", "step1", "role", "middle", signal=False),
                Transition("middle", "step2", "role", "late", signal=False),
                Transition("late", "step3", "role", "done", signal=True),
            ],
        )
        self.assertEqual(check_machine(m), [])

    def test_a_cap_exceeded_by_signalling_transitions_alone_is_reported(self):
        # Two consecutive `signal: true` transitions and nothing else on
        # the only run to a terminal state, cap 1. The direction that
        # matters most to get right: under-counting here would silently
        # accept a machine that really does exceed its cap.
        m = Machine(
            "signal-only-test", "v1", "x",
            {"role": "party"}, {"step1", "step2"}, 1,
            "start",
            {
                "start": State("start"),
                "middle": State("middle"),
                "done": State("done", terminal=True, accepting=True),
            },
            [
                Transition("start", "step1", "role", "middle", signal=True),
                Transition("middle", "step2", "role", "done", signal=True),
            ],
        )
        problems = check_machine(m)
        cap_problems = [p for p in problems if "cap" in p]
        self.assertEqual(len(cap_problems), 1, problems)
        self.assertIn("2 signalling transitions", cap_problems[0])

    def test_a_declared_kind_no_transition_fires_on_is_reported(self):
        m = mutate("kinds: [triage, question, answer, conclusion, stalemate]",
                   "kinds: [triage, question, answer, conclusion, stalemate, shouting]")
        problems = check_machine(m)
        self.assertTrue(any("'shouting'" in p for p in problems), problems)


class TestAcceptingStates(unittest.TestCase):
    """Accepting is not terminal, and the checks that tell them apart.

    Cycle A shipped a schema that required `cap`, required at least one
    *terminal* state, and required every state to reach one -- which bakes
    "a protocol terminates" into the framework as a law. It is not one. It
    is a property of some protocols, and requiring it forces an author with
    a continuous protocol to declare a bound they do not mean, which is the
    exact failure this framework exists to answer.

    **Accepting** means nothing further is *required*: it is fine for the
    conversation to stop here. **Terminal** means nothing further is
    *possible*. The two are independent, and all four combinations are
    legal:

    - accepting and terminal -- `concluded`. Done, and nothing was left owed.
    - accepting, not terminal -- a responder sitting idle, willing to answer
      another question but owing nobody anything. The gossip shape.
    - neither -- a session that has just sent a message and is waiting for
      the reply. Something is owed and the conversation can continue.
    - **terminal and not accepting** -- an error state. The conversation
      ended while something was still owed, *and that is the point of
      reaching it*: an abort, a protocol violation, a peer that went away.
      The machine stops, the effects notify the peers, and the fact that
      the conversation was unfinished is exactly what is being reported.

    That fourth row is the one this class exists to protect. An earlier
    draft of these checks required every terminal state to be accepting,
    which would have forbidden the most useful error state a protocol can
    have.
    """

    def test_a_machine_with_no_accepting_state_is_reported(self):
        # Assert the *specific* message, not merely the word "accepting".
        # The predecessor of this test (against `terminal`) was shown to
        # pass with the check under test deleted outright, because the
        # per-state reachability messages contain the same word. A test a
        # deleted check still satisfies is not testing that check.
        m = parse(VALID)
        for s in m.states.values():
            s.accepting = False
        problems = check_machine(m)
        self.assertTrue(any("no state is accepting" in p for p in problems))
        # And exactly that, once. Every state can still reach a terminal
        # state, so the reachability check has nothing to say -- the
        # cascade its `terminal`-era predecessor produced (one message per
        # state on top of the real finding) does not happen here.
        self.assertEqual(len(problems), 1, problems)

    def test_a_branch_whose_every_future_ends_badly_is_deliberately_not_reported(self):
        # `doomed` is non-accepting and its only future is `aborted`, which
        # is terminal and non-accepting. Entering `doomed` commits the run
        # to ending with something still owed.
        #
        # That is legal, on purpose, and this test pins the decision rather
        # than the absence of a thought. The checker cannot tell a bug from
        # a correctly-modelled doomed branch -- "once the versions are
        # incompatible, every route aborts" is a true thing to declare --
        # and there is no field with which an author could say "yes, I mean
        # it". An unsuppressible complaint about a valid machine is worse
        # than a missing one. Recorded as an open question in the design
        # spec, not decided here.
        m = Machine(
            "doomed-branch", "v1", "x",
            {"role": "party"}, {"fork", "fail"}, None,
            "idle",
            {
                "idle": State("idle", holder="role", accepting=True),
                "doomed": State("doomed", holder="role"),
                "aborted": State("aborted", terminal=True),
            },
            [
                Transition("idle", "fork", "role", "doomed", signal=True),
                Transition("doomed", "fail", "role", "aborted", signal=True,
                           effects=["escalate"]),
            ],
        )
        self.assertEqual(check_machine(m), [])

    def test_a_state_owed_something_with_no_way_to_stop_at_all_is_reported(self):
        # Remove both exits from awaiting-triage, leaving awaiting-triage
        # and awaiting-answer trading messages forever with no route to
        # anywhere a run may stop -- not to an accepting state, and not to
        # a terminal one either. Being owed something forever with no exit
        # is the property this check protects.
        m = parse(VALID)
        m.transitions = [t for t in m.transitions
                         if t.on not in ("conclusion", "stalemate")]
        problems = check_machine(m)
        self.assertTrue(
            any("awaiting-triage" in p and "cannot reach a state where a run "
                "may stop" in p for p in problems), problems)
        self.assertTrue(
            any("awaiting-answer" in p and "cannot reach a state where a run "
                "may stop" in p for p in problems), problems)

    def test_an_accepting_state_needs_no_path_to_anywhere(self):
        # The other direction of the same check: an accepting state is
        # already somewhere a run may stop, so it owes no path onward. A
        # check that flooded backwards and then complained about every
        # state outside the flood would report the seeds themselves.
        m = parse(VALID)
        self.assertEqual(
            [p for p in check_machine(m) if "may stop" in p], [])

    def test_a_terminal_state_that_is_not_accepting_is_legal(self):
        # The error state. `stalled` is terminal and not accepting: the
        # thread stops with the initiator's question unanswered, the label
        # is swapped and a human is escalated to. Something is still owed
        # -- by a person, outside the machine -- and saying so is the whole
        # purpose of the state.
        #
        # This is asserted against the shipped fixture rather than a
        # hand-built machine because it is the fixture's own shape, and
        # because a check requiring terminal states to be accepting would
        # reject `session-relay` itself.
        m = parse(VALID)
        self.assertTrue(m.states["stalled"].terminal)
        self.assertFalse(m.states["stalled"].accepting)
        self.assertEqual(check_machine(m), [])

    def test_a_terminal_non_accepting_state_is_not_asked_to_reach_anything(self):
        # Directly, on a machine that is nothing but the abort: a terminal
        # non-accepting state can reach nothing at all, by definition, so
        # a reachability check that did not exempt it would report every
        # error state in every protocol as a defect.
        m = Machine(
            "abort-test", "v1", "x",
            {"role": "party"}, {"go", "give-up"}, None,
            "idle",
            {
                "idle": State("idle", holder="role", accepting=True),
                "aborted": State("aborted", terminal=True),
            },
            [
                Transition("idle", "go", "role", "idle", signal=True),
                Transition("idle", "give-up", "role", "aborted", signal=True,
                           effects=["escalate"]),
            ],
        )
        self.assertEqual(check_machine(m), [])

    def test_a_machine_with_no_cap_at_all_passes_every_check(self):
        # The case this change exists to permit, pinned so it cannot be
        # taken away again by accident: a protocol that declares no bound.
        # `cap` is absent, not zero and not a sentinel, and nothing here
        # reports it.
        m = Machine(
            "uncapped", "v1", "x",
            {"role": "party"}, {"ping"}, None,
            "idle",
            {"idle": State("idle", holder="role", accepting=True)},
            [Transition("idle", "ping", "role", "idle", signal=True)],
        )
        self.assertEqual(check_machine(m), [])

    def test_a_machine_that_is_entirely_accepting_and_never_terminates_passes(self):
        # The gossip shape. Every state is accepting: at any moment it is
        # fine for the conversation to stop, and it is equally fine for
        # another message to arrive. No state is terminal, because nothing
        # ever makes a further message impossible. Cycle A rejected this
        # machine outright ("no state is terminal; the machine cannot
        # terminate") even though there is nothing wrong with it.
        m = Machine(
            "gossip", "v1", "x",
            {"peer": "session"}, {"rumour", "ack"}, None,
            "idle",
            {
                "idle": State("idle", holder="peer", accepting=True),
                "informed": State("informed", holder="peer", accepting=True),
            },
            [
                Transition("idle", "rumour", "peer", "informed", signal=True),
                Transition("informed", "rumour", "peer", "informed", signal=True),
                Transition("informed", "ack", "peer", "idle", signal=True),
            ],
        )
        problems = check_machine(m)
        self.assertEqual(problems, [])
        self.assertEqual([s for s in m.states.values() if s.terminal], [])

    def test_a_cap_too_small_for_the_shortest_run_to_an_accepting_state_is_reported(self):
        # The cap check re-targeted: the goal set is the accepting states,
        # not the terminal ones. Here `done` is accepting and *not*
        # terminal -- it has an outgoing transition -- so a check still
        # measuring to terminal states would find no goal at all and report
        # nothing, which is the failure this test exists to catch.
        m = Machine(
            "recap", "v1", "x",
            {"role": "party"}, {"a", "b", "c"}, 1,
            "start",
            {
                "start": State("start", holder="role"),
                "middle": State("middle", holder="role"),
                "done": State("done", holder="role", accepting=True),
            },
            [
                Transition("start", "a", "role", "middle", signal=True),
                Transition("middle", "b", "role", "done", signal=True),
                Transition("done", "c", "role", "start", signal=True),
            ],
        )
        problems = check_machine(m)
        cap_problems = [p for p in problems if "cap" in p]
        self.assertEqual(len(cap_problems), 1, problems)
        self.assertIn("2 signalling transitions", cap_problems[0])
        self.assertIn("accepting state", cap_problems[0])

    def test_local_moves_are_still_free_on_the_way_to_an_accepting_state(self):
        # Re-targeting the goal set must not have disturbed the 0-1 BFS
        # weighting underneath it: a `signal: false` edge still costs
        # nothing, so this three-transition run costs 1 and cap 1 accepts
        # it. Asserted against an accepting, non-terminal goal, which the
        # pre-change check could not have reached.
        m = Machine(
            "free-moves", "v1", "x",
            {"role": "party"}, {"a", "b", "c", "d"}, 1,
            "start",
            {
                "start": State("start", holder="role"),
                "middle": State("middle", holder="role"),
                "late": State("late", holder="role"),
                "done": State("done", holder="role", accepting=True),
            },
            [
                Transition("start", "a", "role", "middle", signal=False),
                Transition("middle", "b", "role", "late", signal=False),
                Transition("late", "c", "role", "done", signal=True),
                Transition("done", "d", "role", "start", signal=True),
            ],
        )
        self.assertEqual(check_machine(m), [])


class TestCapSubjects(unittest.TestCase):
    """The stronger cap check: measured from every state where something
    is owed, not only from `initial`. The shipped check
    measured only from `initial`, so a machine whose initial state is
    accepting -- session-relay's `unopened` -- always measured a distance
    of zero, and no positive cap could ever be reported. `session-relay`
    has exactly that shape, so the framework's only real declaration
    exercised the old check not at all.
    """

    def test_a_cap_is_measured_from_every_state_where_something_is_owed(self):
        # `start` is initial and accepting, so the old check -- which only
        # ever measured from `initial` -- would report nothing at any cap.
        # The new check asks the question at every subject: `near`, two
        # signalling transitions from the nearest accepting state, is one
        # such subject; `far`, one transition away, is not.
        m = Machine(
            "every-subject-test", "v1", "x",
            {"role": "party"}, {"x", "y", "z"}, 1,
            "start",
            {
                "start": State("start", holder="role", accepting=True),
                "near": State("near", holder="role"),
                "far": State("far", holder="role"),
                "done": State("done", holder="role", accepting=True),
            },
            [
                Transition("start", "x", "role", "near", signal=True),
                Transition("near", "y", "role", "far", signal=True),
                Transition("far", "z", "role", "done", signal=True),
            ],
        )
        problems = [p for p in check_machine(m) if "cap" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("near", problems[0])

    def test_an_accepting_state_is_not_a_subject(self):
        # Every state here is accepting, so nothing is ever owed anywhere.
        # Cap 0 -- a value no non-accepting subject could ever satisfy --
        # must still be satisfied everywhere, because there is no subject:
        # an accepting state's own distance to the goal set (itself) is
        # always zero, and it is never asked the question at all.
        m = Machine(
            "accepting-not-subject-test", "v1", "x",
            {"peer": "session"}, {"rumour"}, 0,
            "idle",
            {
                "idle": State("idle", holder="peer", accepting=True),
                "informed": State("informed", holder="peer", accepting=True),
            },
            [
                Transition("idle", "rumour", "peer", "informed", signal=True),
                Transition("informed", "rumour", "peer", "idle", signal=True),
            ],
        )
        self.assertEqual([p for p in check_machine(m) if "cap" in p], [])

    def test_a_terminal_non_accepting_state_is_not_a_subject(self):
        # `aborted` is terminal and not accepting: something was owed and
        # the run stopped anyway. Cap 0 must still report nothing, because
        # a terminal non-accepting state is never asked the question --
        # not because asking it would be wrong (it can reach no accepting
        # state at all, so the no-goal-reachable case below would clear it
        # anyway), but because a subject this check can name is exactly a
        # state the answer is genuinely open for.
        m = Machine(
            "abort-not-subject-test", "v1", "x",
            {"role": "party"}, {"go", "give-up"}, 0,
            "idle",
            {
                "idle": State("idle", holder="role", accepting=True),
                "aborted": State("aborted", terminal=True),
            },
            [
                Transition("idle", "go", "role", "idle", signal=True),
                Transition("idle", "give-up", "role", "aborted", signal=True,
                           effects=["escalate"]),
            ],
        )
        self.assertEqual([p for p in check_machine(m) if "cap" in p], [])

    def test_a_state_from_which_no_accepting_state_is_reachable_reports_no_cap_problem(self):
        # The doomed branch. Spec section 9 refused to report it through
        # the reachability check; the cap check must not report it through
        # the back door either. `doomed` IS a subject -- not accepting,
        # not terminal -- but its only future is `aborted`, terminal and
        # not accepting, so no accepting state is reachable from it at
        # all.
        m = Machine(
            "doomed-branch-cap-test", "v1", "x",
            {"role": "party"}, {"fork", "fail"}, 1,
            "idle",
            {
                "idle": State("idle", holder="role", accepting=True),
                "doomed": State("doomed", holder="role"),
                "aborted": State("aborted", terminal=True),
            },
            [
                Transition("idle", "fork", "role", "doomed", signal=True),
                Transition("doomed", "fail", "role", "aborted", signal=True,
                           effects=["escalate"]),
            ],
        )
        self.assertEqual(check_machine(m), [])

    def test_a_terminal_non_accepting_state_does_not_count_as_a_cap_goal(self):
        # Pins the goal set: the accepting states, and only the accepting
        # states -- not `accepting | terminal`. `start` has a cheap (one
        # signalling transition) route to `aborted`, terminal and not
        # accepting; if the goal set were widened to include terminal
        # states, that route would satisfy cap 1 and this test would go
        # quiet. The only route from `start` to an ACCEPTING state
        # (`start` -> `mid` -> `done`) costs 2, over cap 1. Measured: with
        # the goal set widened to `{done, aborted}`, `start`'s distance
        # drops from 2 to 1 and the finding below disappears entirely --
        # confirmed directly against `_signal_distances` before writing
        # this test (see the fix-round report).
        m = Machine(
            "goal-set-test", "v1", "x",
            {"role": "party"}, {"a", "b", "c"}, 1,
            "start",
            {
                "start": State("start", holder="role"),
                "mid": State("mid", holder="role"),
                "done": State("done", holder="role", accepting=True),
                "aborted": State("aborted", terminal=True),
            },
            [
                Transition("start", "a", "role", "aborted", signal=True,
                           effects=["escalate"]),
                Transition("start", "b", "role", "mid", signal=True),
                Transition("mid", "c", "role", "done", signal=True),
            ],
        )
        problems = [p for p in check_machine(m) if "cap" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("start", problems[0])

    def test_a_per_role_cap_is_satisfied_where_a_per_channel_cap_of_the_same_size_is_not(self):
        # Measured on session-relay at limit 1: per channel reports
        # `awaiting-answer` at 2; per role reports nothing, because the two
        # transitions on that run (`answer` by initiator, `conclusion` by
        # responder) are sent by different roles.
        channel_m = mutate("cap: 10", "cap: 1")
        role_m = mutate("cap: 10", "cap: { limit: 1, per: role }")
        channel_problems = [p for p in check_machine(channel_m) if "cap" in p]
        role_problems = [p for p in check_machine(role_m) if "cap" in p]
        self.assertEqual(len(channel_problems), 1, channel_problems)
        self.assertEqual(role_problems, [])

    def test_an_undeclared_by_on_a_per_role_search_edge_does_not_crash_the_checker(self):
        # `check_machine` must return every problem and never raise, on
        # every input -- including this one. `role_index` is built from
        # `m.roles`, but a transition's `by` is not cross-referenced
        # against `m.roles` anywhere before phase 2 walks the search
        # graph by `by`; a typo'd `by` on the one edge phase 2 must
        # actually traverse (session-relay's `answer`, from the subject
        # `awaiting-answer`, which phase 1 cannot clear at limit 1) used
        # to raise `KeyError` out of `_role_cap_satisfiable` instead of
        # returning a problem list. The undeclared-role problem the
        # top-of-function loop already reports for this transition is
        # still present; there is simply no cap message piled on top of
        # it, the same as any other prerequisite-missing skip in this
        # function (R3, G3, G4).
        text = VALID.replace("cap: 10", "cap: { limit: 1, per: role }")
        assert text != VALID, "the cap splice matched nothing in VALID"
        old = "on: answer, by: initiator, to: awaiting-triage, signal: true }"
        assert old in text, "the by splice matched nothing"
        text = text.replace(
            old, "on: answer, by: initator, to: awaiting-triage, signal: true }")
        m = parse(text)
        problems = check_machine(m)  # must return, not raise
        self.assertTrue(any("initator" in p for p in problems), problems)
        self.assertEqual([p for p in problems if "cap" in p], [])

    def test_the_cap_check_is_still_skipped_entirely_when_cap_is_absent(self):
        # Not merely "an uncapped machine happens to pass": the machine
        # here is one that *would* fail the cap check for any cap under 2,
        # and with no cap declared there is nothing to compare against.
        m = _linear_machine(cap=None)
        self.assertEqual([p for p in check_machine(m) if "cap" in p], [])


class TestCapSearchBudget(unittest.TestCase):
    """`_MAX_CAP_SEARCH` guards phase 2 of the per-role cap search, whose
    state space is `len(m.states) * (limit + 1) ** len(m.roles)`. See the
    comment beside `_MAX_CAP_SEARCH` in machine.py for the measured
    numbers this pins.
    """

    def test_a_real_machine_is_far_inside_the_search_budget(self):
        # Pins the headroom claim so that lowering the constant fails
        # loudly rather than silently switching real machines onto the
        # silent path. Derived from the parsed fixtures, not transcribed
        # as literals: session-relay and paxos-acceptor are free to grow
        # a state without this test, `_MAX_CAP_SEARCH`'s comment and
        # SCHEMA.md's "605 / 245" going stale together with nothing to
        # catch it.
        session_relay = parse(VALID)
        paxos_acceptor = parse(GUARDED)
        self.assertLess(
            len(session_relay.states)
            * (session_relay.cap + 1) ** len(session_relay.roles),
            machine_module._MAX_CAP_SEARCH)
        self.assertLess(
            len(paxos_acceptor.states)
            * (paxos_acceptor.cap + 1) ** len(paxos_acceptor.roles),
            machine_module._MAX_CAP_SEARCH)

    def test_a_machine_past_the_search_budget_reports_nothing_and_returns(self):
        # The guard's silent path, actually exercised. Patch the constant
        # DOWN rather than building a machine with many roles: the suite
        # must keep running fast. Copies test_registry.py's pattern for
        # patching a module constant, including the `finally`.
        m = _phase2_machine(limit=1)
        original = machine_module._MAX_CAP_SEARCH
        try:
            machine_module._MAX_CAP_SEARCH = 1          # below any real product
            problems = check_machine(m)                 # must return, not hang
        finally:
            machine_module._MAX_CAP_SEARCH = original
        self.assertEqual([p for p in problems if "cap" in p], [], problems)

    def test_the_same_machine_is_reported_when_the_budget_allows_the_search(self):
        # Without this, the test above passes for a machine that was simply
        # satisfiable and proves nothing about the guard. THIS is what
        # makes the silence above attributable to the budget. Asserting
        # only "some cap problem exists" would also pass if the guard
        # reported the wrong subject, so name `s0` -- the only one of
        # `_phase2_machine`'s three subjects that is actually
        # unsatisfiable (see its docstring).
        m = _phase2_machine(limit=1)
        problems = [p for p in check_machine(m) if "cap" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("s0", problems[0])


if __name__ == "__main__":
    unittest.main()
