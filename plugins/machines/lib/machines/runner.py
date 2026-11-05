"""The runner: performs one call of one verb of an installed transport (spec
2026-10-27-machines-transport-declaration-design.md, sections 3, 4 and 8).

This is the only code in the framework that executes a publisher's file. The
engine never calls a verb: `engine.py`, `fold.py` and `envelope.py` do not
import this module, and a test pins that for the engine.

One call is one process: `<root>/bin/transport <verb>`, no shell, the call
`{"channel": ..., "args": ...}` as JSON on stdin, the result envelope as JSON
on stdout. Exit 0 means stdout is the answer, `ok` either way. Any other exit
means the transport could not run, and stdout is not read as an answer.
"""
import json
import os
import selectors
import signal
import subprocess
import time

from .envelope import TraceError, parse_trace
from .machine import arg_type

# The time bound for one call, in seconds. Measured on 2026-11-05 on a
# Raspberry Pi (aarch64, 4 cores), Python time.monotonic() around
# subprocess.run: one `gh api .../issues/28/comments?per_page=100` took 0.64 s
# and 0.65 s; one `gh issue view 28 --comments --json comments` took 1.31 s,
# 2.03 s and 1.37 s. A channel at the fold limit (MAX_FOLD_STEPS = 10000
# messages, fold.py) is 100 pages of 100, about 100 x 0.65 s = 65 s. Doubled:
# 120 s. A session-relay thread is one page, about 0.65-2 s.
CALL_TIMEOUT_SECONDS = 120

# The output bound for one call, in bytes. Measured with len(json.dumps(m))
# over every message of tests/fixtures/trace-*.json: the largest is 152 bytes
# (paxos-acceptor) and 142 bytes (session-relay). A channel at the fold limit
# is 10000 x 152 bytes, about 1.5 MB; a factor of about 5 leaves room for
# longer header fields. A channel larger than this would be truncated by the
# fold anyway.
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

_ENTRY = os.path.join("bin", "transport")
_CHUNK = 65536

# Called with the process group id of every spawned entry point, so a test
# can prove the group is gone after a bound. None in normal use.
_on_spawn = None


class TransportCannotRun(Exception):
    """The entry point could not run, or exited non-zero, or answered with
    something that is not a result envelope. Never a verb that failed."""


class ChannelReadFailed(Exception):
    """`channel.list` ran and answered `ok: false`. `.error` is its text.
    Raised rather than returning an empty trace: an empty trace would read
    as a channel with nothing on it."""

    def __init__(self, error):
        super().__init__("channel.list failed: %s" % error)
        self.error = error


def _check_call(transport, verb, args):
    if transport.root is None:
        raise ValueError("transport %r has no root: load it with "
                         "load_transport so its entry point can be found"
                         % transport.name)
    if verb not in transport.verbs:
        raise ValueError("transport %r declares no verb %r"
                         % (transport.name, verb))
    declared = transport.verbs[verb]
    if declared.performer != "transport":
        raise ValueError("verb %r has performer %s: Claude performs it, the "
                         "runner never does" % (verb, declared.performer))
    if not isinstance(args, dict):
        raise ValueError("args of verb %r must be a mapping, not %r"
                         % (verb, args))
    for name in args:
        if name not in declared.args:
            raise ValueError("verb %r declares no argument %r"
                             % (verb, name))
    for name, word in declared.args.items():
        if name not in args:
            raise ValueError("verb %r is missing argument %r" % (verb, name))
        got = arg_type(args[name])
        if got != word:
            raise ValueError("argument %r of verb %r must be %s, not %s"
                             % (name, verb, word, got))


def _envelope(out, entry):
    try:
        answer = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise TransportCannotRun("%s answered with something that is not "
                                 "JSON: %s" % (entry, e))
    if not isinstance(answer, dict):
        raise TransportCannotRun("%s answered with %s, not a result envelope"
                                 % (entry, type(answer).__name__))
    ok = answer.get("ok")
    if type(ok) is not bool:
        raise TransportCannotRun("%s answered with 'ok' %r, which is not a "
                                 "boolean" % (entry, ok))
    other = "result" if ok else "error"
    for key in answer:
        if key not in ("ok", other):
            raise TransportCannotRun("%s answered ok: %s with key %r; the "
                                     "envelope is exactly ok and %s"
                                     % (entry, json.dumps(ok), key, other))
    if other not in answer:
        raise TransportCannotRun("%s answered ok: %s with no %r"
                                 % (entry, json.dumps(ok), other))
    if not ok and not isinstance(answer["error"], str):
        raise TransportCannotRun("%s answered an 'error' that is not a "
                                 "string: %r" % (entry, answer["error"]))
    return answer


def _kill(proc):
    # Kill the group before reaping the leader: while the leader is an
    # unreaped zombie its pid, and so the group id, cannot be reused.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def _close(proc):
    for stream in (proc.stdin, proc.stdout):
        stream.close()


def _exchange(proc, payload, deadline, max_output):
    """Write the call, read the answer, wait for the exit, all under one
    deadline. Returns (stdout bytes, the bound hit or None)."""
    out = bytearray()
    bound = None
    with selectors.DefaultSelector() as sel:
        os.set_blocking(proc.stdin.fileno(), False)
        sel.register(proc.stdin, selectors.EVENT_WRITE)
        sel.register(proc.stdout, selectors.EVENT_READ)
        sent = 0
        while sel.get_map():
            left = deadline - time.monotonic()
            if left <= 0:
                bound = "timeout"
                break
            for key, _ in sel.select(left):
                if key.fileobj is proc.stdin:
                    try:
                        sent += os.write(proc.stdin.fileno(),
                                         payload[sent:sent + _CHUNK])
                    except BrokenPipeError:
                        sent = len(payload)
                    if sent >= len(payload):
                        sel.unregister(proc.stdin)
                        proc.stdin.close()
                    continue
                chunk = os.read(proc.stdout.fileno(),
                                min(_CHUNK, max_output + 1 - len(out)))
                if not chunk:
                    sel.unregister(proc.stdout)
                    continue
                out += chunk
                if len(out) > max_output:
                    bound = "max_output"
                    break
            if bound:
                break
    if bound is None:
        try:
            proc.wait(max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            bound = "timeout"
    return out, bound


def call(transport, verb, channel, args, timeout=CALL_TIMEOUT_SECONDS,
         max_output=MAX_OUTPUT_BYTES):
    """Perform one verb. Returns the envelope exactly: {"ok": True,
    "result": ...} or {"ok": False, "error": str}. A bound that is hit is
    {"ok": False, "error": ...} naming the bound, and the process group is
    killed. Raises ValueError before spawning anything if the call does not
    match the declaration, and TransportCannotRun if the transport could not
    run."""
    _check_call(transport, verb, args)
    entry = os.path.join(transport.root, _ENTRY)
    payload = json.dumps({"channel": channel, "args": args}).encode("utf-8")
    deadline = time.monotonic() + timeout
    try:
        proc = subprocess.Popen([entry, verb], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True)
    except OSError as e:
        raise TransportCannotRun("%s could not run: %s" % (entry, e))
    # From here the publisher's process group is running. Whatever escapes
    # (an error, a KeyboardInterrupt, which with start_new_session=True a
    # terminal Ctrl-C does not deliver to the group) kills the group first.
    try:
        if _on_spawn is not None:
            _on_spawn(proc.pid)
        out, bound = _exchange(proc, payload, deadline, max_output)
    except BaseException:
        _kill(proc)
        _close(proc)
        raise
    if bound is not None:
        _kill(proc)
        _close(proc)
        if bound == "timeout":
            return {"ok": False, "error": "%s %s took longer than the "
                    "timeout of %s seconds" % (entry, verb, timeout)}
        return {"ok": False, "error": "%s %s wrote more than the max_output "
                "of %d bytes" % (entry, verb, max_output)}
    proc.stdout.close()
    if proc.returncode != 0:
        raise TransportCannotRun("%s %s exited %d; its stdout is not an "
                                 "answer" % (entry, verb, proc.returncode))
    return _envelope(bytes(out), entry)


def read_channel(transport, machine, channel, **bounds):
    """Read a channel through `channel.list` and return it as a Trace.
    `bounds` (timeout, max_output) pass through to `call`. An ok: false
    answer raises ChannelReadFailed; TraceError passes through."""
    answer = call(transport, "channel.list", channel, {}, **bounds)
    if not answer["ok"]:
        raise ChannelReadFailed(answer["error"])
    result = answer["result"]
    if not isinstance(result, dict):
        raise TraceError("channel.list result must be a mapping, not %s"
                         % type(result).__name__, field="result")
    for key in result:
        if key != "messages":
            raise TraceError("channel.list result has unknown key %r; it "
                             "is exactly {\"messages\": [...]}" % (key,),
                             field="result")
    if "messages" not in result:
        raise TraceError("channel.list result is missing 'messages'",
                         field="result")
    return parse_trace({"channel": channel, "machine": machine.name,
                        "version": machine.version,
                        "total_order": transport.total_order,
                        "messages": result["messages"]})
