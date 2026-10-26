#!/usr/bin/env bash
# Populate the eval run's working directory with the fixture codebase the
# reviewer is to audit. Runs on the host, as the invoking user (requires
# `claude plugin eval --scaffold`). It copies every fixture file EXCEPT the
# answer key (SEEDED.md), so the reviewer never sees the ground truth it is
# graded against.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/fixture"

for path in "$SRC"/*; do
  name="$(basename "$path")"
  if [ "$name" = "SEEDED.md" ]; then
    continue
  fi
  cp -R "$path" .
done
