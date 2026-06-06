"""
Aggregate per-scan flexibility scores into a single wide-format table.

Script 04 already runs Leiden N_RUNS=100 times per scan and writes the mean
flexibility per node to:

    window_communities/<subject_folder>/<scan_id>.csv

with columns:
    Node | flexibility

This script collects those files and pivots them into the final table:
    subject | condition | DMNa | DMNp | SAL | ...
"""

import os
import pandas as pd
from datetime import datetime
from glob import glob

WINDOW_COMMUNITIES_DIR = os.path.join(os.path.dirname(__file__), "window_communities")
FLEXIBILITY_DIR = os.path.join(os.path.dirname(__file__), "flexibility")


def parse_scan_id(path: str) -> tuple[str, str, str]:
    """Return (scan_id, condition, phase) from a community CSV path.

    Examples:
      sub-ag231031b_SHAM_bold_parcellated.csv -> ('sub-ag231031b', 'SHAM', 'full')
      sub-ag240729a_EXP_bold_CNO_parcellated.csv -> ('sub-ag240729a', 'EXP', 'CNO')
    """
    stem = os.path.basename(path).replace(".csv", "")
    parts = stem.split("_")
    scan_id = parts[0]
    condition = parts[1]
    if "CNO" in parts:
        phase = "CNO"
    elif "baseline" in parts:
        phase = "baseline"
    else:
        phase = "full"
    return scan_id, condition, phase


def parse_dataset_context(communities_dir: str, path: str) -> dict[str, str]:
    """Extract dataset metadata from nested window_communities outputs."""
    rel_parts = os.path.relpath(path, communities_dir).split(os.sep)
    if len(rel_parts) >= 4:
        dataset = rel_parts[0]
        preproc_pipeline = rel_parts[1]
        subject_folder = rel_parts[-2]
    else:
        dataset = ""
        preproc_pipeline = ""
        subject_folder = rel_parts[-2] if len(rel_parts) >= 2 else ""

    dataset_parts = dataset.split("_")
    cohort = dataset_parts[1] if len(dataset_parts) >= 3 else ""
    state_token = dataset_parts[2] if len(dataset_parts) >= 3 else ""
    state = {"awk": "awake", "anes": "anesthetized"}.get(state_token, state_token)

    return {
        "dataset": dataset,
        "preproc_pipeline": preproc_pipeline,
        "cohort": cohort,
        "state": state,
        "subject_folder": subject_folder,
    }


def compute_flexibility(communities_dir: str, output_dir: str):
    """Pivot per-scan flexibility CSVs into one wide-format output table."""
    flex_files = sorted(glob(os.path.join(communities_dir, "*", "*", "*", "*.csv")))
    assert flex_files, f"No flexibility files found in {communities_dir}"

    os.makedirs(output_dir, exist_ok=True)

    rows = []
    for path in flex_files:
        scan_id, condition, phase = parse_scan_id(path)
        df = pd.read_csv(path)  # columns: Node, flexibility

        row = parse_dataset_context(communities_dir, path)
        row.update({"subject": scan_id, "condition": condition, "phase": phase})
        row.update(dict(zip(df["Node"], df["flexibility"])))
        rows.append(row)
        label = row["dataset"]
        print(f"Processed {label}/{scan_id} ({condition}, {phase})")

    result = pd.DataFrame(rows)
    result["last_run"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    output_path = os.path.join(output_dir, "flexibility_scores.csv")
    result.to_csv(output_path, index=False)
    print(f"Saved {output_path}")


if __name__ == "__main__":
    compute_flexibility(WINDOW_COMMUNITIES_DIR, FLEXIBILITY_DIR)
