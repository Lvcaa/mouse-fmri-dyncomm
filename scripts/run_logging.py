"""Shared helpers for recording when and how each pipeline script was run.

Each script calls `record_run` once it has produced its output. This writes a
`run_manifest.json` into the script's output directory (timestamp, git commit,
parameters, and any result info) and appends a one-line summary to the central
`outputs/pipeline_run_log.csv` for a chronological overview across all scripts.
"""

import csv
import json
import os
import subprocess
from datetime import datetime

OUTPUTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "outputs")
RUN_LOG_PATH = os.path.join(OUTPUTS_ROOT, "pipeline_run_log.csv")


def _git_commit() -> str:
    """Return the short hash of HEAD, or 'unknown' if not in a git repo / git unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(__file__),
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def record_run(script_name: str, output_dir: str, params: dict, **results) -> None:
    """Write a run manifest into output_dir and append a row to the central run log.

    params: the configuration the run was executed with (e.g. window length, gamma).
    results: anything produced by the run worth recording (e.g. n_windows, n_computed).
    """
    timestamp = datetime.now().isoformat(timespec="seconds")
    git_commit = _git_commit()

    os.makedirs(output_dir, exist_ok=True)
    manifest = {
        "script": script_name,
        "timestamp": timestamp,
        "git_commit": git_commit,
        "params": params,
        "results": results,
    }
    with open(os.path.join(output_dir, "run_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    os.makedirs(OUTPUTS_ROOT, exist_ok=True)
    write_header = not os.path.exists(RUN_LOG_PATH)
    with open(RUN_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "script", "git_commit", "output_dir", "params", "results"])
        writer.writerow([
            timestamp,
            script_name,
            git_commit,
            os.path.relpath(output_dir, OUTPUTS_ROOT),
            json.dumps(params),
            json.dumps(results),
        ])
