import argparse
import os
import re
import pandas as pd


def check_line(line: pd.Series) -> bool:
    """Return True if the row is censored."""
    roi_values = line.drop(["Time (sec)"], errors="ignore")
    return roi_values.isna().all()


def subject_folder_from_scan_id(scan_id: str) -> str:
    """Return subject folder name, grouping run letters under one subject."""
    subject_id = scan_id.split("_")[0]
    return re.sub(r"[a-z]$", "", subject_id)


def _expected_output_paths(valid_windows: pd.DataFrame, scan_output_dir: str, scan_id: str) -> list[str]:
    """Return the list of CSV paths that compute_window_connectivity would write for this scan."""
    return [
        os.path.join(scan_output_dir, f"{scan_id}_window_{int(row['window_id']):04d}.csv")
        for _, row in valid_windows.iterrows()
    ]


def compute_window_connectivity(window_summary_path: str, output_dir: str, force: bool = False):
    window_summary = pd.read_csv(window_summary_path)

    group_cols = [col for col in ["dataset", "preproc_pipeline", "scan_id"] if col in window_summary.columns]

    n_scans = window_summary.groupby(group_cols).ngroups
    n_skipped = 0
    n_computed = 0

    for group_key, group in window_summary.groupby(group_cols):
        if isinstance(group_key, tuple):
            group_values = dict(zip(group_cols, group_key))
        else:
            group_values = {group_cols[0]: group_key}
        scan_id = group_values["scan_id"]
        dataset = group_values.get("dataset")
        preproc_pipeline = group_values.get("preproc_pipeline")
        subject_folder = subject_folder_from_scan_id(scan_id)

        valid_windows = group[group["keep_window"] == True]

        if valid_windows.empty:
            print(f"No valid windows for {scan_id}, skipping.")
            continue

        if dataset and preproc_pipeline:
            scan_output_dir = os.path.join(output_dir, dataset, preproc_pipeline, subject_folder)
        else:
            scan_output_dir = os.path.join(output_dir, subject_folder)

        # Skip this scan if all expected output files already exist and --force was not given.
        # Checked at scan level (not per-window) to avoid partial/inconsistent scan outputs.
        if not force:
            expected = _expected_output_paths(valid_windows, scan_output_dir, scan_id)
            if all(os.path.exists(p) for p in expected):
                n_skipped += 1
                continue

        os.makedirs(scan_output_dir, exist_ok=True)

        csv_path = valid_windows.iloc[0]["csv_path"]
        df = pd.read_csv(csv_path)

        for _, row in valid_windows.iterrows():
            start_tr = int(row["start_tr"])
            end_tr = int(row["end_tr"])
            window_id = int(row["window_id"])

            window_data = df.iloc[start_tr:end_tr + 1].copy()

            censored_rows = window_data.apply(check_line, axis=1)
            window_data = window_data.loc[~censored_rows]

            window_data = window_data.drop(columns=["Time (sec)"], errors="ignore")

            connectivity_matrix = window_data.corr()

            for roi in connectivity_matrix.columns:
                connectivity_matrix.loc[roi, roi] = 0

            output_path = os.path.join(scan_output_dir, f"{scan_id}_window_{window_id:04d}.csv")
            connectivity_matrix.to_csv(output_path)
            n_computed += 1

        print(f"Computed connectivity for {scan_id} ({len(valid_windows)} windows)")

    if n_skipped:
        print(f"\nSkipped {n_skipped}/{n_scans} scans (all window files already present). Use --force to recompute.")
    if n_computed == 0 and n_skipped == n_scans:
        print("Nothing to do — all connectivity matrices are up to date.")
    else:
        print(f"Wrote {n_computed} connectivity matrices.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Compute per-window connectivity matrices.")
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Recompute and overwrite even if output files already exist.",
    )
    args = parser.parse_args()

    window_summary_path = os.path.join(os.path.dirname(__file__), "window_summary.csv")
    output_dir = os.path.join(os.path.dirname(__file__), "window_connectivity")
    os.makedirs(output_dir, exist_ok=True)

    compute_window_connectivity(window_summary_path, output_dir, force=args.force)
