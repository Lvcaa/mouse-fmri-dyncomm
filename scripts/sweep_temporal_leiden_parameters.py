#!/usr/bin/env python3
"""Sweep temporal Leiden gamma and omega values for one DTA anesthesia mouse."""

import argparse
import json
import multiprocessing
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from glob import glob
from pathlib import Path

import igraph as ig
import leidenalg as la
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUTS_ROOT = SCRIPT_DIR.parent / "outputs"
DEFAULT_DATASET_DIR = OUTPUTS_ROOT / "window_connectivity" / "Bf_DTA_anes"
DEFAULT_OUTPUT_DIR = OUTPUTS_ROOT / "community_parameter_sweeps"
DIVIDER = "=" * 72

_worker_graphs = None
_worker_gamma = None
_worker_omega = None


class Terminal:
    """Small ANSI formatter that disables colors when stdout is redirected."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(int(seconds), 60)
    return f"{minutes}m {remaining:02d}s"


def parse_float_values(value: str) -> list[float]:
    """Parse comma values or inclusive start:stop:step notation."""
    try:
        if ":" in value:
            start, stop, step = (float(part) for part in value.split(":"))
            if step <= 0 or stop < start:
                raise ValueError
            count = int(np.floor((stop - start) / step + 1e-9)) + 1
            values = start + np.arange(count) * step
        else:
            values = np.asarray([float(part) for part in value.split(",")])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Use comma values (0.1,0.2) or start:stop:step (0.1:0.4:0.1)"
        ) from exc

    if len(values) == 0 or not np.all(np.isfinite(values)):
        raise argparse.ArgumentTypeError("Parameter list must contain finite values")
    return [round(float(item), 10) for item in values]


def get_mouse_name(csv_path: str) -> str:
    """Return the mouse ID encoded by the letter after the acquisition date."""
    filename = os.path.basename(csv_path)
    match = re.match(r"^(sub-[A-Za-z]+\d+)([A-Za-z])_", filename)
    if match is None:
        raise ValueError(f"Cannot retrieve mouse name from: {filename}")
    return f"{match.group(1)}{match.group(2).lower()}"


def get_window_id(csv_path: str) -> int:
    match = re.search(r"_window_(\d+)\.csv$", os.path.basename(csv_path))
    if match is None:
        raise ValueError(f"Cannot retrieve window number from: {csv_path}")
    return int(match.group(1))


def discover_mice(dataset_dir: Path, preprocessing_folder: str | None):
    preprocessing_folders = sorted(path for path in dataset_dir.glob("*") if path.is_dir())
    if not preprocessing_folders:
        raise FileNotFoundError(f"No preprocessing folders found inside {dataset_dir}")

    if preprocessing_folder:
        selected_preprocessing = dataset_dir / preprocessing_folder
        if not selected_preprocessing.is_dir():
            raise FileNotFoundError(
                f"Preprocessing folder does not exist: {selected_preprocessing}"
            )
    else:
        selected_preprocessing = preprocessing_folders[0]

    mice = defaultdict(lambda: defaultdict(list))
    for date_folder in sorted(selected_preprocessing.glob("sub-*")):
        if not date_folder.is_dir():
            continue
        date_name = date_folder.name
        for csv_path in date_folder.glob("*/*.csv"):
            mice[date_name][get_mouse_name(str(csv_path))].append(str(csv_path))

    for date_name in mice:
        for mouse_name in mice[date_name]:
            mice[date_name][mouse_name].sort(key=get_window_id)

    if not mice:
        raise FileNotFoundError(f"No mouse window CSV files found in {selected_preprocessing}")
    return selected_preprocessing, mice


def choose_mouse(mice, date_name: str | None, mouse_name: str | None):
    selected_date = date_name or sorted(mice)[0]
    if selected_date not in mice:
        raise ValueError(
            f"Unknown date {selected_date}. Available: {', '.join(sorted(mice))}"
        )

    selected_mouse = mouse_name or sorted(mice[selected_date])[0]
    if selected_mouse not in mice[selected_date]:
        raise ValueError(
            f"Unknown mouse {selected_mouse} for {selected_date}. "
            f"Available: {', '.join(sorted(mice[selected_date]))}"
        )
    return selected_date, selected_mouse, mice[selected_date][selected_mouse]


def build_connectivity_graph(connectivity_df: pd.DataFrame, edge_mode: str) -> ig.Graph:
    """Build the same signed complete graph used by the notebook."""
    roi_names = list(connectivity_df.columns)
    if list(connectivity_df.index) != roi_names:
        raise ValueError("Connectivity matrix row and column labels differ")

    values = connectivity_df.to_numpy(dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("Connectivity matrix contains non-finite values")
    if not np.allclose(values, values.T):
        raise ValueError("Connectivity matrix is not symmetric")

    row_indices, col_indices = np.triu_indices(len(roi_names), k=1)
    edge_weights = values[row_indices, col_indices]

    if edge_mode == "signed":
        keep = np.ones(len(edge_weights), dtype=bool)
    else:
        keep = edge_weights > 0

    graph = ig.Graph()
    graph.add_vertices(len(roi_names))
    graph.vs["name"] = roi_names
    graph.vs["id"] = roi_names
    graph.add_edges(
        list(zip(row_indices[keep].tolist(), col_indices[keep].tolist()))
    )
    graph.es["weight"] = edge_weights[keep].tolist()
    return graph


def build_temporal_graphs(csv_paths: list[str], edge_mode: str):
    graphs = []
    expected_rois = None
    for csv_path in csv_paths:
        connectivity_df = pd.read_csv(csv_path, index_col=0)
        roi_names = list(connectivity_df.columns)
        if expected_rois is None:
            expected_rois = roi_names
        elif roi_names != expected_rois:
            raise ValueError(f"ROI names or order differ in {csv_path}")
        graphs.append(build_connectivity_graph(connectivity_df, edge_mode))

    if len(graphs) < 2:
        raise ValueError("Temporal community detection requires at least two windows")
    return graphs, expected_rois


def init_worker(graphs, gamma: float, omega: float):
    global _worker_graphs, _worker_gamma, _worker_omega
    _worker_graphs = graphs
    _worker_gamma = gamma
    _worker_omega = omega


def run_leiden_once(seed: int):
    memberships, improvement = la.find_partition_temporal(
        _worker_graphs,
        la.CPMVertexPartition,
        interslice_weight=_worker_omega,
        vertex_id_attr="id",
        weight_attr="weight",
        resolution_parameter=_worker_gamma,
        seed=seed,
    )
    membership = np.asarray(memberships, dtype=np.int32)
    n_windows, n_rois = membership.shape

    community_counts = np.asarray(
        [len(np.unique(row)) for row in membership], dtype=float
    )
    singleton_nodes = 0
    coassignment = np.zeros((n_rois, n_rois), dtype=float)
    for row in membership:
        _, counts = np.unique(row, return_counts=True)
        singleton_nodes += int(np.sum(counts == 1))
        coassignment += row[:, None] == row[None, :]
    coassignment /= n_windows

    flexibility = np.mean(membership[1:] != membership[:-1], axis=0)
    return {
        "seed": seed,
        "improvement": float(improvement),
        "communities_mean": float(community_counts.mean()),
        "communities_min": int(community_counts.min()),
        "communities_max": int(community_counts.max()),
        "singleton_fraction": singleton_nodes / (n_windows * n_rois),
        "flexibility_mean": float(flexibility.mean()),
        "coassignment": coassignment,
    }


def run_parameter_pair(
    graphs,
    gamma: float,
    omega: float,
    n_runs: int,
    run_workers: int,
    seeds: list[int],
):
    init_args = (graphs, gamma, omega)
    if run_workers == 1:
        init_worker(*init_args)
        run_results = [run_leiden_once(seed) for seed in seeds]
    else:
        context = multiprocessing.get_context("fork")
        run_results = []
        with ProcessPoolExecutor(
            max_workers=run_workers,
            mp_context=context,
            initializer=init_worker,
            initargs=init_args,
        ) as executor:
            futures = [executor.submit(run_leiden_once, seed) for seed in seeds]
            for future in as_completed(futures):
                run_results.append(future.result())

    coassignments = np.stack([result.pop("coassignment") for result in run_results])
    consensus = coassignments.mean(axis=0)
    stability = 1.0 - float(np.mean(np.abs(coassignments - consensus)))
    run_table = pd.DataFrame(run_results)

    summary = {
        "gamma": gamma,
        "omega": omega,
        "n_runs": n_runs,
        "communities_mean": run_table["communities_mean"].mean(),
        "communities_run_sd": run_table["communities_mean"].std(ddof=0),
        "communities_min": run_table["communities_min"].min(),
        "communities_max": run_table["communities_max"].max(),
        "singleton_fraction": run_table["singleton_fraction"].mean(),
        "flexibility_mean": run_table["flexibility_mean"].mean(),
        "coassignment_stability": stability,
        "quality_improvement_mean": run_table["improvement"].mean(),
    }
    return summary, consensus, run_table


def save_coassignment(
    matrix: np.ndarray,
    roi_names: list[str],
    output_dir: Path,
    gamma: float,
    omega: float,
):
    filename = f"coassignment_gamma-{gamma:g}_omega-{omega:g}.csv"
    pd.DataFrame(matrix, index=roi_names, columns=roi_names).to_csv(
        output_dir / filename
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Sweep temporal Leiden gamma and omega values for one mouse. "
            "Gamma/omega accept comma lists or start:stop:step notation."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--preprocessing-folder")
    parser.add_argument("--date", help="Date folder, for example sub-ag230920")
    parser.add_argument("--mouse", help="Mouse ID, for example sub-ag230920a")
    parser.add_argument("--gamma", type=parse_float_values, default=parse_float_values("0.1:0.3:0.05"))
    parser.add_argument("--omega", type=parse_float_values, default=parse_float_values("0.25,0.5,1.0"))
    parser.add_argument("--n-runs", type=int, default=10)
    parser.add_argument("--run-workers", type=int, default=1)
    parser.add_argument("--edge-mode", choices=("signed", "positive"), default="signed")
    parser.add_argument(
        "--max-windows",
        type=int,
        help="Use only the first N windows. Intended for smoke tests.",
    )
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-color", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.n_runs < 1:
        raise ValueError("--n-runs must be at least 1")
    if args.run_workers < 1:
        raise ValueError("--run-workers must be at least 1")

    terminal = Terminal(sys.stdout.isatty() and not args.no_color)
    preprocessing_dir, mice = discover_mice(
        args.dataset_dir.resolve(), args.preprocessing_folder
    )
    date_name, mouse_name, mouse_windows = choose_mouse(
        mice, args.date, args.mouse
    )
    if args.max_windows is not None:
        if args.max_windows < 2:
            raise ValueError("--max-windows must be at least 2")
        mouse_windows = mouse_windows[: args.max_windows]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir.resolve() / f"{mouse_name}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=False)

    print(terminal.bold(DIVIDER))
    print(terminal.bold("  Temporal Leiden parameter sweep"))
    print(f"  Mouse:       {terminal.cyan(mouse_name)} ({date_name})")
    print(f"  Preprocess:  {preprocessing_dir.name}")
    print(f"  Edge mode:   {args.edge_mode}")
    print(f"  Windows:     {len(mouse_windows)}")
    print(f"  Gamma:       {args.gamma}")
    print(f"  Omega:       {args.omega}")
    print(f"  Runs/pair:   {args.n_runs}")
    print(f"  Workers:     {args.run_workers}")
    print(f"  Output:      {output_dir}")
    print(terminal.bold(DIVIDER))

    load_start = time.time()
    graphs, roi_names = build_temporal_graphs(mouse_windows, args.edge_mode)
    print(
        f"  {terminal.green('loaded')}      {len(graphs)} graphs, "
        f"{len(roi_names)} ROIs in {format_time(time.time() - load_start)}"
    )

    combinations = [(gamma, omega) for gamma in args.gamma for omega in args.omega]
    seed_generator = np.random.default_rng(args.seed)
    summary_rows = []
    all_start = time.time()

    for index, (gamma, omega) in enumerate(combinations, start=1):
        pair_start = time.time()
        print(
            f"\n  [{index:>2}/{len(combinations)}] "
            f"{terminal.bold(f'gamma={gamma:g}  omega={omega:g}')}"
        )
        seeds = seed_generator.integers(
            0, 2**31 - 1, size=args.n_runs, dtype=np.int64
        ).tolist()
        summary, consensus, run_table = run_parameter_pair(
            graphs,
            gamma,
            omega,
            args.n_runs,
            min(args.run_workers, args.n_runs),
            seeds,
        )
        summary_rows.append(summary)
        save_coassignment(consensus, roi_names, output_dir, gamma, omega)
        run_table.to_csv(
            output_dir / f"runs_gamma-{gamma:g}_omega-{omega:g}.csv",
            index=False,
        )
        pd.DataFrame(summary_rows).to_csv(output_dir / "summary.csv", index=False)

        print(
            f"       communities={summary['communities_mean']:.2f}  "
            f"singletons={summary['singleton_fraction']:.1%}  "
            f"flexibility={summary['flexibility_mean']:.3f}"
        )
        print(
            f"       stability={summary['coassignment_stability']:.3f}  "
            f"time={format_time(time.time() - pair_start)}"
        )

    metadata = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "date": date_name,
        "mouse": mouse_name,
        "preprocessing_directory": str(preprocessing_dir),
        "edge_mode": args.edge_mode,
        "n_windows": len(mouse_windows),
        "n_rois": len(roi_names),
        "gamma_values": args.gamma,
        "omega_values": args.omega,
        "n_runs": args.n_runs,
        "run_workers": args.run_workers,
        "seed": args.seed,
        "first_window": os.path.basename(mouse_windows[0]),
        "last_window": os.path.basename(mouse_windows[-1]),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    summary_df = pd.DataFrame(summary_rows)
    print(f"\n{terminal.bold(DIVIDER)}")
    print(terminal.green(f"  Completed {len(combinations)} parameter pairs"))
    print(f"  Total time:  {format_time(time.time() - all_start)}")
    print(f"  Summary:     {output_dir / 'summary.csv'}")
    print(terminal.bold(DIVIDER))

    display_columns = [
        "gamma",
        "omega",
        "communities_mean",
        "singleton_fraction",
        "flexibility_mean",
        "coassignment_stability",
    ]
    print("\n" + summary_df[display_columns].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
