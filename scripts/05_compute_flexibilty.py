"""
For each ROI, collect its community membership set at each window in order.
Walk consecutive pairs — count how many times the membership set changes (switches) vs. total pairs (transitions).
Divide switches by transitions to get flexibility score in [0, 1].

Membership sets are used instead of raw community labels to avoid the label-alignment
problem: Louvain assigns arbitrary integers each run, so the same integer across two
windows does not mean the same community.

The final table has:
| subject | condition | DMNa | DMNp | SAL | ... |
"""

import os
import re
import pandas as pd
from glob import glob
from collections import defaultdict

WINDOW_COMMUNITIES_DIR = os.path.join(os.path.dirname(__file__), "window_communities")
FLEXIBILITY_DIR = os.path.join(os.path.dirname(__file__), "flexibility")


def parse_scan_id(path: str) -> tuple[str, str]:
    """Return (scan_id, condition) from a community CSV path.

    Example: sub-ag231031b_SHAM_bold_parcellated.csv -> ('sub-ag231031b', 'SHAM')
    """
    stem = os.path.basename(path).replace(".csv", "")
    parts = stem.split("_")
    scan_id = parts[0]
    condition = parts[1]
    return scan_id, condition


def build_membership_sets(df_window: pd.DataFrame) -> dict[str, frozenset]:
    """For each node in a window, return the frozenset of all nodes sharing its community."""
    
    # Build a mapping from community label to the set of nodes in that community for this window.
    community_to_nodes: dict[int, set] = defaultdict(set)
    for _, row in df_window.iterrows():
        community_to_nodes[row["Community"]].add(row["Node"])

    return {
        # For each node, return the frozenset of nodes in its community. This allows us to compare membership sets across windows without worrying about label alignment.
        row["Node"]: frozenset(community_to_nodes[row["Community"]])
        for _, row in df_window.iterrows()
    }


def compute_flexibility_for_scan(df: pd.DataFrame) -> dict[str, float]:
    """Compute flexibility score for each node across all windows in a scan."""
    window_ids = sorted(df["window_id"].unique())
    n_transitions = len(window_ids) - 1

    if n_transitions == 0:
        return {}

    # Get the unique nodes across all windows. We will compute flexibility for each of these nodes.
    nodes = df["Node"].unique()
    switches: dict[str, int] = defaultdict(int)

    # Initialize previous memberships with the first window's community assignments.
    prev_memberships = build_membership_sets(df[df["window_id"] == window_ids[0]])

    # Walk through each subsequent window after the first one, compare membership sets to previous window, and count switches.
    for window_id in window_ids[1:]:

        # Build current memberships for this window and compare to previous memberships. If a node's membership set changes, count it as a switch.
        curr_memberships = build_membership_sets(df[df["window_id"] == window_id])
        for node in nodes:
            if prev_memberships.get(node) != curr_memberships.get(node):
                switches[node] += 1
        prev_memberships = curr_memberships

    return {node: switches[node] / n_transitions for node in nodes}


def compute_flexibility(communities_dir: str, output_dir: str):
    community_files = sorted(glob(os.path.join(communities_dir, "*", "*.csv")))
    assert community_files, f"No community assignments found in {communities_dir}"

    os.makedirs(output_dir, exist_ok=True)

    rows = []

    # Walk through each scan's community assignments, compute flexibility, and collect results.
    for path in community_files:

        # Extract scan_id and condition from filename, read the community assignments, and compute flexibility.
        scan_id, condition = parse_scan_id(path)
        df = pd.read_csv(path)

        # Compute flexibility scores for each node in this scan and store them in a row with subject and condition.
        flexibility = compute_flexibility_for_scan(df)

        row = {"subject": scan_id, "condition": condition}
        row.update(flexibility)
        rows.append(row)
        print(f"Processed {scan_id} ({condition})")

    result = pd.DataFrame(rows)
    output_path = os.path.join(output_dir, "flexibility_scores.csv")
    result.to_csv(output_path, index=False)
    print(f"Saved {output_path}")


if __name__ == "__main__":
    compute_flexibility(WINDOW_COMMUNITIES_DIR, FLEXIBILITY_DIR)
