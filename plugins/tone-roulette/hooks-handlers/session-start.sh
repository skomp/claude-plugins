#!/usr/bin/env bash
#
# tone-roulette SessionStart handler.
#
# Reads the SessionStart hook JSON from stdin, rolls (or resumes) a
# conversational tone from the plugin's output-styles catalogue, persists the
# choice per session, and emits a JSON object on stdout carrying a one-line
# announcement (`systemMessage`) and the tone body with its YAML frontmatter
# stripped (`hookSpecificOutput.additionalContext`). Stands down entirely —
# prints nothing, does nothing — when the user has already chosen a Claude
# Code output style through the harness's own settings mechanism; see
# output_style_is_set() in tone-common.sh (sourced below).
#
# Contract (see docs/superpowers/specs/2026-09-13-tone-roulette-design.md):
#   - bash + coreutils only. No jq, no python, no `shuf` (absent on the
#     target machine) — randomness comes from $RANDOM.
#   - Every failure path exits 0. On a fatal problem this script prints
#     nothing and exits 0.
#   - No tone text is hardcoded here: the catalogue in output-styles/*.md is
#     the only source of tone names and bodies.
#   - Never rolls or re-injects over a tone the user chose deliberately via
#     the `outputStyle` settings key (by `/config`, by hand-editing a
#     settings file, or by any other means) — the plugin only ever manages
#     the *rolled* tone, never a *chosen* one.
#
# Catalogue location: ${CLAUDE_PLUGIN_ROOT}/output-styles when
# CLAUDE_PLUGIN_ROOT is set (the normal case — Claude Code sets it when it
# runs this hook), falling back to the directory next to this script so the
# handler also works invoked standalone. Tests point CLAUDE_PLUGIN_ROOT at an
# isolated fixture directory so they never touch the shipped catalogue.

set -u

# --- Shared helpers (get_output_style_value/output_style_is_set,
#     sanitize_id, resolve_session_id, tone_state_dir, tone_is_active) live
#     in tone-common.sh, sourced from the plugin's own directory so this
#     handler works both under CLAUDE_PLUGIN_ROOT and invoked standalone.
#     They were extracted from here verbatim (not rewritten) once a second
#     handler — hooks-handlers/user-prompt-submit.sh — needed the exact
#     same "has the user explicitly chosen an output style, and what is
#     this session's id" detection this file always used; see
#     tone-common.sh's own header for the full rationale each function
#     used to carry inline here, and
#     docs/superpowers/specs/2026-09-13-tone-roulette-design.md's
#     "Detecting a chosen style" section for the exactness argument behind
#     the grep+sed pull. output_style_is_set() below is the same
#     boolean-only check this file always called at this point: when it
#     signals a style is set, Claude Code's own output-style machinery
#     owns the tone for this session and this hook must get out of the way
#     entirely — on every source (startup, resume, clear, compact, fork),
#     not just startup. Re-injecting the state file's tone over a
#     deliberate choice on resume/clear/compact is exactly the bug this
#     guards against. ---
_TONE_COMMON_DIR="${BASH_SOURCE[0]%/*}"
[ "$_TONE_COMMON_DIR" = "${BASH_SOURCE[0]}" ] && _TONE_COMMON_DIR="."
_TONE_COMMON_DIR="$(cd "$_TONE_COMMON_DIR" && pwd)"
_TONE_COMMON_FILE="$_TONE_COMMON_DIR/tone-common.sh"

# --- Guard the source: a missing, unreadable, truncated or otherwise
#     corrupt tone-common.sh must never put a line on stderr or a nonzero
#     exit onto every session start — a partial plugin install degrades to
#     silence, same as every other fatal condition this handler already
#     treats that way (see Error handling in the design spec).
#       1. Read test before sourcing: cheaply catches "missing" (and
#          "unreadable", e.g. wrong permissions) without relying on the
#          `source` builtin's own error path at all.
#       2. `2>/dev/null` on the source itself, plus checking its own exit
#          status: a corrupt file can still fail to source (a syntax error
#          from a bad truncation point) even though it passed the read
#          test above — bash detects that at parse time, before executing
#          anything in the file, and reports it with a nonzero return from
#          the `.` builtin and a message on stderr, both handled here.
#       3. A `command -v` check by name, after a *successful* source: the
#          truncated-but-syntactically-valid case (cut at a point that
#          leaves the file parseable but drops one or more function
#          definitions) sources cleanly and returns 0, so step 2 alone
#          would miss it. This checks that every function this handler
#          actually calls below (output_style_is_set, resolve_session_id,
#          tone_state_dir) exists before relying on any of them. ---
if [ ! -r "$_TONE_COMMON_FILE" ]; then
  exit 0
fi
# shellcheck source=./tone-common.sh
. "$_TONE_COMMON_FILE" 2>/dev/null || exit 0
if ! command -v output_style_is_set >/dev/null 2>&1 \
  || ! command -v resolve_session_id >/dev/null 2>&1 \
  || ! command -v tone_state_dir >/dev/null 2>&1; then
  exit 0
fi

main() {
  local script_dir styles_dir state_dir input session_id source_val state_file
  local tones=() f base existing selected count idx off_token is_off rolled
  local _source_re
  local tone_file body escaped_body sys_message escaped_sys_message

  # --- Stand down entirely when an output style is explicitly set. This
  #     must run before anything else in main(): before the catalogue is
  #     even read, before stdin is parsed, and regardless of `source` — a
  #     chosen style pre-empts both the roll path and the resume path. ---
  if output_style_is_set; then
    return 0
  fi

  script_dir="$_TONE_COMMON_DIR"

  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    styles_dir="${CLAUDE_PLUGIN_ROOT}/output-styles"
  else
    styles_dir="$(cd "$script_dir/.." 2>/dev/null && pwd)/output-styles"
  fi

  # --- Read the catalogue. Empty/missing catalogue is fatal: nothing to
  #     announce, nothing to inject. Print nothing, exit 0. ---
  tones=()
  if [ -d "$styles_dir" ]; then
    # --- Parameter expansion, not `basename`: this loop runs once per
    #     catalogue entry, and forking basename 20 times was roughly half
    #     the handler's entire wall time (~2.6ms per fork on macOS).
    #     "${f##*/}" strips the directory and "${b%.md}" the suffix —
    #     exactly what `basename "$f" .md` returned for these paths. ---
    for f in "$styles_dir"/*.md; do
      [ -e "$f" ] || continue
      base="${f##*/}"
      tones+=("${base%.md}")
    done
  fi
  count=${#tones[@]}
  if [ "$count" -eq 0 ]; then
    return 0
  fi

  # --- Read stdin (the hook JSON). Never fatal: malformed or empty stdin
  #     just means session_id extraction below finds nothing. Guarded
  #     against a closed fd 0: with fd 0 closed and no writer, `cat` would
  #     otherwise block forever — bash reuses the closed fd 0 for the
  #     command substitution's own capture pipe, so `cat` ends up reading a
  #     pipe that never sees EOF (issue #7 item 1). Testing fd 0 via a
  #     throwaway dup to fd 3 costs nothing on the normal piped path and
  #     never touches fd 0 itself, so that path is unchanged. Claude Code
  #     always pipes the payload, so a closed fd 0 is not reachable in
  #     normal use; this guard exists so the handler's own "every path
  #     exits 0" contract holds even when it isn't. ---
  input=""
  if { exec 3<&0; } 2>/dev/null; then
    exec 3<&-
    input="$(cat 2>/dev/null)"
  fi

  # --- Resolve session_id via the shared helper (extract from stdin JSON,
  #     sanitise, fall back to a sanitised $PWD and then "_") — the exact
  #     resolution this file always used, now shared with
  #     user-prompt-submit.sh so both handlers key the same session's state
  #     on the same string. See tone-common.sh's resolve_session_id(). ---
  session_id="$(resolve_session_id "$input")"

  # --- Extract source the same way: it names the matcher value
  #     (startup|resume|clear|compact|fork), and decides whether a leftover
  #     "off" state is honored (everything but startup) or ignored
  #     (startup always rolls fresh — see the off-token handling below). ---
  source_val=""
  _source_re='"source"[[:space:]]*:[[:space:]]*"([^"]*)"'
  if [[ $input =~ $_source_re ]]; then
    source_val="${BASH_REMATCH[1]}"
  fi

  # --- State directory. Create if absent; if we can't, we simply can't
  #     persist a resume — still roll and announce below. ---
  state_dir="$(tone_state_dir)"
  [ -d "$state_dir" ] || mkdir -p "$state_dir" 2>/dev/null
  state_file=""
  if [ -d "$state_dir" ]; then
    state_file="$state_dir/$session_id"
  fi

  # --- Off token: the /tone skill's "off" switches the tone off by writing
  #     this literal value to the state file rather than deleting it, so
  #     absence keeps meaning "roll" and "off" gets its own representation
  #     (a genuinely missing/unreadable/stale state file still rolls fresh,
  #     unchanged from before). It can never collide with a real tone name:
  #     tone names are catalogue basenames, and the catalogue is asserted to
  #     hold none of those named this, whatever the catalogue's current
  #     size. ---
  off_token="__off__"
  is_off=0

  # --- Resume path: only for a non-startup source (resume/clear/compact,
  #     or anything unrecognized). A fresh session (source=startup) always
  #     rolls below, regardless of what a previous session left in the
  #     state file — including a leftover off_token, which must never leak
  #     into a new session. ---
  selected=""
  if [ "$source_val" != "startup" ] && [ -n "$state_file" ] && [ -f "$state_file" ]; then
    existing=""
    IFS= read -r existing < "$state_file" 2>/dev/null
    existing="${existing%$'\r'}"
    if [ "$existing" = "$off_token" ]; then
      is_off=1
    elif [ -n "$existing" ]; then
      for base in "${tones[@]}"; do
        if [ "$base" = "$existing" ]; then
          selected="$existing"
          break
        fi
      done
    fi
  fi

  # --- Off path: the session was explicitly switched off and this isn't a
  #     fresh startup. Print nothing, exit 0 — the session stays untoned. ---
  if [ "$is_off" -eq 1 ]; then
    return 0
  fi

  # --- Roll path: source=startup, or no usable state, or the recorded tone
  #     is stale. `rolled` records whether this run actually rolled a new
  #     tone (true here) or is re-announcing one already in force (false,
  #     set when `selected` came from the resume path above) — the
  #     announcement below says "rolled" only when it's true. ---
  rolled=0
  if [ -z "$selected" ]; then
    idx=$((RANDOM % count))
    selected="${tones[$idx]}"
    rolled=1
    if [ -n "$state_file" ]; then
      { printf '%s\n' "$selected" > "$state_file"; } 2>/dev/null
    fi
  fi

  # --- Prune stale per-session state files (issue #6). Every session that
  #     loads this plugin leaves one ~20-byte file behind forever, because
  #     session ids are UUIDs the handler can never see again to know a
  #     session ended. Age is the only available signal, so this removes
  #     files whose mtime is older than 30 days — chosen generously because
  #     resume/clear/compact (below, and see the resume branch above) only
  #     READ the state file without rewriting it, so a long-running
  #     session's file keeps its original mtime the whole time and must not
  #     look stale just because the session has been open for a while.
  #
  #     Runs only on `startup`, and only after this run's own state_file has
  #     just been persisted above, so it always has a name to protect.
  #     `resume`/`clear`/`compact` never reach here: they are reading state
  #     for a possibly-still-live session, and a prune racing that read is
  #     how a live session loses its tone. Every safety property is
  #     enforced by the find invocation itself, not by trusting its inputs:
  #       - refuses to run at all unless state_dir is a real directory
  #         (empty/unset/non-directory all skip the block below);
  #       - "-maxdepth 1 -type f" never descends and never follows a
  #         symlink (a symlink's find type is its own, not its target's, so
  #         a symlink inside state_dir pointing outside it is never a match
  #         and is never touched);
  #       - "! -name" excludes this session's own file by exact name,
  #         regardless of age;
  #       - "-exec rm -f {} +" (not the non-POSIX "-delete") only ever fires
  #         on paths find itself produced, which are already confined to
  #         state_dir by -maxdepth 1.
  #     Any failure here (permission denied, race with another process,
  #     etc.) is swallowed by the redirect below: this must never be the
  #     reason a session-start hook prints to stderr or exits non-zero.
  if [ "$source_val" = "startup" ] && [ -n "${state_dir:-}" ] && [ -d "$state_dir" ] && [ -n "$state_file" ]; then
    {
      find "$state_dir" -maxdepth 1 -type f -mtime +30 ! -name "$(basename "$state_file")" -exec rm -f {} +
    } 2>/dev/null
  fi

  tone_file="$styles_dir/$selected.md"
  [ -r "$tone_file" ] || return 0

  # --- Strip YAML frontmatter (the two `---` lines and everything between
  #     them), keeping the exact remaining bytes. A trailing sentinel byte
  #     defeats command substitution's trailing-newline stripping so the
  #     body's real trailing newline survives. ---
  body="$(
    {
      awk '
        NR == 1 && $0 == "---" { infm = 1; next }
        infm && $0 == "---"    { infm = 0; next }
        infm                   { next }
        { print }
      ' "$tone_file"
      printf 'X'
    }
  )"
  body="${body%X}"

  # --- JSON-escape the body in ONE awk pass. This used to be four
  #     chained passes (sed for backslash and quote, awk for the other C0
  #     controls, awk for newlines), each in its own command substitution
  #     with its own sentinel dance — six processes and three full copies
  #     of the body. They were ordered so that no pass re-escaped a
  #     backslash an earlier pass had introduced; mapping every input
  #     character exactly once removes that ordering constraint entirely
  #     rather than preserving it, so the result is the same bytes by
  #     construction:
  #       \ -> \\ , " -> \" , TAB -> \t , CR -> \r ,
  #       every other C0 character -> \u00XX ,
  #       and a real newline -> literal \n appended per record.
  #     (U+0000 cannot reach here: bash command substitution truncates the
  #     captured string at the first NUL byte. The map covers it anyway so
  #     the escaping is complete on its own terms.)
  #     Shell text processing only, per Global Constraint 3. ---
  escaped_body="$(
    {
      printf '%s' "$body" | awk '
        BEGIN {
          for (c = 0; c <= 31; c++) {
            if (c == 10) continue  # real newline: the printf below handles it
            ch = sprintf("%c", c)
            if (c == 9)       esc = "\\t"
            else if (c == 13) esc = "\\r"
            else              esc = sprintf("\\u%04x", c)
            ctrl_map[ch] = esc
          }
          ctrl_map["\\"] = "\\\\"
          ctrl_map["\""]  = "\\\""
        }
        {
          line = $0
          out = ""
          n = length(line)
          for (i = 1; i <= n; i++) {
            ch = substr(line, i, 1)
            out = out ((ch in ctrl_map) ? ctrl_map[ch] : ch)
          }
          printf "%s\\n", out
        }
      '
      printf 'X'
    }
  )"
  escaped_body="${escaped_body%X}"

  # --- Announcement: only claim "rolled" when a roll actually happened
  #     this run. A resumed tone (clear/compact/resume with valid state)
  #     did not just get rolled, and saying so was a lie the user had no
  #     way to catch — say "held" instead. The message is never dropped:
  #     after a /clear the user may genuinely not remember which tone is
  #     active, and silence would be worse than a plain restatement. ---
  if [ "$rolled" -eq 1 ]; then
    sys_message="🎲 Tone rolled: ${selected}"
  else
    sys_message="🎲 Tone held: ${selected}"
  fi
  escaped_sys_message="$(printf '%s' "$sys_message" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"

  printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}' \
    "$escaped_sys_message" "$escaped_body"

  return 0
}

main
exit 0
