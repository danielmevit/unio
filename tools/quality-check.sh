#!/usr/bin/env bash
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
# Repeatable checks; no installed user configuration or live providers.
#
#   bash tools/quality-check.sh              # full offline gate (unchanged)
#   bash tools/quality-check.sh --list       # dry listing, runs nothing
#   bash tools/quality-check.sh --lane NAME  # named lane (repeatable, PARTIAL)
#
# The ordered command catalogue lives in tools/quality-gate-commands.json and
# the dispatcher in tools/quality-gate.py. See
# docs/development/VALIDATION-MATRIX.md for lanes, timings and limitations.
set -euo pipefail
QUALITY_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$QUALITY_REPO"
command -v python3 >/dev/null || { echo "missing dependency: python3" >&2; exit 1; }
exec python3 -B tools/quality-gate.py "$@"
