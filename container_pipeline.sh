#!/usr/bin/env bash
set -euo pipefail

INSTANCE_NAME="${GOZZI_INSTANCE_NAME:-gozzi_pipeline}"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${PROJECT_ROOT}/containers/progetto_gozzi.sif"

instance_is_running() {
  apptainer instance list | awk 'NR > 1 { print $1 }' | grep -Fxq "${INSTANCE_NAME}"
}

stop_instance() {
  if instance_is_running; then
    echo "Stopping Apptainer instance ${INSTANCE_NAME}..."
    apptainer instance stop --signal TERM --timeout 30 "${INSTANCE_NAME}"
  fi
}

run_pipeline() {
  if instance_is_running; then
    echo "Apptainer instance ${INSTANCE_NAME} is already running." >&2
    echo "Use '$0 status' to inspect it or '$0 stop' to stop it." >&2
    exit 1
  fi

  if [[ ! -f "${IMAGE}" ]]; then
    echo "Container image not found: ${IMAGE}" >&2
    exit 1
  fi

  apptainer instance start \
    --bind "${PROJECT_ROOT}:${PROJECT_ROOT}" \
    "${IMAGE}" \
    "${INSTANCE_NAME}"

  trap stop_instance EXIT HUP INT TERM

  echo "Running the pipeline in instance ${INSTANCE_NAME}."
  echo "From another terminal, stop it with: $0 stop"
  apptainer exec \
    --cwd "${PROJECT_ROOT}" \
    "instance://${INSTANCE_NAME}" \
    bash ./run_pipeline.sh
}

case "${1:-}" in
  run)
    run_pipeline
    ;;
  stop)
    if instance_is_running; then
      stop_instance
    else
      echo "Apptainer instance ${INSTANCE_NAME} is not running."
    fi
    ;;
  status)
    apptainer instance list
    ;;
  *)
    echo "Usage: $0 {run|stop|status}" >&2
    exit 2
    ;;
esac
