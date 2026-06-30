#!/usr/bin/env python3
"""Standalone watchdog for the parameters_inspection.py parameter sweep.

Runs independently of any chat session — intended to be launched in its own
`screen` session on the cluster (see usage at the bottom of this file).

Every CHECK_INTERVAL_SEC, reads the sweep's run_manifest.json. If the
currently running combo has been running longer than STALL_THRESHOLD_SEC,
walks the process tree rooted at the `SCREEN -S parameter_inspection`
session, and for every leaf worker that looks genuinely stuck (R state,
CPU time roughly equal to elapsed time, >30 min), verifies it strictly
before touching it:

  1. cmdline must literally contain "parameters_inspection.py"
  2. /proc/<pid>/status Uid: must exactly equal this script's own UID
  3. both (1) and (2) are re-checked again immediately before the signal
     (protects against the process exiting/PID being reused mid-check)

Only ever sends SIGTERM to a single, fully-verified PID at a time — never
a process group, never SIGKILL, never a name-pattern kill across the
whole machine. If a candidate fails any check, or exits on its own before
the re-check, it is skipped and logged, not killed.

After a kill, waits for the manifest to mark the combo "failed", then
diffs that combo's output directory against another completed combo of
the same width AND dataset to identify exactly which scan(s) are missing
(the run dir can hold combos for more than one dataset — e.g. the
2026-06-20 run dir holds both Bf_DTA_anes and Bf_DTA_awk — so the reference
combo must match both, or the diff is meaningless: different datasets have
disjoint scan filenames), and appends a dated entry to
docs/ParameterInspectionStuckRun.md with the PIDs killed, verification
done, and the missing scan(s) + output paths.

Stops on its own once the manifest's overall status is no longer
"running" (sweep finished or interrupted).
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

REPO_DIR = "/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm"
SWEEP_OUTPUT_ROOT = os.path.join(REPO_DIR, "outputs", "parameter_inspection")
DOC_PATH = os.path.join(REPO_DIR, "docs", "ParameterInspectionStuckRun.md")
LOG_PATH = os.path.join(SWEEP_OUTPUT_ROOT, "watchdog.log")
PIDFILE_PATH = os.path.join(SWEEP_OUTPUT_ROOT, "watchdog.pid")

sys.path.insert(0, os.path.dirname(__file__))
from parameters_inspection import RESUME_RUN_NAME  # noqa: E402

CHECK_INTERVAL_SEC = 1200      # 20 min between checks
STALL_THRESHOLD_SEC = 2100     # 35 min — past this, a combo is "stalled"
MIN_WORKER_ETIME_SEC = 1800    # 30 min — minimum age to even consider a worker stuck
CPU_PEG_TOLERANCE_SEC = 180    # CPU time must be within this of elapsed time
POST_KILL_POLL_SEC = 5
POST_KILL_POLL_MAX_TRIES = 12  # up to 60s waiting for manifest to flip to "failed"

MY_UID = os.getuid()


def log(msg: str) -> None:
    line = f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def find_latest_run_dir() -> str | None:
    """Pick the run dir to watch.

    Prefers RESUME_RUN_NAME (parameters_inspection.py's own target run dir)
    when set, since that's the single source of truth for where the sweep is
    currently writing — directory mtime is not reliable here: resuming a run
    to add a new dataset only touches subdirectories nested deep inside the
    run dir (e.g. wl35/gamma_X_omega_Y/Bf_DTA_awk/), which bumps that
    subdirectory's own mtime, not the top-level run dir's. Falls back to the
    mtime heuristic only if RESUME_RUN_NAME is unset (fresh, non-resumed
    sweep).
    """
    if RESUME_RUN_NAME:
        candidate = os.path.join(SWEEP_OUTPUT_ROOT, RESUME_RUN_NAME)
        if os.path.exists(os.path.join(candidate, "run_manifest.json")):
            return candidate
        return None

    if not os.path.isdir(SWEEP_OUTPUT_ROOT):
        return None
    candidates = [
        os.path.join(SWEEP_OUTPUT_ROOT, d)
        for d in os.listdir(SWEEP_OUTPUT_ROOT)
        if os.path.isdir(os.path.join(SWEEP_OUTPUT_ROOT, d)) and os.path.exists(
            os.path.join(SWEEP_OUTPUT_ROOT, d, "run_manifest.json")
        )
    ]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def read_manifest(run_dir: str) -> dict:
    with open(os.path.join(run_dir, "run_manifest.json")) as f:
        return json.load(f)


def get_running_combo(manifest: dict) -> dict | None:
    running = [r for r in manifest.get("runs", []) if r.get("status") == "running"]
    return running[-1] if running else None


def find_screen_root_pid() -> int | None:
    try:
        out = subprocess.run(
            ["pgrep", "-f", "SCREEN -S parameter_inspection"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    except Exception:
        return None
    pids = [int(p) for p in out.splitlines() if p.strip().isdigit()]
    return pids[0] if pids else None


def walk_descendants(root_pid: int) -> list[int]:
    """Structural tree-walk via /proc — never matches by process name."""
    def children_of(pid: int) -> list[int]:
        out = []
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/stat") as f:
                    fields = f.read().split(")")[-1].split()
                ppid = int(fields[1])
                if ppid == pid:
                    out.append(int(entry))
            except (FileNotFoundError, ProcessLookupError, IndexError, ValueError):
                continue
        return out

    acc: list[int] = []

    def walk(pid: int) -> None:
        acc.append(pid)
        for c in children_of(pid):
            walk(c)

    walk(root_pid)
    return acc


def parse_cpu_time(ps_time: str) -> int:
    """Parse ps's TIME field: '[DD-]HH:MM:SS' or 'MM:SS' -> seconds."""
    days = 0
    if "-" in ps_time:
        days_str, ps_time = ps_time.split("-", 1)
        days = int(days_str)
    parts = [int(p) for p in ps_time.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return days * 86400 + h * 3600 + m * 60 + s


def get_proc_timing(pid: int) -> dict | None:
    try:
        out = subprocess.run(
            ["ps", "-o", "stat=,etimes=,time=", "-p", str(pid)],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    except Exception:
        return None
    if not out:
        return None
    parts = out.split(None, 2)
    if len(parts) < 3:
        return None
    stat, etimes, cputime = parts
    try:
        return {
            "state": stat,
            "etimes": int(etimes),
            "cputime_sec": parse_cpu_time(cputime),
        }
    except ValueError:
        return None


def read_cmdline(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
        return raw.replace(b"\0", b" ").decode(errors="replace").strip()
    except (FileNotFoundError, ProcessLookupError):
        return None


def read_uid(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("Uid:"):
                    return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError):
        return None
    return None


def find_stuck_candidates(root_pid: int) -> list[int]:
    candidates = []
    for pid in walk_descendants(root_pid):
        if pid == root_pid:
            continue
        timing = get_proc_timing(pid)
        if timing is None:
            continue
        if not timing["state"].startswith("R"):
            continue
        if timing["etimes"] < MIN_WORKER_ETIME_SEC:
            continue
        if abs(timing["etimes"] - timing["cputime_sec"]) > CPU_PEG_TOLERANCE_SEC:
            continue  # not genuinely pegged -> ambiguous, don't touch
        candidates.append(pid)
    return candidates


def verify_strictly(pid: int) -> bool:
    """Both checks must pass: exact script-name match, exact UID match."""
    cmdline = read_cmdline(pid)
    if cmdline is None or "parameters_inspection.py" not in cmdline:
        log(f"SKIP PID {pid}: cmdline does not strictly match parameters_inspection.py ({cmdline!r})")
        return False
    uid = read_uid(pid)
    if uid != MY_UID:
        log(f"SKIP PID {pid}: owned by UID {uid}, not mine ({MY_UID})")
        return False
    return True


def kill_candidate(pid: int) -> bool:
    """Verify once more immediately before signaling, then SIGTERM only this PID."""
    if not verify_strictly(pid):
        log(f"SKIP PID {pid}: failed re-verification immediately before kill")
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        log(f"SKIP PID {pid}: exited on its own before the kill could be sent (self-resolved)")
        return False
    except PermissionError:
        log(f"SKIP PID {pid}: kill raised PermissionError (should be impossible given UID check) — not retrying")
        return False

    time.sleep(5)
    if os.path.exists(f"/proc/{pid}"):
        log(f"WARNING: sent SIGTERM to PID {pid} but it is still present after 5s")
        return False
    log(f"KILLED PID {pid}")
    return True


def dataset_dir_abs(output_dir_rel: str) -> str:
    """combo['output_dir'] in the manifest is already '.../gamma_X_omega_Y/<dataset>'."""
    return os.path.join(REPO_DIR, output_dir_rel)


def scan_output_path(dataset_dir: str, scan_filename: str) -> str:
    scan_id = scan_filename[:-4] if scan_filename.endswith(".csv") else scan_filename
    subject_id = scan_id.split("_")[0]
    subject_date = re.sub(r"[a-z]$", "", subject_id)
    return os.path.join(dataset_dir, subject_date, subject_id, scan_filename)


def find_missing_scans(combo: dict, manifest: dict) -> list[str]:
    output_dir_abs = dataset_dir_abs(combo["output_dir"])
    if not os.path.isdir(output_dir_abs):
        return []
    have = set()
    for _, _, files in os.walk(output_dir_abs):
        have.update(fn for fn in files if fn.endswith(".csv"))

    reference = None
    for r in manifest.get("runs", []):
        if (
            r.get("status") == "completed"
            and r.get("width") == combo["width"]
            and r.get("dataset") == combo.get("dataset")
            and r.get("output_dir") != combo["output_dir"]
        ):
            reference = r
    if reference is None:
        return []
    ref_dir_abs = dataset_dir_abs(reference["output_dir"])
    expected = set()
    for _, _, files in os.walk(ref_dir_abs):
        expected.update(fn for fn in files if fn.endswith(".csv"))

    return sorted(expected - have)


def wait_for_combo_resolution(run_dir: str, combo: dict) -> dict | None:
    for _ in range(POST_KILL_POLL_MAX_TRIES):
        time.sleep(POST_KILL_POLL_SEC)
        manifest = read_manifest(run_dir)
        for r in manifest.get("runs", []):
            if (
                r.get("width") == combo["width"]
                and r.get("gamma") == combo["gamma"]
                and r.get("omega") == combo["omega"]
                and r.get("started_at") == combo["started_at"]
                and r.get("status") != "running"
            ):
                return manifest
    return None


def append_doc_entry(combo: dict, killed_pids: list[int], skipped: list[str], missing_scans: list[str], dataset_dir: str) -> None:
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = []
    lines.append(f"\n## Watchdog occurrence — {ts}")
    lines.append("")
    lines.append(
        f"Combo **width={combo['width']}, γ={combo['gamma']}, ω={combo['omega']}** "
        f"(started `{combo['started_at']}`) flagged as stalled by the standalone "
        f"watchdog (`scripts/parameter_inspection_watchdog.py`), running independently "
        f"in its own `screen` session."
    )
    lines.append("")
    if killed_pids:
        lines.append(f"Killed PID(s): {', '.join(str(p) for p in killed_pids)}. Each was "
                      f"verified via `/proc/<pid>/cmdline` (must contain "
                      f"`parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` "
                      f"(must equal the script's own `os.getuid()`), re-checked again "
                      f"immediately before each individual `SIGTERM`. All confirmed gone "
                      f"within 5s.")
    if skipped:
        lines.append("")
        lines.append("Skipped candidates (not killed):")
        for s in skipped:
            lines.append(f"- {s}")
    lines.append("")
    if missing_scans:
        lines.append("Missing scan(s) to rerun:")
        for fn in missing_scans:
            full_path = scan_output_path(dataset_dir, fn)
            scan_id = fn[:-4] if fn.endswith(".csv") else fn
            lines.append(f"- `{scan_id}` → `{full_path}`")
    else:
        lines.append("No missing scans identified (or no reference combo available yet for this width).")
    lines.append("")

    with open(DOC_PATH, "a") as f:
        f.write("\n".join(lines) + "\n")
    log(f"Logged occurrence to {DOC_PATH}")


def handle_stall(run_dir: str, combo: dict, manifest: dict) -> None:
    root_pid = find_screen_root_pid()
    if root_pid is None:
        log("Could not find SCREEN -S parameter_inspection root PID; skipping this cycle (no action taken).")
        return

    candidates = find_stuck_candidates(root_pid)
    if not candidates:
        log(f"No qualifying stuck workers found for width={combo['width']} gamma={combo['gamma']} "
            f"omega={combo['omega']} (elapsed-based threshold crossed, but no candidate matched the "
            f"stuck signature) — will recheck next cycle.")
        return

    killed_pids = []
    skipped = []
    for pid in candidates:
        if kill_candidate(pid):
            killed_pids.append(pid)
        else:
            skipped.append(f"PID {pid}")

    if not killed_pids:
        log("No candidates were actually killed this cycle (all skipped/self-resolved).")
        return

    resolved_manifest = wait_for_combo_resolution(run_dir, combo)
    if resolved_manifest is None:
        log("Killed worker(s) but manifest did not flip to a resolved status within 60s — "
            "will pick up the missing-scan diff next time the script restarts or on manual follow-up.")
        return

    missing = find_missing_scans(combo, resolved_manifest)
    append_doc_entry(combo, killed_pids, skipped, missing, dataset_dir_abs(combo["output_dir"]))


def main() -> None:
    os.makedirs(SWEEP_OUTPUT_ROOT, exist_ok=True)
    with open(PIDFILE_PATH, "w") as f:
        f.write(str(os.getpid()) + "\n")
    log(f"Watchdog started (PID {os.getpid()}, my UID {MY_UID}). "
        f"Check interval {CHECK_INTERVAL_SEC}s, stall threshold {STALL_THRESHOLD_SEC}s.")

    while True:
        run_dir = find_latest_run_dir()
        if run_dir is None:
            log("No run dir with a manifest found; sleeping.")
            time.sleep(CHECK_INTERVAL_SEC)
            continue

        try:
            manifest = read_manifest(run_dir)
        except Exception as e:
            log(f"Could not read manifest ({e}); sleeping.")
            time.sleep(CHECK_INTERVAL_SEC)
            continue

        if manifest.get("status") != "running":
            log(f"Sweep overall status is '{manifest.get('status')}' — sweep finished. Watchdog exiting.")
            return

        combo = get_running_combo(manifest)
        if combo is None:
            log("No running combo found in manifest; sleeping.")
            time.sleep(CHECK_INTERVAL_SEC)
            continue

        started = datetime.fromisoformat(combo["started_at"])
        elapsed = (datetime.now().astimezone() - started).total_seconds()
        width, gamma, omega = combo["width"], combo["gamma"], combo["omega"]

        if elapsed < STALL_THRESHOLD_SEC:
            log(f"OK: width={width} gamma={gamma} omega={omega} elapsed={elapsed/60:.1f}min "
                f"(< {STALL_THRESHOLD_SEC/60:.0f}min threshold)")
            time.sleep(CHECK_INTERVAL_SEC)
            continue

        log(f"STALL SUSPECTED: width={width} gamma={gamma} omega={omega} "
            f"elapsed={elapsed/60:.1f}min — investigating")
        handle_stall(run_dir, combo, manifest)
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
