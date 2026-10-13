#!/usr/bin/env bash
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
# Repeatable checks; no installed user configuration or live providers.
set -euo pipefail
QUALITY_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
QUALITY_CHECK_DIR=$(mktemp -d)
trap 'rm -rf -- "$QUALITY_CHECK_DIR"' EXIT
cd "$QUALITY_REPO"
export UNIO_AUTO_VERIFY=0 UNIO_AUTO_OFF=0 UNIO_AUTO_SYNC=0
for dependency in python3 shellcheck node; do
  command -v "$dependency" >/dev/null || { echo "missing dependency: $dependency" >&2; exit 1; }
done
bash -n unio-install.sh
python3 -B tools/embed-lead-cooldown.py --check
python3 -B tools/embed-browser.py --check
python3 -B tools/embed-capacity.py --check
python3 -B tools/embed-readiness.py --check
python3 -B tools/embed-fleet.py --check
python3 -B tools/embed-task-plan.py --check
python3 -B tools/embed-task-dispatch.py --check
python3 -B tools/embed-dashboard.py --check
python3 -B tools/embed-adapters.py --check
python3 -B tools/embed-model-experience.py --check
UNIO_BIN_DIR="$QUALITY_CHECK_DIR/bin" UNIO_CONF_DIR="$QUALITY_CHECK_DIR/conf" \
  UNIO_COMPLETION_DIR="$QUALITY_CHECK_DIR/completion" bash unio-install.sh > "$QUALITY_CHECK_DIR/install.log"
shellcheck -S warning "$QUALITY_CHECK_DIR/bin/unio"
UNIO_CONF_DIR="$QUALITY_CHECK_DIR/conf" "$QUALITY_CHECK_DIR/bin/unio" selftest
bash tests/unio-quality.sh
python3 -B tests/unio-review-receipts.py
python3 -B tests/unio-review-collection.py
python3 -B tests/unio-review-findings.py
python3 tests/unio-loop-brake.py
python3 tests/unio-limit-wall.py
python3 tests/unio-watch.py
python3 tests/unio-opencode.py
python3 -B tests/unio-prompt-transport.py
python3 -B tests/unio-perplexity.py
python3 -B tests/unio-vibe.py
python3 -B tests/unio-copilot.py
python3 -B tests/unio-adapters-install.py
python3 -B bridge/tests/progress_test.py
python3 -B bridge/tests/progress_api_test.py
python3 -B bridge/tests/worker_files_test.py
node --check bridge/worker_console.js
node --check bridge/theme.js
python3 -B bridge/tests/server_test.py
python3 -B bridge/tests/limits_api_test.py
python3 -B tests/unio-browser-launcher.py
python3 -B tests/unio-dashboard.py
python3 -B bridge/tests/capacity_test.py
python3 -B tests/unio-capacity.py
python3 -B tests/unio-readiness.py
python3 -B tests/unio-fleet.py
python3 -B tests/unio-model-experience.py
python3 -B tests/unio-task-plan.py
python3 -B tests/unio-task-dispatch.py
python3 -B tests/unio-task-dispatch-install.py
python3 -B tests/unio-readiness-install.py
python3 -B bridge/tests/provider_capacity_test.py
python3 -B tests/unio-provider-capacity.py
python3 -B tests/unio-work-policy.py
python3 -B tests/unio-work-policy-guard.py
python3 -B tests/unio-save-walk.py
python3 -B tests/unio-save-performance.py
python3 -B tests/unio-work-saving.py
python3 -B tests/unio-save-retention.py
python3 -B tests/unio-save-benchmark.py
python3 -B tests/unio-work-saving-auto.py
python3 -B tests/unio-save-capture-budget.py
python3 -B tests/unio-work-saving-continue.py
python3 -B tests/unio-kill-pid.py
python3 -B tests/unio-lead-cooldown.py
python3 -B bridge/tests/plan_store_test.py
python3 -B bridge/tests/plan_api_test.py
python3 -B bridge/tests/job_store_test.py
python3 -B bridge/tests/execution_service_test.py
python3 -B bridge/tests/execution_api_test.py
bash tests/unio-probes.sh
bash tests/unio-branding.sh
bash tools/check-docs.sh
echo 'quality-check: all checks passed'
