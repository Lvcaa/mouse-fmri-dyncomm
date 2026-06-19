import argparse
import re
import time
import numpy as np
import pandas as pd
import igraph as ig
import leidenalg as la
import os
from collections import defaultdict
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from glob import glob

from run_logging import record_run

OUTPUTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "outputs")
OUTPUTS_DIR = os.path.join(OUTPUTS_ROOT, "community_detection")


def connectivity_dir_for_width(window_length: int) -> str:
    return os.path.join(OUTPUTS_ROOT, f"window_connectivity_wl{window_length}")

# Dataset to process, hardcoded for now.
DATASET = "Bf_PV_awk"

# ── Algorithm parameters (from TO_DO.md) ──────────────────────────────────────
# Resolution parameter (γ): controls community granularity.
#   γ=1 is the default per TO_DO but NOTE: CPMVertexPartition requires internal
#   edge density > γ. With Pearson correlations in [0, 1], γ=1 forces all nodes
#   into singletons → flexibility = 0 always. Lower γ (e.g. 0.1–0.3) produces
#   biologically meaningful communities. Tune as needed.
GAMMA = 0.35

# Interslice coupling (ω): penalises a node for switching communities between
# consecutive windows. Higher → more stable partitions across time.
INTERSLICE_WEIGHT = 0.25

# Number of independent Leiden runs per scan. Each run gets a fresh random
# seed, and flexibility is averaged across all runs.
N_RUNS = 20
SCAN_WORKERS = 8
RUN_WORKERS = 8

# ── Logging helpers ────────────────────────────────────────────────────────────
_DIVIDER = "═" * 64


def _fmt_time(seconds: float) -> str:
    """Format elapsed seconds as '4m 32s' or '3.2s'."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _step(verb: str, detail: str, elapsed: float) -> None:
    """Print one aligned step line: '  verb  detail .............. elapsed'."""
    body = f"  {verb:<10} {detail}"
    print(f"{body:<56} {_fmt_time(elapsed)}", flush=True)


def read_window(connectivity_path: str) -> pd.DataFrame:
    """Read a connectivity matrix CSV and zero the diagonal."""
    df = pd.read_csv(connectivity_path, index_col=0)
    for col in df.columns:
        # Zero the diagonal (self-connections) to avoid trivial communities of single nodes.
        df.loc[col, col] = 0
    # df.shape      → (16, 16)
    # df.columns    → ['DMNa', 'DMNp', 'SAL', 'OLF', 'STR', 'AUD', 'VIS',
    #                   'TH', 'MOp', 'SSp', 'SSs', 'HCa', 'SUB', 'CTXsp', 'BF', 'HY']
    # df.iloc[0, 1] → 0.545   (example DMNa–DMNp Pearson r)
    # df.iloc[0, 0] → 0.0     (diagonal, zeroed)
    return df


def build_igraph(df: pd.DataFrame) -> ig.Graph:
    """Convert a sliding-window correlation matrix to a weighted igraph Graph.

    Node order is preserved so vertex indices map consistently to ROI names
    across all windows of the same scan. Only positive correlations are kept
    as edges (negative weights are dropped).

    Node = ROI column name
    Edge = Positive Correlation between two ROIs within a window
    Edge weight = Pearson Correlation value

    No negative correlation nor diagonal (zeroed)
    """
    roi_names = list(df.columns)
    graph = ig.Graph()
    graph.add_vertices(len(roi_names))
    graph.vs["name"] = roi_names
    graph.vs["id"] = roi_names

    corr_array = df.to_numpy(dtype=float)
    row_indices, col_indices = np.triu_indices(len(roi_names), k=1)
    edge_weights = corr_array[row_indices, col_indices]
    positive_mask = edge_weights > 0

    graph.add_edges(list(zip(row_indices[positive_mask].tolist(), col_indices[positive_mask].tolist())))
    graph.es["weight"] = edge_weights[positive_mask].tolist()
    # graph.vcount()          → 16      (one vertex per ROI)
    # graph.ecount()          → ~94     (positive-correlation pairs only; varies per window)
    # graph.vs["name"][:3]    → ['DMNa', 'DMNp', 'SAL']
    # graph.es["weight"][:3]  → [0.545, 0.182, 0.408]
    return graph


def _multiprocessing_context():
    """Prefer fork on Linux so workers can inherit the temporal graph list."""
    try:
        return multiprocessing.get_context("fork")
    except ValueError:
        return multiprocessing.get_context("spawn")


# ── Worker-global state ────────────────────────────────────────────────────────
# Set once per worker process via _init_worker; the temporal graph list is never
# pickled into individual task arguments.
_worker_graphs = None
_worker_n_transitions = None
_worker_gamma = None
_worker_omega = None


def _init_worker(graphs, n_transitions, gamma, omega):
    """Load temporal graphs into each worker process exactly once.

    Called by ProcessPoolExecutor as an initializer — runs once per worker
    at startup, not once per task. With fork the graphs are COW-inherited.
    """
    global _worker_graphs, _worker_n_transitions, _worker_gamma, _worker_omega
    _worker_graphs = graphs
    _worker_n_transitions = n_transitions  # T-1
    _worker_gamma = gamma
    _worker_omega = omega


def _leiden_single_run(seed: int) -> list[float]:
    """Run one layer-aware temporal Leiden optimisation.

    CPM quality is evaluated separately within each time slice, while matching
    ROI IDs in adjacent slices are coupled with weight omega.
    """
    graphs = _worker_graphs
    n_transitions = _worker_n_transitions
    gamma = _worker_gamma
    omega = _worker_omega

    memberships, improvement = la.find_partition_temporal(
        graphs,
        la.CPMVertexPartition,
        interslice_weight=omega,
        vertex_id_attr="id",
        weight_attr="weight",
        resolution_parameter=gamma,
        seed=seed,
    )
    if not np.isfinite(improvement):
        raise RuntimeError(f"Temporal Leiden returned invalid improvement: {improvement}")

    # Retrieve membership matrix and save it
    membership_matrix = np.asarray(memberships, dtype=np.int32)
    expected_shape = (len(graphs), graphs[0].vcount())
    if membership_matrix.shape != expected_shape:
        raise RuntimeError(
            f"Unexpected temporal membership shape {membership_matrix.shape}; "
            f"expected {expected_shape}"
        )

    # Count transitions where community label changed between adjacent windows.
    switches = np.sum(membership_matrix[1:] != membership_matrix[:-1], axis=0)  # (N,)

    # Normalise to [0, 1] flexibility: fraction of T-1 transitions with a community switch.
    return (switches / n_transitions).tolist()


def run_community_detection(
    windows: list[tuple[int, str]],
    n_runs: int = N_RUNS,
    gamma: float = GAMMA,
    omega: float = INTERSLICE_WEIGHT,
    run_workers: int = RUN_WORKERS,
) -> pd.DataFrame:
    """Run temporal Leiden community detection N_RUNS times and return mean flexibility.

    Each correlation graph is one time slice. ``find_partition_temporal``
    evaluates CPM quality within each slice and couples matching ROI IDs in
    adjacent slices with weight omega.

    Flexibility for ROI i = fraction of the T-1 consecutive-window transitions
    where its community label changed, averaged across N_RUNS independent runs.
    flexibility_std is the standard deviation of that per-run fraction across
    the N_RUNS runs, i.e. how much the stochastic Leiden runs disagree on ROI i.

    Returns a DataFrame with columns:
        Node | flexibility | flexibility_std | gamma | interslice_weight | n_runs | n_windows
    """
    sorted_windows = sorted(windows, key=lambda x: x[0])
    n_windows = len(sorted_windows)
    n_transitions = n_windows - 1

    # ── Step 1: load windows ───────────────────────────────────────────────────
    graphs: list[ig.Graph] = []
    node_names: list[str] | None = None
    t0 = time.time()
    for _, (window_id, path) in enumerate(sorted_windows, start=1):
        df = read_window(path)
        if node_names is None:
            node_names = list(df.columns)
        elif list(df.columns) != node_names:
            raise ValueError(f"ROI columns or order differ across windows: {path}")
        graphs.append(build_igraph(df))
    _step("loading", f"{n_windows} windows", time.time() - t0)
    # len(graphs)           → 664
    # graphs[0].vcount()    → 16
    # graphs[0].ecount()    → ~94   (varies per window)
    # node_names            → ['DMNa', 'DMNp', ..., 'HY']

    n_nodes = len(node_names)

    if n_transitions == 0:
        return pd.DataFrame({
            "Node": node_names,
            "flexibility": [float("nan")] * n_nodes,
            "flexibility_std": [float("nan")] * n_nodes,
        })

    # ── Step 2: run layer-aware temporal Leiden ───────────────────────────────
    n_runs = max(1, n_runs)
    run_workers = max(1, min(run_workers, n_runs))
    seeds = [int.from_bytes(os.urandom(4), "little") % (2**31 - 1) for _ in range(n_runs)]

    init_args = (graphs, n_transitions, gamma, omega)

    t0 = time.time()
    if run_workers == 1:
        # Sequential path: initialise the globals in the main process directly
        # so _leiden_single_run can read from them without any pickling.
        _init_worker(*init_args)
        all_runs = [_leiden_single_run(seed) for seed in seeds]
    else:
        all_runs = [None] * n_runs
        mp_context = _multiprocessing_context()
        with ProcessPoolExecutor(
            max_workers=run_workers,
            mp_context=mp_context,
            initializer=_init_worker,
            initargs=init_args,
        ) as executor:
            # Each task now only sends an integer seed across the process boundary
            futures = {executor.submit(_leiden_single_run, seed): i for i, seed in enumerate(seeds)}
            for future in as_completed(futures):
                all_runs[futures[future]] = future.result()
    _step("running", f"{n_runs} × Leiden  ({run_workers} workers)", time.time() - t0)

    runs_array = np.asarray(all_runs, dtype=float)  # shape (n_runs, n_nodes)

    return pd.DataFrame({
        "Node": node_names,
        "flexibility": runs_array.mean(axis=0),
        "flexibility_std": runs_array.std(axis=0),
        "gamma": gamma,
        "interslice_weight": omega,
        "n_runs": len(all_runs),
        "n_windows": n_windows,
    })


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


def connectivity_context(connectivity_dir: str, path: str) -> str:
    """Return dataset/preprocessing context for subject-nested connectivity files."""
    rel_parts = os.path.relpath(path, connectivity_dir).split(os.sep)
    if len(rel_parts) != 5:
        raise ValueError(
            f"Expected <dataset>/<preproc>/<animal_id>/<subject_id>/<window>.csv under {connectivity_dir}, got {path}"
        )
    return os.path.join(rel_parts[0], rel_parts[1])


def _run_scan_group(args: tuple) -> None:
    context, subject_folder, scan_id, entries, output_dir, n_runs, gamma, omega, run_workers, scan_idx, n_scans = args
    subject_dir = os.path.join(output_dir, context, subject_folder)
    os.makedirs(subject_dir, exist_ok=True)

    # Scan header — [i/N] makes interleaved output from parallel workers identifiable
    print(f"\n[{scan_idx}/{n_scans}] {scan_id}  [{context}]  {len(entries)} windows", flush=True)
    t0_scan = time.time()

    result = run_community_detection(
        entries,
        n_runs=n_runs,
        gamma=gamma,
        omega=omega,
        run_workers=run_workers,
    )
    result["last_run"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    output_path = os.path.join(subject_dir, f"{scan_id}.csv")
    result.to_csv(output_path, index=False)

    print(f"  {'saved':<10} → {output_path}", flush=True)
    print(f"  {'total':<10} {_fmt_time(time.time() - t0_scan)}", flush=True)


def run_all(
    connectivity_dir: str,
    output_dir: str,
    n_runs: int = N_RUNS,
    gamma: float = GAMMA,
    omega: float = INTERSLICE_WEIGHT,
    scan_workers: int = SCAN_WORKERS,
    run_workers: int = RUN_WORKERS,
):
    """Run temporal Leiden on all scans and save one CSV per scan.

    Output CSV columns: Node | flexibility
    """
    connectivity_files = sorted(glob(os.path.join(connectivity_dir, DATASET, "*", "*", "*", "*.csv")))
    assert connectivity_files, f"No connectivity matrices found for dataset {DATASET!r} in {connectivity_dir}"

    # Group window files by dataset/preprocessing context, subject, and scan.
    groups: dict[tuple[str, str, str], list[tuple[int, str]]] = defaultdict(list)
    for path in connectivity_files:
        subject_folder, scan_id, window_id = parse_filename(path)
        context = connectivity_context(connectivity_dir, path)
        groups[(context, subject_folder, scan_id)].append((window_id, path))

    n_scans = len(groups)
    scan_workers = max(1, min(scan_workers, n_scans))

    # Build jobs, including each scan's position index for the [i/N] header
    scan_jobs = [
        (context, subject_folder, scan_id, entries, output_dir, n_runs, gamma, omega, run_workers, idx + 1, n_scans)
        for idx, ((context, subject_folder, scan_id), entries) in enumerate(groups.items())
    ]

    # ── Header ────────────────────────────────────────────────────────────────
    print(_DIVIDER)
    print(f"  Temporal Leiden  |  {n_scans} scans  |  γ={gamma}  ω={omega}  |  {n_runs} runs")
    print(f"  scan_workers={scan_workers}  run_workers={run_workers}")
    print(_DIVIDER)

    t0_all = time.time()

    if scan_workers == 1:
        for job in scan_jobs:
            _run_scan_group(job)
    else:
        # Output lines from parallel workers will interleave; [i/N] prefixes keep them identifiable
        mp_context = _multiprocessing_context()
        with ProcessPoolExecutor(max_workers=scan_workers, mp_context=mp_context) as executor:
            futures = {executor.submit(_run_scan_group, job): job[2] for job in scan_jobs}
            for future in as_completed(futures):
                future.result()

    # ── Footer ────────────────────────────────────────────────────────────────
    print(f"\n{_DIVIDER}")
    print(f"  All done — {n_scans} scans in {_fmt_time(time.time() - t0_all)}")
    print(_DIVIDER)

    return n_scans


def test_one_connectivity_file(window_length: int = 35):
    """Smoke test on the first available scan (first 5 windows, 5 runs)."""
    connectivity_dir = connectivity_dir_for_width(window_length)
    connectivity_files = sorted(glob(os.path.join(connectivity_dir, "*", "*", "*", "*", "*.csv")))
    assert connectivity_files, f"No connectivity matrices found in {connectivity_dir}"

    stem = os.path.basename(connectivity_files[0]).replace(".csv", "")
    match = re.search(r"_window_(\d+)$", stem)
    scan_prefix = stem[: match.start()]
    scan_files = sorted(
        f for f in connectivity_files if os.path.basename(f).startswith(scan_prefix)
    )[:5]

    result = run_community_detection(
        [(parse_filename(f)[2], f) for f in scan_files],
        n_runs=5,
        run_workers=1,
    )
    assert not result.empty
    assert {"Node", "flexibility"}.issubset(result.columns)
    print(f"Tested: {scan_files}")
    print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run temporal Leiden community detection.")
    parser.add_argument(
        "--window-length", type=int, default=35,
        help="Window length in TR; selects window_connectivity_wl{N}/ as input and "
             "namespaces the output dir as leiden_flex_wl{N}_...",
    )
    args = parser.parse_args()

    connectivity_dir = connectivity_dir_for_width(args.window_length)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(OUTPUTS_DIR, f"leiden_flex_wl{args.window_length}_{N_RUNS}_{timestamp}")
    n_scans = run_all(connectivity_dir, output_dir)

    record_run(
        "04_run_community_detection",
        output_dir,
        params={
            "dataset": DATASET,
            "window_length": args.window_length,
            "gamma": GAMMA,
            "interslice_weight": INTERSLICE_WEIGHT,
            "n_runs": N_RUNS,
            "scan_workers": SCAN_WORKERS,
            "run_workers": RUN_WORKERS,
        },
        n_scans=n_scans,
    )
