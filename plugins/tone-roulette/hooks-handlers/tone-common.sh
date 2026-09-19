#!/usr/bin/env bash
#
# tone-roulette shared handler helpers.
#
# Sourced by both hooks-handlers/session-start.sh (SessionStart) and
# hooks-handlers/user-prompt-submit.sh (UserPromptSubmit). Never executed
# directly — it defines functions only and has no `main`.
#
# Same contract as every handler in this plugin (see
# docs/superpowers/specs/2026-09-13-tone-roulette-design.md):
#   - bash + coreutils only. No jq, no python, no `shuf`.
#   - Verified clean under bash 3.2 (macOS /bin/bash), not just bash 4+.
#   - Every function here is side-effect-free except where its own comment
#     says otherwise (none currently write anything) — callers own all
#     file I/O so each handler's own "every path exits 0, nothing on
#     stderr" contract stays visible in one place per handler.

# --- get_output_style_value: print the `outputStyle` settings value, if
#     any settings file sets it, in Claude Code's own precedence order
#     (highest first): managed settings, project local settings, shared
#     project settings, user settings. Prints nothing and returns 1 if none
#     of them set it. This is the exact detection session-start.sh always
#     used (originally named output_style_is_set() there and boolean-only,
#     never returning here below) — relocated, not changed, so both
#     handlers share one copy instead of keeping their own. See
#     session-start.sh's git history / the design spec's "Detecting a
#     chosen style" section for the full exactness argument (why a plain
#     grep+sed pull over newline-flattened text is safe here and not a
#     heuristic). ---
get_output_style_value() {
  local project_dir candidates=() f content re

  # --- Both managed-settings locations are listed unconditionally, macOS's
  #     first, instead of picking one by `uname -s`. A platform only ever
  #     has its own path present, so the `[ -f ]`/`[ -r ]` guard below
  #     selects exactly what the `uname` branch used to select — one fewer
  #     process on a hook that runs at every session start. ---
  candidates+=(
    "/Library/Application Support/ClaudeCode/managed-settings.json"
    "/etc/claude-code/managed-settings.json"
  )

  project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
  candidates+=(
    "$project_dir/.claude/settings.local.json"
    "$project_dir/.claude/settings.json"
    "${HOME:-}/.claude/settings.json"
  )

  # --- The extraction is the same newline-flattened "outputStyle" pull it
  #     always was, done with bash's own builtins instead of a
  #     tr | printf | grep | head | sed pipeline: `$(<file)` reads without
  #     exec'ing anything, `${x//.../ }` does the flattening `tr` did, and
  #     `[[ =~ ]]` + BASH_REMATCH does what grep|head|sed did. Four
  #     processes per candidate file became none. bash 3.2 supports all
  #     three (the regex is held in a variable and referenced unquoted,
  #     which is what 3.2 requires). ---
  re='"outputStyle"[[:space:]]*:[[:space:]]*"([^"]*)"'

  for f in "${candidates[@]}"; do
    [ -n "$f" ] && [ -f "$f" ] && [ -r "$f" ] || continue
    content="$(<"$f")"
    content="${content//$'\r'/ }"
    content="${content//$'\n'/ }"
    if [[ $content =~ $re ]] && [ -n "${BASH_REMATCH[1]}" ]; then
      printf '%s' "${BASH_REMATCH[1]}"
      return 0
    fi
  done
  return 1
}

# --- output_style_is_set: boolean wrapper over get_output_style_value(),
#     kept for session-start.sh's "stand down entirely" check, which only
#     ever needs to know whether a style is set, never which one. ---
output_style_is_set() {
  get_output_style_value >/dev/null
}

# --- sanitize_id: apply the one hygiene rule every state-file key shares —
#     collapse anything outside [A-Za-z0-9_.-] to "_" — to whatever is
#     piped to it. Used on both the stdin-supplied session_id and the $PWD
#     fallback, so a value like "../../escaped" can never compose into a
#     path that escapes the state directory. ---
sanitize_id() {
  tr -c 'A-Za-z0-9_.-' '_'
}

# --- resolve_session_id INPUT: the exact session_id resolution
#     session-start.sh always used — extract the stdin JSON's "session_id"
#     string field (a plain grep+sed pull, not newline-flattened: a real
#     session_id is a UUID Claude Code emits on one line, never split
#     across lines the way a hand-edited settings file's outputStyle key
#     might be), sanitize it, and fall back to a sanitized $PWD and then
#     the literal "_" when both are empty. Both handlers must resolve the
#     same session's id to the same string, since both read and write
#     state keyed on it. ---
resolve_session_id() {
  local input="$1" session_id re
  # --- Same extraction and same hygiene rule as before, using bash's own
  #     regex match and pattern substitution rather than grep|head|sed plus
  #     two `tr` calls: five processes per hook invocation became none.
  #     `${x//[!A-Za-z0-9_.-]/_}` is the exact character class sanitize_id()
  #     collapses, so "../../escaped" still cannot compose into a path that
  #     escapes the state directory. ---
  re='"session_id"[[:space:]]*:[[:space:]]*"([^"]*)"'
  session_id=""
  if [[ $input =~ $re ]]; then
    session_id="${BASH_REMATCH[1]}"
  fi
  session_id="${session_id//[!A-Za-z0-9_.-]/_}"
  if [ -z "$session_id" ]; then
    session_id="${PWD//[!A-Za-z0-9_.-]/_}"
  fi
  if [ -z "$session_id" ]; then
    session_id="_"
  fi
  printf '%s' "$session_id"
}

# --- tone_state_dir: the one per-session state directory every
#     tone-roulette handler shares. ---
tone_state_dir() {
  printf '%s/.claude/tone-roulette' "${HOME:-}"
}

# --- tone_is_active WANT SESSION_ID STATE_DIR: true (via exit status) when
#     WANT is the tone currently in force for this session:
#       - an output style explicitly chosen via the outputStyle settings
#         key pre-empts everything else (same precedence as
#         session-start.sh's own stand-down check) — checked first;
#       - otherwise, the tone named in this session's state file (what
#         session-start.sh most recently rolled or resumed into it), if
#         any. A missing state file, an empty one, or one holding the
#         "__off__" sentinel or an unrelated name is simply "not WANT" —
#         never an error.
#     This never rolls, resumes, prunes, or writes anything; it only
#     answers "is WANT the one active tone right now", cheaply enough to
#     call unconditionally at the top of a hook that must cost nothing
#     when the answer is no. ---
tone_is_active() {
  local want="$1" session_id="$2" state_dir="$3" style_val state_file existing
  style_val="$(get_output_style_value)"
  if [ -n "$style_val" ]; then
    [ "$style_val" = "$want" ]
    return $?
  fi
  [ -n "$state_dir" ] || return 1
  state_file="$state_dir/$session_id"
  [ -f "$state_file" ] || return 1
  existing="$(head -n 1 "$state_file" 2>/dev/null | tr -d '\r\n')"
  [ "$existing" = "$want" ]
}
