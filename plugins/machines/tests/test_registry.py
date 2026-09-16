import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from machines.cli import main
from machines.declaration import parse
from machines.registry import check_all
from tests.test_declaration import VALID


def named(name, prefix, version="v1"):
    text = VALID.replace("machine: session-relay", "machine: " + name)
    text = text.replace('prefix: "session-relay:v1 "', 'prefix: "%s"' % prefix)
    return parse(text.replace("version: v1", "version: " + version))


FIXTURES = Path(__file__).parent / "fixtures"


class TestCheckAll(unittest.TestCase):
    def test_no_machines_reports_zero_examined_and_no_collisions(self):
        report = check_all([])
        self.assertEqual(report.collisions, [])
        self.assertEqual(report.examined, 0)

    def test_two_disjoint_machines_do_not_collide(self):
        report = check_all([named("alpha", "alpha:v1 "), named("beta", "beta:v1 ")])
        self.assertEqual(report.collisions, [])
        self.assertEqual(report.examined, 2)

    def test_two_machines_claiming_one_prefix_collide(self):
        report = check_all([named("alpha", "shared:v1 "), named("beta", "shared:v1 ")])
        self.assertEqual(report.collisions, [("alpha", "beta")])

    def test_a_proper_prefix_collides(self):
        report = check_all([named("alpha", "shared:"), named("beta", "shared:v1 ")])
        self.assertEqual(report.collisions, [("alpha", "beta")])

    def test_two_versions_of_one_machine_are_not_a_collision(self):
        report = check_all([named("alpha", "alpha:v1 ", "v1"),
                            named("alpha", "alpha:v1 ", "v2")])
        self.assertEqual(report.collisions, [])

    def test_a_malformed_machine_is_reported_under_its_own_name(self):
        bad = named("alpha", "alpha:v1 ")
        bad.initial = "nowhere"
        report = check_all([bad, named("beta", "beta:v1 ")])
        self.assertIn("alpha", report.problems)
        self.assertNotIn("beta", report.problems)

    # --- gap found while preparing this task: a prefix that won't compile
    # (unparseable, or nullable -- see pattern.py's compile_pattern) must
    # not crash check_all. It is reported like any other problem, and the
    # machine that carries it is excluded from collision checking, since a
    # pattern that will not compile cannot be intersected with anything.

    def test_a_pattern_that_will_not_compile_is_reported_not_raised(self):
        # "x*" is nullable (matches the empty string), so compile_pattern
        # raises PatternError for it -- see pattern.py's module docstring
        # and compile_pattern's nullability check.
        bad = named("badpattern", "x*")
        report = check_all([bad, named("beta", "beta:v1 ")])
        self.assertIn("badpattern", report.problems)
        self.assertNotIn("beta", report.problems)
        self.assertEqual(report.collisions, [])

    def test_a_good_pair_either_side_of_a_bad_machine_still_collides(self):
        bad = named("badpattern", "x*")
        alpha = named("alpha", "shared:v1 ")
        beta = named("beta", "shared:v1 ")
        report = check_all([alpha, bad, beta])
        self.assertIn("badpattern", report.problems)
        self.assertEqual(report.collisions, [("alpha", "beta")])
        self.assertEqual(report.examined, 3)

    # --- gap found by the cycle-A reviewer: a prefix nested deep enough
    # in `(...)` groups used to reach `compile_pattern` and blow the stack
    # with an uncaught RecursionError, past the 400-character length guard
    # (which bounds a different route -- see declaration.py). pattern.py's
    # nesting-depth guard closes the ordinary case with a named
    # PatternError; the tests below check `check_all` reports it as a
    # normal problem either way, including via a raw RecursionError that
    # bypasses the parser's own guard (a stand-in for "whatever shape, if
    # any, we haven't thought of").

    def test_a_deeply_nested_prefix_is_reported_not_raised(self):
        deep = named("deepprefix", "(" * 199 + "a" + ")" * 199)
        report = check_all([deep, named("beta", "beta:v1 ")])
        self.assertIn("deepprefix", report.problems)
        self.assertNotIn("beta", report.problems)
        self.assertEqual(report.collisions, [])

    def test_a_moderately_nested_prefix_is_not_reported_as_a_problem(self):
        # The guard must not reject a legitimate pattern: 60 levels is
        # well under the 100-level limit.
        ok = named("okprefix", "(" * 60 + "a" + ")" * 60)
        report = check_all([ok])
        self.assertNotIn("okprefix", report.problems)

    def test_a_raw_recursion_error_is_still_reported_not_raised(self):
        # Exercises the RecursionError backstop directly (not the parser's
        # nesting-depth guard, which would normally catch this shape
        # first): if some other AST shape ever reaches a deep stack, the
        # backstop at the compile_pattern call site must still turn it
        # into a named problem, the same as PatternError does.
        import machines.pattern as pattern_module
        original_limit = pattern_module._MAX_GROUP_DEPTH
        pattern_module._MAX_GROUP_DEPTH = 10 ** 9
        try:
            deep = named("deepprefix", "(" * 199 + "a" + ")" * 199)
            report = check_all([deep, named("beta", "beta:v1 ")])
        finally:
            pattern_module._MAX_GROUP_DEPTH = original_limit
        self.assertIn("deepprefix", report.problems)
        self.assertIn("too deeply nested", report.problems["deepprefix"][0])
        self.assertNotIn("beta", report.problems)
        self.assertEqual(report.collisions, [])

    # --- gap found by the commit that moved prefix validation into
    # check_machine (machine.py's prefix_problem), so a bad prefix
    # must be reported exactly once, not once by check_machine and again
    # by check_all re-deriving the same verdict.

    def test_a_bad_prefix_is_reported_once_not_twice(self):
        bad = named("alpha", "alpha:v1 ")
        bad.prefix = "a*"
        report = check_all([bad, named("beta", "beta:v1 ")])
        self.assertEqual(
            len([p for p in report.problems["alpha"] if "prefix" in p]), 1,
            report.problems["alpha"])
        self.assertEqual(report.collisions, [])   # excluded from collision checking


class TestCli(unittest.TestCase):
    def test_no_paths_exits_2_and_says_so(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            code = main([])
        self.assertEqual(code, 2)

    def test_a_missing_path_exits_2(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            code = main(["/nonexistent/SKILL.md"])
        self.assertEqual(code, 2)

    def test_a_valid_fixture_exits_0_and_reports_the_count(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([str(FIXTURES / "valid-session-relay.md")])
        self.assertEqual(code, 0)
        self.assertIn("Examined 1 machine", out.getvalue())

    def test_zero_machines_examined_prints_the_count_not_a_bare_pass(self):
        # A directory that exists but holds no SKILL.md is zero machines
        # found, not a broken tool -- exit 0, and the count must still be
        # stated. What must *not* appear is "No collisions found": a
        # collision needs a pair, and with zero machines there was no pair
        # to examine, so the sentence would be a pass that checked nothing
        # worded like a pass that checked something -- exactly the
        # evidence-discipline failure this requirement exists to prevent.
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as empty_dir:
            with contextlib.redirect_stdout(out):
                code = main([empty_dir])
        self.assertEqual(code, 0)
        self.assertIn("Examined 0 machines", out.getvalue())
        self.assertNotIn("No collisions found", out.getvalue())

    def test_one_machine_examined_claims_no_collision_check(self):
        # Same reasoning one machine up: a single machine has no peer to
        # collide with, so the run examined no pair and must not say it
        # found no collisions.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([str(FIXTURES / "valid-session-relay.md")])
        self.assertEqual(code, 0)
        self.assertIn("Examined 1 machine", out.getvalue())
        self.assertNotIn("No collisions found", out.getvalue())

    def test_two_clean_machines_do_claim_no_collisions_found(self):
        # And the sentence must still appear when it was earned, or the
        # gate above would just be silence dressed up as discipline.
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            for name in ("alpha", "beta"):
                path = os.path.join(d, name + ".md")
                with open(path, "w") as f:
                    f.write(VALID.replace("machine: session-relay",
                                          "machine: " + name)
                                 .replace('prefix: "session-relay:v1 "',
                                          'prefix: "%s:v1 "' % name))
            with contextlib.redirect_stdout(out):
                code = main([os.path.join(d, "alpha.md"),
                             os.path.join(d, "beta.md")])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("Examined 2 machines", out.getvalue())
        self.assertIn("No collisions found", out.getvalue())

    def test_a_malformed_declaration_exits_1_not_2(self):
        # A file that fails to parse is a problem the checker found, not a
        # reason the tool itself could not run -- it must not share exit 2
        # with a missing path or missing PyYAML.
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            bad_path = os.path.join(d, "SKILL.md")
            with open(bad_path, "w") as f:
                f.write("no machine block here\n")
            with contextlib.redirect_stdout(out):
                code = main([bad_path])
        self.assertEqual(code, 1)

    # --- end to end, through the shipped CLI: the reviewer's reproduction
    # for the deeply-nested-prefix gap (see TestCheckAll above for the
    # same fixture exercised directly against check_all).

    def test_a_199_deep_prefix_exits_1_with_a_named_problem_not_a_traceback(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "SKILL.md")
            with open(path, "w") as f:
                f.write(VALID.replace(
                    'prefix: "session-relay:v1 "',
                    'prefix: "%s"' % ("(" * 199 + "a" + ")" * 199)))
            with contextlib.redirect_stdout(out):
                code = main([path])
        self.assertEqual(code, 1)
        self.assertIn("nesting", out.getvalue())

    def test_a_60_deep_prefix_exits_0(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "SKILL.md")
            with open(path, "w") as f:
                f.write(VALID.replace(
                    'prefix: "session-relay:v1 "',
                    'prefix: "%s"' % ("(" * 60 + "a" + ")" * 60)))
            with contextlib.redirect_stdout(out):
                code = main([path])
        self.assertEqual(code, 0, out.getvalue())

    # --- the cycle's worked guarded example, end to end through the
    # shipped CLI: the fixture-loading path, the collision check and the
    # CLI itself had not seen a guarded declaration until this task.

    def test_the_paxos_fixture_is_well_formed_end_to_end(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([str(FIXTURES / "valid-paxos-acceptor.md")])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("Examined 1 machine", out.getvalue())

    def test_the_two_fixtures_do_not_collide(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([str(FIXTURES / "valid-session-relay.md"),
                         str(FIXTURES / "valid-paxos-acceptor.md")])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("Examined 2 machines", out.getvalue())
        self.assertIn("No collisions found", out.getvalue())


if __name__ == "__main__":
    unittest.main()
