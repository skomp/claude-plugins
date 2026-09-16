"""The restricted prefix pattern language.

A machine's `prefix` (see SCHEMA.md) is not a literal string but a pattern in
a deliberately small language: literals, `.`, character classes, grouping,
alternation, and `*`/`+`/`?` repetition. Nothing else. In particular: no
backreferences, no lookaround, no `{n,m}` counted repetition, no named
groups, no shorthand classes. `^` and `$` are *not* anchors here -- this
grammar has none -- they are ordinary literal characters, same as any other
(see SCHEMA.md).

The restriction exists because the installer's central guarantee -- that no
two installed machines can claim the same message -- is decided by
intersecting two compiled automata (`product.py`). That only works if
every prefix pattern is a *regular* language. A backreference (`(a)\\1`)
or lookaround is not regular; a pattern containing one could be accepted
here, sail through every other check, and the guarantee would silently stop
holding for that one machine. Parse time is the only place this can be
caught, so it is caught here, loudly, by name, rather than surfacing later
as a wrong collision verdict.

This module knows nothing about protocols, machines, or messages -- it is a
standalone grammar-to-AST parser and a Thompson NFA compiler for what that
parser produces, tested as two separate things. Intersecting two of those
NFAs is `product.py`'s job.

Grammar::

    pattern := alt
    alt     := cat ('|' cat)*
    cat     := rep*
    rep     := atom ('*' | '+' | '?')?
    atom    := literal | '.' | class | '(' alt ')'
    class   := '[' '^'? item+ ']'
    item    := char '-' char | char
    literal := any char except | * + ? ( ) [ ] . \\  -- or '\\' followed by
               one of those

One deliberate departure from that grammar as written: the brief's prose
says plainly "no {n,m}" and requires `a{2,3}` to be rejected, but the
literal-exclusion list above does not name `{`. Taken fully literally, the
grammar would accept `{` as an ordinary character and parse `a{2,3}` as six
concatenated literals, which contradicts the required rejection test.

CORRECTION (fix round 1): the first version of this fix reserved `{`
wholesale -- rejecting every bare `{` and every `\\{` escape, with no way to
match a literal brace at all. That went wider than the defect: "no counted
repetition" is not "no brace character", and a JSON-shaped prefix like
`{"type":"force"}` is a plausible thing for a publisher to want to match.
`{` is rejected *only* when it opens something shaped like a genuine
counted repetition -- `\\d+(,\\d*)?\\}` immediately following it, i.e. `{2}`,
`{2,}`, `{2,3}` -- via a lookahead in `_Parser._parse_atom`, not by
reserving the character outright. A bare `{` that isn't followed by that
shape (`{oops}`, a lone `{`) is an ordinary literal, and `\\{`/`\\}` are
valid escapes to a literal brace (both are in `_METACHARACTERS`).

AST node types: `Lit`, `Cat`, `Alt`, `Star`, `Empty` -- five, not seven,
because the parser desugars `+` to `Cat(x, Star(x))` and `?` to
`Alt(x, Empty())` rather than inventing Plus/Opt node types. The NFA
compiler below therefore only ever has to handle Cat, Alt, and Star.
"""

import re

from .errors import DeclarationError

# The full Unicode codepoint span. '.' and a negated class are both defined
# relative to this.
_FULL_SPAN = (0, 0x10FFFF)

# Characters that are metacharacters in this grammar and therefore *not*
# available as a bare literal. '\' escapes any of these back to a literal.
# '{' and '}' are here so `\{`/`\}` always escape to a literal brace, even
# though a *bare* '{' is only rejected when it opens something shaped like
# a counted repetition -- see _COUNTED_REPETITION_RE and _parse_atom.
_METACHARACTERS = set("|*+?(){}[].\\")

# What a counted repetition looks like, immediately after '{': one or more
# digits, then an optional ',' and zero or more digits, then '}' -- {2},
# {2,}, {2,3}. Matched with .match(src, pos) so it's anchored at the '{'
# without needing to re-slice the string. A bare '{' that isn't followed by
# this shape is an ordinary literal character, not a syntax error -- see
# the CORRECTION note in the module docstring.
_COUNTED_REPETITION_RE = re.compile(r"\{\d+(,\d*)?\}")

# How many levels of `(...)` nesting `_parse_group` will follow before
# giving up and naming the problem, rather than letting Python's own call
# stack be the limit.
#
# `_parse_group` is the *only* recursive production in this grammar --
# `_parse_alt` and `_parse_cat` consume repeated `|`-branches and
# concatenated atoms in a `while` loop, not by recursing per element (see
# their bodies below), so a long chain of literals, `|` branches, or `*`/
# `+`/`?` suffixes never deepens the call stack on its own. Only `(`
# recursing back into `_parse_alt` does, and it does so on both sides of
# this module: here in the parser, and again in `_Compiler.compile`, which
# walks the resulting AST by the same kind of recursion. A prefix of
# `'(' * 199 + 'a' + ')' * 199` (199 levels, 399 characters -- under the
# 400-character length guard in declaration.py, which bounds a different
# failure; see that module) drives `_parse_group` to a `RecursionError`
# at depth 199; depth 198 still parses. 100 is comfortably under that
# measured failure point while being far beyond any real prefix, so a
# publisher gets a named `PatternError` here in the ordinary case. The
# `RecursionError` backstop in machine.py's `prefix_problem` exists for
# whatever shape (if any) reaches a deep stack some other way -- this
# guard is the nice error, not the guarantee.
_MAX_GROUP_DEPTH = 100


class PatternError(DeclarationError):
    """A prefix pattern violates the restricted grammar.

    Subclasses DeclarationError (see errors.py, which stays the one base
    module for declaration-time failures) rather than introducing a second
    exception hierarchy for what is, from a publisher's point of view, the
    same kind of problem: something they wrote in a bundle is rejected
    before install.
    """


# --- AST ---------------------------------------------------------------
#
# Plain classes (matching the style already used for Machine/State/
# Transition in machine.py), with value equality so tests -- and the
# compiler below -- can compare ASTs structurally instead of by identity.


class Node(object):
    def __eq__(self, other):
        return type(self) is type(other) and self._fields() == other._fields()

    # No explicit __ne__: Python 3's default already inverts __eq__.

    def __hash__(self):
        return hash((type(self), self._fields()))

    def _fields(self):
        raise NotImplementedError


class Lit(Node):
    """A single character drawn from a set of inclusive codepoint ranges."""

    def __init__(self, chars):
        """`chars` is a frozenset of (low, high) inclusive codepoint ranges."""
        self.chars = frozenset(chars)

    def _fields(self):
        return (self.chars,)

    def __repr__(self):
        return "Lit(%r)" % (sorted(self.chars),)


class Cat(Node):
    """`left` followed by `right`."""

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def _fields(self):
        return (self.left, self.right)

    def __repr__(self):
        return "Cat(%r, %r)" % (self.left, self.right)


class Alt(Node):
    """`left` or `right`."""

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def _fields(self):
        return (self.left, self.right)

    def __repr__(self):
        return "Alt(%r, %r)" % (self.left, self.right)


class Star(Node):
    """Zero or more repetitions of `node`."""

    def __init__(self, node):
        self.node = node

    def _fields(self):
        return (self.node,)

    def __repr__(self):
        return "Star(%r)" % (self.node,)


class Empty(Node):
    """Matches the empty string. Only ever produced by the parser's own
    `?` desugaring (Alt(x, Empty())) -- never by parsing zero atoms
    directly; see the module docstring and _Parser.parse_cat below for why
    that distinction matters.
    """

    def _fields(self):
        return ()

    def __repr__(self):
        return "Empty()"


# --- range helpers -------------------------------------------------------
#
# Kept separate from the parser and tested directly (TestComplementHelper /
# TestMergeRangesHelper in test_pattern.py): an off-by-one here is the
# defect most likely to survive into `product.py`, where it would
# silently produce a wrong collision verdict instead of a visible crash.


def _merge_ranges(ranges):
    """Sort `ranges` and coalesce overlapping or adjacent (low, high)
    inclusive codepoint ranges into the minimal equivalent list.

    Adjacency matters, not just overlap: (0, 5) and (6, 10) share no
    codepoint but cover a contiguous span, so they must still merge --
    otherwise a class built from adjacent items would carry a spurious
    internal gap.
    """
    if not ranges:
        return []
    ordered = sorted(ranges)
    merged = [ordered[0]]
    for lo, hi in ordered[1:]:
        mlo, mhi = merged[-1]
        if lo <= mhi + 1:
            merged[-1] = (mlo, max(mhi, hi))
        else:
            merged.append((lo, hi))
    return merged


def _complement(ranges, full=_FULL_SPAN):
    """The complement of `ranges` within `full`, as a frozenset of
    (low, high) inclusive ranges: everything in `full` not covered by
    `ranges`, computed by merging then walking the gaps between merged
    ranges (and before the first / after the last).
    """
    merged = _merge_ranges(list(ranges))
    lo_bound, hi_bound = full
    result = []
    cursor = lo_bound
    for lo, hi in merged:
        if lo > cursor:
            result.append((cursor, lo - 1))
        cursor = max(cursor, hi + 1)
    if cursor <= hi_bound:
        result.append((cursor, hi_bound))
    return frozenset(result)


# --- parser ----------------------------------------------------------------


def parse_pattern(src):
    """Parse `src` as a prefix pattern and return its AST (a Node).

    Raises PatternError if `src` does not conform to the grammar in this
    module's docstring.
    """
    return _Parser(src).parse()


class _Parser(object):
    """A recursive-descent parser over the grammar in the module docstring.
    One method per production; `pos` is the cursor into `src`.
    """

    def __init__(self, src):
        self.src = src
        self.pos = 0
        self._group_depth = 0  # see _MAX_GROUP_DEPTH and _parse_group below

    def parse(self):
        node = self._parse_alt()
        if self.pos != len(self.src):
            raise PatternError(
                "unexpected %r at position %d" % (self.src[self.pos], self.pos)
            )
        return node

    # -- helpers --

    def _peek(self):
        return self.src[self.pos] if self.pos < len(self.src) else None

    def _advance(self):
        ch = self.src[self.pos]
        self.pos += 1
        return ch

    # -- grammar productions --

    def _parse_alt(self):
        # alt := cat ('|' cat)*
        node = self._parse_cat()
        while self._peek() == "|":
            self._advance()
            node = Alt(node, self._parse_cat())
        return node

    def _parse_cat(self):
        # cat := rep*
        #
        # Decision 2: cat() may syntactically consume zero reps -- that is
        # what makes "a|" and "" parse at all under this grammar's raw
        # production rules. But a cat that matches the empty string means
        # the branch it belongs to (or, if it's the only branch, the whole
        # pattern) matches every message, colliding with every other
        # installed machine while every other check still passes. That is
        # the framework's central guarantee failing silently, so it is
        # rejected here, at the one point in the grammar where an empty
        # match can be produced *syntactically* -- with no NFA involved.
        #
        # This is deliberately narrower than full nullability: `a*` and
        # `a?` at top level are also nullable, but detecting that needs the
        # compiled automaton. compile_pattern below does that -- it raises
        # PatternError whenever the start state's epsilon-closure meets the
        # accept set. Do not extend this syntactic check to cover them.
        start = self.pos
        parts = []
        while True:
            ch = self._peek()
            if ch is None or ch in "|)":
                break
            parts.append(self._parse_rep())
        if not parts:
            raise PatternError(
                "empty alternation branch at position %d: a pattern (or "
                "branch) that matches the empty string would collide with "
                "every message" % start
            )
        node = parts[0]
        for part in parts[1:]:
            node = Cat(node, part)
        return node

    def _parse_rep(self):
        # rep := atom ('*' | '+' | '?')?
        node = self._parse_atom()
        ch = self._peek()
        if ch == "*":
            self._advance()
            return Star(node)
        if ch == "+":
            # Desugared here, not as its own node type -- see point 4 in
            # the module docstring.
            self._advance()
            return Cat(node, Star(node))
        if ch == "?":
            self._advance()
            return Alt(node, Empty())
        return node

    def _parse_atom(self):
        # atom := literal | '.' | class | '(' alt ')'
        ch = self._peek()
        if ch is None:
            raise PatternError("unexpected end of pattern at position %d" % self.pos)

        if ch == "(":
            return self._parse_group()
        if ch == ".":
            self._advance()
            return Lit(frozenset([_FULL_SPAN]))
        if ch == "[":
            return self._parse_class()
        if ch == "\\":
            return self._parse_escape()
        if ch == "{" and _COUNTED_REPETITION_RE.match(self.src, self.pos):
            # Only reject '{' when it actually opens {n}/{n,}/{n,m} -- see
            # the CORRECTION note in the module docstring. A '{' that
            # doesn't match this shape falls through to the plain-literal
            # case below.
            raise PatternError(
                "counted repetition '{n,m}' is not supported (at position "
                "%d)" % self.pos
            )
        if ch in "|*+?)]":
            raise PatternError(
                "unexpected metacharacter %r at position %d" % (ch, self.pos)
            )
        self._advance()
        return Lit(frozenset([(ord(ch), ord(ch))]))

    def _parse_group(self):
        start = self.pos
        self._advance()  # consume '('
        if self._peek() == "?":
            # CORRECTION (fix round 1): covers lookaround ((?=...),
            # (?!...), (?<=...), (?<!...)) and named/non-capturing groups
            # ((?P<name>...), (?<name>...), (?:...)) alike -- every one of
            # those starts with '(?'. The brief's decision 2 said to name
            # this "lookaround", but that's only true of some of them; the
            # message instead names what's true of the whole family: this
            # language has only plain groups.
            raise PatternError(
                "extended group syntax '(?...)' is not supported; this "
                "language has only plain groups (at position %d)" % start
            )
        # This is the one recursive step in the grammar (see
        # _MAX_GROUP_DEPTH above): every other production consumes
        # repeated elements in a loop. Count depth on the way in, checked
        # before recursing further, so the rejection fires at 101 levels
        # deep -- comfortably before Python's own call stack would --
        # rather than after.
        self._group_depth += 1
        if self._group_depth > _MAX_GROUP_DEPTH:
            raise PatternError(
                "nesting is %d levels deep; the limit is %d levels "
                "(group opened at position %d)"
                % (self._group_depth, _MAX_GROUP_DEPTH, start)
            )
        try:
            node = self._parse_alt()
        finally:
            self._group_depth -= 1
        if self._peek() != ")":
            raise PatternError("unclosed group starting at position %d" % start)
        self._advance()  # consume ')'
        return node

    def _parse_escape(self):
        start = self.pos
        self._advance()  # consume '\'
        ch = self._peek()
        if ch is None:
            raise PatternError(
                "dangling backslash at end of pattern (position %d)" % start
            )
        if ch.isdigit():
            raise PatternError(
                "backreferences are not supported (\\%s at position %d)"
                % (ch, start)
            )
        if ch in _METACHARACTERS:
            self._advance()
            return Lit(frozenset([(ord(ch), ord(ch))]))
        raise PatternError(
            "unsupported escape \\%s at position %d" % (ch, start)
        )

    def _parse_class(self):
        # class := '[' '^'? item+ ']'
        # item  := char '-' char | char
        start = self.pos
        self._advance()  # consume '['
        negate = False
        if self._peek() == "^":
            negate = True
            self._advance()

        ranges = []
        while True:
            ch = self._peek()
            if ch is None:
                raise PatternError(
                    "unclosed character class starting at position %d" % start
                )
            if ch == "]":
                break
            ranges.append(self._parse_class_item())

        if not ranges:
            raise PatternError("empty character class at position %d" % start)

        self._advance()  # consume ']'
        chars = frozenset(_merge_ranges(ranges))
        if negate:
            chars = _complement(chars)
        return Lit(chars)

    def _parse_class_item(self):
        # item := char '-' char | char
        lo = self._advance()
        has_range = (
            self._peek() == "-"
            and self.pos + 1 < len(self.src)
            and self.src[self.pos + 1] != "]"
        )
        if not has_range:
            return (ord(lo), ord(lo))
        self._advance()  # consume '-'
        hi = self._advance()
        if ord(hi) < ord(lo):
            raise PatternError(
                "invalid range %r-%r at position %d" % (lo, hi, self.pos)
            )
        return (ord(lo), ord(hi))


# --- NFA compiler ---------------------------------------------------------
#
# Thompson construction from the AST above into an NFA over Unicode
# codepoint ranges. The representation is a contract, not a private
# choice: `product.py` intersects two of these NFAs directly, reading
# `moves` and `epsilon` as plain dicts/lists/sets rather than through any
# method on this class.
#
# One thing the AST forces on this compiler: the parser desugars `x+` to
# Cat(x, Star(x)) and `x?` to Alt(x, Empty()) using the *same* node object
# in both positions of the Cat/Alt (see _parse_rep above). Node also
# defines value equality (__eq__/__hash__), so two structurally-identical
# but distinct subtrees compare equal too. Neither fact may be used to
# cache or reuse a compiled fragment: every *occurrence* of a node in the
# tree needs its own states, because Thompson construction wires a
# fragment's internal states to whatever comes immediately before and
# after it, and `x+`/`x?` need two independently-wired copies of `x`, not
# one fragment referenced twice. This compiler never memoises by node
# identity, by id(), or via a dict keyed on nodes -- it walks the tree
# and allocates fresh states on every visit, full stop.
#
# That is correct, and it is also why a ceiling is needed. Allocating fresh
# states per occurrence means nested repetition duplicates a subtree on
# every level: `x+` compiles both halves of Cat(x, Star(x)) independently,
# so wrapping a pattern in `+` roughly doubles its state count. Measured on
# this compiler: a 52-character pattern nesting `+` seventeen deep compiles
# to 524,286 states in 0.80s, and each further level doubles that again --
# twenty-two deep is around 8.4 million. No legitimate message prefix needs
# anything near this, and the honest answer to one that does is to say so
# by name rather than to allocate until the process dies. Restructuring `+`
# into its own node type would remove the duplication, but that is a sixth
# AST node for a later cycle's compiler to carry; the ceiling is the cheap
# fix and changes no contract.

# The state ceiling. This is not what bounds a literal prefix's length --
# recursion binds first, in the *compiler*, not the parser: a bare literal
# parses fine at any length (`_parse_cat`, above, is an iterative loop),
# but it builds a left-deep Cat tree one level per character, and
# `_Compiler._compile_cat` walks that tree by recursion, so a literal
# longer than 498 characters raises RecursionError during compilation
# before state count is ever in question. A plain literal therefore never
# reaches anywhere near 10,000 states -- the longest one that compiles at
# all costs under 1,000. (declaration.py's `_require_prefix_length`
# rejects a prefix past 400 characters by name, for exactly that reason,
# well before either limit is in play.)
#
# What this ceiling actually guards against is nested repetition: as the
# comment above measures, `x+` duplicates a subtree per occurrence, so
# state count roughly doubles per nesting level and reaches 10,000 in
# about a dozen levels of nesting -- far too shallow to hit a recursion
# limit in either the parser or the compiler on its own. This is the only
# way `_MAX_NFA_STATES` is ever reached.
_MAX_NFA_STATES = 10000


class NFA(object):
    """A Thompson-constructed nondeterministic finite automaton over
    Unicode codepoint ranges.

    Attributes (this shape is the contract `product.py` depends on):

    - `start`: int -- the id of the start state.
    - `accept`: Set[int] -- ids of accepting states. Thompson construction
      as done here always produces exactly one, but the type is a set so
      `product.py`'s intersection (which will generally have several)
      does not need a different shape.
    - `moves`: Dict[int, List[Tuple[FrozenSet[Tuple[int, int]], int]]] --
      for each state, the list of (charset, target) character moves out of
      it. `charset` is a frozenset of inclusive (low, high) codepoint
      ranges, the same representation `Lit.chars` already uses, so Task
      6's `ranges_intersect` can operate on it directly with no
      conversion.
    - `epsilon`: Dict[int, Set[int]] -- for each state, the set of states
      reachable by an epsilon (no-input) move.

    Every state id in [0, n) that this compiler allocated has an entry in
    both `moves` (possibly an empty list) and `epsilon` (possibly an empty
    set), so callers never need `.get(state, default)`.
    """

    def __init__(self, start, accept, moves, epsilon):
        self.start = start
        self.accept = accept
        self.moves = moves
        self.epsilon = epsilon

    def epsilon_closure(self, states):
        """The set of states reachable from `states` (an iterable of state
        ids) by zero or more epsilon moves, `states` itself included.
        """
        closure = set(states)
        stack = list(closure)
        while stack:
            state = stack.pop()
            for target in self.epsilon.get(state, ()):
                if target not in closure:
                    closure.add(target)
                    stack.append(target)
        return closure

    def accepts(self, text):
        """Whether this NFA matches `text` exactly -- the whole string,
        not a prefix.

        This exists only so the compiler can be tested against strings,
        where a wrong answer is obvious, rather than against another
        automaton, where it usually isn't. It is not part of the
        installer's collision check: a message prefix pattern `a` is meant
        to match any message that *starts with* something in L(a), i.e.
        the language L(a).Sigma* -- but that Sigma*-suffix semantics
        belongs to `product.py`, where the checker builds it once and
        intersects. Doing it here too would double-apply it (every pattern
        would effectively become L(a).Sigma*.Sigma*, which happens to be
        the same language, masking the bug) and, worse, would make this
        method answer a different question than the one `product.py`
        actually asks, so a passing `accepts` test here would say nothing
        about `patterns_collide` being correct. Whole-string matching is a
        strictly narrower question, which is exactly why it is useful as a
        test oracle.
        """
        current = self.epsilon_closure({self.start})
        for ch in text:
            cp = ord(ch)
            step = set()
            for state in current:
                for charset, target in self.moves.get(state, ()):
                    if _codepoint_in(cp, charset):
                        step.add(target)
            current = self.epsilon_closure(step)
            if not current:
                return False
        return bool(current & self.accept)


def _codepoint_in(cp, charset):
    """Whether codepoint `cp` falls in any (low, high) inclusive range of
    `charset`. Charsets here are small (a handful of ranges at most, since
    they come from a single character class or `.`), so a linear scan is
    fine -- no interval tree needed.
    """
    for lo, hi in charset:
        if lo <= cp <= hi:
            return True
    return False


class _Compiler(object):
    """Builds an NFA by walking a pattern AST once, Thompson-style. Each
    `_compile_*` method returns a (start, accept) pair of state ids for a
    single-entry, single-exit fragment; callers wire fragments together
    with fresh epsilon moves rather than sharing states between them.
    """

    def __init__(self):
        self._next_state = 0
        self.moves = {}
        self.epsilon = {}

    def new_state(self):
        if self._next_state >= _MAX_NFA_STATES:
            raise PatternError(
                "pattern is too complex: compiling it needs more than %d NFA "
                "states. Nested '+' or '*' repetition duplicates a subtree on "
                "every level (x+ is compiled as Cat(x, Star(x)), with fresh "
                "states for each occurrence of x), so a short pattern can "
                "compile to millions of states" % _MAX_NFA_STATES
            )
        state = self._next_state
        self._next_state += 1
        self.moves[state] = []
        self.epsilon[state] = set()
        return state

    def add_epsilon(self, src, dst):
        self.epsilon[src].add(dst)

    def add_move(self, src, charset, dst):
        self.moves[src].append((charset, dst))

    def compile(self, node):
        """Compile `node` into a fresh (start, accept) fragment. Dispatches
        structurally on the node's type -- deliberately not memoised by
        node identity or by node value (see the module-level note above
        this class): the same node object, or an equal-but-distinct one,
        compiles to independent states on every call.
        """
        if isinstance(node, Lit):
            return self._compile_lit(node)
        if isinstance(node, Cat):
            return self._compile_cat(node)
        if isinstance(node, Alt):
            return self._compile_alt(node)
        if isinstance(node, Star):
            return self._compile_star(node)
        if isinstance(node, Empty):
            return self._compile_empty(node)
        raise TypeError("compile_pattern: unknown AST node %r" % (node,))

    def _compile_lit(self, node):
        start = self.new_state()
        accept = self.new_state()
        self.add_move(start, node.chars, accept)
        return start, accept

    def _compile_cat(self, node):
        left_start, left_accept = self.compile(node.left)
        right_start, right_accept = self.compile(node.right)
        self.add_epsilon(left_accept, right_start)
        return left_start, right_accept

    def _compile_alt(self, node):
        start = self.new_state()
        accept = self.new_state()
        left_start, left_accept = self.compile(node.left)
        right_start, right_accept = self.compile(node.right)
        self.add_epsilon(start, left_start)
        self.add_epsilon(start, right_start)
        self.add_epsilon(left_accept, accept)
        self.add_epsilon(right_accept, accept)
        return start, accept

    def _compile_star(self, node):
        start = self.new_state()
        accept = self.new_state()
        inner_start, inner_accept = self.compile(node.node)
        self.add_epsilon(start, inner_start)
        self.add_epsilon(start, accept)
        self.add_epsilon(inner_accept, inner_start)
        self.add_epsilon(inner_accept, accept)
        return start, accept

    def _compile_empty(self, node):
        state = self.new_state()
        return state, state


def compile_pattern(src):
    """Parse `src` and compile it to an `NFA`.

    Raises PatternError if `src` does not conform to the grammar (via
    `parse_pattern`), or if the compiled pattern is nullable -- see below.

    Nullability check: after Thompson construction, this takes the
    epsilon-closure of the start state and rejects the pattern if that
    closure meets the accept set, i.e. if the NFA matches the empty
    string. This is deliberately the *general* check -- unlike
    _Parser._parse_cat's syntactic check for "" and an empty alternation
    branch, this one catches every nullable pattern regardless of shape:
    `a*`, `a?`, `(a|)`, `(ab)*` at top level all parse fine and all reach
    here. It matters because a message-prefix pattern is matched as
    L(pattern).Sigma* (see `product.py`): if L(pattern) contains the empty
    string,
    L(pattern).Sigma* is exactly Sigma*, i.e. the pattern claims *every*
    message. That machine would then collide with every other installed
    machine -- while every other well-formedness check still passes, so
    nothing else catches it. The install-time collision report does not
    fail loudly in that case; it starts saying "everything conflicts",
    forever, with no single obviously-wrong machine to point at. Catching
    it here, at compile time, turns that into a named PatternError at the
    one machine that caused it.
    """
    node = parse_pattern(src)
    compiler = _Compiler()
    start, accept = compiler.compile(node)
    nfa = NFA(start, {accept}, compiler.moves, compiler.epsilon)
    if nfa.epsilon_closure({nfa.start}) & nfa.accept:
        raise PatternError(
            "pattern %r can match the empty string; as a message prefix "
            "this claims every message (L(pattern).Sigma* becomes "
            "Sigma*) and would collide with every other installed "
            "machine" % src
        )
    return nfa
