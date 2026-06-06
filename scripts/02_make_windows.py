"""For each scan, define valid sliding windows."""

import os
import pandas as pd
from glob import glob

WINDOW_LENGTH = 35
STEP_SIZE = 3
MAX_CENSORED_TRS = 8
MAX_SCAN_CENSORED_FRAC = 0.25

script_dir = os.path.dirname(__file__)
DATA_ROOT = os.path.join(script_dir, "..", "for_ludo")
data_glob = os.path.join(DATA_ROOT, "*", "*", "*.csv")
output_path = os.path.join(script_dir, "window_summary.csv")


def check_line(line: pd.Series) -> bool:
    """Return True if the row is censored."""
    roi_values = line.drop(["Time (sec)"], errors="ignore")
    return roi_values.isna().all()


def parse_dataset_path(csv_path: str) -> tuple[str, str]:
    """Return (dataset, preproc_pipeline) for a for_ludo input CSV."""
    rel_path = os.path.relpath(csv_path, DATA_ROOT)
    parts = rel_path.split(os.sep)
    if len(parts) < 3:
        raise ValueError(f"Expected for_ludo/<dataset>/<preproc>/<file>.csv, got {csv_path}")
    return parts[0], parts[1]


def make_windows(csv_path: str) -> list[dict]:

    """ Takes a csv path, checks for censored TRs, and creates sliding windows of length WINDOW_LENGTH with step STEP_SIZE. Returns a list of dicts with window info.
    """
    df = pd.read_csv(csv_path)
    dataset, preproc_pipeline = parse_dataset_path(csv_path)

    # Check which rows are censored (all ROIs are NaN)
    censored_rows = df.apply(check_line, axis=1)

    # Scan-level censoring: skip scans with >25% censored TRs
    scan_censored_frac = censored_rows.sum() / len(df)
    if scan_censored_frac > MAX_SCAN_CENSORED_FRAC:
        print(f"Skipping {os.path.basename(csv_path)}: {scan_censored_frac:.1%} censored TRs (scan-level threshold exceeded)")
        return []

    windows = []

    # Create sliding windows of length WINDOW_LENGTH with step STEP_SIZE
    for start_tr in range(0, len(df) - WINDOW_LENGTH + 1, STEP_SIZE):
        
        end_tr = start_tr + WINDOW_LENGTH

        # Count how many TRs in this window are censored
        n_censored = int(censored_rows.iloc[start_tr:end_tr].sum())
        n_valid = WINDOW_LENGTH - n_censored

        windows.append(
            {
                "dataset": dataset,
                "preproc_pipeline": preproc_pipeline,
                "scan_id": os.path.basename(csv_path).replace(".csv", ""),
                "csv_path": csv_path,
                "window_id": len(windows),
                "start_tr": start_tr,
                "end_tr": end_tr - 1,
                "n_total_trs": WINDOW_LENGTH,
                "n_censored_trs": n_censored,
                "n_valid_trs": n_valid,
                "keep_window": n_censored <= MAX_CENSORED_TRS,
            }
        )

    return windows


if __name__ == '__main__':
    all_windows = []

    for csv_path in sorted(glob(data_glob)):
        all_windows.extend(make_windows(csv_path))

    pd.DataFrame(all_windows).to_csv(output_path, index=False)
    print(f"Wrote {len(all_windows)} windows to {output_path}")
