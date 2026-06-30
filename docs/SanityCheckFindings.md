# Sanity Check Findings — `outputs/parameter_inspection/2026_06_20__01-16-56/`

Executed per `docs/SanityCheckSpec.md`. Read-only audit; no code changed, no combos rerun.

## 1. Completeness table

48/48 grid combos (3 widths × 4 γ × 4 ω × `Bf_DTA_anes`) ran. 32 combos are fully
complete (42/42 scans); 16 are short a total of **65 scans**, all due to the
documented watchdog-killed non-converging Leiden seeds
(`docs/ParameterInspectionStuckRun.md`) — independently recomputed from disk,
not taken from the doc, and the totals match exactly.

| Width | Failed combos (γ,ω) | Missing scans |
|---|---|---|
| 35 | γ0.25/ω0.4(1), γ0.30/ω0.4(1), γ0.35/ω0.4(2), γ0.40/ω0.4(4) | 8 |
| 50 | γ0.25/ω0.3(1), γ0.25/ω0.4(2), γ0.30/ω0.3(1), γ0.30/ω0.4(4), γ0.35/ω0.4(7), γ0.40/ω0.4(8) | 23 |
| 70 | γ0.25/ω0.4(4), γ0.30/ω0.4(8), γ0.35/ω0.3(1), γ0.35/ω0.4(8), γ0.40/ω0.3(1), γ0.40/ω0.4(12) | 34 |

No combo marked `completed` has a disk count below its recorded `n_scans` —
no silent data loss anywhere. All 16 `manifest["errors"]` entries are
`BrokenProcessPool` — no new failure mode. As of this audit, **0 of the 65
missing scans have been backfilled** (confirmed via mtime clustering — every
existing file in every incomplete combo falls within the original sweep
run's tight time window).

## 2. Pass/fail per check

| Check | Result |
|---|---|
| 1 — Completeness vs. manifest/grid | **PASS** (gap confirmed = known issue, no new bug) |
| 2 — Code path / provenance | **PASS** — `git_commit` (`9c741e6`) == current HEAD, no drift; sampled CSVs' params match folder names; `n_runs==10` everywhere sampled |
| 3 — Window length sweep sanity | **PASS**, with one provenance note (see §3 below) |
| 4 — Window connectivity correctness | **PASS** — 9/9 from-scratch recomputations matched exactly; 21/21 sampled matrices structurally valid; 0 mismatches vs. `connectivity_summary.csv` |
| 5 — Flexibility value sanity | **PASS** — all 31,216 rows in `[0,1]`, structure/columns/params all correct, monotonicity holds (ω↑→flex↓ in 12/12 cells, γ↑→flex↓ in 12/12 slices, width↑→flex↓ at all 4 tested corners) |
| 6 — Backfill consistency | **N/A** — 0 scans backfilled yet, nothing to cross-check |
| 7 — Signed-edge code path | **PASS (confirmed)** — `build_igraph` at HEAD uses `nonzero_mask = edge_weights != 0`; 8/9 sampled connectivity windows contain negative off-diagonal values that the old positive-only path would have dropped |

## 3. Outliers / provenance notes found

- **wl35 censoring threshold is stale.** `window_summary_wl35.csv` (a symlink to
  the legacy `outputs/window_summary.csv`) was generated *before* the commit
  that changed `MAX_CENSORED_TRS` from a hardcoded `8` to `round(0.25*width)`
  (which is `9` for width=35). wl50/wl70 were generated after and correctly
  use `12`/`18`. No row anywhere exceeds its *own* file's effective
  threshold, so this isn't corrupting the sweep, but wl35's `keep_window`
  mean (92.92%) is computed under the old, slightly stricter rule —
  re-running wl35's windowing with current code would likely retain a touch
  more data. Low priority; flagging for awareness, not urgent action.
- **Duplicate rows in wl50/wl70 skip logs.** `outputs/report_mouse_censoring/wl50/skipped_scans.csv`
  has 7 rows for 6 unique scans, and `wl70`'s has 12 rows for the same 6
  scans (each duplicated) — an append-only logging artifact from
  `02_make_windows.py` being run more than once without clearing the log.
  Underlying skip set is identical (6 scans, none in `Bf_DTA_anes`) across
  all three widths — log hygiene only, no data-correctness impact.
- **One outlier parameter cell**: (width=70, γ=0.40, ω=0.4) mean flexibility
  is >3σ below its neighbor cells — but this is exactly the most-incomplete
  combo in the sweep (30/42 scans, 12 missing), so it's the expected
  artifact of the missing-data gap, not a new finding. Re-check once
  backfilled.
- **Two scans show broad, cell-independent flexibility extremity**:
  `sub-ag230926b_SHAM_bold_parcellated` (193 of 243 total |z|>3 flags) and
  `sub-ag230919c_EXP_bold_parcellated` (48 flags) — both have high
  `valid_window_ratio` (0.966–0.988), ruling out low data quality as the
  cause. Since the extremity shows up broadly across γ/ω/width cells rather
  than isolated to specific parameter combos, this looks like genuine
  scan-level (biological/mouse-level) signal rather than a computational
  artifact. Worth a closer look before the FDR stage — candidates for
  either flagging as biologically notable or excluding as outliers,
  pending the user's judgment.
- **Lowest-data scan**: `sub-ag241002c_EXP_bold_CNO_parcellated`, the
  global minimum `valid_window_ratio` at every width (wl35: 0.554, wl50:
  0.568, wl70: 0.621) — passed the per-scan 0.25 censoring gate but is
  borderline. Same recommendation as above: a judgment call for the user,
  not an error.

## 4. Signed-edge code path confirmation (Check 7)

Confirmed: the design intent (signed correlations, not positive-only) was
correctly settled per spec §1, and execution matched intent — the commit
that actually ran (`9c741e6`, == current HEAD) uses the signed-weight
`build_igraph`, and sampled connectivity data contains real negative edges
that materially change the graph versus the old positive-only logic.

## 5. Recommendation

No bugs found anywhere in the pipeline (windowing → connectivity → community
detection → manifest/provenance). The sweep's data is sound modulo the 65
known-missing scans, which should be backfilled (per
`docs/ParameterInspectionStuckRun.md`'s per-combo missing-scan lists) before
final parameter selection, since (width=70, γ=0.40, ω=0.4) — the most
data-starved cell — currently reads as a flexibility outlier purely due to
the gap.

On region selection: width=70 combos show the most consistent low-flexibility,
low-noise behavior across the monotonicity checks, but I'm not recommending a
specific (width, γ, ω) pick — that's a modeling choice for the user, informed
by these monotonicity/outlier results once the 65 scans are backfilled and
the two flagged scans are reviewed.

**No code was fixed and no combos were rerun**, per the spec's instruction
that any fix/rerun be a follow-up the user explicitly approves.
