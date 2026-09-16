import re
import yaml
from .errors import DeclarationError
from .machine import (FIELDS, REQUIRED, Machine, State, Transition, Field,
                       FIELD_TYPES, NAME, _MAX_PREFIX_LENGTH, Register, FOLDS,
                       Guard, OP_ATOMS, CAP_SCOPES)

_FENCE = re.compile(r"^```machine[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)

_STATE_KEYS = {"name", "holder", "terminal", "accepting"}
_TRANSITION_KEYS = {"from", "on", "by", "to", "signal", "effects", "guard"}
_REGISTER_KEYS = {"fold", "field", "on", "initial"}
_GUARD_KEYS = {"field", "op", "register"}
_CAP_KEYS = {"limit", "per"}


class MachineSafeLoader(yaml.SafeLoader):
    """A SafeLoader whose implicit boolean resolution is narrowed to
    true/false (and case variants) only.

    PyYAML's default resolver follows YAML 1.1, under which the bare words
    yes/no/on/off (and their case variants -- Yes, ON, off, ...; bare y/n
    alone are unaffected) also resolve to booleans, in *any* scalar position
    a publisher can write -- a mapping key as much as a value. For this
    schema that is not a cosmetic surprise, it is a correctness hole: a kind
    declared `on`, a state named `no`, a role called `yes`, a transition's
    `on: yes` -- each would silently become a Python bool instead of the
    string the publisher wrote, and every check built on equality
    (`t.on in m.kinds`, a dict key lookup) keeps "working" against the
    corrupted value with no error raised anywhere. That is worse than a
    crash: coherent-looking data that is simply wrong.

    Narrowing the resolver removes the landmine in one place, for every
    field, present and future, rather than patching each exposed position
    by hand. The cost: `signal: yes` no longer means true. A publisher must
    write `signal: true`. Documented in SCHEMA.md.
    """


MachineSafeLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers
            if tag != "tag:yaml.org,2002:bool"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
MachineSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def extract_block(text):
    blocks = _FENCE.findall(text)
    if not blocks:
        raise DeclarationError("no ```machine block found")
    if len(blocks) > 1:
        raise DeclarationError(
            "found %d ```machine blocks; a bundle declares exactly one" % len(blocks)
        )
    return blocks[0]

def parse(text):
    data = yaml.load(extract_block(text), Loader=MachineSafeLoader)
    if not isinstance(data, dict):
        raise DeclarationError("a machine block must be a mapping")

    for key in data:
        if key not in FIELDS:
            raise DeclarationError("unknown field %r" % key, field=key)
    for key in REQUIRED:
        if key not in data:
            raise DeclarationError("missing field %r" % key, field=key)

    for key in ("machine", "version", "prefix", "initial"):
        _require_string(data[key], key)

    _require_prefix_length(data["prefix"])

    # `cap` is optional, and its absence is meaningful: this protocol
    # declares no bound. No default is substituted -- a cap the publisher
    # did not write is a bound nobody agreed to, and `check_machine` skips
    # the satisfiability check outright rather than measuring against an
    # invented number. Optional is not unvalidated, though: a cap that *is*
    # written must be a real count, and must not be a bool (Python
    # considers `True` an `int`, so `cap: true` would otherwise land as 1).
    cap, cap_scope = _cap_field(data)

    kinds = data["kinds"]
    if not isinstance(kinds, list):
        raise DeclarationError("kinds must be a list of strings", field="kinds")
    for kind in kinds:
        _require_string(kind, "kinds", "each entry of ")

    roles = data["roles"]
    if not isinstance(roles, dict):
        raise DeclarationError(
            "roles must be a mapping of role name to what it binds to",
            field="roles")
    # `check_machine` sorts `m.roles` (to build `role_index` for the
    # per-role cap search) -- a role key that is not a string sails past
    # the mapping check above and then crashes that sort with a raw
    # `TypeError` comparing e.g. `str` to `int`. Every other name in this
    # schema is validated at parse time; the keys of `roles` were the one
    # exception, because nothing before the `role`-scoped cap search ever
    # needed them to be more than mapping keys.
    for role in roles:
        _require_string(role, "roles", "each key of ")

    fields = _fields_section(data)
    registers = _registers_section(data)

    raw_states = data["states"]
    if not isinstance(raw_states, list):
        raise DeclarationError("states must be a list", field="states")

    raw_transitions = data["transitions"]
    if not isinstance(raw_transitions, list):
        raise DeclarationError("transitions must be a list", field="transitions")

    states = {}
    for raw in raw_states:
        _require_mapping(raw, "states")
        _reject_unknown(raw, _STATE_KEYS, "states")
        name = _require_string(_require_present(raw, "name", "states"),
                               "name", "a states entry's ")
        if name in states:
            raise DeclarationError("duplicate state %r" % name, field="states")
        holder = raw.get("holder")
        if holder is not None:
            _require_string(holder, "holder", "a states entry's ")
        states[name] = State(name, holder,
                              _bool_field(raw, "terminal", False),
                              _bool_field(raw, "accepting", False))

    transitions = []
    for raw in raw_transitions:
        _require_mapping(raw, "transitions")
        _reject_unknown(raw, _TRANSITION_KEYS, "transitions")
        field = {}
        for key in ("from", "on", "by", "to"):
            field[key] = _require_string(
                _require_present(raw, key, "transitions"),
                key, "a transitions entry's ")
        transitions.append(Transition(
            field["from"], field["on"], field["by"], field["to"],
            _bool_field(raw, "signal", False), _effects_field(raw),
            _guard_field(raw),
        ))

    return Machine(
        data["machine"], data["version"], data["prefix"],
        dict(roles), set(kinds), cap,
        data["initial"], states, transitions,
        fields=fields, registers=registers, cap_scope=cap_scope,
    )

def _fields_section(data):
    """The optional `fields` mapping: declared header field name to its
    type. Entirely parse-time -- there is no cross-reference for
    `check_machine` to make, because a field's type is fixed right here
    and nothing later depends on another field's value.

    Absent or empty means no fields declared, and the result is `{}`, not
    `None` -- a caller (cycle B's engine, and `_registers_section` below,
    which references a field by name) never has to check for the
    difference.

    A mapping, not a list of `{name, type}` objects: a list would be a
    third entry shape to validate for the same information a mapping
    already carries, and a mapping cannot carry a duplicate name at all --
    there is no `[{name: ballot, ...}, {name: ballot, ...}]` here to
    catch.

    Each key must match `NAME` (machine.py) -- in particular, no `.`: the
    dotted namespace is reserved for the message envelope a later cycle
    adds (`envelope.clock` and the like), and a declared field colliding
    with it would be the readable route back to guarding that clock
    directly, which the spec forbids. Each value must be a string found in
    `FIELD_TYPES` -- closed, so a publisher who writes `ballot: integer`
    or `ballot: number` is told the word is wrong instead of getting a
    machine whose guard the engine cannot evaluate, and `fields: {ballot:
    3}` is rejected here, before a non-string type word ever reaches a
    guard's type check.
    """
    if "fields" not in data:
        return {}
    raw = data["fields"]
    if not isinstance(raw, dict):
        raise DeclarationError(
            "fields must be a mapping of field name to type, not %r" % (raw,),
            field="fields")
    fields = {}
    for name, type_word in raw.items():
        if not isinstance(name, str) or not NAME.match(name):
            raise DeclarationError(
                "field name %r must match %s" % (name, NAME.pattern),
                field="fields")
        if not isinstance(type_word, str) or type_word not in FIELD_TYPES:
            raise DeclarationError(
                "field %r has type %r, which is not one of %s"
                % (name, type_word, FIELD_TYPES), field="fields")
        fields[name] = Field(name, type_word)
    return fields

def _registers_section(data):
    """The optional `registers` mapping: register name to its fold
    declaration. Entirely shape validation here -- whether the register's
    `field` and `on` actually name declared things is a cross-reference
    `check_machine` makes (R1, R2), not this function, the same split
    `_fields_section` documents above.

    Absent or empty means no registers declared, and the result is `{}`,
    not `None` -- the same reason `_fields_section` gives.

    A mapping, keyed the same way `fields` is and for the same reason: a
    list of `{name: ...}` objects would be a third entry shape to
    validate for information a mapping already carries, and could carry a
    duplicate register name a mapping cannot.

    Each key must match `NAME` (machine.py), the same pattern `fields`
    uses and the same reasoning -- register names and field names share
    one namespace (see `NAME`'s comment in machine.py) and both must stay
    clear of the dotted `envelope.*` one.

    Each value must be a mapping with exactly the four keys `fold`,
    `field`, `on`, `initial` -- all required, none else tolerated:

    - `fold` a string in `FOLDS`.
    - `field` a string -- not checked against `fields` here; that is R1.
    - `on` a non-empty list of strings -- not checked against `kinds`
      here; that is R2. Non-empty because an `on` that never fires would
      be a register that never updates, which is a constant declared
      through the back door; see SCHEMA.md's `registers` section for why
      that is a stated gap rather than a feature to admit this way.
    - `initial` an `int` (Python's `bool` is a subclass of `int`, so this
      test alone accepts both) -- whether it agrees with the field's
      declared type is R3, a cross-reference this function cannot make.
    """
    if "registers" not in data:
        return {}
    raw = data["registers"]
    if not isinstance(raw, dict):
        raise DeclarationError(
            "registers must be a mapping of register name to its fold "
            "declaration, not %r" % (raw,), field="registers")
    registers = {}
    for name, spec in raw.items():
        if not isinstance(name, str) or not NAME.match(name):
            raise DeclarationError(
                "register name %r must match %s" % (name, NAME.pattern),
                field="registers")
        _require_mapping(spec, "registers")
        _reject_unknown(spec, _REGISTER_KEYS, "registers")

        fold = _require_string(
            _require_present(spec, "fold", "registers"), "fold",
            "a register's ")
        if fold not in FOLDS:
            raise DeclarationError(
                "register %r has fold %r, which is not one of %s"
                % (name, fold, FOLDS), field="registers")

        field = _require_string(
            _require_present(spec, "field", "registers"), "field",
            "a register's ")

        on = _require_present(spec, "on", "registers")
        if not isinstance(on, list) or not on:
            raise DeclarationError(
                "register %r must have a non-empty list of kinds under "
                "'on', not %r" % (name, on), field="registers")
        for kind in on:
            _require_string(kind, "on", "each entry of a register's ")

        initial = _require_present(spec, "initial", "registers")
        if not isinstance(initial, int):
            raise DeclarationError(
                "register %r initial must be an int or a bool, not %r"
                % (name, initial), field="registers")

        registers[name] = Register(name, fold, field, list(on), initial)
    return registers

def _reject_unknown(raw, allowed, where):
    for key in raw:
        if key not in allowed:
            raise DeclarationError("unknown field %r in %s" % (key, where), field=key)

# --- shape guards -------------------------------------------------------
#
# Everything below exists so that no hand-written declaration can reach a
# caller as a raw Python traceback. `machines-check` has three exit codes on
# purpose: 1 means "I checked, and found a problem", 2 means "I could not
# check at all". An uncaught KeyError/TypeError/ValueError out of `parse`
# exits 1 with a traceback, which reports the tool's own crash as if it
# were a finding about the publisher's machine -- exactly what exit 2
# exists to prevent. Every guard here raises DeclarationError naming the
# field instead, which the CLI already knows how to report.
#
# The existing list-shape guards above (`kinds`, `states`, `transitions`
# must be lists) are the same idea; these extend it to the containers and
# scalars those guards did not reach.

def _require_mapping(value, where):
    """Each `states`/`transitions` entry must be a mapping.

    Checked before `_reject_unknown` iterates it: `for key in 5` is a
    TypeError, and `for key in "abc"` silently iterates characters.
    """
    if not isinstance(value, dict):
        raise DeclarationError(
            "each %s entry must be a mapping, not %r" % (where, value),
            field=where)
    return value

def _require_present(raw, key, where):
    if key not in raw:
        raise DeclarationError(
            "a %s entry is missing required field %r" % (where, key), field=key)
    return raw[key]

# `_MAX_PREFIX_LENGTH` is defined in machine.py, next to `prefix_problem`
# (imported above), not here -- see it there for the full measurement and
# reasoning (a 498-character literal recursion limit in compile_pattern,
# the 399-character nested-group case, and why the number is shared
# between this module's parse-time check and `prefix_problem`'s check for
# a hand-built `Machine` that skipped this parser entirely). It stays
# enforced here too, at parse time, so a publisher gets a named field and
# a stated limit before the pattern parser ever sees the text, rather
# than only after a `Machine` has already been constructed.
def _require_prefix_length(prefix):
    if len(prefix) > _MAX_PREFIX_LENGTH:
        raise DeclarationError(
            "prefix is %d characters long; the limit is %d characters"
            % (len(prefix), _MAX_PREFIX_LENGTH),
            field="prefix")


def _require_string(value, field, where=""):
    """A field the schema documents as a string must actually be one.

    Not cosmetic: `prefix: 5` parses fine and then fails with
    `TypeError: object of type 'int' has no len()` deep inside the pattern
    compiler, and a state `name` that is an int becomes a dict key no
    transition can ever name.
    """
    if not isinstance(value, str):
        raise DeclarationError(
            "%s%s must be a string, not %r" % (where, field, value), field=field)
    return value

def _effects_field(raw):
    """`effects` is an optional list of strings.

    The bare-string case is called out separately because it is the one
    that did not crash: `effects: escalate` is iterable, so the effect
    vocabulary check walked it character by character and emitted eight
    problems about `'e'`, `'s'`, `'c'`... -- eight wrong answers instead of
    one right one. Same hazard as `kinds: "yes"`, same fix.
    """
    if "effects" not in raw:
        return []
    effects = raw["effects"]
    if not isinstance(effects, list):
        raise DeclarationError(
            "effects must be a list of strings, not %r" % (effects,),
            field="effects")
    for effect in effects:
        _require_string(effect, "effects", "each entry of ")
    return effects

def _guard_field(raw):
    """A transition's optional `guard`: a mapping with exactly the three
    keys `field`, `op`, `register` -- all required, none else tolerated,
    each a string, `op` one of `OP_ATOMS`'s six words. Entirely shape
    validation here -- whether `field` and `register` actually name a
    declared field and a declared register is a cross-reference
    `check_machine` makes (G1, G2), the same split `_fields_section` and
    `_registers_section` document above for their own contents.

    Absent means the transition fires unconditionally, and the result is
    `None`, not a `Guard` with empty fields -- the same reasoning
    `_fields_section` gives for returning `{}` rather than `None`, read in
    the other direction: here, nothing declared means nothing to compare.

    `op` must be spelled as a word, never a symbol. Loaded through the
    shipped `MachineSafeLoader`, an unquoted `op: >` in block context
    parses to the empty string with no error raised anywhere -- `>` is
    YAML's block-scalar indicator, not a comparison operator reaching this
    function -- and `op: !=` fails with a YAML error about a tag instead
    of a named field. Neither is the failure a publisher who tried a
    symbol should get; requiring one of `OP_ATOMS`'s words sidesteps both
    by construction, rather than trying to detect the symbol forms after
    the fact.
    """
    if "guard" not in raw:
        return None
    spec = raw["guard"]
    _require_mapping(spec, "guard")
    _reject_unknown(spec, _GUARD_KEYS, "guard")
    field = _require_string(
        _require_present(spec, "field", "guard"), "field", "a guard's ")
    op = _require_string(
        _require_present(spec, "op", "guard"), "op", "a guard's ")
    if op not in OP_ATOMS:
        raise DeclarationError(
            "guard has op %r, which is not one of %s"
            % (op, sorted(OP_ATOMS)), field="guard")
    register = _require_string(
        _require_present(spec, "register", "guard"), "register",
        "a guard's ")
    return Guard(field, op, register)


def _cap_field(data):
    """The optional top-level `cap`: a bare positive integer, or a mapping
    `{ limit: <positive integer>, per: <one of CAP_SCOPES> }`. Both forms
    say the same thing when `per` is `channel` -- the bare form is not a
    separate rule, it is the mapping form's `channel` case spelled without
    the mapping, and stays valid on that basis rather than as a special
    case ported forward for its own sake. Returns `(cap, cap_scope)`;
    absent `cap` returns `(None, "channel")` -- the scope is meaningless
    with no cap to scope, but the attribute must still exist on every
    `Machine`, mapping form or not.

    Only shape and spelling are validated here. What `channel` and `role`
    each count, and whether a declared cap is large enough, is
    `check_machine`'s question, not `parse`'s -- the same split every
    other cross-referencing check in this module keeps.
    """
    if "cap" not in data:
        return None, "channel"
    cap = data["cap"]
    if isinstance(cap, dict):
        _reject_unknown(cap, _CAP_KEYS, "cap")
        limit = _require_present(cap, "limit", "cap")
        per = _require_string(
            _require_present(cap, "per", "cap"), "per", "a cap's ")
        if per not in CAP_SCOPES:
            raise DeclarationError(
                "cap has per %r, which is not one of %s"
                % (per, sorted(CAP_SCOPES)), field="cap")
        _require_positive_cap(limit)
        return limit, per
    _require_positive_cap(cap)
    return cap, "channel"


def _require_positive_cap(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DeclarationError("cap must be a positive integer", field="cap")


def _bool_field(raw, key, default):
    # Narrowing MachineSafeLoader's bool resolution (above) stops YAML from
    # silently turning `signal: yes` into the boolean True at parse time --
    # but Python's own bool() is just as happy to turn the resulting string
    # "yes" into True by truthiness, which is the same silent corruption
    # wearing a different hat. Require an actual bool here instead.
    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, bool):
        raise DeclarationError(
            "%s must be true or false, not %r" % (key, value), field=key)
    return value
