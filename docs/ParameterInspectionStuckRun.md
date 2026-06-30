# Stuck Leiden run — 2026-06-20 parameter sweep

## What happened

During the sweep started at `2026-06-20 01:16:55` (run dir
`outputs/parameter_inspection/2026_06_20__01-16-56/`), the combo
**width=35, γ=0.25, ω=0.4** hung for ~19 hours instead of the usual ~22 min.

Root cause: a single `_leiden_single_run` call (one seed, inside the inner
`run_workers` pool) never converged for one specific scan:

- **Scan:** `sub-ag230922a_SHAM_bold_parcellated` (subject `sub-ag230922a`)
- **Params:** width=35, γ=0.25, ω=0.4
- All 9 other seeds for that scan finished normally; all 41 other scans in
  the combo completed normally (42 expected, 41 CSVs on disk).

This wasn't system contention — load average and `iostat` were normal, and
the hung worker (PID 489720) was pegged at ~100% CPU the entire time,
meaning `leidenalg.find_partition_temporal` was actually computing, just
never finishing for that (graph, seed, γ=0.25, ω=0.4) combination.

## Action taken

Sent `SIGTERM` to the single hung worker process (PID 489720) only — no
other process touched. The parent `ProcessPoolExecutor` raised
`BrokenProcessPool`, which `run_parameter_grid()`'s own try/except caught
and recorded:

```
35 0.25 0.4  failed  68714.263s  BrokenProcessPool
```

The sweep then auto-continued to the next combo (γ=0.30, ω=0.1) — confirmed
recovering normally in the screen session. No other combos or processes
were affected; the 41 scan CSVs already written for γ=0.25/ω=0.4 are intact
on disk.

## What's left to resume

- **`width=35, γ=0.25, ω=0.4`** is marked `failed` in `run_manifest.json` and
  was *not* retried automatically. 41/42 scan outputs already exist under
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.25_omega_0.4/Bf_DTA_anes/`.
  To complete it, only the missing scan needs to be (re)run:
  `sub-ag230922a_SHAM_bold_parcellated` (γ=0.25, ω=0.4, width=35).
- Before rerunning, consider whether γ=0.25/ω=0.4 is intrinsically
  pathological for this scan's graph (e.g. low resolution + high interslice
  coupling producing a degenerate CPM optimization landscape) — it may hang
  again with the same seed distribution. Worth either:
  - adding a per-run timeout in `_leiden_single_run` (e.g. via
    `concurrent.futures.TimeoutError` on the future) so one bad seed can't
    block an entire combo, or
  - testing that specific scan/γ/ω combination standalone first.
- The rest of the sweep (γ=0.30–0.40 × all ω, and widths 50/70) is
  unaffected and proceeding normally.

## Second occurrence — 2026-06-21, width=35, γ=0.30, ω=0.4

Same failure mode recurred on the very next γ at ω=0.4: combo
**width=35, γ=0.30, ω=0.4** (started `2026-06-20 22:37:47`) hung for
~14h36m on a single scan instead of the usual ~22 min for the whole combo.

- **Scan:** `sub-ag230912a_SHAM_bold_parcellated` — a *different* scan than
  the first incident (`sub-ag230922a`), confirming this isn't one cursed
  scan but rather width=35 + ω=0.4 (high interslice coupling at this window
  length) being generally prone to non-converging seeds.
- 41/42 scans for the combo completed normally; only this one seed/scan
  inside the inner `run_workers` pool never returned.
- Verified before touching anything: the hung worker (PID 3867807) was
  owned by UID 260858 (`luca.galli-1@unitn.it`, my own user), parented
  under my own `parameters_inspection.py` / `SCREEN -S parameter_inspection`
  session — confirmed via `ps -o pid,user,uid,ppid` immediately before
  killing, since this is a shared cluster and no other user's process was
  touched.
- Sent `SIGTERM` to PID 3867807 only. Confirmed terminated within 2s.
  `ProcessPoolExecutor` in the parent raised `BrokenProcessPool`, caught by
  `run_parameter_grid()`'s try/except, recorded as:
  ```
  35 0.30 0.4  failed  BrokenProcessPool
  ```
  The sweep auto-continued to the next combo (γ=0.35, ω=0.1), confirmed
  running normally afterward. No other processes were affected.

### Next actions to take

- **`width=35, γ=0.30, ω=0.4`** is marked `failed` in `run_manifest.json`,
  not retried automatically. Only the missing scan needs to be (re)run:
  `sub-ag230912a_SHAM_bold_parcellated` → output path
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912a/sub-ag230912a_SHAM_bold_parcellated.csv`
- Do **not** re-run `run_all()` for this combo — it has no skip-existing
  logic (`_run_scan_group` unconditionally recomputes and overwrites every
  scan), so it would needlessly redo all 42 scans (~22 min) instead of just
  the missing one.
- Instead, call `run_community_detection()` directly on that scan's window
  files with `gamma=0.30, omega=0.4, n_runs=10, run_workers=10` (the
  sweep's defaults) and write the result to the path above. Expected cost:
  ~30-60s if it converges normally.
- Risk: it may hit the same pathological CPM landscape again on a different
  seed and hang again. There is still no per-seed timeout in
  `_leiden_single_run`/`run_community_detection`. Given this has now
  happened twice at ω=0.4/width=35 with two different scans, it's worth
  prioritizing:
  - adding a per-seed timeout (`concurrent.futures` `TimeoutError` on the
    future) so one bad seed can't block an entire combo or require manual
    intervention, and/or
  - investigating whether ω=0.4 at width=35 is intrinsically harder for the
    CPM optimization (e.g. profile a few of these scans standalone to see
    how often a seed fails to converge) before continuing to spend manual
    kill/resume cycles on it.
- The rest of the grid (γ=0.35-0.40 × all ω, widths 50/70) is unaffected
  and proceeding normally as of this update.

## Third occurrence — 2026-06-21, width=35, γ=0.35, ω=0.4 — TWO simultaneous stalls, not killed

An automated watchdog (cron job, every 20 min, checking `run_manifest.json`
for any combo running past the healthy 22.0-23.5 min band) flagged combo
**width=35, γ=0.35, ω=0.4** (started `2026-06-21T14:30:04+02:00`) at 37.2
min elapsed.

Unlike the first two incidents, the process tree this time showed **two**
separate scans stuck at once, each with the same single-pegged-worker
signature:

| PID | Parent (outer scan worker) | Elapsed | CPU time | State |
|---|---|---|---|---|
| 1888039 | 1286169 | 26.3 min | 26:11 | R+, 99.4% CPU |
| 4073614 | 1286171 | 31.3 min | 31:09 | R+, 99.4% CPU |

Both confirmed owned by UID 260858 (my own user), both structurally under
the known `parameter_inspection` tree (`pstree -p` from the `SCREEN -S
parameter_inspection` root), both showing CPU time ≈ elapsed time (i.e.
genuinely computing, not deadlocked) — the same signature as the two prior
single-worker hangs. All other inner-pool siblings under each are idle
(S+, low %CPU), having already finished their seeds.

**No kill was performed.** The watchdog's own safety rule says: if more
than one candidate looks stuck, treat it as ambiguous and stop rather than
guess. Two simultaneous hangs breaks the "exactly one bad seed" assumption
the rule was built around, so this was surfaced for manual review instead.

### Resolution — killed both, 2026-06-21T17:23

Authorized by user. Re-verified ownership of each PID immediately before
each `SIGTERM` (not as a batch):

- PID 1888039: `/proc/1888039/status` `Uid: 260858 260858 260858 260858`,
  matched `id -u` exactly → `kill -TERM 1888039` → confirmed gone within 5s.
- PID 4073614: re-checked alive + `Uid: 260858 ...` matched again
  immediately before signaling → `kill -TERM 4073614` → confirmed gone
  within 5s.

Total stall duration before kill: ~2h53m (combo started 14:30:04, killed
17:23, vs. the usual ~22 min). Manifest confirms:

```
35 0.35 0.4  failed  BrokenProcessPool   (started 14:30:04, finished 17:23:27)
35 0.40 0.1  running                      (started 17:23:27)
```

The sweep auto-continued to the next combo (γ=0.40, ω=0.1) immediately
after the second `BrokenProcessPool`. No other processes were touched.

40/42 scans for γ=0.35/ω=0.4 are intact on disk. The two missing scans
(confirmed via diff against a completed reference combo) are:
- `sub-ag230918b_SHAM_bold_parcellated`
- `sub-ag230919a_EXP__bold_parcellated`

### Next actions to take

- **`width=35, γ=0.35, ω=0.4`** is marked `failed`, not retried
  automatically. To complete it, run just the two missing scans above via
  `run_community_detection()` directly (`gamma=0.35, omega=0.4, n_runs=10,
  run_workers=10`), writing to:
  - `outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230918/sub-ag230918b/sub-ag230918b_SHAM_bold_parcellated.csv`
  - `outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230919/sub-ag230919a/sub-ag230919a_EXP__bold_parcellated.csv`
  Do not re-run `run_all()` for this combo (no skip-existing logic, would
  redo all 42 scans).
- This is now the **fourth** non-converging-seed incident at width=35,
  ω=0.4 (γ=0.25, 0.30, and twice within 0.35), and it's getting worse, not
  better — both occurrence rate and simultaneity are increasing. Strongly
  recommend pausing further width=35/ω=0.4 combos (γ=0.40, ω=0.4 is next
  in that row) to add a per-seed timeout in `_leiden_single_run` before
  continuing, rather than relying on the watchdog to catch and kill manually
  each time — each incident has now cost 1-3 hours of wall-clock blocking
  even with monitoring in place.
- The watchdog (cron job, 20 min interval, checking elapsed time + process
  CPU/state signature) correctly detected the stall at 37 min and correctly
  refused to auto-kill when it saw two simultaneous candidates, surfacing
  it for manual decision instead of guessing — working as designed.

## Fourth occurrence — 2026-06-21, width=35, γ=0.40, ω=0.4 — FOUR simultaneous stalls, auto-killed

User granted standing authorization for the watchdog to terminate stuck
workers autonomously (no longer needs to ask each cycle), with handling
extended to kill multiple simultaneous candidates independently rather
than aborting on ambiguity.

Combo **width=35, γ=0.40, ω=0.4** (started `2026-06-21T18:37:12+02:00`)
crossed the 35 min stall threshold at the 18:57 check (still under
threshold) and was confirmed stalled at the 19:17 check, 50.6 min elapsed.
This time **four** scans were stuck simultaneously — one per inner pool,
each under a different outer scan-worker:

| PID | Parent (outer scan worker) | Elapsed | CPU time | State |
|---|---|---|---|---|
| 1909397 | 1230135 | 34.6 min | 34:23 | R+, 99.4% CPU |
| 1267396 | 1230263 | 50.9 min | 50:35 | R+, 99.4% CPU |
| 581718 | 1230284 | 44.3 min | 44:06 | R+, 99.5% CPU |
| 1267411 | 1230289 | 50.9 min | 50:35 | R+, 99.4% CPU |

For each candidate: confirmed `/proc/<pid>/cmdline` literally contains
`parameters_inspection.py`, confirmed `/proc/<pid>/status` `Uid:
260858 ...` matches `id -u` exactly, then re-confirmed both immediately
before each individual `kill -TERM` (not batched — one verified PID per
kill call, looped). All four confirmed gone within 5s of their respective
signal.

`BrokenProcessPool` raised once all four pool members were gone; the
combo was marked `failed`; the sweep auto-continued to the next combo —
which, since this was the last γ/ω cell for width=35, was
**`width=50, γ=0.25, ω=0.1`** (started `2026-06-21T19:29:00+02:00`),
confirming the entire width=35 block of the grid is now done. No other
process, combo, or the screen session itself was touched.

38/42 scans for γ=0.40/ω=0.4 are intact on disk. The four missing scans
(confirmed via diff against the γ=0.40/ω=0.3 reference combo) are:
- `sub-ag230911b_EXP__bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230911/sub-ag230911b/sub-ag230911b_EXP__bold_parcellated.csv`
- `sub-ag230913a_EXP_bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230913/sub-ag230913a/sub-ag230913a_EXP_bold_parcellated.csv`
- `sub-ag230913d_SHAM_bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230913/sub-ag230913d/sub-ag230913d_SHAM_bold_parcellated.csv`
- `sub-ag230921a_EXP__bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230921/sub-ag230921a/sub-ag230921a_EXP__bold_parcellated.csv`

### Updated pattern summary (width=35 complete)

Every ω=0.4 combo at width=35 has now failed (4 for 4: γ=0.25, 0.30, 0.35,
0.40), and every ω=0.1/0.2/0.3 combo has completed normally (12 for 12).
Stuck-worker count per incident has trended up: 1 → 1 → 2 → 4. This is
strong, consistent evidence that ω=0.4 produces a genuinely degenerate CPM
optimization landscape at width=35, independent of γ — not a fluke, not a
specific bad scan/mouse. Width=35 is now fully swept (with 4 combos
needing the missing-scan backfill above); the grid has moved on to
width=50, which will show whether this is width=35-specific or a more
general ω=0.4 issue.

## Fifth occurrence — 2026-06-21, width=50, γ=0.25, ω=0.3 — breaks the ω=0.4-only pattern

Combo **width=50, γ=0.25, ω=0.3** (started `2026-06-21T20:13:33+02:00`)
stalled at 54.2 min elapsed (crossed the 35 min threshold sometime between
the 20:47 check at 34.2 min and the 21:08 check at 54.2 min). This is
notable: **ω=0.3**, not ω=0.4 — the first stall outside the previously
all-ω=0.4 pattern, and the first one at width=50.

Only one stuck candidate this time:

| PID | Parent (outer scan worker) | Elapsed | CPU time | State |
|---|---|---|---|---|
| 3398601 | 1503076 | 48.5 min | 48:12 | R+, 99.4% CPU |

Confirmed `/proc/3398601/cmdline` = `python3 parameters_inspection.py`,
confirmed `Uid: 260858 ...` matched `id -u` exactly, re-confirmed both
immediately before signaling. `kill -TERM 3398601` sent; confirmed gone
within 5s. `BrokenProcessPool` raised, combo marked `failed`, sweep
auto-continued to **`width=50, γ=0.25, ω=0.4`** (started
`2026-06-21T21:08:15+02:00`) — now running, and the one to watch closely
given the width=35 history.

41/42 scans for γ=0.25/ω=0.3 (width=50) are intact. The one missing scan:
- `sub-ag230918a_SHAM__bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.25_omega_0.3/Bf_DTA_anes/sub-ag230918/sub-ag230918a/sub-ag230918a_SHAM__bold_parcellated.csv`

### Revised read on the pattern

This stall at ω=0.3/width=50 means the failure mode is **not** strictly
"ω=0.4 only" — high interslice coupling relative to the per-slice graph's
signal-to-noise ratio is the more likely general driver, and width=50
(longer windows, presumably less noisy per-slice graphs than width=35)
still hit it at a lower ω than width=35 ever needed to. Worth holding off
on the "width=35-specific" conclusion until more width=50/70 combos are
observed. The per-seed-timeout fix recommended earlier remains the right
mitigation regardless of which axis turns out to matter most.

## Sixth occurrence — 2026-06-21, width=50, γ=0.25, ω=0.4 — 3 candidates, 1 self-resolved

Combo **width=50, γ=0.25, ω=0.4** (started `2026-06-21T21:08:15+02:00`)
stalled at 39.5 min elapsed. Three candidates found across two inner
pools:

| PID | Parent (outer scan worker) | Elapsed | CPU time | State | Outcome |
|---|---|---|---|---|---|
| 2514999 | 583298 | 24.3 min | 24:10 | R+, 99.4% CPU | killed |
| 2515002 | 583298 | 24.3 min | 24:11 | R+, 99.4% CPU | **self-resolved** |
| 638872 | 583304 | 39.7 min | 39:29 | R+, 99.4% CPU | killed |

For PID 2515002: passed the cmdline + UID checks at detection time, but
on the re-verify-immediately-before-signal step (safety layer e), the
process no longer existed — `/proc/2515002/cmdline` and `/proc/.../status`
both returned "No such file or directory" and `kill` itself errored "No
such process." It had converged and exited naturally between detection
and action. **No signal was sent to it** — this is the re-verify step
working exactly as designed, avoiding a kill on a worker that was no
longer actually stuck.

For PID 2514999 and 638872: both re-confirmed cmdline =
`python3 parameters_inspection.py` and `Uid: 260858 ...` matching `id -u`
immediately before each individual `kill -TERM`. Both confirmed gone
within 5s.

`BrokenProcessPool` raised (from the two actual kills), combo marked
`failed`, sweep auto-continued to **`width=50, γ=0.30, ω=0.1`** (started
`2026-06-21T21:48:46+02:00`) — now running.

40/42 scans for γ=0.25/ω=0.4 (width=50) are intact — consistent with
exactly 2 scans lost (the 2 actually killed; PID 2515002's scan finished
and is presumably among the 40). The two missing scans:
- `sub-ag230912c_EXP_bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.25_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912c/sub-ag230912c_EXP_bold_parcellated.csv`
- `sub-ag230921a_EXP__bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.25_omega_0.4/Bf_DTA_anes/sub-ag230921/sub-ag230921a/sub-ag230921a_EXP__bold_parcellated.csv`

Pattern note: width=50 has now failed at both ω=0.3 and ω=0.4 (2 for 2 of
the ω≥0.3 combos tried), same general shape as width=35's all-ω=0.4
failures. The interslice-coupling-vs-graph-noise hypothesis continues to
hold up.

## Seventh occurrence — 2026-06-21, width=50, γ=0.30, ω=0.3 — 1 stuck worker, auto-killed

Combo **width=50, γ=0.30, ω=0.3** (started `2026-06-21T22:34:34+02:00`)
stalled at 53.2 min elapsed (crossed the 35 min threshold between the
23:08 check at 33.2 min and the 23:28 check at 53.2 min). One stuck
candidate, single active inner pool:

| PID | Parent (outer scan worker) | Elapsed | CPU time | State |
|---|---|---|---|---|
| 1369203 | 1318414 | 47.2 min | 46:58 | R+, 99.4% CPU |

Confirmed `/proc/1369203/cmdline` = `python3 parameters_inspection.py`,
confirmed `Uid: 260858 ...` matched `id -u`, re-confirmed both immediately
before signaling. `kill -TERM 1369203` sent; confirmed gone within 5s.
`BrokenProcessPool` raised, combo marked `failed`, sweep auto-continued to
**`width=50, γ=0.30, ω=0.4`** (started `2026-06-21T23:28:14+02:00`) — now
running.

41/42 scans for γ=0.30/ω=0.3 (width=50) are intact. The one missing scan:
- `sub-ag230914c_SHAM_bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.3_omega_0.3/Bf_DTA_anes/sub-ag230914/sub-ag230914c/sub-ag230914c_SHAM_bold_parcellated.csv`

Pattern note: width=50 has now failed at ω=0.3 for both γ=0.25 and γ=0.30,
and at ω=0.4 for γ=0.25 — 3 for 3 of the ω≥0.3 combos tried at width=50 so
far. ω=0.4/γ=0.30 (now running) is the next test point.

## Eighth occurrence — 2026-06-22, width=50, γ=0.30, ω=0.4 — 4 simultaneous stalls, auto-killed

Combo **width=50, γ=0.30, ω=0.4** (started `2026-06-21T23:28:14+02:00`)
stalled at 39.5 min elapsed. Four stuck candidates across four separate
inner pools:

| PID | Parent (outer scan worker) | Elapsed | CPU time | State |
|---|---|---|---|---|
| 3167845 | 2752640 | 23.2 min | 23:04 | R+, 99.4% CPU |
| 2789730 | 2752641 | 39.8 min | 39:32 | R+, 99.4% CPU |
| 2789696 | 2752644 | 39.8 min | 39:32 | R+, 99.4% CPU |
| 3983736 | 2752648 | 29.2 min | 29:05 | R+, 99.5% CPU |

Each confirmed via `/proc/<pid>/cmdline` = `python3 parameters_inspection.py`
and `/proc/<pid>/status` `Uid: 260858 ...` matching `id -u`, re-confirmed
immediately before each individual `kill -TERM` (sequential, not
batched). All four confirmed gone within 5s of their respective signal.

`BrokenProcessPool` raised, combo marked `failed`, sweep auto-continued to
**`width=50, γ=0.35, ω=0.1`** (started `2026-06-22T00:08:51+02:00`) — now
running, confirming width=50/γ=0.30 row is done.

38/42 scans for γ=0.30/ω=0.4 (width=50) are intact. The four missing
scans:
- `sub-ag230911b_EXP__bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230911/sub-ag230911b/sub-ag230911b_EXP__bold_parcellated.csv`
- `sub-ag230911d_SHAM_bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230911/sub-ag230911d/sub-ag230911d_SHAM_bold_parcellated.csv`
- `sub-ag230918a_SHAM__bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230918/sub-ag230918a/sub-ag230918a_SHAM__bold_parcellated.csv`
- `sub-ag230921a_EXP__bold_parcellated` →
  `outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230921/sub-ag230921a/sub-ag230921a_EXP__bold_parcellated.csv`

Pattern note: width=50 has now failed at every ω≥0.3 combo tried (4 for
4: γ=0.25/ω=0.3, γ=0.25/ω=0.4, γ=0.30/ω=0.3, γ=0.30/ω=0.4), with stuck-
worker counts of 1, 3(+1 self-resolved), 1, 4 — same escalating-with-γ
shape seen in width=35. `sub-ag230921a_EXP__bold_parcellated` has now
been a missing/stuck scan twice (γ=0.25/ω=0.4 and γ=0.30/ω=0.4 at
width=50) — worth a closer look at that scan specifically once the
per-seed timeout fix is in place, though it's still consistent with
random seed-order bad luck rather than a uniquely cursed scan.

## Watchdog occurrence — 2026-06-22T02:37:44+02:00

Combo **width=50, γ=0.35, ω=0.4** (started `2026-06-22T01:21:28+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 1648557. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag230908a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230908/sub-ag230908a/sub-ag230908a_EXP_bold_parcellated.csv`
- `sub-ag230911b_EXP__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230911/sub-ag230911b/sub-ag230911b_EXP__bold_parcellated.csv`
- `sub-ag230912d_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912d/sub-ag230912d_SHAM_bold_parcellated.csv`
- `sub-ag230914a_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230914/sub-ag230914a/sub-ag230914a_SHAM_bold_parcellated.csv`
- `sub-ag230914b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230914/sub-ag230914b/sub-ag230914b_SHAM_bold_parcellated.csv`
- `sub-ag230921a_EXP__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230921/sub-ag230921a/sub-ag230921a_EXP__bold_parcellated.csv`
- `sub-ag230926a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230926/sub-ag230926a/sub-ag230926a_EXP_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-22T04:59:38+02:00

Combo **width=50, γ=0.4, ω=0.4** (started `2026-06-22T03:54:25+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 3102144, 2105144, 2820937. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag230911a_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230911/sub-ag230911a/sub-ag230911a_SHAM_bold_parcellated.csv`
- `sub-ag230912a_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912a/sub-ag230912a_SHAM_bold_parcellated.csv`
- `sub-ag230912c_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912c/sub-ag230912c_EXP_bold_parcellated.csv`
- `sub-ag230913a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230913/sub-ag230913a/sub-ag230913a_EXP_bold_parcellated.csv`
- `sub-ag230913b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230913/sub-ag230913b/sub-ag230913b_SHAM_bold_parcellated.csv`
- `sub-ag230919a_EXP__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230919/sub-ag230919a/sub-ag230919a_EXP__bold_parcellated.csv`
- `sub-ag230921d_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230921/sub-ag230921d/sub-ag230921d_EXP_bold_parcellated.csv`
- `sub-ag230926a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230926/sub-ag230926a/sub-ag230926a_EXP_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-22T07:00:06+02:00

Combo **width=70, γ=0.25, ω=0.4** (started `2026-06-22T06:07:53+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 1109382, 4039638, 2988742, 3025776. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Skipped candidates (not killed):
- PID 4040076

Missing scan(s) to rerun:
- `sub-ag230911a_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.25_omega_0.4/Bf_DTA_anes/sub-ag230911/sub-ag230911a/sub-ag230911a_SHAM_bold_parcellated.csv`
- `sub-ag230915a_EXP__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.25_omega_0.4/Bf_DTA_anes/sub-ag230915/sub-ag230915a/sub-ag230915a_EXP__bold_parcellated.csv`
- `sub-ag230918a_SHAM__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.25_omega_0.4/Bf_DTA_anes/sub-ag230918/sub-ag230918a/sub-ag230918a_SHAM__bold_parcellated.csv`
- `sub-ag230922d_EXP__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.25_omega_0.4/Bf_DTA_anes/sub-ag230922/sub-ag230922d/sub-ag230922d_EXP__bold_parcellated.csv`


## Watchdog occurrence — 2026-06-22T09:21:59+02:00

Combo **width=70, γ=0.3, ω=0.4** (started `2026-06-22T08:11:20+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 1589976. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Skipped candidates (not killed):
- PID 1589979

Missing scan(s) to rerun:
- `sub-ag230908a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230908/sub-ag230908a/sub-ag230908a_EXP_bold_parcellated.csv`
- `sub-ag230911a_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230911/sub-ag230911a/sub-ag230911a_SHAM_bold_parcellated.csv`
- `sub-ag230912a_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912a/sub-ag230912a_SHAM_bold_parcellated.csv`
- `sub-ag230912b_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912b/sub-ag230912b_EXP_bold_parcellated.csv`
- `sub-ag230912c_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912c/sub-ag230912c_EXP_bold_parcellated.csv`
- `sub-ag230913a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230913/sub-ag230913a/sub-ag230913a_EXP_bold_parcellated.csv`
- `sub-ag230914b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230914/sub-ag230914b/sub-ag230914b_SHAM_bold_parcellated.csv`
- `sub-ag230921a_EXP__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_DTA_anes/sub-ag230921/sub-ag230921a/sub-ag230921a_EXP__bold_parcellated.csv`


## Watchdog occurrence — 2026-06-22T11:02:11+02:00

Combo **width=70, γ=0.35, ω=0.3** (started `2026-06-22T10:10:50+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 3751607. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag230912c_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.3/Bf_DTA_anes/sub-ag230912/sub-ag230912c/sub-ag230912c_EXP_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-22T12:25:05+02:00

Combo **width=70, γ=0.35, ω=0.4** (started `2026-06-22T11:02:01+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 1313755. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag230908a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230908/sub-ag230908a/sub-ag230908a_EXP_bold_parcellated.csv`
- `sub-ag230911c_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230911/sub-ag230911c/sub-ag230911c_EXP_bold_parcellated.csv`
- `sub-ag230912b_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230912/sub-ag230912b/sub-ag230912b_EXP_bold_parcellated.csv`
- `sub-ag230913b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230913/sub-ag230913b/sub-ag230913b_SHAM_bold_parcellated.csv`
- `sub-ag230918a_SHAM__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230918/sub-ag230918a/sub-ag230918a_SHAM__bold_parcellated.csv`
- `sub-ag230919a_EXP__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230919/sub-ag230919a/sub-ag230919a_EXP__bold_parcellated.csv`
- `sub-ag230919b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230919/sub-ag230919b/sub-ag230919b_SHAM_bold_parcellated.csv`
- `sub-ag230926a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.4/Bf_DTA_anes/sub-ag230926/sub-ag230926a/sub-ag230926a_EXP_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-22T14:05:16+02:00

Combo **width=70, γ=0.4, ω=0.3** (started `2026-06-22T13:13:24+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 1317658. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag230908a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.3/Bf_DTA_anes/sub-ag230908/sub-ag230908a/sub-ag230908a_EXP_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-22T15:28:33+02:00

Combo **width=70, γ=0.4, ω=0.4** (started `2026-06-22T14:05:07+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 1319989, 1319822. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag230908a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230908/sub-ag230908a/sub-ag230908a_EXP_bold_parcellated.csv`
- `sub-ag230913b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230913/sub-ag230913b/sub-ag230913b_SHAM_bold_parcellated.csv`
- `sub-ag230914a_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230914/sub-ag230914a/sub-ag230914a_SHAM_bold_parcellated.csv`
- `sub-ag230914b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230914/sub-ag230914b/sub-ag230914b_SHAM_bold_parcellated.csv`
- `sub-ag230914c_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230914/sub-ag230914c/sub-ag230914c_SHAM_bold_parcellated.csv`
- `sub-ag230915a_EXP__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230915/sub-ag230915a/sub-ag230915a_EXP__bold_parcellated.csv`
- `sub-ag230918a_SHAM__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230918/sub-ag230918a/sub-ag230918a_SHAM__bold_parcellated.csv`
- `sub-ag230918b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230918/sub-ag230918b/sub-ag230918b_SHAM_bold_parcellated.csv`
- `sub-ag230919b_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230919/sub-ag230919b/sub-ag230919b_SHAM_bold_parcellated.csv`
- `sub-ag230920a_SHAM__bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230920/sub-ag230920a/sub-ag230920a_SHAM__bold_parcellated.csv`
- `sub-ag230922a_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230922/sub-ag230922a/sub-ag230922a_SHAM_bold_parcellated.csv`
- `sub-ag230926a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.4_omega_0.4/Bf_DTA_anes/sub-ag230926/sub-ag230926a/sub-ag230926a_EXP_bold_parcellated.csv`

## Backfill run — 2026-06-23, 11:44–13:16 — recovers 48/65, 17 stall a second time

After the sweep finished (`status: completed_with_errors`, 16 combos short a
total of 65 scans across all incidents above), a dedicated backfill script
(`scripts/backfill_missing_scans.py`) was written to recompute only the
missing scans via `run_community_detection()` directly — never `run_all()`,
which has no skip-existing logic and would have redone all 42 scans per
combo. The script independently re-diffed each gappy combo against a clean
same-width reference combo (not from this doc's enumeration, which could be
stale) and reproduced the same 65-scan/16-combo gap documented above exactly.

Launched with `--concurrency 10` (10 scans at once, each with the sweep's own
`run_workers=10` → 100 worker processes total, matching the original sweep's
own 10×10 sizing). Each scan ran in its own subprocess with a 30-minute
wall-clock timeout — generous headroom over the normal ~30-60s per scan,
intended to catch a non-converging seed without hanging indefinitely the way
the original incidents did.

**Result after 1h32m: 48/65 backfilled successfully, 17/65 timed out.**

Every one of the 17 timeouts was already on the missing-scan list going into
this run — meaning each had already failed to converge once during the
original sweep (that's the only reason it was missing), and then failed
again under a fresh, independently-drawn random seed during the backfill.
**This is the second independent stall for all 17**, which is a different
and stronger signal than "one unlucky seed": two separate random seed draws
both failing to converge for the same (scan, width, γ, ω) argues for a
genuinely degenerate CPM optimization landscape at that specific point in
the grid, not random bad luck. Consistent with the pre-existing pattern, all
17 are at ω≥0.3, and 14/17 are at width=70 — the hardest corner of the grid.

A sanity check on the 48 successfully recovered scans (see
`docs/SanityCheckFindings.md` for methodology) found no structural issues,
no values outside expected ranges, no within-combo statistical outliers, and
no discontinuity relative to each scan's own flexibility trend across
neighboring γ/ω cells — the backfilled data is indistinguishable in quality
from scans computed in the original sweep.

### Scans successfully recovered (48)

| Combo | Scans recovered |
|---|---|
| wl35/γ0.25/ω0.4 | 1 |
| wl35/γ0.30/ω0.4 | 1 |
| wl35/γ0.35/ω0.4 | 2 |
| wl35/γ0.40/ω0.4 | 4 |
| wl50/γ0.25/ω0.3 | 1 |
| wl50/γ0.25/ω0.4 | 2 |
| wl50/γ0.30/ω0.3 | 1 |
| wl50/γ0.30/ω0.4 | 4 |
| wl50/γ0.35/ω0.4 | 6 |
| wl50/γ0.40/ω0.4 | 6 |
| wl70/γ0.25/ω0.4 | 4 |
| wl70/γ0.30/ω0.4 | 4 |
| wl70/γ0.35/ω0.3 | 1 |
| wl70/γ0.35/ω0.4 | 4 |
| wl70/γ0.40/ω0.3 | 1 |
| wl70/γ0.40/ω0.4 | 6 |

All of wl35's and most of wl50's gap is now closed. wl35 is fully complete
(42/42 everywhere). Remaining gaps are concentrated in wl50/γ0.35-0.40/ω0.4
and wl70/γ0.30-0.40/ω0.3-0.4.

### Scans that stalled a second time (17) — still missing

| Combo | Scan | Disk count now |
|---|---|---|
| wl50/γ0.35/ω0.4 | `sub-ag230921a_EXP__bold_parcellated` | 41/42 |
| wl50/γ0.40/ω0.4 | `sub-ag230912c_EXP_bold_parcellated` | 40/42 |
| wl50/γ0.40/ω0.4 | `sub-ag230921d_EXP_bold_parcellated` | 40/42 |
| wl70/γ0.30/ω0.4 | `sub-ag230908a_EXP_bold_parcellated` | 38/42 |
| wl70/γ0.30/ω0.4 | `sub-ag230912a_SHAM_bold_parcellated` | 38/42 |
| wl70/γ0.30/ω0.4 | `sub-ag230912b_EXP_bold_parcellated` | 38/42 |
| wl70/γ0.30/ω0.4 | `sub-ag230921a_EXP__bold_parcellated` | 38/42 |
| wl70/γ0.35/ω0.4 | `sub-ag230912b_EXP_bold_parcellated` | 38/42 |
| wl70/γ0.35/ω0.4 | `sub-ag230918a_SHAM__bold_parcellated` | 38/42 |
| wl70/γ0.35/ω0.4 | `sub-ag230919a_EXP__bold_parcellated` | 38/42 |
| wl70/γ0.35/ω0.4 | `sub-ag230926a_EXP_bold_parcellated` | 38/42 |
| wl70/γ0.40/ω0.4 | `sub-ag230908a_EXP_bold_parcellated` | 36/42 |
| wl70/γ0.40/ω0.4 | `sub-ag230914b_SHAM_bold_parcellated` | 36/42 |
| wl70/γ0.40/ω0.4 | `sub-ag230915a_EXP__bold_parcellated` | 36/42 |
| wl70/γ0.40/ω0.4 | `sub-ag230918a_SHAM__bold_parcellated` | 36/42 |
| wl70/γ0.40/ω0.4 | `sub-ag230918b_SHAM_bold_parcellated` | 36/42 |
| wl70/γ0.40/ω0.4 | `sub-ag230926a_EXP_bold_parcellated` | 36/42 |

`sub-ag230908a_EXP_bold_parcellated` and `sub-ag230918a_SHAM__bold_parcellated`
each stalled twice independently across *different* (γ,ω) cells at width=70
(γ0.30/ω0.4 and γ0.40/ω0.4 for the former; γ0.35/ω0.4 and γ0.40/ω0.4 for the
latter) — worth flagging as scans whose graph structure may be intrinsically
harder for the CPM optimization at width=70/high-ω, independent of the exact
γ used.

### Bug found and fixed during cleanup: orphaned inner-pool workers on timeout

The backfill script's timeout handling had a real bug: each missing scan ran
inside an outer `multiprocessing.Process` wrapper, but that wrapper's own
call to `run_community_detection()` spawns a *second*, inner
`ProcessPoolExecutor` of `run_workers=10` Leiden workers. On timeout, the
script called `proc.terminate()` on the outer wrapper only — which does not
cascade to the inner pool's children. Those children get reparented to PID 1
and keep running indefinitely, orphaned, doing nothing useful (the result
they'd eventually produce is discarded since the wrapper that would have
collected it is already dead).

This was caught ~2 hours after the backfill script itself had exited
(`finished_at: 2026-06-23T13:16:12+02:00`): **171 orphaned
`backfill_missing_scans.py` worker processes** were still running, all
descended from the 17 timed-out scans (each leaving up to 10 leftover inner
workers). Cleaned up by iterating every PID matching
`backfill_missing_scans.py`, verifying `/proc/<pid>/status` `Uid:` matched
`id -u` (260858) and `/proc/<pid>/cmdline` literally contained
`backfill_missing_scans.py` immediately before each individual `kill -TERM`,
then re-confirming via `ps aux` that zero matching processes remained. No
other user's process was touched.

**Fix still needed** before retrying the 17: the script must kill the inner
pool too on timeout (e.g. track and signal the whole process group, not just
the top-level wrapper PID), or the next retry will leak processes again.

### Next actions to take

- Fix the orphan-on-timeout bug in `scripts/backfill_missing_scans.py`
  before any further retry.
- Decide on a longer per-scan timeout for a retry of the 17 (30 min wasn't
  enough; these are now confirmed-twice non-convergent, so a longer timeout
  may just delay the same outcome — worth considering whether to accept the
  gap, try a different seed count, or test these specific (scan, γ, ω, width)
  combinations standalone with verbose Leiden diagnostics instead of blindly
  retrying).
- 17 of 2016 total scans across the full sweep (48 width×γ×ω combos × 42
  scans, ≈0.8%) remain missing — small enough that the user may choose to
  exclude these specific (scan, combo) pairs from the FDR t-test stage
  rather than keep retrying.

## Watchdog occurrence — 2026-06-26T13:05:07+02:00

Combo **width=35, γ=0.35, ω=0.4** (started `2026-06-26T12:24:15+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 2270711. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag231113c_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.35_omega_0.4/Bf_DTA_awk/sub-ag231113/sub-ag231113c/sub-ag231113c_SHAM_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-26T15:45:19+02:00

Combo **width=50, γ=0.25, ω=0.4** (started `2026-06-26T14:52:47+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 2303700. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag231114d_SHAM_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.25_omega_0.4/Bf_DTA_awk/sub-ag231114/sub-ag231114d/sub-ag231114d_SHAM_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-26T19:46:42+02:00

Combo **width=50, γ=0.4, ω=0.4** (started `2026-06-26T18:42:26+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 2374505. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag231110a_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_awk/sub-ag231110/sub-ag231110a/sub-ag231110a_EXP_bold_parcellated.csv`
- `sub-ag231113f_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_awk/sub-ag231113/sub-ag231113f/sub-ag231113f_EXP_bold_parcellated.csv`
- `sub-ag231130c_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.4_omega_0.4/Bf_DTA_awk/sub-ag231130/sub-ag231130c/sub-ag231130c_EXP_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-26T23:06:53+02:00

Combo **width=70, γ=0.35, ω=0.3** (started `2026-06-26T22:30:39+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 2420576. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag231031c_EXP_bold_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.35_omega_0.3/Bf_DTA_awk/sub-ag231031/sub-ag231031c/sub-ag231031c_EXP_bold_parcellated.csv`


## Watchdog occurrence — 2026-06-27T23:05:26+02:00

Combo **width=50, γ=0.35, ω=0.4** (started `2026-06-27T22:13:00+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 2457708. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag240926a_EXP_bold_CNO_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl50/gamma_0.35_omega_0.4/Bf_PV_awk/sub-ag240926/sub-ag240926a/sub-ag240926a_EXP_bold_CNO_parcellated.csv`


## Watchdog occurrence — 2026-06-28T05:05:37+02:00

Combo **width=70, γ=0.3, ω=0.4** (started `2026-06-28T04:22:56+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 2467408. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag240926c_SHAM_bold_baseline_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl70/gamma_0.3_omega_0.4/Bf_PV_awk/sub-ag240926/sub-ag240926c/sub-ag240926c_SHAM_bold_baseline_parcellated.csv`


## Watchdog occurrence — 2026-06-29T10:41:34+02:00

Combo **width=35, γ=0.3, ω=0.4** (started `2026-06-29T09:08:27+02:00`) flagged as stalled by the standalone watchdog (`scripts/parameter_inspection_watchdog.py`), running independently in its own `screen` session.

Killed PID(s): 2505903. Each was verified via `/proc/<pid>/cmdline` (must contain `parameters_inspection.py`) and `/proc/<pid>/status` `Uid:` (must equal the script's own `os.getuid()`), re-checked again immediately before each individual `SIGTERM`. All confirmed gone within 5s.

Missing scan(s) to rerun:
- `sub-ag240722a_EXP_bold_CNO_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.3_omega_0.4/Bf_PV_anes/sub-ag240722/sub-ag240722a/sub-ag240722a_EXP_bold_CNO_parcellated.csv`
- `sub-ag240806c_EXP_bold_CNO_parcellated` → `/home/luca.galli-1/neuro3ducate/mouse-fmri-dyncomm/outputs/parameter_inspection/2026_06_20__01-16-56/wl35/gamma_0.3_omega_0.4/Bf_PV_anes/sub-ag240806/sub-ag240806c/sub-ag240806c_EXP_bold_CNO_parcellated.csv`

