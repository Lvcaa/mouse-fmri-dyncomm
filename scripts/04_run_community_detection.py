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

CONNECTIVITY_DIR = os.path.join(os.path.dirname(__file__), "window_connectivity")
COMMUNITIES_DIR = os.path.join(os.path.dirname(__file__), "window_communities")

# ── Algorithm parameters (from TO_DO.md) ──────────────────────────────────────
# Resolution parameter (γ): controls community granularity.
#   γ=1 is the default per TO_DO but NOTE: CPMVertexPartition requires internal
#   edge density > γ. With Pearson correlations in [0, 1], γ=1 forces all nodes
#   into singletons → flexibility = 0 always. Lower γ (e.g. 0.1–0.3) produces
#   biologically meaningful communities. Tune as needed.
GAMMA = 0.1

# Interslice coupling (ω): penalises a node for switching communities between
# consecutive windows. Higher → more stable partitions across time.
INTERSLICE_WEIGHT = 0.5

# Number of independent Leiden runs per scan. Each run gets a fresh random
# seed, and flexibility is averaged across all runs.
N_RUNS = 100
SCAN_WORKERS = 1
RUN_WORKERS = 1

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
    """Prefer fork on Linux so workers do not pickle huge igraph layers."""
    try:
        return multiprocessing.get_context("fork")
    except ValueError:
        return multiprocessing.get_context("spawn")


# ── Worker-global state ────────────────────────────────────────────────────────
# Set once per worker process via _init_worker; the supra-graph is never
# pickled into individual task arguments.
_worker_supra_graph = None
_worker_n_windows = None
_worker_n_transitions = None
_worker_n_nodes = None
_worker_gamma = None


def _init_worker(supra_graph, n_windows, n_transitions, n_nodes, gamma):
    """Load supra-graph into each worker process exactly once.

    Called by ProcessPoolExecutor as an initializer — runs once per worker
    at startup, not once per task. With fork the graph is COW-inherited and
    never actually copied.
    """
    global _worker_supra_graph, _worker_n_windows, _worker_n_transitions
    global _worker_n_nodes, _worker_gamma
    _worker_supra_graph = supra_graph   # single graph: T*N nodes, intra + interslice edges
    _worker_n_windows = n_windows       # T
    _worker_n_transitions = n_transitions  # T-1
    _worker_n_nodes = n_nodes           # N (ROIs per window)
    _worker_gamma = gamma


def _leiden_single_run(seed: int) -> list[float]:
    """Run one Leiden optimisation on the supra-graph and return per-node flexibility.

    The supra-graph vertex layout is:  node t*N+i  =  ROI i in window t.
    Intra-window correlation edges couple ROIs within each window block.
    Interslice edges  (t*N+i) — ((t+1)*N+i)  with weight ω couple the same
    ROI across adjacent windows, encoding temporal continuity.

    A single find_partition call replaces the T+1 partition multiplex approach,
    reducing cost from O(T²·N) to O(T·N) per sweep.
    """
    supra_graph = _worker_supra_graph
    n_windows = _worker_n_windows
    n_transitions = _worker_n_transitions
    n_nodes = _worker_n_nodes
    gamma = _worker_gamma

    partition = la.find_partition(
        supra_graph,
        la.CPMVertexPartition,
        weights="weight",
        resolution_parameter=gamma,
        seed=seed,
    )
    # len(partition.membership)    → 10,624
    # partition.membership[:5]     → [0, 0, 1, 0, 2]   (community label per supra-vertex)
    # partition.membership[0]      → community of DMNa in window 0
    # partition.membership[16]     → community of DMNa in window 1 (same or different)

    # membership is a flat T*N vector; reshape to (T, N).
    # entry [t, i] = community label of ROI i in window t.
    membership_matrix = np.array(partition.membership, dtype=np.int32).reshape(n_windows, n_nodes)
    # membership_matrix.shape      → (664, 16)
    # membership_matrix[0]         → [0, 0, 1, 0, 2, 1, 0, 3, 0, 0, 1, 2, 2, 1, 3, 0]
    # membership_matrix[1]         → [0, 0, 1, 0, 2, 1, 0, 3, 0, 0, 1, 2, 2, 1, 3, 0]  ← stable
    # membership_matrix[200]       → [1, 1, 0, 1, 0, 2, 1, 0, 1, 1, 0, 3, 3, 0, 0, 1]  ← switched

    # Count transitions where community label changed between adjacent windows.
    switches = np.sum(membership_matrix[1:] != membership_matrix[:-1], axis=0)  # (N,)
    # switches  → [591, 631, 645, ...]   raw count of community changes per ROI across 663 transitions

    # Normalise to [0, 1]: fraction of T-1 transitions with a community switch.
    return (switches / n_transitions).tolist()
    # return → [0.891, 0.951, 0.972, ...]   one flexibility value per ROI for this run


def run_community_detection(
    windows: list[tuple[int, str]],
    n_runs: int = N_RUNS,
    gamma: float = GAMMA,
    omega: float = INTERSLICE_WEIGHT,
    run_workers: int = RUN_WORKERS,
) -> pd.DataFrame:
    """Run temporal Leiden community detection N_RUNS times and return mean flexibility.

    Builds a supra-adjacency graph (Mucha et al. 2010) where each time window
    occupies a contiguous block of N vertices:

        vertex  t*N + i  =  ROI i in window t

    Edges:
        intra-window  (t*N+r) — (t*N+c)  weight = Pearson correlation  (positive only)
        interslice    (t*N+i) — ((t+1)*N+i)  weight = ω  (adjacent windows only)

    A single leidenalg.find_partition call over this one graph replaces the old
    T+1 layered multiplex, reducing cost from O(T²·N) to O(T·N) per sweep.

    Flexibility for ROI i = fraction of the T-1 consecutive-window transitions
    where its community label changed, averaged across N_RUNS independent runs.

    Returns a DataFrame with columns:
        Node | flexibility | gamma | interslice_weight | n_runs | n_windows
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
        graphs.append(build_igraph(df))
    _step("loading", f"{n_windows} windows", time.time() - t0)
    # len(graphs)           → 664
    # graphs[0].vcount()    → 16
    # graphs[0].ecount()    → ~94   (varies per window)
    # node_names            → ['DMNa', 'DMNp', ..., 'HY']

    n_nodes = len(node_names)

    if n_transitions == 0:
        return pd.DataFrame({"Node": node_names, "flexibility": [float("nan")] * n_nodes})

    # ── Step 2: build supra-adjacency graph ───────────────────────────────────
    # One graph, T*N vertices.  Vertex layout: t*N+i = ROI i in window t.
    # Intra-window edges carry correlation weights; interslice chain edges
    # carry weight ω and connect each ROI to itself in the adjacent window only.
    t0 = time.time()
    intra_sources: list[int] = []
    intra_targets: list[int] = []
    intra_weights: list[float] = []
    for window_idx, window_graph in enumerate(graphs):
        vertex_offset = window_idx * n_nodes
        for edge in window_graph.es:
            intra_sources.append(vertex_offset + edge.source)
            intra_targets.append(vertex_offset + edge.target)
            intra_weights.append(edge["weight"])

    window_indices = np.repeat(np.arange(n_transitions), n_nodes)
    roi_indices    = np.tile(np.arange(n_nodes), n_transitions)
    interslice_src = (window_indices * n_nodes + roi_indices).tolist()
    interslice_tgt = ((window_indices + 1) * n_nodes + roi_indices).tolist()

    supra = ig.Graph()
    supra.add_vertices(n_windows * n_nodes)
    supra.add_edges(list(zip(intra_sources + interslice_src, intra_targets + interslice_tgt)))
    supra.es["weight"] = intra_weights + [omega] * (n_transitions * n_nodes)
    _step("building", "supra-graph", time.time() - t0)
    # supra.vcount()  → 10,624   (664 windows × 16 ROIs)
    # supra.ecount()  → ~73,000  (62,495 intra-window + 10,608 interslice)
    # vertex layout:  t*16+i  =  ROI i in window t
    #   vertex   0  = DMNa in window   0
    #   vertex  16  = DMNa in window   1  ← connected to vertex 0 via ω edge
    #   vertex  80  = DMNa in window   5
    #   vertex 10608 = DMNa in window 663

    # ── Step 3: run Leiden ────────────────────────────────────────────────────
    n_runs = max(1, n_runs)
    run_workers = max(1, min(run_workers, n_runs))
    seeds = [int.from_bytes(os.urandom(4), "little") % (2**31 - 1) for _ in range(n_runs)]

    init_args = (supra, n_windows, n_transitions, n_nodes, gamma)

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
            initializer=_init_worker,  # runs once per worker process at startup
            initargs=init_args,        # multiplex data pickled run_workers times, not n_runs times
        ) as executor:
            # Each task now only sends an integer seed across the process boundary
            futures = {executor.submit(_leiden_single_run, seed): i for i, seed in enumerate(seeds)}
            for future in as_completed(futures):
                all_runs[futures[future]] = future.result()
    _step("running", f"{n_runs} × Leiden  ({run_workers} workers)", time.time() - t0)

    flexibility_sum = [sum(run[i] for run in all_runs) for i in range(n_nodes)]
    # flexibility_sum[0]  → sum of DMNa flexibility across 100 runs, e.g. 89.7
    # divided by 100 below → mean flexibility 0.897

    return pd.DataFrame({
        "Node": node_names,
        "flexibility": [s / len(all_runs) for s in flexibility_sum],
        # Node     flexibility
        # DMNa     0.897       ← switches community in ~90% of window transitions
        # BF       0.943
        # CTXsp    0.987       ← highest flexibility: rarely stays in one community
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
    if len(rel_parts) != 4:
        raise ValueError(
            f"Expected <dataset>/<preproc>/<subject>/<window>.csv under {connectivity_dir}, got {path}"
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
    connectivity_files = sorted(glob(os.path.join(connectivity_dir, "*", "*", "*", "*.csv")))
    assert connectivity_files, f"No connectivity matrices found in {connectivity_dir}"

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


def test_one_connectivity_file():
    """Smoke test on the first available scan (first 5 windows, 5 runs)."""
    connectivity_files = sorted(glob(os.path.join(CONNECTIVITY_DIR, "*", "*", "*", "*.csv")))
    assert connectivity_files, f"No connectivity matrices found in {CONNECTIVITY_DIR}"

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


def parse_args():
    parser = argparse.ArgumentParser(description="Run temporal Leiden community detection.")
    parser.add_argument("--connectivity-dir", default=CONNECTIVITY_DIR)
    parser.add_argument("--output-dir", default=COMMUNITIES_DIR)
    parser.add_argument("--n-runs", type=int, default=N_RUNS)
    parser.add_argument("--scan-workers", type=int, default=SCAN_WORKERS)
    parser.add_argument("--run-workers", type=int, default=RUN_WORKERS)
    parser.add_argument("--gamma", type=float, default=GAMMA)
    parser.add_argument("--omega", type=float, default=INTERSLICE_WEIGHT)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_all(
        args.connectivity_dir,
        args.output_dir,
        n_runs=args.n_runs,
        gamma=args.gamma,
        omega=args.omega,
        scan_workers=args.scan_workers,
        run_workers=args.run_workers,
    )
