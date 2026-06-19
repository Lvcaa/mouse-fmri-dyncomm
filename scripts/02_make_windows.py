"""For each scan, define valid sliding windows."""

import argparse
import csv
import os
import pandas as pd
from glob import glob

from run_logging import record_run

# Defaults; overridden by CLI args in __main__ (kept here so make_windows() has
# sensible globals when imported directly, e.g. from notebooks).
WINDOW_LENGTH = 35
STEP_SIZE = 3
MAX_CENSORED_TRS = round(0.25 * WINDOW_LENGTH)
MAX_SCAN_CENSORED_FRAC = 0.25

script_dir = os.path.dirname(__file__)
DATA_ROOT = os.path.join(script_dir, "..", "for_ludo")
OUTPUTS_DIR = os.path.join(script_dir, "..", "outputs")
data_glob = os.path.join(DATA_ROOT, "*", "*", "*.csv")
output_path = os.path.join(OUTPUTS_DIR, f"window_summary_wl{WINDOW_LENGTH}.csv")

report_mouse_dir = os.path.join(OUTPUTS_DIR, "report_mouse_censoring", f"wl{WINDOW_LENGTH}")

def check_line(line: pd.Series) -> bool:
    """Return True if the row is censored."""
    roi_values = line.drop(["Time (sec)"], errors="ignore")
    return roi_values.isna().all()


def extract_subject(csv_path: str) -> str:
    """Return the basename of the csv file (e.g. sub-ag231130c_EXP_bold_parcellated), so the group (EXP/SHAM) is visible."""
    return os.path.basename(csv_path).replace(".csv", "")


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

    # If the scan-level censoring threshold is exceeded, skip this scan and log it in report_mouse_censoring/skipped_scans.csv
    if scan_censored_frac > MAX_SCAN_CENSORED_FRAC:
        print(f"Skipping {os.path.basename(csv_path)}: {scan_censored_frac:.1%} censored TRs (scan-level threshold exceeded)")

        # Report mouse: log skipped entire csv and their censored row count
        os.makedirs(report_mouse_dir, exist_ok=True)
        skipped_path = os.path.join(report_mouse_dir, "skipped_scans.csv")
        write_header = not os.path.exists(skipped_path)

        # Append to skipped_scans.csv with scan_id, csv_path, and n_censored_rows
        with open(skipped_path, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["dataset", "preproc_pipeline", "scan_id", "csv_path", "n_censored_rows", "pct_censored"])
            writer.writerow([
                dataset,
                preproc_pipeline,
                extract_subject(csv_path),
                csv_path,
                f"{int(censored_rows.sum())} / {len(df)}",
                f"{scan_censored_frac:.1%}",
            ])
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
    parser = argparse.ArgumentParser(description="Build sliding windows for each scan.")
    parser.add_argument(
        "--window-length", type=int, default=WINDOW_LENGTH,
        help="Window length in TR (TR=1.0s in this dataset).",
    )
    parser.add_argument(
        "--step-size", type=int, default=STEP_SIZE,
        help="Step size in TR between consecutive windows.",
    )
    args = parser.parse_args()

    WINDOW_LENGTH = args.window_length
    STEP_SIZE = args.step_size
    MAX_CENSORED_TRS = round(0.25 * WINDOW_LENGTH)
    output_path = os.path.join(OUTPUTS_DIR, f"window_summary_wl{WINDOW_LENGTH}.csv")
    report_mouse_dir = os.path.join(OUTPUTS_DIR, "report_mouse_censoring", f"wl{WINDOW_LENGTH}")

    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    all_windows = []

    for csv_path in sorted(glob(data_glob)):
        all_windows.extend(make_windows(csv_path))

    pd.DataFrame(all_windows).to_csv(output_path, index=False)
    print(f"Wrote {len(all_windows)} windows to {output_path}")

    record_run(
        "02_make_windows",
        OUTPUTS_DIR,
        params={
            "WINDOW_LENGTH": WINDOW_LENGTH,
            "STEP_SIZE": STEP_SIZE,
            "MAX_CENSORED_TRS": MAX_CENSORED_TRS,
            "MAX_SCAN_CENSORED_FRAC": MAX_SCAN_CENSORED_FRAC,
        },
        n_windows=len(all_windows),
        output_path=os.path.relpath(output_path, OUTPUTS_DIR),
    )
