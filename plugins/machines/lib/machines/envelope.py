"""The wire shape of a recorded trace.

A trace is a channel-layer fact: it knows nothing about any declaration, so this
module imports nothing from machine.py. It also has no slot for a message body.
Every mapping is closed, and an unknown key is refused by name, so a trace that
carries content is a TraceError rather than something a later cycle could read.
"""

import json

from machines.errors import DeclarationError

ENVELOPE_KEYS = ("clock", "sender", "channel_order")
MESSAGE_KEYS = ("kind", "by", "envelope", "fields", "world_reads")
TRACE_KEYS = ("channel", "machine", "version", "total_order", "messages")
_WORLD_READ_KEYS = ("verb", "result")


class TraceError(DeclarationError):
    pass


class WorldRead:
    def __init__(self, verb, result):
        self.verb = verb
        self.result = result  # opaque: nothing validates it, nothing may read it


class Envelope:
    def __init__(self, clock, sender, channel_order=None):
        self.clock = clock
        self.sender = sender
        self.channel_order = channel_order


class Message:
    def __init__(self, kind, by, envelope, fields=None, world_reads=()):
        self.kind = kind
        self.by = by
        self.envelope = envelope
        self.fields = {} if fields is None else fields
        self.world_reads = tuple(world_reads)


class Trace:
    def __init__(self, channel, machine, version, total_order, messages):
        self.channel = channel
        self.machine = machine
        self.version = version
        self.total_order = total_order
        self.messages = tuple(messages)


def _mapping(value, where):
    if not isinstance(value, dict):
        raise TraceError("%s must be a mapping, not %s"
                         % (where, type(value).__name__), field=where)
    return value


def _reject_unknown(raw, allowed, where):
    for key in raw:
        if key not in allowed:
            raise TraceError(
                "%s has an unknown key %r; the allowed keys are %s"
                % (where, key, ", ".join(allowed)), field=where)


def _present(raw, key, where):
    if key not in raw:
        raise TraceError("%s is missing the required key %r" % (where, key),
                         field=where)
    return raw[key]


def _string(value, key, where):
    if not isinstance(value, str) or not value:
        raise TraceError("%s %r must be a non-empty string" % (where, key),
                         field=where)
    return value


def _int(value, key, where, minimum):
    # bool is an int in Python; a clock of True would compare as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceError("%s %r must be an integer, not %r"
                         % (where, key, value), field=where)
    if value < minimum:
        raise TraceError("%s %r must be at least %d, not %d"
                         % (where, key, minimum, value), field=where)
    return value


def _parse_envelope(raw, where):
    raw = _mapping(raw, where)
    _reject_unknown(raw, ENVELOPE_KEYS, where)
    clock = _int(_present(raw, "clock", where), "clock", where, 1)
    sender = _string(_present(raw, "sender", where), "sender", where)
    order = raw.get("channel_order")
    if order is not None:
        order = _int(order, "channel_order", where, 0)
    return Envelope(clock, sender, order)


def _parse_fields(raw, where):
    raw = _mapping(raw, where)
    for name, value in raw.items():
        if not isinstance(value, (int, bool)):
            raise TraceError(
                "%s field %r must be an int or a bool, not %s"
                % (where, name, type(value).__name__), field=where)
    return dict(raw)


def _parse_world_reads(raw, where):
    if not isinstance(raw, list):
        raise TraceError("%s world_reads must be a list" % where, field=where)
    reads = []
    for i, entry in enumerate(raw):
        here = "%s world_reads[%d]" % (where, i)
        entry = _mapping(entry, here)
        _reject_unknown(entry, _WORLD_READ_KEYS, here)
        reads.append(WorldRead(_string(_present(entry, "verb", here),
                                       "verb", here),
                               _present(entry, "result", here)))
    return reads


def _parse_message(raw, index):
    where = "message %d" % index
    raw = _mapping(raw, where)
    _reject_unknown(raw, MESSAGE_KEYS, where)
    return Message(
        _string(_present(raw, "kind", where), "kind", where),
        _string(_present(raw, "by", where), "by", where),
        _parse_envelope(_present(raw, "envelope", where),
                        where + " envelope"),
        _parse_fields(raw.get("fields", {}), where),
        _parse_world_reads(raw.get("world_reads", []), where))


def parse_trace(obj):
    where = "trace"
    obj = _mapping(obj, where)
    _reject_unknown(obj, TRACE_KEYS, where)
    channel = _string(_present(obj, "channel", where), "channel", where)
    machine = _string(_present(obj, "machine", where), "machine", where)
    version = _string(_present(obj, "version", where), "version", where)
    total_order = _present(obj, "total_order", where)
    if not isinstance(total_order, bool):
        raise TraceError("trace 'total_order' must be a boolean, not %r"
                         % (total_order,), field=where)
    messages = _present(obj, "messages", where)
    if not isinstance(messages, list):
        raise TraceError("trace 'messages' must be a list", field=where)
    return Trace(channel, machine, version, total_order,
                 [_parse_message(m, i) for i, m in enumerate(messages)])


def load_trace(path):
    with open(path, encoding="utf-8") as handle:
        return parse_trace(json.load(handle))
