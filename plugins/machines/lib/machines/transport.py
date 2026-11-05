"""The transport declaration: `transport/transport.yaml`, the closed-language
description of what an installed transport can do (spec
2026-10-27-machines-transport-declaration-design.md, sections 2, 5, 6, 13.3).

Data only. Parsing a declaration never imports, runs or interpolates
anything the publisher wrote. `run`, `cmd` and `shell` are not special: the
entry point is fixed by the spec, so the declaration has nowhere to put a
command, and those words are unknown keys like any other.
"""
import os
import yaml

from .declaration import MachineSafeLoader
from .errors import DeclarationError
from .machine import ARG_TYPES, NAME, VERB

TOUCHES = ("channel-read", "channel-write", "world-read", "world-write")
PERFORMERS = ("transport", "agent")
# The only channel-read return shape (spec section 4).
RETURNS = ("messages",)

_TOP_KEYS = ("transport", "version", "channel", "verbs")
_CHANNEL_KEYS = ("total_order", "id")
_VERB_KEYS = ("touches", "performer", "args", "returns")

_LIST = "channel.list"
_APPEND = "channel.append"


class TransportError(DeclarationError):
    """A transport declaration that is refused. `.field` names the key."""


class Verb:
    def __init__(self, name, touches, performer, args, returns=None):
        self.name = name
        self.touches = touches
        self.performer = performer
        self.args = args
        self.returns = returns

    def _key(self):
        return (self.name, self.touches, self.performer, self.args,
                self.returns)

    def __eq__(self, other):
        return isinstance(other, Verb) and self._key() == other._key()

    __hash__ = None

    def __repr__(self):
        return "Verb%r" % (self._key(),)


class Transport:
    def __init__(self, name, version, total_order, channel_id, verbs,
                 root=None):
        self.name = name
        self.version = version
        self.total_order = total_order
        self.channel_id = channel_id
        self.verbs = verbs
        self.root = root

    def _key(self):
        return (self.name, self.version, self.total_order, self.channel_id,
                self.verbs, self.root)

    def __eq__(self, other):
        return isinstance(other, Transport) and self._key() == other._key()

    __hash__ = None

    def __repr__(self):
        return "Transport%r" % (self._key(),)


def _err(message, field):
    return TransportError(message, field=field)


def _mapping(value, key, what):
    if not isinstance(value, dict):
        raise _err("%s must be a mapping, not %r" % (what, value), key)
    return value


def _reject_unknown(raw, allowed, where):
    for key in raw:
        if key not in allowed:
            raise _err("unknown field %r in %s" % (key, where),
                       key if isinstance(key, str) else where)


def _require(raw, key, where):
    if key not in raw:
        raise _err("%s is missing required field %r" % (where, key), key)
    return raw[key]


def _string(value, key, where):
    if not isinstance(value, str):
        raise _err("%s%s must be a string, not %r" % (where, key, value), key)
    return value


def parse_transport(text):
    try:
        data = yaml.load(text, Loader=MachineSafeLoader)
    except yaml.YAMLError as e:
        raise _err("transport.yaml is not valid YAML: %s" % e, None)
    if not isinstance(data, dict):
        raise _err("a transport declaration must be a mapping", None)
    _reject_unknown(data, _TOP_KEYS, "the transport declaration")

    name = _string(_require(data, "transport", "the declaration"),
                   "transport", "")
    if not NAME.match(name):
        raise _err("transport %r must match %s" % (name, NAME.pattern),
                   "transport")
    version = _string(_require(data, "version", "the declaration"),
                      "version", "")

    total_order, channel_id = _channel(_require(data, "channel",
                                                "the declaration"))
    verbs = _verbs(_require(data, "verbs", "the declaration"))
    _required_verbs(verbs)
    return Transport(name, version, total_order, channel_id, verbs)


def _channel(raw):
    _mapping(raw, "channel", "channel")
    _reject_unknown(raw, _CHANNEL_KEYS, "channel")
    if "total_order" not in raw:
        raise _err("channel is missing total_order, which has no default: "
                   "the engine behaves differently for each value and "
                   "guessing would pick one silently", "total_order")
    total_order = raw["total_order"]
    if not isinstance(total_order, bool):
        raise _err("total_order must be true or false, not %r"
                   % (total_order,), "total_order")
    channel_id = None
    if "id" in raw:
        channel_id = _string(raw["id"], "id", "channel ")
    return total_order, channel_id


def _verbs(raw):
    if not isinstance(raw, dict) or not raw:
        raise _err("verbs must be a non-empty mapping of verb name to its "
                   "declaration, not %r" % (raw,), "verbs")
    verbs = {}
    for name, spec in raw.items():
        if not isinstance(name, str) or not VERB.match(name):
            raise _err("verb name %r must be lower-case words joined by "
                       "dots, like 'label.add'" % (name,), "verbs")
        verbs[name] = _verb(name, spec)
    return verbs


def _verb(name, spec):
    where = "verb %r" % name
    _mapping(spec, "verbs", where)
    _reject_unknown(spec, _VERB_KEYS, where)

    touches = _require(spec, "touches", where)
    if touches not in TOUCHES:
        raise _err("%s has touches %r, which is not one of %s"
                   % (where, touches, ", ".join(TOUCHES)), "touches")
    performer = _require(spec, "performer", where)
    if performer not in PERFORMERS:
        raise _err("%s has performer %r, which is not one of %s"
                   % (where, performer, ", ".join(PERFORMERS)), "performer")
    args = _args(name, _require(spec, "args", where))

    returns = None
    if touches == "channel-read":
        if "returns" not in spec:
            raise _err("%s touches channel-read, so it must declare "
                       "returns (one of %s)" % (where, ", ".join(RETURNS)),
                       "returns")
        returns = spec["returns"]
        if returns not in RETURNS:
            raise _err("%s has returns %r, which is not one of %s"
                       % (where, returns, ", ".join(RETURNS)), "returns")
    elif "returns" in spec:
        raise _err("%s touches %s, and only a channel-read verb declares "
                   "returns" % (where, touches), "returns")

    # The channel is the transport's to read and write. A verb Claude
    # performs sits outside it. This rule is the controller's call, not the
    # spec's (task 1 brief).
    if performer == "agent" and touches in ("channel-read", "channel-write"):
        raise _err("%s has performer agent but touches %s; the channel is "
                   "the transport's to read and write" % (where, touches),
                   "performer")
    return Verb(name, touches, performer, args, returns)


def _args(verb, raw):
    if not isinstance(raw, dict):
        raise _err("args of verb %r must be a mapping of argument name to "
                   "type, not %r" % (verb, raw), "args")
    args = {}
    for arg, word in raw.items():
        if not isinstance(arg, str) or not NAME.match(arg):
            raise _err("argument name %r of verb %r must match %s"
                       % (arg, verb, NAME.pattern), "args")
        if not isinstance(word, str) or word not in ARG_TYPES:
            raise _err("argument %r of verb %r has type %r, which is not "
                       "one of %s" % (arg, verb, word, ", ".join(ARG_TYPES)),
                       "args")
        args[arg] = word
    return args


def _required_verbs(verbs):
    """Spec section 13.3: exactly one channel-read verb, named channel.list,
    returning messages and performed by the transport; and a channel.append
    that writes the channel, performed by the transport. `returns: messages`
    is enforced for any channel-read verb, and `performer: transport` for any
    channel-read or channel-write verb, by `_verb`: an agent may touch
    neither, so a second check here would be dead code (a mutation removing
    it survived all 50 tests, which is how that was found)."""
    reads = [v.name for v in verbs.values() if v.touches == "channel-read"]
    if len(reads) > 1:
        raise _err("a transport declares exactly one channel-read verb, "
                   "found %d: %s" % (len(reads), ", ".join(reads)), "verbs")
    if reads != [_LIST]:
        raise _err("the transport's one channel-read verb must be named "
                   "%r%s" % (_LIST, "; found %r" % reads[0] if reads
                             else "; it declares none"), "verbs")
    if _APPEND not in verbs:
        raise _err("a transport must declare a %r verb" % _APPEND, "verbs")
    append = verbs[_APPEND]
    if append.touches != "channel-write":
        raise _err("verb %r must touch channel-write, not %s"
                   % (_APPEND, append.touches), "touches")


def load_transport(path):
    """`path` is a `transport.yaml`, or a directory containing one. OSError
    passes through. `.root` is the directory holding transport.yaml."""
    if os.path.isdir(path):
        path = os.path.join(path, "transport.yaml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    transport = parse_transport(text)
    transport.root = os.path.dirname(os.path.abspath(path))
    return transport
