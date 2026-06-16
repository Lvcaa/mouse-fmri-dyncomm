"""
Aggregate per-scan flexibility scores into a single wide-format table.

Script 04 runs Leiden N_RUNS times per scan and writes the mean flexibility
per node to the most recent:

    outputs/leiden_flex_<n_runs>_<timestamp>/<dataset>/<preproc>/<subject>/<scan_id>.csv

with columns:
    Node | flexibility | flexibility_std | ...

This script collects those files and pivots them into the final table:
    subject_id | condition | DMNa | DMNp | SAL | ...
"""

import os
import pandas as pd
from datetime import datetime
from glob import glob

from run_logging import record_run

OUTPUTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "outputs")
OUTPUTS_DIR = os.path.join(OUTPUTS_ROOT, "community_detection")
FLEXIBILITY_DIR = os.path.join(OUTPUTS_ROOT, "flexibility")


def latest_leiden_output_dir(outputs_dir: str) -> str:
    """Return the most recently produced outputs/leiden_flex_<n_runs>_<timestamp>/ dir."""
    candidates = glob(os.path.join(outputs_dir, "leiden_flex_*"))
    assert candidates, f"No leiden_flex_* output directories found in {outputs_dir}"
    return max(candidates, key=os.path.getmtime)


def parse_scan_id(path: str) -> tuple[str, str, str]:
    """Return (subject_id, condition, phase) from a community CSV path.

    Examples:
      sub-ag231031b_SHAM_bold_parcellated.csv -> ('sub-ag231031b', 'SHAM', 'full')
      sub-ag240729a_EXP_bold_CNO_parcellated.csv -> ('sub-ag240729a', 'EXP', 'CNO')
    """
    stem = os.path.basename(path).replace(".csv", "")
    parts = stem.split("_")
    subject_id = parts[0]
    condition = parts[1]
    if "CNO" in parts:
        phase = "CNO"
    elif "baseline" in parts:
        phase = "baseline"
    else:
        phase = "full"
    return subject_id, condition, phase


def parse_dataset_context(communities_dir: str, path: str) -> dict[str, str]:
    """Extract dataset metadata from nested window_communities outputs."""
    rel_parts = os.path.relpath(path, communities_dir).split(os.sep)
    if len(rel_parts) >= 4:
        dataset = rel_parts[0]
        preproc_pipeline = rel_parts[1]
        animal_id = rel_parts[-2]
    else:
        dataset = ""
        preproc_pipeline = ""
        animal_id = rel_parts[-2] if len(rel_parts) >= 2 else ""

    dataset_parts = dataset.split("_")
    cohort = dataset_parts[1] if len(dataset_parts) >= 3 else ""
    state_token = dataset_parts[2] if len(dataset_parts) >= 3 else ""
    state = {"awk": "awake", "anes": "anesthetized"}.get(state_token, state_token)

    return {
        "dataset": dataset,
        "preproc_pipeline": preproc_pipeline,
        "cohort": cohort,
        "state": state,
        "animal_id": animal_id,
    }


def compute_flexibility(communities_dir: str, output_dir: str):
    """Pivot per-scan flexibility CSVs into one wide-format output table."""
    flex_files = sorted(glob(os.path.join(communities_dir, "*", "*", "*", "*.csv")))
    assert flex_files, f"No flexibility files found in {communities_dir}"

    os.makedirs(output_dir, exist_ok=True)

    rows = []
    for path in flex_files:
        subject_id, condition, phase = parse_scan_id(path)
        df = pd.read_csv(path)  # columns: Node, flexibility

        row = parse_dataset_context(communities_dir, path)
        row.update({"subject_id": subject_id, "condition": condition, "phase": phase})
        row.update(dict(zip(df["Node"], df["flexibility"])))
        rows.append(row)
        label = row["dataset"]
        print(f"Processed {label}/{subject_id} ({condition}, {phase})")

    result = pd.DataFrame(rows)
    result["last_run"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    output_path = os.path.join(output_dir, "flexibility_scores.csv")
    result.to_csv(output_path, index=False)
    print(f"Saved {output_path}")

    return len(flex_files)


if __name__ == "__main__":
    source_dir = latest_leiden_output_dir(OUTPUTS_DIR)
    n_scans = compute_flexibility(source_dir, FLEXIBILITY_DIR)

    record_run(
        "05_compute_flexibilty",
        FLEXIBILITY_DIR,
        params={"source_dir": os.path.relpath(source_dir, OUTPUTS_ROOT)},
        n_scans=n_scans,
    )
