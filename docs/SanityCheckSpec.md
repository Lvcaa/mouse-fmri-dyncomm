# Sanity Check Spec — `outputs/parameter_inspection/` parameter sweep

Purpose: before trusting the parameter sweep enough to pick a (width, γ, ω)
combo and commit to FDR-corrected t-tests on the full analysis, verify (1)
we ran the right code, on the right inputs, completely, (2) the upstream
windowing/connectivity/censoring stages that feed the sweep are correct,
and (3) the resulting flexibility values are statistically reasonable, not
artifacts of a bug, a stuck-run backfill gap, or a degenerate parameter
region (see `docs/ParameterInspectionStuckRun.md` for the latter).

This is a spec only — no code should be run yet. It's written so a future
session ("run the sanity check") can implement it directly without
re-deriving context.

Target run: `outputs/parameter_inspection/2026_06_20__01-16-56/`
(the current/latest sweep; ignore `2026_06_18__15-27-32` and
`2026_06_18__16-26-18` — those are earlier pilot runs with a different,
now-superseded parameter grid and folder layout, kept only for reference).

---

## 0. Inputs to read first (context, not checks)

- `scripts/parameters_inspection.py` — the sweep driver. Grid is
  `WIDTHS=[35,50,70]` × `GAMMAS=[0.25,0.30,0.35,0.40]` × `OMEGAS=[0.10,0.20,0.30,0.40]`
  × `DATASETS=["Bf_DTA_anes"]` = 48 combos, `N_RUNS=10` Leiden runs/scan.
- `scripts/02_make_windows.py` — defines sliding windows + per-window and
  per-scan censoring (`MAX_CENSORED_TRS = round(0.25*WINDOW_LENGTH)` per
  window, `MAX_SCAN_CENSORED_FRAC = 0.25` per scan). Output:
  `outputs/window_summary_wl{N}.csv`, one row per candidate window.
- `scripts/03_compute_window_connectivity.py` — consumes
  `window_summary_wl{N}.csv`, keeps only `keep_window == True` rows, computes
  Pearson connectivity per window (after dropping censored rows *within* the
  window), zeroes the diagonal. Output: `outputs/window_connectivity_wl{N}/`
  + `connectivity_summary.csv` (one row per scan with
  `valid_windows_count`/`total_windows`/`valid_window_ratio`).
- `scripts/parameters_inspection.py` builds the igraph per window
  (`build_igraph`): **keeps both positive and negative correlations** as
  signed edge weights, drops only exact zeros.
- `outputs/parameter_inspection/<run>/run_manifest.json` — live manifest
  written by `run_parameter_grid()`/`_build_manifest()`: one entry per combo
  in `manifest["runs"]` with `status` (`completed`/`failed`/`running`),
  timing, and `manifest["errors"]`.
- `docs/ParameterInspectionStuckRun.md` — incident log. As of this writing,
  every combo with **ω=0.3 or ω=0.4** has hit at least one non-converging
  Leiden seed and was `SIGTERM`-killed mid-combo, leaving that combo's
  scan-CSV count short of 42 (`Bf_DTA_anes` has 42 scans) until the missing
  scans are backfilled. **Confirmed still unbacked-filled** at the time this
  spec was written — wl35: gamma_0.25/0.3/0.4 omega_0.4 short by 1/1/4 scans,
  gamma_0.35_omega_0.4 short by 2; wl50: short across most ω≥0.3 combos by
  1–8 scans; wl70 likely similar (not fully enumerated here — check 1 must
  re-derive this from disk, not from this paragraph, since backfills may
  have happened since).

## 1. Known, confirmed-intentional discrepancy — do not re-flag

`scripts/04_run_community_detection.py::build_igraph` (the original
production script that `parameters_inspection.py` was forked from) **drops
negative correlations** (`positive_mask = edge_weights > 0`) before building
the graph, while `scripts/parameters_inspection.py::build_igraph` **keeps
signed weights** (`nonzero_mask = edge_weights != 0`). **Confirmed by the
user (2026-06-22) to be an intentional change**, not drift — the sweep is
meant to use signed (full) correlation, not positive-only. Check 7 below is
reduced to a provenance confirmation (verify every sweep output actually
used the signed-weight code path, since that's now the *expected* behavior)
rather than an open question about which behavior is correct.

---

## 2. Checks

### Check 1 — Run completeness vs. the manifest and the grid

- Parse `run_manifest.json`. Assert `len(manifest["parameter_grid"]) == 48`
  (3 widths × 4 γ × 4 ω × 1 dataset) and that every grid cell has a
  corresponding entry in `manifest["runs"]`.
- For every run entry, recompute actual scan-CSV count on disk
  (`wl{width}/gamma_{γ}_omega_{ω}/Bf_DTA_anes/**/*.csv`, recursive, 3 levels
  under the dataset dir per `_run_scan_group`'s `dataset/subject_date/mouse_id/scan.csv`
  layout) and compare against `run_entry["n_scans"]` (expect 42 for every
  combo — confirm 42 is still the right denominator by counting scans in a
  combo recorded as fully `completed` with no incident logged against it).
- Flag any combo where status is `completed` but disk count < recorded
  `n_scans` (would indicate silent data loss, not just a known stuck-run
  gap) — this should not happen if `status=="completed"`, so treat it as a
  bug if found.
- Flag any combo `status == "failed"` and report disk-count vs. expected
  per the incident log in `ParameterInspectionStuckRun.md`, but **independently
  recompute** missing scans by diffing the scan-ID set against a same-width
  combo that completed cleanly (don't trust the doc's enumeration as
  current — it predates possible backfills).
- Cross-check `manifest["errors"]` entries all have `error_type ==
  "BrokenProcessPool"` (expected cause given the stuck-run history) — any
  other error type is a genuine new failure mode worth separate
  investigation.
- Report final tally: combos fully complete (42/42) vs. combos with N
  missing scans, per width.

### Check 2 — Correct code path / provenance

- Confirm `manifest["script"]` == `scripts/parameters_inspection.py` and
  `manifest["git_commit"]` matches a real commit (`git show <hash>
  --stat`); if commit differs from current HEAD, diff
  `scripts/parameters_inspection.py` between that commit and HEAD to see if
  semantics changed since the run (e.g. the signed-vs-positive edge weight
  question in §1, or any change to `GAMMAS`/`OMEGAS`/`WIDTHS`/`N_RUNS`).
- Confirm `manifest["command"]` shows no unexpected CLI args (script takes
  none currently, so this should just be `python3 parameters_inspection.py`
  or similar).
- Spot-check 2–3 output CSVs' `gamma`/`interslice_weight`/`n_runs`/`n_windows`
  columns against the folder name they live in (e.g. a file under
  `gamma_0.35_omega_0.2/...` should have `gamma==0.35`,
  `interslice_weight==0.2` in every row) — catches any folder/parameter
  mismatch bug.
- Confirm every output CSV's `n_runs == 10` (the sweep's `N_RUNS`) — a
  lower value would indicate a partial/interrupted scan run that wasn't
  caught by the manifest as `failed` (since the manifest only tracks
  combo-level status, not per-scan completeness within a combo).

### Check 3 — Window length sweep (`window_summary_wl{35,50,70}.csv`) sanity

- For each width, confirm window count consistency:
  `n_windows_per_scan ≈ floor((scan_length - width) / STEP_SIZE) + 1`
  using `STEP_SIZE=3` (from `02_make_windows.py` defaults) and each scan's
  actual TR count (`for_ludo/<dataset>/<preproc>/<scan>.csv` row count).
- Confirm `MAX_CENSORED_TRS == round(0.25*width)` per width (5 for 35, 13
  for 50 [round(12.5)], 18 for 70 [round(17.5)] — verify Python's
  round-half-to-even doesn't surprise here, e.g. `round(12.5)==12` not 13 in
  Python 3 banker's rounding — recompute exactly, don't trust hand
  arithmetic) and that no `keep_window==True` row has `n_censored_trs` above
  that threshold for its width (this would mean the threshold logic broke).
- Confirm `n_total_trs == width` for every row of `window_summary_wl{width}.csv`
  and `end_tr - start_tr + 1 == width`.
- Sanity-check the monotonic relationship across widths: larger windows
  should retain a *higher or equal* fraction of TRs as censored-frame noise
  gets averaged over more frames relative to the censoring threshold —
  current snapshot shows wl35 retains 92.9%, wl50 94.2%, wl70 95.9% of
  windows (`keep_window` mean) — confirm this monotonic trend still holds
  and flag if it doesn't (would suggest a width-dependent bug, not just
  noise).
- Confirm scan-level skip logic: cross-check
  `outputs/report_mouse_censoring/wl{50,70}/skipped_scans.csv` (note: no
  `wl35` subfolder currently exists — only a root-level
  `outputs/report_mouse_censoring/skipped_scans.csv`; confirm whether that
  root file is wl35's skip log under an older path convention or a stale
  leftover, since `02_make_windows.py`'s `report_mouse_dir` is
  width-namespaced) against `window_summary_wl{N}.csv`: every scan in a
  skip log should have **zero** rows in the corresponding
  `window_summary_wl{N}.csv` (skipped before window generation), and every
  scan_id in skip logs should genuinely exceed `MAX_SCAN_CENSORED_FRAC=0.25`
  censored-TR fraction at full scan length.
- Confirm total unique `scan_id` count is identical across all three
  `window_summary_wl{N}.csv` (should be, since scan-level skip is
  width-independent — censored-row detection doesn't depend on window
  width) — current snapshot shows 193 for all three widths, which is
  consistent; re-verify this still holds.

### Check 4 — Window connectivity computation correctness

- For a handful of scans (e.g. 3 random scans × all 3 widths), recompute one
  connectivity window from scratch from the raw `for_ludo` CSV
  (`pd.read_csv(...).iloc[start_tr:end_tr+1]`, drop fully-censored rows, drop
  `Time (sec)`, `.corr()`, zero diagonal) and diff numerically
  (`np.allclose`) against the corresponding file in
  `outputs/window_connectivity_wl{N}/...window_NNNN.csv` — confirms script 03
  hasn't drifted from its current source or been run with stale code.
- Confirm every connectivity matrix CSV is 16×16 (the N16 atlas, per
  `docs/CSV_FORMAT.md` column list), symmetric (`np.allclose(M, M.T)`), has
  zero diagonal, and all off-diagonal values in `[-1, 1]` (Pearson bounds) —
  flag any matrix with NaN/Inf (would mean a window had <2 non-censored
  rows or zero-variance ROI, both should be impossible given the windowing
  thresholds but worth confirming directly rather than assuming).
- Cross-check `connectivity_summary.csv` (per width) against
  `window_summary_wl{N}.csv`: `valid_windows_count` should equal the count
  of `keep_window==True` rows for that scan, and `total_windows` should
  equal the total row count for that scan in the summary. Confirm
  `valid_windows_count` files actually exist on disk for every scan
  (`os.path.exists` for each expected output path) — script 03 has
  skip-if-exists logic keyed on *all* expected files existing, so a partial
  write from an interrupted run could silently look "skipped" on a rerun
  without ever being completed; check for scans where disk file count <
  `valid_windows_count`.
- Flag any scan with `valid_window_ratio` below ~0.6 as a low-data outlier
  worth separate scrutiny even if it passed the 0.25 scan-level censoring
  gate (current wl35 snapshot min is 0.554 — identify which scan that is
  and whether it's a borderline case worth excluding from the parameter
  sweep's interpretation, not just from the strict per-window threshold).

### Check 5 — Community detection / flexibility value sanity

For every **completed** scan CSV under
`outputs/parameter_inspection/<run>/wl{N}/gamma_{γ}_omega_{ω}/Bf_DTA_anes/`:

- Confirm exactly 16 rows (one per ROI), columns
  `Node,flexibility,flexibility_std,gamma,interslice_weight,n_runs,n_windows,last_run`
  present, and `gamma`/`interslice_weight`/`n_runs` constant within file and
  matching the folder name (see Check 2).
- Confirm `flexibility` is in `[0, 1]` for every row (it's a switch-fraction
  by construction in `_leiden_single_run` — `switches / n_transitions` —
  values outside `[0,1]` would indicate a bug in the transition-counting
  logic).
- Confirm `flexibility_std` is non-negative and, given `n_runs=10`,
  not absurdly large relative to `flexibility` itself (e.g. flag
  `flexibility_std > flexibility` when `flexibility` is well above 0, since
  std should be of order ≤ flexibility for a fraction bounded in [0,1] with
  realistic seed-to-seed variability — use this as a soft outlier flag, not
  a hard fail).
- Confirm `n_windows` matches the scan's `valid_windows_count` from
  `connectivity_summary.csv` for the matching width (catches any
  width/scan mismatch in how the sweep grouped window files).
- **Parameter monotonicity sanity** (the calibration goal stated in
  `parameters_inspection.py`'s own comments): aggregate mean flexibility
  across all ROIs/scans per (width, γ, ω) cell and confirm:
  - Higher ω (interslice coupling) → lower mean flexibility, for fixed
    (width, γ) — coupling penalizes switching by construction.
  - The γ calibration note in the script claims γ∈[0.20,0.45] should yield
    5–7 communities at γ=1 reference; confirm γ=0.25 vs γ=0.40 cells show
    the expected direction (higher γ → typically more, smaller communities
    → not a strict flexibility prediction, but should show *some* monotonic
    or at least non-erratic trend across the 4 γ values; flag any γ/ω cell
    that's a wild outlier relative to its immediate neighbors in the grid,
    e.g. mean flexibility jumping >3 standard deviations from the
    neighboring cells' distribution — this is exactly the kind of artifact
    a non-converged/aborted-then-backfilled combo could produce if
    backfilled scans used a different code path or seed distribution than
    the original 40 in the same combo).
- Compare across widths (35 vs 50 vs 70) at matched (γ, ω): expect mean
  flexibility to decrease as width increases (longer windows → smoother,
  less noise-driven label switching) — flag if this doesn't hold at all
  three γ/ω corners of the grid (low/low, high/high, mid/mid).
- Per-ROI outlier scan check: within each (width, γ, ω) cell, z-score each
  scan's per-ROI flexibility across the ~42 scans and flag any
  scan/ROI/cell combination beyond |z|>3 — distinguish "one mouse is
  globally extreme" (likely real biological/QC signal, cross-check against
  `valid_window_ratio` for that scan from Check 4) from "one mouse is
  extreme only in specific cells" (more likely a computational artifact,
  e.g. the backfilled-scan seed-distribution concern above).

### Check 6 — Cross-combo consistency for backfilled scans

For every combo flagged in Check 1 as having had a stuck-run incident
(history in `ParameterInspectionStuckRun.md`), once/if missing scans are
backfilled:

- Confirm the backfilled scan's `n_runs`, `gamma`, `interslice_weight` match
  the rest of the combo exactly.
- Compare the backfilled scan's flexibility distribution against the same
  scan's values in *adjacent* γ/ω cells (where it wasn't stuck) for
  plausibility — large unexplained jumps relative to its own neighboring-
  parameter trend (vs. other scans' trends across the same cells) would
  suggest the backfill used different conditions (different seed count,
  different code revision) than the bulk of the combo.

### Check 7 — Confirm signed-edge code path was actually used everywhere (§1)

The signed-vs-positive question itself is resolved (§1: intentional). This
check only confirms execution matched intent, since a stale `.pyc`, a wrong
script invocation, or a partially-edited file at sweep launch time could
still cause a silent mismatch:

- Spot-check `manifest["git_commit"]` (Check 2) actually points to a commit
  where `parameters_inspection.py::build_igraph` uses
  `nonzero_mask = edge_weights != 0` (signed), not
  `positive_mask = edge_weights > 0`.
- For 2–3 sample windows, manually verify at least one negative-weight edge
  survived into the graph construction used for the sweep (e.g. confirm a
  window's connectivity matrix has off-diagonal values < 0, and that the
  edge count used by `build_igraph` for that window equals the count of
  nonzero off-diagonal entries, not just positive ones) — if every sampled
  window happens to have all-positive correlations this check is
  inconclusive and should be retried on different samples, not treated as a
  pass.
- No further action needed beyond reporting pass/fail — do not treat a
  mismatch here as "the sweep needs rerunning because the design is wrong";
  the design is confirmed correct. A mismatch here would instead point to
  an execution bug (wrong code actually ran), which is a Check 1/2-style
  provenance issue.

---

## 3. Deliverable

A findings report (new doc, e.g. `docs/SanityCheckFindings.md`) covering:

1. Completeness table: combo × (expected scans, actual scans, status,
   missing scan IDs if any).
2. Pass/fail per check above, with concrete numbers (not just "looks ok").
3. List of any outlier scans/ROIs/combos found, with enough detail
   (scan ID, width, γ, ω, metric, z-score or threshold exceeded) to decide
   whether to exclude them before the FDR t-test stage.
4. Confirmation (Check 7) that the signed-edge code path was actually used
   throughout the sweep (design intent itself is already settled — see §1).
5. A recommendation (or "insufficient evidence yet") for which
   width/γ/ω region looks most stable and biologically plausible, based on
   the monotonicity and outlier checks — but only as input to the user's
   decision, not a unilateral pick.

Do not silently "fix" any code or rerun any combos as part of this check —
surface findings only. Any fix/rerun should be a follow-up the user
explicitly approves, especially since reruns are multi-hour cluster jobs
with a known history of needing manual intervention.
