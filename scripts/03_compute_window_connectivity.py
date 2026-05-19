import os
import pandas as pd


def check_line(line: pd.Series) -> bool:
    """Return True if the row is censored."""
    roi_values = line.drop(["Time (sec)"], errors="ignore")
    return roi_values.isna().all()


def compute_window_connectivity(window_summary_path: str, output_dir: str):
    window_summary = pd.read_csv(window_summary_path)

    # Iterate trough grouped dataframes by scan_id
    for scan_id, group in window_summary.groupby("scan_id"):

        # Filter only the windows to keep
        valid_windows = group[group["keep_window"] == True]

        # If there are no valid windows, skip this scan
        if valid_windows.empty:
            print(f"No valid windows for {scan_id}, skipping.")
            continue

        csv_path = valid_windows.iloc[0]["csv_path"]
        df = pd.read_csv(csv_path)

        # Loop through each row of the valid windows
        for _, row in valid_windows.iterrows():
            start_tr = int(row["start_tr"])
            end_tr = int(row["end_tr"])
            window_id = int(row["window_id"])

            # Extract the data for the current window in the actual csv registration file
            window_data = df.iloc[start_tr:end_tr + 1].copy()

            # Remove censored rows before computing correlations
            censored_rows = window_data.apply(check_line, axis=1)
            window_data = window_data.loc[~censored_rows]

            # Drop the time column so only ROI signals are correlated
            window_data = window_data.drop(columns=["Time (sec)"], errors="ignore")

            # Compute and clean the connectivity matrix
            connectivity_matrix = window_data.corr()

            # Set negative correlations to zero and diagonal to zero
            connectivity_matrix = connectivity_matrix.clip(lower=0)

            # Loop over the diagonal and set it to zero
            for roi in connectivity_matrix.columns:
                connectivity_matrix.loc[roi, roi] = 0

            output_path = os.path.join(output_dir, f"{scan_id}_window_{window_id:04d}.csv")
            connectivity_matrix.to_csv(output_path)
            print(f"Saved connectivity matrix for {scan_id} window {window_id} to {output_path}")


if __name__ == '__main__':
    window_summary_path = os.path.join(os.path.dirname(__file__), "window_summary.csv")

    output_dir = os.path.join(os.path.dirname(__file__), "window_connectivity")
    os.makedirs(output_dir, exist_ok=True)

    compute_window_connectivity(window_summary_path, output_dir)
