import re
import time
import json
import shlex
import numpy as np
import pandas as pd
import igraph as ig
import leidenalg as la
import os
import subprocess
import sys
from collections import defaultdict
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from glob import glob
from typing import Dict, List, Optional, Tuple

OUTPUTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "outputs")
OUTPUTS_DIR = os.path.join(OUTPUTS_ROOT, "parameter_inspection")


def connectivity_dir_for_width(window_length: int) -> str:
    return os.path.join(OUTPUTS_ROOT, f"window_connectivity_wl{window_length}")


# Dataset to process, hardcoded for now.
# TEMPORARY: restricted to a single dataset for the pilot run (48 combos:
# 4 gammas x 4 omegas x 3 widths). Restore the full list before the real sweep.
DATASETS = ["Bf_PV_anes"]

# Resume into an already-existing run directory instead of starting a fresh
# timestamped one. When set, run_parameter_grid() writes new combos under
# OUTPUTS_DIR/RESUME_RUN_NAME/wl{N}/gamma_X_omega_Y/{dataset}/... alongside
# whatever datasets that run already has, and merges into its run_manifest.json
# rather than overwriting it. Set to None to start a brand-new run as usual.
# Currently pointed at the 2026-06-20 sweep so the Bf_DTA_awk combos land next
# to the already-computed Bf_DTA_anes ones under the same wl{N}/gamma_X_omega_Y
# folders (see docs/ParameterInspectionStuckRun.md).
RESUME_RUN_NAME: Optional[str] = "2026_06_20__01-16-56"

# Window lengths (TR, 1 TR = 1s) to sweep, each read from its own
# window_connectivity_wl{N}/ directory (see 02/03_*.py --window-length).
WIDTHS = [35, 50, 70]

# ── Algorithm parameters ──────────────────────────────────────────────────────
# Resolution parameter (γ): controls community granularity.
#   γ=1 is the default per TO_DO but NOTE: CPMVertexPartition requires internal
#   edge density > γ. With Pearson correlations in [0, 1], γ=1 forces all nodes
#   into singletons → flexibility = 0 always. Calibrated empirically (see
#   inspect_output_communities_param.ipynb) so each γ lands in the 5–7
#   community range: 0.20 undershoots, 0.45 overshoots.
GAMMAS = [0.25, 0.30, 0.35, 0.40]


# Interslice coupling (ω): penalises a node for switching communities between
# consecutive windows. Higher → more stable partitions across time.
OMEGAS = [0.10, 0.20, 0.30, 0.40]

DEFAULT_GAMMA = 0.35
DEFAULT_OMEGA = 0.25

# Number of independent Leiden runs per scan. Each run gets a fresh random
# seed, and flexibility is averaged across all runs.
N_RUNS = 10

# Two-level pool: SCAN_WORKERS scans run concurrently, each spinning up its own
# RUN_WORKERS pool of size min(RUN_WORKERS, N_RUNS) for its N_RUNS Leiden runs.
# Total concurrent processes = SCAN_WORKERS * RUN_WORKERS. Sized to 10x10=100
# (leaving ~40 of the cluster's 144 cores free for other users) with
# RUN_WORKERS == N_RUNS so no inner worker ever sits idle.
SCAN_WORKERS = 10
RUN_WORKERS = 10

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


def _now_iso() -> str:
    """Return the local timestamp with timezone, trimmed to seconds."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _repo_relpath(path: str) -> str:
    return os.path.relpath(os.path.abspath(path), _repo_root())


def _git_commit() -> str:
    """Return the short hash of HEAD, or 'unknown' if git is unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_repo_root(),
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _shell_join(args: List[str]) -> str:
    if hasattr(shlex, "join"):
        return shlex.join(args)
    return " ".join(shlex.quote(arg) for arg in args)


def _write_manifest(manifest: dict, manifest_path: str) -> None:
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)


def _parameter_value_slug(value) -> str:
    """Make a parameter value safe and compact enough for folder names."""
    label = str(value)
    return label.replace(os.sep, "-").replace(" ", "")


def _parameter_folder_name(gamma, omega) -> str:
    return f"gamma_{_parameter_value_slug(gamma)}_omega_{_parameter_value_slug(omega)}"


def _unique_run_dir(base_dir: str, run_name: str) -> Tuple[str, str]:
    candidate_name = run_name
    candidate = os.path.join(base_dir, candidate_name)
    suffix = 2
    while os.path.exists(candidate):
        candidate_name = f"{run_name}__{suffix:02d}"
        candidate = os.path.join(base_dir, candidate_name)
        suffix += 1
    return candidate_name, candidate


def read_window(connectivity_path: str) -> pd.DataFrame:
    """Read a connectivity matrix CSV and zero the diagonal."""
    df = pd.read_csv(connectivity_path, index_col=0)
    for col in df.columns:
        # Zero the diagonal (self-connections) to avoid trivial communities of single nodes.
        df.loc[col, col] = 0
    return df


def build_igraph(df: pd.DataFrame) -> ig.Graph:
    """Convert a sliding-window correlation matrix to a weighted igraph Graph.

    Node order is preserved so vertex indices map consistently to ROI names
    across all windows of the same scan. Both positive and negative
    correlations are kept as signed edge weights; only exact zeros are omitted.

    Node = ROI column name
    Edge = Non-zero correlation between two ROIs within a window
    Edge weight = Signed Pearson correlation value

    Diagonal entries are zeroed before graph construction.
    """
    roi_names = list(df.columns)
    graph = ig.Graph()
    graph.add_vertices(len(roi_names))
    graph.vs["name"] = roi_names
    graph.vs["id"] = roi_names

    corr_array = df.to_numpy(dtype=float)
    row_indices, col_indices = np.triu_indices(len(roi_names), k=1)
    edge_weights = corr_array[row_indices, col_indices]
    nonzero_mask = edge_weights != 0

    graph.add_edges(list(zip(row_indices[nonzero_mask].tolist(), col_indices[nonzero_mask].tolist())))
    graph.es["weight"] = edge_weights[nonzero_mask].tolist()
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


def _leiden_single_run(seed: int) -> List[float]:
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
    windows: List[Tuple[int, str]],
    n_runs: int = N_RUNS,
    gamma: float = DEFAULT_GAMMA,
    omega: float = DEFAULT_OMEGA,
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
    graphs: List[ig.Graph] = []
    node_names: Optional[List[str]] = None
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


def parse_filename(path: str) -> Tuple[str, str, str, int]:
    """Return (subject_date, mouse_id, scan_id, window_id) from a connectivity CSV path.

    subject_date strips the final mouse letter so same-day mice share a folder.
    Example: sub-ag231031b_SHAM_bold_parcellated_window_0008.csv
      -> subject_date: sub-ag231031
      -> mouse_id:     sub-ag231031b
      -> scan_id:      sub-ag231031b_SHAM_bold_parcellated
      -> window_id:    8
    """
    stem = os.path.basename(path).replace(".csv", "")
    match = re.search(r"_window_(\d+)$", stem)
    window_id = int(match.group(1))
    scan_id = stem[: match.start()]
    subject_id = scan_id.split("_")[0]
    subject_date = re.sub(r"[a-z]$", "", subject_id)
    return subject_date, subject_id, scan_id, window_id


def connectivity_context(connectivity_dir: str, path: str) -> Tuple[str, str]:
    """Return dataset and preprocessing context for subject-nested connectivity files."""
    rel_parts = os.path.relpath(path, connectivity_dir).split(os.sep)
    if len(rel_parts) != 5:
        raise ValueError(
            f"Expected <dataset>/<preproc>/<animal_id>/<subject_id>/<window>.csv under {connectivity_dir}, got {path}"
        )
    return rel_parts[0], rel_parts[1]


def _run_scan_group(args: tuple) -> None:
    (
        dataset,
        preproc_pipeline,
        subject_date,
        mouse_id,
        scan_id,
        entries,
        output_dir,
        n_runs,
        gamma,
        omega,
        run_workers,
        scan_idx,
        n_scans,
    ) = args
    mouse_dir = os.path.join(output_dir, dataset, subject_date, mouse_id)
    os.makedirs(mouse_dir, exist_ok=True)

    # Scan header — [i/N] makes interleaved output from parallel workers identifiable
    print(f"\n[{scan_idx}/{n_scans}] {scan_id}  [{dataset}/{preproc_pipeline}]  {len(entries)} windows", flush=True)
    t0_scan = time.time()

    result = run_community_detection(
        entries,
        n_runs=n_runs,
        gamma=gamma,
        omega=omega,
        run_workers=run_workers,
    )
    result["last_run"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    output_path = os.path.join(mouse_dir, f"{scan_id}.csv")
    result.to_csv(output_path, index=False)

    print(f"  {'saved':<10} → {output_path}", flush=True)
    print(f"  {'total':<10} {_fmt_time(time.time() - t0_scan)}", flush=True)


def run_all(
    connectivity_dir: str,
    output_dir: str,
    dataset: str,
    n_runs: int = N_RUNS,
    gamma: float = DEFAULT_GAMMA,
    omega: float = DEFAULT_OMEGA,
    scan_workers: int = SCAN_WORKERS,
    run_workers: int = RUN_WORKERS,
) -> dict:
    """Run temporal Leiden on all scans and save one CSV per scan.

    Output CSV columns: Node | flexibility
    """
    connectivity_files = sorted(glob(os.path.join(connectivity_dir, dataset, "*", "*", "*", "*.csv")))
    assert connectivity_files, f"No connectivity matrices found for dataset {dataset!r} in {connectivity_dir}"

    # Group window files by dataset, subject date, mouse, and scan.
    groups: Dict[Tuple[str, str, str, str, str], List[Tuple[int, str]]] = defaultdict(list)
    for path in connectivity_files:
        subject_date, mouse_id, scan_id, window_id = parse_filename(path)
        dataset_name, preproc_pipeline = connectivity_context(connectivity_dir, path)
        groups[(dataset_name, preproc_pipeline, subject_date, mouse_id, scan_id)].append((window_id, path))

    n_scans = len(groups)
    scan_workers = max(1, min(scan_workers, n_scans))

    # Build jobs, including each scan's position index for the [i/N] header
    scan_jobs = [
        (
            dataset_name,
            preproc_pipeline,
            subject_date,
            mouse_id,
            scan_id,
            entries,
            output_dir,
            n_runs,
            gamma,
            omega,
            run_workers,
            idx + 1,
            n_scans,
        )
        for idx, ((dataset_name, preproc_pipeline, subject_date, mouse_id, scan_id), entries) in enumerate(groups.items())
    ]

    # ── Header ────────────────────────────────────────────────────────────────
    print(_DIVIDER)
    print(f"  Temporal Leiden  |  {dataset}  |  {n_scans} scans  |  γ={gamma}  ω={omega}  |  {n_runs} runs")
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

    return {
        "dataset": dataset,
        "output_dir": _repo_relpath(os.path.join(output_dir, dataset)),
        "n_scans": n_scans,
        "n_subject_dates": len({key[2] for key in groups}),
        "n_mice": len({key[3] for key in groups}),
        "preprocessing_pipelines": sorted({key[1] for key in groups}),
    }


def _build_manifest(run_name: str, run_dir: str, started_at: str) -> dict:
    parameter_grid = [
        {
            "width": width,
            "gamma": gamma,
            "omega": omega,
            "folder": os.path.join(f"wl{width}", _parameter_folder_name(gamma, omega)),
        }
        for width in WIDTHS
        for gamma in GAMMAS
        for omega in OMEGAS
    ]

    return {
        "run_name": run_name,
        "script": _repo_relpath(__file__),
        "command": _shell_join([sys.executable] + sys.argv),
        "git_commit": _git_commit(),
        "started_at": started_at,
        "finished_at": None,
        "elapsed_seconds": None,
        "output_root": _repo_relpath(run_dir),
        "input_roots": {width: _repo_relpath(connectivity_dir_for_width(width)) for width in WIDTHS},
        "datasets": DATASETS,
        "widths": WIDTHS,
        "gammas": GAMMAS,
        "omegas": OMEGAS,
        "n_runs": N_RUNS,
        "scan_workers": SCAN_WORKERS,
        "run_workers": RUN_WORKERS,
        "parameter_grid": parameter_grid,
        "runs": [],
        "errors": [],
        "skipped": [],
        "status": "running",
    }


def _validate_parameter_grid() -> None:
    if not DATASETS:
        raise ValueError("DATASETS is empty; add at least one dataset before running parameter inspection.")
    if not WIDTHS:
        raise ValueError("WIDTHS is empty; add at least one window length before running parameter inspection.")
    if not GAMMAS:
        raise ValueError("GAMMAS is empty; add at least one gamma value before running parameter inspection.")
    if not OMEGAS:
        raise ValueError("OMEGAS is empty; add at least one omega value before running parameter inspection.")


def _load_or_init_manifest(run_name: str, run_dir: str, manifest_path: str, started_at: str) -> dict:
    """Build a fresh manifest, or merge into one already on disk at run_dir.

    Merging only updates ``datasets`` (union with the current DATASETS) and
    flips ``status`` back to "running" — the existing ``runs``/``errors``/
    ``skipped`` history from prior datasets in this run dir is preserved as-is;
    new combos get appended to it by the caller.
    """
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
        manifest["datasets"] = sorted(set(manifest.get("datasets", [])) | set(DATASETS))
        manifest["status"] = "running"
        manifest["finished_at"] = None
        manifest["elapsed_seconds"] = None
        return manifest
    return _build_manifest(run_name, run_dir, started_at)


def run_parameter_grid() -> dict:
    """Run every dataset for every width/gamma/omega combination and keep a live manifest."""
    _validate_parameter_grid()

    started_at = _now_iso()
    if RESUME_RUN_NAME:
        run_name = RESUME_RUN_NAME
        run_dir = os.path.join(OUTPUTS_DIR, run_name)
        assert os.path.isdir(run_dir), f"RESUME_RUN_NAME={run_name!r} but {run_dir} does not exist"
    else:
        run_name = datetime.now().astimezone().strftime("%Y_%m_%d__%H-%M-%S")
        run_name, run_dir = _unique_run_dir(OUTPUTS_DIR, run_name)

    manifest_path = os.path.join(run_dir, "run_manifest.json")
    manifest = _load_or_init_manifest(run_name, run_dir, manifest_path, started_at)

    os.makedirs(run_dir, exist_ok=True)
    _write_manifest(manifest, manifest_path)

    t0 = time.time()
    try:
        for width in WIDTHS:
            connectivity_dir = connectivity_dir_for_width(width)
            width_dir = os.path.join(run_dir, f"wl{width}")

            for gamma in GAMMAS:
                for omega in OMEGAS:
                    parameter_folder = _parameter_folder_name(gamma, omega)
                    parameter_dir = os.path.join(width_dir, parameter_folder)

                    for dataset in DATASETS:
                        dataset_output_dir = os.path.join(parameter_dir, dataset)
                        run_entry = {
                            "width": width,
                            "gamma": gamma,
                            "omega": omega,
                            "parameter_folder": parameter_folder,
                            "dataset": dataset,
                            "output_dir": _repo_relpath(dataset_output_dir),
                            "started_at": _now_iso(),
                            "finished_at": None,
                            "elapsed_seconds": None,
                            "status": "running",
                        }
                        manifest["runs"].append(run_entry)
                        _write_manifest(manifest, manifest_path)

                        run_t0 = time.time()
                        try:
                            summary = run_all(
                                connectivity_dir,
                                parameter_dir,
                                dataset,
                                n_runs=N_RUNS,
                                gamma=gamma,
                                omega=omega,
                                scan_workers=SCAN_WORKERS,
                                run_workers=RUN_WORKERS,
                            )
                            run_entry.update(summary)
                            run_entry["status"] = "completed"
                        except Exception as exc:
                            run_entry["status"] = "failed"
                            run_entry["error_type"] = type(exc).__name__
                            run_entry["error"] = str(exc)
                            manifest["errors"].append({
                                "width": width,
                                "gamma": gamma,
                                "omega": omega,
                                "parameter_folder": parameter_folder,
                                "dataset": dataset,
                                "error_type": type(exc).__name__,
                                "message": str(exc),
                            })
                        finally:
                            run_entry["finished_at"] = _now_iso()
                            run_entry["elapsed_seconds"] = round(time.time() - run_t0, 3)
                            _write_manifest(manifest, manifest_path)
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
        manifest["finished_at"] = _now_iso()
        manifest["elapsed_seconds"] = round(time.time() - t0, 3)
        _write_manifest(manifest, manifest_path)
        raise

    completed_runs = sum(1 for entry in manifest["runs"] if entry["status"] == "completed")
    if manifest["errors"]:
        manifest["status"] = "completed_with_errors" if completed_runs else "failed"
    else:
        manifest["status"] = "completed"
    manifest["finished_at"] = _now_iso()
    manifest["elapsed_seconds"] = round(time.time() - t0, 3)
    _write_manifest(manifest, manifest_path)

    print(f"\nParameter inspection manifest: {manifest_path}")
    if manifest["errors"]:
        raise RuntimeError(f"{len(manifest['errors'])} parameter inspection run(s) failed; see {manifest_path}")
    return manifest


def test_one_connectivity_file(width: int = 35):
    """Smoke test on the first available scan (first 5 windows, 5 runs)."""
    connectivity_dir = connectivity_dir_for_width(width)
    connectivity_files = sorted(glob(os.path.join(connectivity_dir, "*", "*", "*", "*", "*.csv")))
    assert connectivity_files, f"No connectivity matrices found in {connectivity_dir}"

    stem = os.path.basename(connectivity_files[0]).replace(".csv", "")
    match = re.search(r"_window_(\d+)$", stem)
    scan_prefix = stem[: match.start()]
    scan_files = sorted(
        f for f in connectivity_files if os.path.basename(f).startswith(scan_prefix)
    )[:5]

    result = run_community_detection(
        [(parse_filename(f)[3], f) for f in scan_files],
        n_runs=5,
        run_workers=1,
    )
    assert not result.empty
    assert {"Node", "flexibility"}.issubset(result.columns)
    print(f"Tested: {scan_files}")
    print(result)


if __name__ == "__main__":
    run_parameter_grid()
