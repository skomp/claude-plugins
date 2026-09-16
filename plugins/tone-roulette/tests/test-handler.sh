#!/usr/bin/env bash
# Tests for the tone-roulette SessionStart handler
# (hooks-handlers/session-start.sh).
#
# Every test points HOME at a fresh temp directory so nothing here ever
# touches the real ~/.claude. Most tests point CLAUDE_PLUGIN_ROOT at the
# real shipped plugin (so STYLES_DIR resolves to the real output-styles/
# catalogue); tests 8 and 10 point it at an isolated fixture root instead,
# so the empty-catalogue and joke-tone-body cases never touch the shipped
# catalogue.
#
# Every test also runs with CLAUDE_PROJECT_DIR pointed at a fresh temp
# directory — DEFAULT_PROJECT_DIR when a test doesn't pass its own — so a
# test never reads this repository's own (nonexistent) .claude/settings*
# files, and so the output-style stand-down (tests 25-30) can be exercised
# by pointing a single test at a project dir that does carry one.
#
# Uses `jq` for assertions (allowed in tests; the handler itself must not
# depend on it). No dependency on `shuf`.
#
# Requires bash 4+ (uses `mapfile` and `declare -A`, both introduced in
# bash 4.0 — this file's own #!/usr/bin/env bash does not guarantee that
# version). The handler it tests has no such dependency: it is verified
# clean under bash 3.2, the version macOS ships at /bin/bash, on both the
# normal and empty-catalogue paths (issue #7 item 2) — `hooks/hooks.json`
# invokes `bash` from PATH, so the handler may run under 3.2 in the real
# world even on a machine where this test file cannot.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HANDLER="$PLUGIN_ROOT/hooks-handlers/session-start.sh"
STYLES_DIR="$PLUGIN_ROOT/output-styles"

fail_count=0
check_count=0

fail() {
  echo "FAIL: $1"
  fail_count=$((fail_count + 1))
}

pass() {
  echo "PASS: $1"
}

check() {
  check_count=$((check_count + 1))
}

if [ ! -x "$HANDLER" ] && [ ! -r "$HANDLER" ]; then
  echo "FAIL: handler not found at $HANDLER"
  exit 1
fi

# --- Fixture directories, cleaned up on exit. ---
TMP_ROOTS=()
cleanup() {
  local d
  for d in "${TMP_ROOTS[@]:-}"; do
    [ -n "$d" ] && rm -rf "$d"
  done
}
trap cleanup EXIT

new_tmp_dir() {
  local d
  d="$(mktemp -d)"
  TMP_ROOTS+=("$d")
  printf '%s' "$d"
}

_id_counter=0
next_session_id() {
  _id_counter=$((_id_counter + 1))
  printf 'sid-%s-%s-%s' "$$" "$_id_counter" "$RANDOM"
}

# List the catalogue's tone basenames, one per line.
catalog_tones() {
  local dir="$1" f base
  for f in "$dir"/*.md; do
    [ -e "$f" ] || continue
    base="$(basename "$f" .md)"
    printf '%s\n' "$base"
  done
}

mapfile -t TONES < <(catalog_tones "$STYLES_DIR")
if [ "${#TONES[@]}" -eq 0 ]; then
  echo "FAIL: no tone files found in $STYLES_DIR — cannot run handler tests"
  exit 1
fi

# A project directory with no .claude/settings*.json in it at all — the
# default CLAUDE_PROJECT_DIR for every run_handler call that doesn't pass
# its own, so the 21 pre-existing call sites (and any that don't care about
# output-style detection) see no outputStyle key by construction, the same
# way they already see an isolated $HOME with no real ~/.claude in it.
# Without this, an unset CLAUDE_PROJECT_DIR would fall back to the
# handler's $PWD — wherever this test file happens to be invoked from —
# which is exactly the kind of ambient, cwd-dependent behaviour these tests
# otherwise go out of their way to avoid.
DEFAULT_PROJECT_DIR="$(new_tmp_dir)"

# run_handler HOME ROOT STDIN_STRING [PROJECT_DIR] > stdout, returns
# handler's exit code. PROJECT_DIR defaults to DEFAULT_PROJECT_DIR (no
# settings files) when omitted.
run_handler() {
  local home="$1" root="$2" stdin_str="$3" project_dir="${4:-$DEFAULT_PROJECT_DIR}"
  printf '%s' "$stdin_str" | HOME="$home" CLAUDE_PLUGIN_ROOT="$root" CLAUDE_PROJECT_DIR="$project_dir" bash "$HANDLER"
}

state_file_for() {
  local home="$1" sid="$2"
  printf '%s/.claude/tone-roulette/%s' "$home" "$sid"
}

# days_ago_ts N -> a timestamp N days in the past, formatted for `touch -t`
# ([[CC]YY]MMDDhhmm). Tries BSD date's `-v` first (macOS); falls back to
# GNU date's `-d` (Linux). Used to age fixtures without depending on
# `find -mtime`'s own BSD/GNU differences to also be the thing under test.
days_ago_ts() {
  local days="$1"
  if date -v-1d +%Y%m%d%H%M >/dev/null 2>&1; then
    date -v-"${days}"d +%Y%m%d%H%M
  else
    date -d "${days} days ago" +%Y%m%d%H%M
  fi
}

# =====================================================================
# Test 1 — output is valid JSON for a roll.
# =====================================================================
{
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq . >/dev/null 2>&1; then
    pass "test1: roll produces valid JSON on stdout (exit 0)"
  else
    fail "test1: roll did not produce valid JSON (exit=$ec, out=$out)"
  fi

  TEST1_OUT="$out"

  # M6 — the tone named in .systemMessage and the tone whose body is in
  # .additionalContext must be the same tone. Determined independently of
  # the handler: sys_tone is whichever catalog tone name is a substring of
  # systemMessage; body_tone is whichever catalog tone's own
  # frontmatter-stripped body (computed here with a plain awk one-liner,
  # not the handler's logic) exactly equals additionalContext.
  sysmsg_for_pairing="$(printf '%s' "$out" | jq -r '.systemMessage // empty')"
  ctx_for_pairing="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')"

  sys_tone=""
  for t in "${TONES[@]}"; do
    case "$sysmsg_for_pairing" in
      *"$t"*) sys_tone="$t" ;;
    esac
  done

  body_tone=""
  for t in "${TONES[@]}"; do
    candidate_body="$(
      awk '
        NR == 1 && $0 == "---" { infm = 1; next }
        infm && $0 == "---"    { infm = 0; next }
        infm                   { next }
        { print }
      ' "$STYLES_DIR/$t.md"
    )"
    if [ "$candidate_body" = "$ctx_for_pairing" ]; then
      body_tone="$t"
      break
    fi
  done

  check
  if [ -n "$sys_tone" ] && [ -n "$body_tone" ] && [ "$sys_tone" = "$body_tone" ]; then
    pass "test1: systemMessage's tone ($sys_tone) matches additionalContext's tone ($body_tone)"
  else
    fail "test1: systemMessage names '$sys_tone' but additionalContext's body matches '$body_tone'"
  fi
}

# =====================================================================
# Test 2 — .systemMessage is non-empty and names a real tone.
# =====================================================================
{
  sysmsg="$(printf '%s' "$TEST1_OUT" | jq -r '.systemMessage // empty')"

  check
  if [ -z "$sysmsg" ]; then
    fail "test2: .systemMessage is empty"
  else
    matched=""
    for t in "${TONES[@]}"; do
      case "$sysmsg" in
        *"$t"*) matched="$t" ;;
      esac
    done
    if [ -n "$matched" ]; then
      pass "test2: .systemMessage ('$sysmsg') names a real catalog tone ($matched)"
    else
      fail "test2: .systemMessage ('$sysmsg') does not name any catalog tone"
    fi
  fi
}

# =====================================================================
# Test 3 — hookEventName is SessionStart, additionalContext non-empty.
# =====================================================================
{
  event_name="$(printf '%s' "$TEST1_OUT" | jq -r '.hookSpecificOutput.hookEventName // empty')"
  ctx="$(printf '%s' "$TEST1_OUT" | jq -r '.hookSpecificOutput.additionalContext // empty')"

  check
  if [ "$event_name" = "SessionStart" ]; then
    pass "test3: hookSpecificOutput.hookEventName == SessionStart"
  else
    fail "test3: hookSpecificOutput.hookEventName == '$event_name', expected SessionStart"
  fi

  check
  if [ -n "$ctx" ]; then
    pass "test3: .additionalContext is non-empty"
  else
    fail "test3: .additionalContext is empty"
  fi
}

# =====================================================================
# Test 4 — frontmatter is stripped.
#
# Ruling in the dispatch overrides the brief's literal test 4 (which would
# fail a correct handler if a tone body happened to contain the substring
# "name:"). Implemented as: the body must not begin with the `---`
# delimiter, and must not contain the specific line `name: <basename>` for
# the selected tone.
# =====================================================================
{
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}")"
  selected="$(cat "$(state_file_for "$home" "$sid")" 2>/dev/null)"
  ctx="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')"
  first3="$(printf '%s' "$ctx" | cut -c1-3)"

  check
  if [ "$first3" != "---" ]; then
    pass "test4: additionalContext does not begin with '---'"
  else
    fail "test4: additionalContext begins with '---' — frontmatter not stripped"
  fi

  check
  if [ -n "$selected" ] && printf '%s\n' "$ctx" | grep -qxF "name: $selected"; then
    fail "test4: additionalContext still contains the frontmatter line 'name: $selected'"
  else
    pass "test4: additionalContext does not contain 'name: $selected'"
  fi
}

# =====================================================================
# Test 5 — randomness is real: 60 fresh rolls, at least 3 distinct tones.
#
# Chosen so a correct implementation (uniform pick among 17 tones) fails
# this bar with probability far below any flakiness budget, while a
# fixed-pick implementation always returns exactly 1 distinct tone and
# always fails it.
# =====================================================================
{
  declare -A seen=()
  for _i in $(seq 1 60); do
    home="$(new_tmp_dir)"
    sid="$(next_session_id)"
    run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" >/dev/null
    sel="$(cat "$(state_file_for "$home" "$sid")" 2>/dev/null)"
    [ -n "$sel" ] && seen["$sel"]=1
  done
  distinct=${#seen[@]}

  check
  if [ "$distinct" -ge 3 ]; then
    pass "test5: 60 fresh rolls produced $distinct distinct tones (>= 3)"
  else
    fail "test5: 60 fresh rolls produced only $distinct distinct tone(s), expected >= 3"
  fi
}

# =====================================================================
# Test 6 — resume does not re-roll: 20 runs, same known tone each time.
# =====================================================================
{
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  known="${TONES[0]}"
  mkdir -p "$(dirname "$(state_file_for "$home" "$sid")")"
  printf '%s\n' "$known" > "$(state_file_for "$home" "$sid")"

  all_same=1
  last_sysmsg=""
  for _i in $(seq 1 20); do
    out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"resume\"}")"
    sysmsg="$(printf '%s' "$out" | jq -r '.systemMessage // empty')"
    last_sysmsg="$sysmsg"
    case "$sysmsg" in
      *"$known"*) ;;
      *) all_same=0 ;;
    esac
  done
  final_state="$(cat "$(state_file_for "$home" "$sid")" 2>/dev/null)"

  check
  if [ "$all_same" -eq 1 ]; then
    pass "test6: 20 resume runs all returned the known tone ($known)"
  else
    fail "test6: at least one of 20 resume runs did not return the known tone ($known)"
  fi

  check
  if [ "$final_state" = "$known" ]; then
    pass "test6: state file still names the known tone after 20 resumes"
  else
    fail "test6: state file was rewritten to '$final_state', expected unchanged '$known'"
  fi

  # R8 — a resume did not just roll a tone, so systemMessage must not claim
  # it did. It should say "held", not "rolled".
  check
  case "$last_sysmsg" in
    *rolled*)
      fail "test6: resume's systemMessage ('$last_sysmsg') says 'rolled', but nothing was rolled"
      ;;
    *held*)
      pass "test6: resume's systemMessage ('$last_sysmsg') says 'held', not 'rolled'"
      ;;
    *)
      fail "test6: resume's systemMessage ('$last_sysmsg') contains neither 'rolled' nor 'held'"
      ;;
  esac
}

# =====================================================================
# Test 7 — stale state recovers: unknown tone in state file triggers a
# fresh roll instead of an error or empty output, and rewrites state.
# =====================================================================
{
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  stale="no-such-tone-xyz"
  mkdir -p "$(dirname "$(state_file_for "$home" "$sid")")"
  printf '%s\n' "$stale" > "$(state_file_for "$home" "$sid")"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}")"
  ec=$?
  ctx="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')"
  newval="$(cat "$(state_file_for "$home" "$sid")" 2>/dev/null)"

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq . >/dev/null 2>&1 && [ -n "$ctx" ]; then
    pass "test7: stale state produces a valid, non-empty roll rather than an error"
  else
    fail "test7: stale state did not recover cleanly (exit=$ec, out=$out)"
  fi

  check
  is_real=0
  for t in "${TONES[@]}"; do
    [ "$t" = "$newval" ] && is_real=1
  done
  if [ "$newval" != "$stale" ] && [ "$is_real" -eq 1 ]; then
    pass "test7: state file was rewritten to a real tone ($newval)"
  else
    fail "test7: state file after recovery is '$newval', expected a real tone != '$stale'"
  fi
}

# =====================================================================
# Test 8 — empty output-styles/ directory: no stdout, exit code 0.
# =====================================================================
{
  empty_root="$(new_tmp_dir)"
  mkdir -p "$empty_root/output-styles"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$empty_root" "{\"session_id\":\"$sid\",\"source\":\"startup\"}")"
  ec=$?

  check
  if [ -z "$out" ] && [ "$ec" -eq 0 ]; then
    pass "test8: empty catalogue produces no stdout and exit 0"
  else
    fail "test8: empty catalogue gave exit=$ec, out='$out' (expected empty output, exit 0)"
  fi
}

# =====================================================================
# Test 9 — malformed / empty stdin: exit code 0 either way.
# =====================================================================
{
  home="$(new_tmp_dir)"
  out="$(printf 'not { valid ] json at all' | HOME="$home" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$HANDLER" 2>/dev/null)"
  ec=$?

  check
  if [ "$ec" -eq 0 ]; then
    pass "test9: malformed (non-JSON) stdin still exits 0"
  else
    fail "test9: malformed stdin exited $ec, expected 0"
  fi

  home2="$(new_tmp_dir)"
  out2="$(printf '' | HOME="$home2" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$HANDLER" 2>/dev/null)"
  ec2=$?

  check
  if [ "$ec2" -eq 0 ]; then
    pass "test9: empty stdin still exits 0"
  else
    fail "test9: empty stdin exited $ec2, expected 0"
  fi
}

# =====================================================================
# Test 10 — a tone file with `"`, `\`, a literal newline, a literal TAB
# and another C0 control character round-trips: emitted JSON parses and
# .additionalContext reproduces the body exactly.
#
# The fixture is built here, in the test's own temp directory — no joke
# tone file is added to the shipped catalogue. Built with printf (not a
# quoted heredoc) so the tab (\t) and unit-separator (\x1f) control bytes
# actually land in the file as real bytes, not as their two-character
# spellings.
# =====================================================================
{
  fixture_root="$(new_tmp_dir)"
  mkdir -p "$fixture_root/output-styles"
  fixture_file="$fixture_root/output-styles/fixture-tone.md"

  {
    printf -- '---\n'
    printf -- 'name: fixture-tone\n'
    printf -- 'description: Round-trip escaping fixture for test-handler.sh.\n'
    printf -- '---\n'
    printf -- '\n'
    printf -- 'He said "hello" and meant it, then typed C:\\path\\to\\file without flinching.\n'
    printf -- 'A lone backslash \\ and a "quoted phrase" share this second line on purpose.\n'
    printf -- 'Column1\tColumn2\tColumn3 has a literal TAB between fields.\n'
    printf -- 'A unit-separator control character sits right here: \x1f — and then text.\n'
  } > "$fixture_file"

  # Expected body: same frontmatter-stripping rule the handler documents
  # (strip the two `---` lines and everything between them), applied here
  # with a plain awk one-liner — not the handler's own escaping logic —
  # so this is an independent check, not a restatement of it.
  expected_body_file="$(new_tmp_dir)/expected-body"
  awk '
    NR == 1 && $0 == "---" { infm = 1; next }
    infm && $0 == "---"    { infm = 0; next }
    infm                   { next }
    { print }
  ' "$fixture_file" > "$expected_body_file"

  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  out_file="$(new_tmp_dir)/handler-out.json"
  # CLAUDE_PROJECT_DIR must be set to an isolated directory, as every other
  # invocation in this file does: unset, the handler falls back to $PWD, so
  # running the suite from a checkout whose own .claude/settings.local.json
  # sets outputStyle (which is what /config writes, and what this repository's
  # working copy has) makes the handler correctly stand down and emit nothing
  # — and this test then reports a body mismatch that has nothing to do with
  # escaping. Green in CI (a fresh checkout has no .claude/), red for anyone
  # who has ever picked an output style here.
  printf '{"session_id":"%s","source":"startup"}' "$sid" \
    | HOME="$home" CLAUDE_PLUGIN_ROOT="$fixture_root" \
      CLAUDE_PROJECT_DIR="$DEFAULT_PROJECT_DIR" bash "$HANDLER" > "$out_file"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && jq . "$out_file" >/dev/null 2>&1; then
    pass "test10: fixture tone produces valid, parseable JSON"
  else
    fail "test10: fixture tone handler run failed (exit=$ec)"
  fi

  actual_body_file="$(new_tmp_dir)/actual-body"
  # -j: raw output, no implicit trailing newline added by jq, so this is
  # exactly the bytes of the JSON string value — a fair byte-for-byte
  # comparison against the plain-file expected_body_file above.
  jq -j '.hookSpecificOutput.additionalContext' "$out_file" > "$actual_body_file" 2>/dev/null

  check
  if diff -q "$expected_body_file" "$actual_body_file" >/dev/null 2>&1; then
    pass "test10: .additionalContext reproduces the fixture body exactly (quotes, backslash, newline)"
  else
    fail "test10: .additionalContext does not match the fixture body exactly"
    echo "  --- expected ---"
    cat "$expected_body_file"
    echo "  --- actual ---"
    cat "$actual_body_file"
  fi
}

# =====================================================================
# Test 11 — the __off__ token (controller ruling R4): "off" is represented
# explicitly in the state file, not by deleting it. Absence still means
# "roll" (test 7 covers that); __off__ means "stay untoned", except on a
# fresh startup, which always rolls and must never let a leftover __off__
# leak into the new session.
# =====================================================================
{
  for src in compact clear resume; do
    home="$(new_tmp_dir)"
    sid="$(next_session_id)"
    mkdir -p "$(dirname "$(state_file_for "$home" "$sid")")"
    printf '__off__\n' > "$(state_file_for "$home" "$sid")"

    out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"$src\"}")"
    ec=$?
    state_after="$(cat "$(state_file_for "$home" "$sid")" 2>/dev/null)"

    check
    if [ -z "$out" ] && [ "$ec" -eq 0 ]; then
      pass "test11: source=$src with __off__ state produces no stdout and exit 0"
    else
      fail "test11: source=$src with __off__ state gave exit=$ec, out='$out' (expected empty output, exit 0)"
    fi

    check
    if [ "$state_after" = "__off__" ]; then
      pass "test11: source=$src leaves the __off__ state file untouched"
    else
      fail "test11: source=$src rewrote the state file to '$state_after', expected it to stay __off__"
    fi
  done

  # source=startup must roll a real tone regardless of a leftover __off__,
  # and must overwrite the state file with that tone (never leave __off__
  # in place for a new session).
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  mkdir -p "$(dirname "$(state_file_for "$home" "$sid")")"
  printf '__off__\n' > "$(state_file_for "$home" "$sid")"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}")"
  ec=$?
  ctx="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')"
  state_after="$(cat "$(state_file_for "$home" "$sid")" 2>/dev/null)"

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq . >/dev/null 2>&1 && [ -n "$ctx" ]; then
    pass "test11: source=startup with a leftover __off__ state still emits a valid, non-empty roll"
  else
    fail "test11: source=startup with a leftover __off__ state failed to roll (exit=$ec, out=$out)"
  fi

  check
  is_real=0
  for t in "${TONES[@]}"; do
    [ "$t" = "$state_after" ] && is_real=1
  done
  if [ "$state_after" != "__off__" ] && [ "$is_real" -eq 1 ]; then
    pass "test11: source=startup overwrote the __off__ state file with a real tone ($state_after)"
  else
    fail "test11: source=startup left the state file as '$state_after', expected a real tone != __off__"
  fi
}

# =====================================================================
# Test 12 — I4: HOME unset must not crash the handler. Under `set -u`, a
# bare `"${HOME}"` reference aborts the whole script with an "unbound
# variable" error and a non-zero exit the moment HOME isn't set — a
# violation of "every failure path exits 0" (stated in this script's own
# header and in the design spec). `env -u HOME` runs the handler with HOME
# genuinely absent from its environment, not merely empty.
# =====================================================================
{
  sid="$(next_session_id)"
  out="$(printf '{"session_id":"%s","source":"startup"}' "$sid" \
    | env -u HOME CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$HANDLER" 2>/dev/null)"
  ec=$?

  check
  if [ "$ec" -eq 0 ]; then
    pass "test12: HOME unset still exits 0"
  else
    fail "test12: HOME unset exited $ec, expected 0"
  fi
}

# =====================================================================
# Test 13 — M4: a path-traversal-shaped session_id must not escape the
# state directory. The state file path is composed as
# "$state_dir/$session_id" with no sanitisation before this fix, so a
# session_id of "../../escaped" wrote outside ~/.claude/tone-roulette/.
# session_id is expected to be a UUID from Claude Code, not attacker
# input, but the fix applies the same `tr` the $PWD fallback already uses,
# so this asserts the state file lands inside the state directory either
# way.
# =====================================================================
{
  home="$(new_tmp_dir)"
  hostile_sid="../../escaped"
  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$hostile_sid\",\"source\":\"startup\"}")"
  ec=$?

  state_dir="$home/.claude/tone-roulette"
  escaped_path="$home/escaped"

  check
  if [ "$ec" -eq 0 ] && [ ! -e "$escaped_path" ]; then
    pass "test13: traversal-shaped session_id did not escape to $escaped_path"
  else
    fail "test13: traversal-shaped session_id produced $escaped_path (exit=$ec) — escaped the state directory"
  fi

  check
  # Exactly one file should exist directly under the state directory (the
  # sanitised name), and it must resolve inside state_dir, not above it.
  # find, not a glob: the sanitised name starts with a literal '.'
  # (".." with "/" replaced by "_"), and bash's default (non-dotglob) "*"
  # silently skips dotfiles, which would make this check pass for the
  # wrong reason (nothing matched) rather than actually verifying anything.
  written_count=0
  wrote_inside=0
  while IFS= read -r f; do
    [ -e "$f" ] || continue
    written_count=$((written_count + 1))
    case "$(cd "$(dirname "$f")" && pwd)" in
      "$state_dir") wrote_inside=1 ;;
    esac
  done < <(find "$state_dir" -mindepth 1 -maxdepth 1 2>/dev/null)
  if [ "$written_count" -ge 1 ] && [ "$wrote_inside" -eq 1 ]; then
    pass "test13: the sanitised session_id's state file landed inside $state_dir"
  else
    fail "test13: expected a state file inside $state_dir, found $written_count candidate(s), inside=$wrote_inside"
  fi
}

# =====================================================================
# Test 14 — issue #6: prune by mtime on startup. A state file older than
# the 30-day threshold is gone by the time a fresh `startup` run finishes.
# =====================================================================
{
  home="$(new_tmp_dir)"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir"

  stale_file="$state_dir/stale-old-session"
  printf '%s\n' "${TONES[0]}" > "$stale_file"
  touch -t "$(days_ago_ts 40)" "$stale_file"

  cur_sid="$(next_session_id)"
  run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}" >/dev/null
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ ! -e "$stale_file" ]; then
    pass "test14: a 40-day-old state file is removed by a startup run"
  else
    fail "test14: expected $stale_file removed by a startup run (exit=$ec)"
  fi
}

# =====================================================================
# Test 15 — a recent state file (1 day old) is kept.
# =====================================================================
{
  home="$(new_tmp_dir)"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir"

  recent_file="$state_dir/recent-session"
  printf '%s\n' "${TONES[0]}" > "$recent_file"
  touch -t "$(days_ago_ts 1)" "$recent_file"

  cur_sid="$(next_session_id)"
  run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}" >/dev/null
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -e "$recent_file" ]; then
    pass "test15: a 1-day-old state file is kept by a startup run"
  else
    fail "test15: expected $recent_file to survive a startup run (exit=$ec)"
  fi
}

# =====================================================================
# Test 16 — the current session's own file is kept even when its mtime
# was 40 days old before this run (design decision #3: never removed,
# regardless of age).
# =====================================================================
{
  home="$(new_tmp_dir)"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir"

  cur_sid="$(next_session_id)"
  cur_file="$state_dir/$cur_sid"
  printf '%s\n' "${TONES[0]}" > "$cur_file"
  touch -t "$(days_ago_ts 40)" "$cur_file"

  run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}" >/dev/null
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -e "$cur_file" ]; then
    pass "test16: the current session's own state file survives a startup run even though its prior mtime was 40 days old"
  else
    fail "test16: expected $cur_file (current session) to survive (exit=$ec)"
  fi
}

# =====================================================================
# Test 17 — resume, clear and compact never prune: an unrelated 40-day-old
# state file is left alone on each of those sources (prune runs only on
# startup, per design decision #2).
# =====================================================================
{
  for src in resume clear compact; do
    home="$(new_tmp_dir)"
    state_dir="$home/.claude/tone-roulette"
    mkdir -p "$state_dir"

    other_file="$state_dir/other-old-session-$src"
    printf '%s\n' "${TONES[0]}" > "$other_file"
    touch -t "$(days_ago_ts 40)" "$other_file"

    cur_sid="$(next_session_id)"
    cur_file="$state_dir/$cur_sid"
    printf '%s\n' "${TONES[0]}" > "$cur_file"

    run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"$src\"}" >/dev/null
    ec=$?

    check
    if [ "$ec" -eq 0 ] && [ -e "$other_file" ]; then
      pass "test17: source=$src does not prune a 40-day-old unrelated state file"
    else
      fail "test17: source=$src removed $other_file (exit=$ec) — prune must not run outside startup"
    fi
  done
}

# =====================================================================
# Test 18 — nothing outside the state directory is touched: a plain old
# file directly in $HOME, and a symlink inside the state directory
# pointing at a file outside it, both survive a startup run that prunes.
# This is the assertion that matters most.
# =====================================================================
{
  home="$(new_tmp_dir)"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir"

  outside_file="$home/outside-plain-file"
  printf 'do not touch\n' > "$outside_file"
  touch -t "$(days_ago_ts 40)" "$outside_file"

  outside_target="$home/outside-symlink-target"
  printf 'do not touch either\n' > "$outside_target"
  touch -t "$(days_ago_ts 40)" "$outside_target"

  link_in_state="$state_dir/escape-link"
  ln -s "$outside_target" "$link_in_state"
  touch -h -t "$(days_ago_ts 40)" "$link_in_state" 2>/dev/null

  cur_sid="$(next_session_id)"
  run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}" >/dev/null
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -e "$outside_file" ]; then
    pass "test18: a plain old file directly in \$HOME (outside the state dir) survives a startup run"
  else
    fail "test18: $outside_file was removed by a startup run (exit=$ec) — prune escaped the state directory"
  fi

  check
  if [ -e "$outside_target" ]; then
    pass "test18: the file a symlink inside the state dir points at survives a startup run"
  else
    fail "test18: $outside_target was removed by a startup run — a symlink in the state dir was followed"
  fi
}

# =====================================================================
# Test 19 — exit code 0 and valid JSON output are unaffected when a stale
# file is present and gets pruned.
# =====================================================================
{
  home="$(new_tmp_dir)"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir"

  stale_file="$state_dir/prune-json-check-old"
  printf '%s\n' "${TONES[0]}" > "$stale_file"
  touch -t "$(days_ago_ts 40)" "$stale_file"

  cur_sid="$(next_session_id)"
  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq . >/dev/null 2>&1; then
    pass "test19: exit code 0 and valid JSON output are unaffected when a stale file gets pruned"
  else
    fail "test19: startup run with a stale file to prune gave exit=$ec, out='$out'"
  fi
}

# =====================================================================
# Test 20 — pruning a directory that contains only the current session's
# file leaves it intact (nothing else exists there to remove, and the
# current file itself is not removed).
# =====================================================================
{
  home="$(new_tmp_dir)"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir"

  cur_sid="$(next_session_id)"
  cur_file="$state_dir/$cur_sid"

  run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}" >/dev/null
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -e "$cur_file" ]; then
    entries="$(find "$state_dir" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$entries" -eq 1 ]; then
      pass "test20: a state directory containing only the current session's file is left intact (1 entry)"
    else
      fail "test20: expected exactly 1 entry in $state_dir after the run, found $entries"
    fi
  else
    fail "test20: expected $cur_file to exist after the run (exit=$ec)"
  fi
}

# =====================================================================
# Test 21 — issue #7 item 1: a closed fd 0 must not hang the handler.
# Bounded on purpose: a regression here must fail the suite, not hang it.
# The handler runs in the background with stdin closed (0<&-, not merely
# empty) and is force-killed if it hasn't exited within ~2s.
# =====================================================================
{
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  out_dir="$(new_tmp_dir)"
  out_file="$out_dir/test21-out"
  ec_file="$out_dir/test21-ec"

  ( HOME="$home" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$HANDLER" 0<&- >"$out_file" 2>/dev/null
    echo "$?" >"$ec_file" ) &
  hpid=$!

  hung=1
  for _i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if ! kill -0 "$hpid" 2>/dev/null; then
      hung=0
      break
    fi
    sleep 0.1
  done

  check
  if [ "$hung" -eq 1 ]; then
    kill -9 "$hpid" 2>/dev/null
    wait "$hpid" 2>/dev/null
    fail "test21: handler with closed stdin did not exit within ~2s (hang reproduced)"
  else
    wait "$hpid" 2>/dev/null
    ec21="$(cat "$ec_file" 2>/dev/null)"
    if [ "$ec21" = "0" ]; then
      pass "test21: handler with closed stdin exits 0 without hanging"
    else
      fail "test21: handler with closed stdin exited $ec21, expected 0"
    fi
  fi
}

# =====================================================================
# Test 22 — issue #7 item 6, variant 1: pruning must not recurse into
# subdirectories of the state directory. A 40-day-old file inside a
# subdirectory must survive a startup run (a handler with `-maxdepth 1`
# removed from its `find` invocation would delete it).
# =====================================================================
{
  home="$(new_tmp_dir)"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir/nested"

  nested_stale="$state_dir/nested/old-in-subdir"
  printf '%s\n' "${TONES[0]}" > "$nested_stale"
  touch -t "$(days_ago_ts 40)" "$nested_stale"

  cur_sid="$(next_session_id)"
  run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}" >/dev/null
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -e "$nested_stale" ]; then
    pass "test22: a 40-day-old file inside a subdirectory of the state dir survives a startup run"
  else
    fail "test22: $nested_stale was removed by a startup run (exit=$ec) — prune recursed into a subdirectory"
  fi
}

# =====================================================================
# Test 23 — issue #7 item 6, variant 2: the current-session exclusion
# must actually be exercised. Test 16 does not exercise it: a startup run
# rewrites the current session's own state file, which refreshes its
# mtime and undoes the 40-day ageing before the prune ever runs, so a
# handler with the `! -name` exclusion removed entirely still passes
# test 16. Here the current session's file is made unwritable before the
# run, so the run's own write attempt fails silently and cannot refresh
# the mtime — the file stays genuinely 40 days old going into the prune,
# and only the exclusion (not an accidental mtime refresh) can save it.
# =====================================================================
{
  home="$(new_tmp_dir)"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir"

  cur_sid="$(next_session_id)"
  cur_file="$state_dir/$cur_sid"
  printf '%s\n' "${TONES[0]}" > "$cur_file"
  touch -t "$(days_ago_ts 40)" "$cur_file"
  chmod 400 "$cur_file"

  run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}" >/dev/null
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -e "$cur_file" ]; then
    pass "test23: the current session's own 40-day-old state file survives a startup run when it could not have been rewritten (exclusion actually exercised)"
  else
    fail "test23: $cur_file was removed by a startup run (exit=$ec) — the current-session exclusion did not fire"
  fi

  chmod 700 "$cur_file" 2>/dev/null
}

# =====================================================================
# Test 24 — issue #7 item 6, variant 3: quoting. `$state_dir` and
# `$(basename ...)` must be quoted in the find invocation, or a state
# directory path containing a space or a glob character breaks pruning
# (word-splitting and/or glob expansion of the unquoted path).
# =====================================================================
{
  home_base="$(new_tmp_dir)"
  home="$home_base/weird home *name"
  mkdir -p "$home"
  state_dir="$home/.claude/tone-roulette"
  mkdir -p "$state_dir"

  stale_file="$state_dir/stale-in-weird-home"
  printf '%s\n' "${TONES[0]}" > "$stale_file"
  touch -t "$(days_ago_ts 40)" "$stale_file"

  cur_sid="$(next_session_id)"
  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$cur_sid\",\"source\":\"startup\"}")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ ! -e "$stale_file" ]; then
    pass "test24: a 40-day-old state file is still pruned when \$HOME contains a space and a glob character"
  else
    fail "test24: $stale_file survived a startup run under a space+glob \$HOME (exit=$ec) — unquoted \$state_dir/\$(basename ...) breaks pruning"
  fi

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq . >/dev/null 2>&1; then
    pass "test24: handler output stays valid JSON when \$HOME contains a space and a glob character"
  else
    fail "test24: handler output was not valid JSON under a space+glob \$HOME (exit=$ec, out=$out)"
  fi
}

# project_dir_with_output_style FILE_BASENAME OUTPUT_STYLE_JSON_VALUE
# -> a fresh project dir whose .claude/<FILE_BASENAME> sets "outputStyle"
# to the given already-JSON-quoted value (e.g. '"pirate"' or '""').
project_dir_with_output_style() {
  local file_basename="$1" value_json="$2" dir
  dir="$(new_tmp_dir)"
  mkdir -p "$dir/.claude"
  printf '{\n  "outputStyle": %s\n}\n' "$value_json" > "$dir/.claude/$file_basename"
  printf '%s' "$dir"
}

# =====================================================================
# Test 25 — the stand-down: an output style set in project local settings
# (.claude/settings.local.json, the file `/config` itself writes to) means
# a `startup` run emits nothing at all and exits 0. No systemMessage, no
# additionalContext, no rolled tone, no state file written.
# =====================================================================
{
  proj="$(project_dir_with_output_style "settings.local.json" '"pirate"')"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ]; then
    pass "test25: startup with an output style set in settings.local.json prints nothing and exits 0"
  else
    fail "test25: expected empty output and exit 0, got exit=$ec out='$out'"
  fi

  check
  if [ ! -e "$(state_file_for "$home" "$sid")" ]; then
    pass "test25: no state file is written when the output style is already chosen"
  else
    fail "test25: a state file was written even though the output style was already chosen"
  fi
}

# =====================================================================
# Test 26 — the contrast case: with no output style set anywhere (a fresh
# project dir with no .claude/settings*.json at all), startup still rolls
# exactly as before. Proves test 25's silence comes from detecting the
# chosen style, not from some unrelated regression that silences every run.
# =====================================================================
{
  proj="$(new_tmp_dir)"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq -e '.systemMessage | test("rolled")' >/dev/null 2>&1; then
    pass "test26: startup with no output style set anywhere still rolls and announces it"
  else
    fail "test26: expected a rolled-tone announcement with no output style set, got exit=$ec out=$out"
  fi
}

# =====================================================================
# Test 27 — the fight this whole change exists to end: an output style
# chosen mid-session must win over a state file that still holds an
# earlier rolled tone, on `resume` (not just `startup`). Before this
# change, resume/clear/compact always re-injected the state file's tone
# regardless of what the user had since chosen natively.
# =====================================================================
{
  proj="$(project_dir_with_output_style "settings.local.json" '"noir-detective"')"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  sfile="$(state_file_for "$home" "$sid")"
  mkdir -p "$(dirname "$sfile")"
  printf '%s\n' "${TONES[0]}" > "$sfile"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"resume\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ]; then
    pass "test27: resume with an output style set prints nothing and exits 0, even with a rolled tone still on file"
  else
    fail "test27: expected silence on resume once a style is chosen, got exit=$ec out='$out'"
  fi

  check
  existing="$(cat "$sfile" 2>/dev/null)"
  if [ "$existing" = "${TONES[0]}" ]; then
    pass "test27: the state file is left exactly as it was — resume does not touch it once a style is chosen"
  else
    fail "test27: the state file changed from '${TONES[0]}' to '$existing'"
  fi
}

# =====================================================================
# Test 28 — user settings (~/.claude/settings.json) is checked too, not
# only the project-level files: /config isn't the only way outputStyle
# gets set by hand, and a user-level choice must stand down just the same.
# =====================================================================
{
  home="$(new_tmp_dir)"
  mkdir -p "$home/.claude"
  printf '{"outputStyle":"Explanatory"}' > "$home/.claude/settings.json"
  proj="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ]; then
    pass "test28: an output style set only in ~/.claude/settings.json also stands the hook down"
  else
    fail "test28: expected silence for a user-settings-only output style, got exit=$ec out='$out'"
  fi
}

# =====================================================================
# Test 29 — false-positive guard: a settings file existing at all must not
# be mistaken for an output style being set. A settings.json with unrelated
# keys and no "outputStyle" key must still roll.
# =====================================================================
{
  proj="$(new_tmp_dir)"
  mkdir -p "$proj/.claude"
  printf '{"model": "opus", "theme": "dark"}' > "$proj/.claude/settings.json"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq -e '.systemMessage | test("rolled")' >/dev/null 2>&1; then
    pass "test29: a settings.json with no outputStyle key still rolls (file presence alone is not the signal)"
  else
    fail "test29: expected a roll when outputStyle is absent from an existing settings file, got exit=$ec out=$out"
  fi
}

# =====================================================================
# Test 30 — edge case: an explicit but empty "outputStyle" value counts as
# not set, and the hook still rolls. Nothing in the real product is known
# to write an empty string here, but the extraction must not treat it as
# a chosen style either.
# =====================================================================
{
  proj="$(project_dir_with_output_style "settings.local.json" '""')"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq -e '.systemMessage | test("rolled")' >/dev/null 2>&1; then
    pass "test30: an empty outputStyle value is treated as not set, and the hook still rolls"
  else
    fail "test30: expected a roll for an empty outputStyle value, got exit=$ec out=$out"
  fi
}

# raw_settings_project RAW_CONTENT -> a fresh project dir whose
# .claude/settings.local.json holds exactly RAW_CONTENT, byte for byte (no
# added framing, unlike project_dir_with_output_style above) — used to plant
# line-layout variants that a fixed-template helper can't produce.
raw_settings_project() {
  local raw="$1" dir
  dir="$(new_tmp_dir)"
  mkdir -p "$dir/.claude"
  printf '%s' "$raw" > "$dir/.claude/settings.local.json"
  printf '%s' "$dir"
}

# =====================================================================
# Test 31 — line-layout: the key and the colon split across lines
# (`"outputStyle"\n: "pirate"`). Legal JSON — whitespace, including a
# newline, is insignificant between a key and its colon. A single-line
# `grep -o` never sees this match because the key and the colon fall on
# different lines; the fix flattens newlines to spaces before matching.
# =====================================================================
{
  proj="$(raw_settings_project "$(printf '{"outputStyle"\n : "pirate"}\n')")"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ]; then
    pass "test31: key and colon split across lines still stands the hook down"
  else
    fail "test31: expected silence with the key and colon on separate lines, got exit=$ec out='$out'"
  fi

  check
  if [ ! -e "$(state_file_for "$home" "$sid")" ]; then
    pass "test31: no state file is written when the split-layout output style is already chosen"
  else
    fail "test31: a state file was written despite the key/colon split output style being set"
  fi
}

# =====================================================================
# Test 32 — line-layout: the colon and the value split across lines
# (`"outputStyle":\n "pirate"`). Same reasoning as test 31, one token pair
# later.
# =====================================================================
{
  proj="$(raw_settings_project "$(printf '{"outputStyle":\n "pirate"}\n')")"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ]; then
    pass "test32: colon and value split across lines still stands the hook down"
  else
    fail "test32: expected silence with the colon and value on separate lines, got exit=$ec out='$out'"
  fi
}

# =====================================================================
# Test 33 — line-layout: a pretty-printed, multi-key settings file with
# `outputStyle` among other keys, and its own colon/value split onto a
# further-indented continuation line — the shape a formatter produces for
# a file that also happens to have other keys around it. Guards two things
# at once: that flattening does not glue adjacent keys together into a
# false or corrupted match, and that the split-value case still stands
# down when it isn't the first or only key in the file.
# =====================================================================
{
  proj="$(raw_settings_project "$(printf '{\n  "model": "opus",\n  "outputStyle":\n    "noir-detective",\n  "theme": "dark"\n}\n')")"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ]; then
    pass "test33: a pretty-printed multi-key file with a split outputStyle value still stands the hook down"
  else
    fail "test33: expected silence for a pretty-printed multi-key file with a split outputStyle value, got exit=$ec out='$out'"
  fi
}

# =====================================================================
# Test 34 — line-layout: CRLF line endings, with the key, colon and value
# split across those CRLF-terminated lines. CRLF alone (single line) was
# already handled before this fix; the untested — and previously broken —
# combination is CRLF *and* a line split together.
# =====================================================================
{
  proj="$(raw_settings_project "$(printf '{"outputStyle"\r\n:\r\n"pirate"\r\n}\r\n')")"
  home="$(new_tmp_dir)"
  sid="$(next_session_id)"

  out="$(run_handler "$home" "$PLUGIN_ROOT" "{\"session_id\":\"$sid\",\"source\":\"startup\"}" "$proj")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ]; then
    pass "test34: CRLF line endings with the key/colon/value split across lines still stands the hook down"
  else
    fail "test34: expected silence for a CRLF, line-split outputStyle value, got exit=$ec out='$out'"
  fi
}

# =====================================================================
# Test 35 — a missing tone-common.sh must not turn every session start
# into stderr noise. A copy of the handler in a fixture directory with no
# sibling tone-common.sh (simulating a partial install) must produce
# empty stdout, empty stderr, and exit 0 — see the design spec's Error
# handling table row for "Shared helper file missing or unreadable".
# CLAUDE_PLUGIN_ROOT still points at the real PLUGIN_ROOT so the
# catalogue itself is fine; only the sibling tone-common.sh is absent.
# =====================================================================
{
  fixture_dir="$(new_tmp_dir)/hooks-handlers"
  mkdir -p "$fixture_dir"
  cp "$HANDLER" "$fixture_dir/session-start.sh"
  # deliberately: no tone-common.sh copied alongside it

  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  err_file="$(new_tmp_dir)/stderr35"
  out="$(printf '{"session_id":"%s","source":"startup"}' "$sid" \
    | HOME="$home" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$DEFAULT_PROJECT_DIR" \
      bash "$fixture_dir/session-start.sh" 2>"$err_file")"
  ec=$?
  err="$(cat "$err_file" 2>/dev/null)"

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ] && [ -z "$err" ]; then
    pass "test35: missing tone-common.sh produces empty stdout, empty stderr, exit 0"
  else
    fail "test35: missing tone-common.sh gave exit=$ec, stdout='$out', stderr='$err'"
  fi
}

# =====================================================================
# Test 36 — a tone-common.sh truncated mid-function is syntactically
# broken, so `source` itself fails (a parse error, reported before any of
# the file executes) — this is the "corrupt" half of the missing-or-
# unreadable row; the guard's own `2>/dev/null` plus checking the
# source's exit status must swallow that failure rather than let it
# reach stderr.
# =====================================================================
{
  fixture_dir="$(new_tmp_dir)/hooks-handlers"
  mkdir -p "$fixture_dir"
  cp "$HANDLER" "$fixture_dir/session-start.sh"
  head -c 400 "$PLUGIN_ROOT/hooks-handlers/tone-common.sh" > "$fixture_dir/tone-common.sh"

  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  err_file="$(new_tmp_dir)/stderr36"
  out="$(printf '{"session_id":"%s","source":"startup"}' "$sid" \
    | HOME="$home" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$DEFAULT_PROJECT_DIR" \
      bash "$fixture_dir/session-start.sh" 2>"$err_file")"
  ec=$?
  err="$(cat "$err_file" 2>/dev/null)"

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ] && [ -z "$err" ]; then
    pass "test36: a tone-common.sh truncated into a syntax error produces empty stdout, empty stderr, exit 0"
  else
    fail "test36: truncated (syntax-broken) tone-common.sh gave exit=$ec, stdout='$out', stderr='$err'"
  fi
}

# =====================================================================
# Test 37 — a tone-common.sh that sources cleanly (no syntax error) but
# defines none of the functions this handler needs — the case a
# truncation lands on a clean statement boundary, which step 2 of the
# guard (checking the source's own exit status) alone would not catch.
# Only the by-name `command -v` check catches this one.
# =====================================================================
{
  fixture_dir="$(new_tmp_dir)/hooks-handlers"
  mkdir -p "$fixture_dir"
  cp "$HANDLER" "$fixture_dir/session-start.sh"
  printf '#!/usr/bin/env bash\n# corrupted: no functions defined\n' > "$fixture_dir/tone-common.sh"

  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  err_file="$(new_tmp_dir)/stderr37"
  out="$(printf '{"session_id":"%s","source":"startup"}' "$sid" \
    | HOME="$home" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$DEFAULT_PROJECT_DIR" \
      bash "$fixture_dir/session-start.sh" 2>"$err_file")"
  ec=$?
  err="$(cat "$err_file" 2>/dev/null)"

  check
  if [ "$ec" -eq 0 ] && [ -z "$out" ] && [ -z "$err" ]; then
    pass "test37: a functionless (but syntactically valid) tone-common.sh produces empty stdout, empty stderr, exit 0"
  else
    fail "test37: functionless tone-common.sh gave exit=$ec, stdout='$out', stderr='$err'"
  fi
}

# =====================================================================
# Test 38 — normal operation is unaffected: a handler copy with its real,
# intact sibling tone-common.sh alongside it still rolls and announces
# exactly as before. Confirms the guard added around the source is inert
# when the sourced file is fine — tests 1-34 already prove this against
# HANDLER directly; this proves the *copied* handler (same guard, fresh
# process, fresh fixture dir) behaves identically.
# =====================================================================
{
  fixture_dir="$(new_tmp_dir)/hooks-handlers"
  mkdir -p "$fixture_dir"
  cp "$HANDLER" "$fixture_dir/session-start.sh"
  cp "$PLUGIN_ROOT/hooks-handlers/tone-common.sh" "$fixture_dir/tone-common.sh"

  home="$(new_tmp_dir)"
  sid="$(next_session_id)"
  out="$(printf '{"session_id":"%s","source":"startup"}' "$sid" \
    | HOME="$home" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$DEFAULT_PROJECT_DIR" \
      bash "$fixture_dir/session-start.sh")"
  ec=$?

  check
  if [ "$ec" -eq 0 ] && printf '%s' "$out" | jq -e '.systemMessage | test("rolled")' >/dev/null 2>&1; then
    pass "test38: with an intact sibling tone-common.sh, the source guard does not change normal roll behaviour"
  else
    fail "test38: expected a normal roll with an intact tone-common.sh, got exit=$ec out=$out"
  fi
}

echo ""
echo "Ran $check_count assertions."
if [ "$fail_count" -gt 0 ]; then
  echo "RESULT: FAILED ($fail_count failing assertion(s))"
  exit 1
fi

echo "RESULT: ALL CHECKS PASSED"
exit 0
