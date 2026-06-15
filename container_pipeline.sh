#!/usr/bin/env bash
set -euo pipefail

INSTANCE_NAME="${GOZZI_INSTANCE_NAME:-gozzi_pipeline}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
CONTAINERS_DIR="${PROJECT_ROOT}/containers"
IMAGE="${GOZZI_IMAGE:-${CONTAINERS_DIR}/progetto_gozzi.sif}"
DEFINITION="${GOZZI_DEFINITION:-${CONTAINERS_DIR}/progetto_gozzi.def}"

instance_is_running() {
  apptainer instance list | awk 'NR > 1 { print $1 }' | grep -Fxq "${INSTANCE_NAME}"
}

stop_instance() {
  if instance_is_running; then
    echo "Stopping Apptainer instance ${INSTANCE_NAME}..."
    apptainer instance stop --signal TERM --timeout 30 "${INSTANCE_NAME}"
  fi
}

build_image() {
  if [[ ! -f "${DEFINITION}" ]]; then
    echo "Container definition not found: ${DEFINITION}" >&2
    exit 1
  fi

  echo "Building container image: ${IMAGE}"
  (
    cd "${PROJECT_ROOT}"
    apptainer build "${IMAGE}" "${DEFINITION}"
  )
}

run_pipeline() {
  if instance_is_running; then
    echo "Apptainer instance ${INSTANCE_NAME} is already running." >&2
    echo "Use '$0 status' to inspect it or '$0 stop' to stop it." >&2
    exit 1
  fi

  if [[ ! -f "${IMAGE}" ]]; then
    echo "Container image not found: ${IMAGE}" >&2
    echo "Build it with: ${SCRIPT_DIR}/container_pipeline.sh build" >&2
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
    bash -c '
      set -euo pipefail

      echo "Step 1/4: making windows"
      python scripts/02_make_windows.py

      echo
      echo "Step 2/4: computing window connectivity"
      python scripts/03_compute_window_connectivity.py

      echo
      echo "Step 3/4: running temporal Leiden community detection"
      python scripts/04_run_community_detection.py

      echo
      echo "Step 4/4: aggregating flexibility scores"
      python scripts/05_compute_flexibilty.py

      echo
      echo "Pipeline complete."
    '
}

case "${1:-}" in
  build)
    build_image
    ;;
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
    echo "Usage: $0 {build|run|stop|status}" >&2
    exit 2
    ;;
esac
