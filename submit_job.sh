#!/usr/bin/env bash
#SBATCH --job-name=gozzi_pipeline
#SBATCH --output=logs/slurm_%j.out
#SBATCH --error=logs/slurm_%j.err
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --nodes=1

# ── Tune these for your cluster ───────────────────────────────────────────────
# scan_workers × run_workers must not exceed --cpus-per-task.
# Good starting point: scan_workers=4, run_workers=8 → 32 cores.
# For 64 cores: scan_workers=8, run_workers=8 → 64 cores.
export GOZZI_N_RUNS=100
export GOZZI_SCAN_WORKERS=4
export GOZZI_RUN_WORKERS=8
# export GOZZI_FORCE=true   # uncomment to recompute connectivity even if files exist
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

cd "$(dirname "$0")"
mkdir -p logs

echo "Job ${SLURM_JOB_ID} started on $(hostname) at $(date)"
echo "CPUs allocated: ${SLURM_CPUS_PER_TASK:-?}"
echo "Parameters: N_RUNS=${GOZZI_N_RUNS}  SCAN_WORKERS=${GOZZI_SCAN_WORKERS}  RUN_WORKERS=${GOZZI_RUN_WORKERS}"
echo

./container_pipeline.sh run

echo
echo "Job finished at $(date)"
