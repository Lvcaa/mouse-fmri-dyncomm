#!/usr/bin/env bash
set -euo pipefail

# ── Parameter resolution ───────────────────────────────────────────────────────
# Interactive (local): prompts the user; Enter accepts the default in brackets.
# Non-interactive (cluster, no TTY): reads env vars, or falls back to defaults.
#   Set them in your SLURM/PBS script, e.g.:
#     export GOZZI_N_RUNS=100 GOZZI_SCAN_WORKERS=16 GOZZI_RUN_WORKERS=4
#
# GOZZI_FORCE=true  →  recompute window connectivity even if files already exist.
#                       Default: skip scans whose window CSVs are all present.
# ──────────────────────────────────────────────────────────────────────────────

prompt_positive_int() {
  local label="$1"
  local default_value="$2"
  local value=""

  while true; do
    read -r -p "${label} [${default_value}]: " value
    value="${value:-$default_value}"

    if [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
      printf '%s' "$value"
      return 0
    fi

    echo "Please enter a positive integer."
  done
}

if [[ -t 0 ]]; then
  # stdin is a TTY → interactive mode
  echo "Pipeline parameters for script 04 (temporal Leiden)."
  echo "Press Enter to accept the default shown in brackets."
  echo

  N_RUNS=$(prompt_positive_int "Number of Leiden runs per scan" "${GOZZI_N_RUNS:-100}")
  echo
  SCAN_WORKERS=$(prompt_positive_int "Number of scans to process in parallel" "${GOZZI_SCAN_WORKERS:-8}")
  echo
  RUN_WORKERS=$(prompt_positive_int "Number of Leiden runs per scan to process in parallel" "${GOZZI_RUN_WORKERS:-8}")
  echo

  TOTAL_PROCESSES=$((SCAN_WORKERS * RUN_WORKERS))
  echo "Requested community-detection parallelism:"
  echo "  n_runs:        ${N_RUNS}"
  echo "  scan_workers:  ${SCAN_WORKERS}"
  echo "  run_workers:   ${RUN_WORKERS}"
  echo "  max processes: ${SCAN_WORKERS} * ${RUN_WORKERS} = ${TOTAL_PROCESSES}"
  echo
  echo "Existing pipeline outputs at the standard paths may be overwritten."
  read -r -p "Continue with these settings? [y/N]: " CONFIRM
  case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *)
      echo "Aborted."
      exit 0
      ;;
  esac
else
  # Non-interactive (cluster job) → use env vars, no prompts, no confirmation
  N_RUNS="${GOZZI_N_RUNS:-100}"
  SCAN_WORKERS="${GOZZI_SCAN_WORKERS:-8}"
  RUN_WORKERS="${GOZZI_RUN_WORKERS:-8}"

  TOTAL_PROCESSES=$((SCAN_WORKERS * RUN_WORKERS))
  echo "Non-interactive mode — using parameters:"
  echo "  n_runs:        ${N_RUNS}"
  echo "  scan_workers:  ${SCAN_WORKERS}"
  echo "  run_workers:   ${RUN_WORKERS}"
  echo "  max processes: ${TOTAL_PROCESSES}"
  echo "  (override via GOZZI_N_RUNS / GOZZI_SCAN_WORKERS / GOZZI_RUN_WORKERS)"
fi

echo
echo "Step 1/4: making windows"
python scripts/02_make_windows.py

echo
echo "Step 2/4: computing window connectivity"
FORCE_FLAG=""
[[ "${GOZZI_FORCE:-false}" == "true" ]] && FORCE_FLAG="--force"
python scripts/03_compute_window_connectivity.py ${FORCE_FLAG}

echo
echo "Step 3/4: running temporal Leiden community detection"
python scripts/04_run_community_detection.py \
  --n-runs "${N_RUNS}" \
  --scan-workers "${SCAN_WORKERS}" \
  --run-workers "${RUN_WORKERS}"

echo
echo "Step 4/4: aggregating flexibility scores"
python scripts/05_compute_flexibilty.py

echo
echo "Pipeline complete."
