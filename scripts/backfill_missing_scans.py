"""Backfill scans missing from a parameter-sweep run due to watchdog-killed
non-converging Leiden workers (see docs/ParameterInspectionStuckRun.md).

For each combo short of the expected 42 scans, diffs its scan-ID set against
a same-width reference combo that completed cleanly, then reruns only the
missing scans via run_community_detection() directly. Never calls run_all()
for a combo -- that has no skip-existing logic and would recompute all 42
scans instead of just the gap.

Each missing scan runs in its own subprocess with a hard wall-clock timeout
(default 30 min, generously above the ~30-60s normal runtime). On timeout the
subprocess is killed and the scan is left for manual review, instead of
blocking the rest of the backfill the way the original stuck seeds blocked
the sweep for hours.

Usage:
    python3 backfill_missing_scans.py --dry-run        # just report the gap
    python3 backfill_missing_scans.py                   # backfill, concurrency=1
    python3 backfill_missing_scans.py --concurrency 4    # 4 scans at a time
                                                          # (4 x run-workers cores)
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from glob import glob

sys.path.insert(0, os.path.dirname(__file__))
from parameters_inspection import (  # noqa: E402
    DATASETS,
    N_RUNS,
    OUTPUTS_DIR,
    RUN_WORKERS,
    WIDTHS,
    connectivity_context,
    connectivity_dir_for_width,
    parse_filename,
    run_community_detection,
)

RUN_NAME = "2026_06_20__01-16-56"
RUN_DIR = os.path.join(OUTPUTS_DIR, RUN_NAME)
EXPECTED_SCANS_PER_COMBO = 42
DEFAULT_TIMEOUT_S = 30 * 60


def _scan_csvs(combo_dir: str, dataset: str) -> dict:
    """Map scan_id -> csv path for every scan CSV already on disk in a combo."""
    pattern = os.path.join(combo_dir, dataset, "*", "*", "*.csv")
    return {os.path.basename(p)[:-4]: p for p in glob(pattern)}


def find_missing_scans(width: int, dataset: str) -> dict:
    """Return {combo_dir: sorted(missing_scan_ids)} for combos short of 42."""
    width_dir = os.path.join(RUN_DIR, f"wl{width}")
    combo_dirs = sorted(
        d for d in glob(os.path.join(width_dir, "gamma_*_omega_*")) if os.path.isdir(d)
    )

    per_combo_scans = {d: _scan_csvs(d, dataset) for d in combo_dirs}
    reference = max(per_combo_scans.values(), key=len)
    if len(reference) != EXPECTED_SCANS_PER_COMBO:
        raise RuntimeError(
            f"width={width}: no combo has the expected {EXPECTED_SCANS_PER_COMBO} scans "
            f"(best has {len(reference)}); can't establish a reference scan set."
        )
    full_scan_set = set(reference)

    missing = {}
    for combo_dir, scans in per_combo_scans.items():
        gap = full_scan_set - set(scans)
        if gap:
            missing[combo_dir] = sorted(gap)
    return missing


def _parse_combo_dir(combo_dir: str):
    """Pull (width, gamma, omega) back out of a '.../wl{N}/gamma_X_omega_Y' path."""
    width = int(os.path.basename(os.path.dirname(combo_dir)).removeprefix("wl"))
    folder = os.path.basename(combo_dir)
    gamma_str, omega_str = folder.removeprefix("gamma_").split("_omega_")
    return width, float(gamma_str), float(omega_str)


def _windows_for_scan(connectivity_dir: str, dataset: str, scan_id: str):
    """Locate every connectivity window CSV belonging to one scan."""
    all_files = glob(os.path.join(connectivity_dir, dataset, "*", "*", "*", "*.csv"))
    windows = []
    dataset_name = subject_date = mouse_id = None
    for path in all_files:
        sd, mid, sid, window_id = parse_filename(path)
        if sid != scan_id:
            continue
        dataset_name, _preproc = connectivity_context(connectivity_dir, path)
        subject_date, mouse_id = sd, mid
        windows.append((window_id, path))
    if not windows:
        raise RuntimeError(f"No connectivity windows found for scan {scan_id!r} under {connectivity_dir}")
    return windows, dataset_name, subject_date, mouse_id


def _backfill_one_scan(combo_dir, dataset, scan_id, gamma, omega, run_workers, n_runs, width):
    """Runs inside its own subprocess. Computes and writes the scan's CSV in place."""
    connectivity_dir = connectivity_dir_for_width(width)
    windows, dataset_name, subject_date, mouse_id = _windows_for_scan(
        connectivity_dir, dataset, scan_id
    )
    result = run_community_detection(
        windows, n_runs=n_runs, gamma=gamma, omega=omega, run_workers=run_workers
    )
    result["last_run"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    mouse_dir = os.path.join(combo_dir, dataset_name, subject_date, mouse_id)
    os.makedirs(mouse_dir, exist_ok=True)
    result.to_csv(os.path.join(mouse_dir, f"{scan_id}.csv"), index=False)


def backfill_scan(combo_dir, dataset, scan_id, gamma, omega, run_workers, n_runs, width, timeout_s):
    """Run one missing scan in its own process with a hard wall-clock timeout."""
    ctx = mp.get_context("fork")
    proc = ctx.Process(
        target=_backfill_one_scan,
        args=(combo_dir, dataset, scan_id, gamma, omega, run_workers, n_runs, width),
    )
    t0 = time.time()
    proc.start()
    proc.join(timeout_s)
    elapsed = time.time() - t0

    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
            proc.join()
        return {"scan_id": scan_id, "status": "timeout", "elapsed_seconds": round(elapsed, 1)}

    if proc.exitcode != 0:
        return {
            "scan_id": scan_id,
            "status": "error",
            "elapsed_seconds": round(elapsed, 1),
            "exitcode": proc.exitcode,
        }

    return {"scan_id": scan_id, "status": "completed", "elapsed_seconds": round(elapsed, 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DATASETS[0])
    parser.add_argument("--n-runs", type=int, default=N_RUNS)
    parser.add_argument("--run-workers", type=int, default=RUN_WORKERS)
    parser.add_argument(
        "--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_S,
        help="Per-scan wall-clock budget before its subprocess is killed (default 30 min).",
    )
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help="How many missing scans to backfill at once (each uses --run-workers cores).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only report what's missing; don't run anything.",
    )
    args = parser.parse_args()

    all_missing = {}
    for width in WIDTHS:
        all_missing.update(find_missing_scans(width, args.dataset))

    total_missing = sum(len(v) for v in all_missing.values())
    print(f"Found {total_missing} missing scans across {len(all_missing)} combos.")
    for combo_dir, scan_ids in sorted(all_missing.items()):
        print(f"  {os.path.relpath(combo_dir, RUN_DIR)}: {len(scan_ids)} missing")

    if args.dry_run or total_missing == 0:
        return

    report_path = os.path.join(RUN_DIR, "backfill_manifest.json")
    report = {"started_at": datetime.now().astimezone().isoformat(timespec="seconds"), "results": []}
    report_lock = threading.Lock()

    def _write_report():
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

    tasks = []
    for combo_dir, scan_ids in sorted(all_missing.items()):
        width, gamma, omega = _parse_combo_dir(combo_dir)
        for scan_id in scan_ids:
            tasks.append((combo_dir, scan_id, width, gamma, omega))

    def _run_task(task):
        combo_dir, scan_id, width, gamma, omega = task
        print(f"\n-> {os.path.relpath(combo_dir, RUN_DIR)} :: {scan_id}", flush=True)
        outcome = backfill_scan(
            combo_dir, args.dataset, scan_id, gamma, omega,
            args.run_workers, args.n_runs, width, args.timeout_seconds,
        )
        outcome.update({"combo": os.path.relpath(combo_dir, RUN_DIR), "width": width, "gamma": gamma, "omega": omega})
        print(f"  {outcome['status']}  ({outcome['elapsed_seconds']}s)", flush=True)
        with report_lock:
            report["results"].append(outcome)
            _write_report()
        return outcome

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [executor.submit(_run_task, task) for task in tasks]
        for future in as_completed(futures):
            future.result()

    report["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with report_lock:
        _write_report()

    n_ok = sum(1 for r in report["results"] if r["status"] == "completed")
    n_bad = len(report["results"]) - n_ok
    print(f"\nDone. {n_ok} backfilled, {n_bad} still failing -- see {report_path}")


if __name__ == "__main__":
    main()
