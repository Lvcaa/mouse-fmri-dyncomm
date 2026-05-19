import re
import networkx as nx
import pandas as pd
import os
from collections import defaultdict
from glob import glob

CONNECTIVITY_DIR = os.path.join(os.path.dirname(__file__), "window_connectivity")
COMMUNITIES_DIR = os.path.join(os.path.dirname(__file__), "window_communities")


def read_window(connectivity_path: str) -> pd.DataFrame:
    """Read the connectivity matrix from given path and return it as a pandas DataFrame."""
    df = pd.read_csv(connectivity_path, index_col=0)
    for col in df.columns:
        df.loc[col, col] = 0
    return df


def run_community_detection(connectivity_path: str) -> pd.DataFrame:
    """Run community detection on the connectivity matrix and return the community assignments as a DataFrame."""
    df = read_window(connectivity_path)
    G = nx.from_pandas_adjacency(df)
    communities = nx.community.louvain_communities(G, seed=123)

    rows = []
    for i, community in enumerate(communities):
        for node in community:
            rows.append({"Node": node, "Community": i})

    return pd.DataFrame(rows)


def parse_filename(path: str) -> tuple[str, str, int]:
    """Return (subject_folder, scan_id, window_id) from a connectivity CSV path.

    subject_folder strips the run letter so all runs of the same subject share a folder.
    Example: sub-ag231031b_SHAM_bold_parcellated_window_0008.csv
      -> subject_folder: sub-ag231031
      -> scan_id:        sub-ag231031b_SHAM_bold_parcellated
      -> window_id:      8
    """
    stem = os.path.basename(path).replace(".csv", "")
    match = re.search(r"_window_(\d+)$", stem)
    window_id = int(match.group(1))
    scan_id = stem[: match.start()]
    subject_id = scan_id.split("_")[0]
    subject_folder = re.sub(r"[a-z]$", "", subject_id)
    return subject_folder, scan_id, window_id


def run_all(connectivity_dir: str, output_dir: str):
    """Run community detection on all windows and save one CSV per scan, organised in per-subject folders."""
    connectivity_files = sorted(glob(os.path.join(connectivity_dir, "*.csv")))
    assert connectivity_files, f"No connectivity matrices found in {connectivity_dir}"

    groups: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    
    for path in connectivity_files:
        subject_folder, scan_id, window_id = parse_filename(path)
        groups[(subject_folder, scan_id)].append((window_id, path))

    for (subject_folder, scan_id), entries in groups.items():
        subject_dir = os.path.join(output_dir, subject_folder)
        os.makedirs(subject_dir, exist_ok=True)

        rows = []
        for window_id, path in sorted(entries):
            community_df = run_community_detection(path)
            community_df.insert(0, "window_id", window_id)
            rows.append(community_df)

        result = pd.concat(rows, ignore_index=True)
        output_path = os.path.join(subject_dir, f"{scan_id}.csv")
        result.to_csv(output_path, index=False)
        print(f"Saved {output_path} ({len(entries)} windows)")


def test_one_connectivity_file():
    """Small smoke test on the first available connectivity matrix."""
    connectivity_files = sorted(glob(os.path.join(CONNECTIVITY_DIR, "*.csv")))
    assert connectivity_files, f"No connectivity matrices found in {CONNECTIVITY_DIR}"

    result = run_community_detection(connectivity_files[0])
    assert not result.empty
    assert set(result.columns) == {"Node", "Community"}

    print(f"Tested: {connectivity_files[0]}")
    print(result)


if __name__ == "__main__":
    run_all(CONNECTIVITY_DIR, COMMUNITIES_DIR)
