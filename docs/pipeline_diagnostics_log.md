# Pipeline Diagnostics Log

A running record of investigations into pipeline behaviour and result quality, in
chronological order of when each issue arose. Each entry documents the symptom,
the root cause, and what (if anything) was changed as a result.

---

## 2026-05-30 — QC report: sub-ag231031, session d global-signal artifact

**Sessions analysed:** b_SHAM, c_EXP, d_SHAM
**Pipeline:** `FD_cut30frames_bandpass0.01-0.1_cut30edges_mot24_CSF_smooth6`

### Summary

Sessions b and c show flexibility values in a plausible range. Session d returns
near-zero flexibility across all ROIs, which is a valid algorithmic output but
reflects an anomalous input: the BOLD time series for session d is dominated by a
strong global oscillation that inflates all pairwise correlations and causes Louvain
to assign all nodes to a single community at nearly every time window.

### Flexibility results

Parameters: γ = 0.1, ω = 0.5, n_runs = 1 (multiprocessing disabled; see note below).

#### Session b — SHAM (688 windows)

| ROI | Flexibility |
|-----|-------------|
| DMNa | 0.0509 |
| DMNp | 0.0480 |
| SAL | 0.0451 |
| OLF | 0.0451 |
| STR | 0.0437 |
| AUD | 0.0422 |
| VIS | 0.0437 |
| TH | 0.0393 |
| MOp | 0.0568 |
| SSp | 0.0451 |
| SSs | 0.0568 |
| HCa | 0.0422 |
| SUB | 0.0378 |
| CTXsp | 0.0451 |
| BF | 0.0408 |
| HY | 0.0466 |

#### Session c — EXP (631 windows)

| ROI | Flexibility |
|-----|-------------|
| DMNa | 0.0254 |
| DMNp | 0.0302 |
| SAL | 0.0397 |
| OLF | 0.0381 |
| STR | 0.0254 |
| AUD | 0.0365 |
| VIS | 0.0444 |
| TH | 0.0365 |
| MOp | 0.0333 |
| SSp | 0.0254 |
| SSs | 0.0286 |
| HCa | 0.0302 |
| SUB | 0.0429 |
| CTXsp | 0.0413 |
| BF | 0.0286 |
| HY | 0.0524 |

#### Session d — SHAM (676 windows) ⚠️

| ROI | Flexibility |
|-----|-------------|
| DMNa | 0.00296 |
| DMNp | 0.00296 |
| SAL | 0.00296 |
| OLF | 0.00296 |
| STR | 0.00296 |
| AUD | 0.00296 |
| VIS | **0.00593** |
| TH | **0.00593** |
| MOp | 0.00296 |
| SSp | 0.00296 |
| SSs | 0.00296 |
| HCa | 0.00296 |
| SUB | 0.00296 |
| CTXsp | 0.00296 |
| BF | 0.00296 |
| HY | 0.00296 |

14 of 16 ROIs switched community exactly **2 times** across 675 transitions (= 2/675).
VIS and TH switched 4 times. This uniformity indicates a near-static single-community
partition throughout the session.

### Input data inspection

#### Session-level connectivity statistics

| Metric | b_SHAM | c_EXP | d_SHAM |
|--------|--------|-------|--------|
| Total timepoints | 2190 | 2190 | 2190 |
| Censored timepoints | 125 (5.7%) | 209 (9.5%) | 152 (6.9%) |
| Valid timepoints | 2065 | 1981 | 2038 |
| Full-session mean pairwise r | 0.202 | 0.228 | **0.592** |
| Full-session % positive pairs | 80% | 85% | **100%** |
| Min pairwise r | −0.37 | −0.23 | **+0.155** |
| Max pairwise r | 0.94 | 0.75 | 0.83 |
| Mean positive edge density (sliding windows) | 66.3% | — | **93.5%** |

Session d has no negative correlations anywhere in the full-session matrix. The
minimum pairwise r (+0.155) is higher than the mean pairwise r for sessions b and c.

#### Sliding-window edge density (200-frame chunks)

| Frames | b_SHAM mean r | b_SHAM % pos | d_SHAM mean r | d_SHAM % pos |
|--------|---------------|--------------|---------------|--------------|
| 0–200 | 0.179 | 78% | 0.603 | 100% |
| 200–400 | 0.222 | 77% | 0.598 | 100% |
| 400–600 | 0.208 | 80% | 0.664 | 100% |
| 600–800 | 0.161 | 66% | 0.636 | 100% |
| 800–1000 | 0.173 | 72% | 0.587 | 100% |
| 1000–1200 | 0.160 | 70% | 0.565 | 100% |
| 1200–1400 | 0.218 | 78% | 0.583 | 100% |
| 1400–1600 | 0.274 | 85% | 0.432 | 98% |
| 1600–1800 | 0.253 | 80% | 0.591 | 100% |
| 1800–2000 | 0.146 | 72% | 0.645 | 100% |

Session d maintains near-100% positive connectivity uniformly across the entire
recording — this is not confined to any particular segment.

#### ROI correlation with global mean signal

The global mean signal (average across all 16 ROIs at each timepoint) was used as a
proxy for global BOLD activity.

| ROI | b_SHAM r | d_SHAM r |
|-----|----------|----------|
| DMNa | 0.237 | 0.834 |
| DMNp | 0.372 | 0.892 |
| SAL | 0.652 | 0.685 |
| OLF | 0.685 | 0.784 |
| STR | 0.532 | 0.827 |
| AUD | 0.714 | 0.757 |
| VIS | 0.170 | 0.798 |
| TH | 0.426 | 0.785 |
| MOp | 0.501 | 0.839 |
| SSp | 0.475 | 0.896 |
| SSs | 0.611 | 0.850 |
| HCa | 0.671 | 0.846 |
| SUB | 0.097 | 0.637 |
| CTXsp | 0.689 | 0.721 |
| BF | 0.247 | 0.643 |
| HY | 0.523 | 0.766 |
| **Global mean std** | **0.108** | **0.225** |

In session b, SUB (r = 0.10) and VIS (r = 0.17) are nearly independent of the global
mean, indicating distinct network dynamics. In session d, every ROI is strongly
coupled to the global mean (minimum r = 0.637), and the global mean itself has twice
the variance. This is the signature of a large, unattenuated global oscillation
driving all ROIs in concert.

### Interpretation

The near-zero flexibility in session d is not a bug in the community detection code.
It is the correct output given the input connectivity structure. Because all ROIs are
positively and strongly correlated at every window, the Louvain algorithm places all
nodes in a single community at nearly every time step, leaving almost no room for
community switching.

#### Possible causes

1. **Residual global signal.** The preprocessing pipeline (`mot24_CSF_smooth6`)
   includes motion and CSF regression but does not explicitly include global signal
   regression (GSR). If the global signal removal step was run for sessions b and c
   but not d — or ran but failed — this would produce exactly the observed pattern.

2. **Different brain state / anesthesia depth.** Under deep anaesthesia, slow and
   highly synchronous BOLD oscillations are common and can produce globally coherent
   signals. If session d was recorded at a different anaesthesia depth or phase, the
   global synchrony could be genuinely biological. The censoring rate (6.9%) and
   signal variance are not out of range by themselves, so the data is not obviously
   corrupted.

### Recommendation (as of 2026-05-30)

Check the preprocessing history of session d:
- Was GSR applied uniformly across all three sessions?
- Are motion summary statistics (mean FD, max FD) for session d comparable to b and c?
- Are there acquisition notes indicating anaesthesia changes during session d?

Until this is resolved, **session d should be excluded from group-level flexibility
comparisons** involving sessions b and c.

#### Notes on analysis parameters at the time of this report

- **n_runs = 1.** The parallel multi-run loop was commented out in
  `scripts/04_run_community_detection.py`. Only one Louvain run was executed per
  scan, so reported flexibility was not averaged across runs. Variability between
  runs was not captured, and values for sessions b and c could shift once
  `n_runs=100` was enabled.
- **γ = 0.1, ω = 0.5.** These were chosen to avoid the CPMVertexPartition singleton
  collapse that occurs at γ = 1 with Pearson correlations in [0, 1]. Values were
  provisional pending a parameter sweep.

> **Status update:** the current pipeline (`scripts/04_run_community_detection.py`)
> runs `N_RUNS=20` with `γ=0.35`, `ω=0.25` (temporal Leiden, supra-adjacency — see
> the 2026-06-06 entry below), addressing the n_runs=1 caveat above.

---

## 2026-06-06 — Louvain slowness: root cause and fix (supra-adjacency)

### The problem in one sentence

`louvain.time_slices_to_layers` represented T=664 windows as 665 separate graph
objects that each carried all 10,624 supra-nodes, so the optimizer bookkept 7 million
node-slots per sweep instead of 10,624.

### Before vs after (intuitive)

#### BEFORE — layered multiplex (original code)

664 windows of 16 ROIs. `time_slices_to_layers` builds this:

```
window 0  →  layer graph with 10,624 vertices, but only 16 of them have edges
window 1  →  layer graph with 10,624 vertices, but only 16 of them have edges
...
window 663→  layer graph with 10,624 vertices, but only 16 of them have edges
interslice→  graph with 10,624 vertices and 10,608 chain edges
```

664 layers × 10,624 vertices = **7 million node-slots**, even though only 10,624 are
real. The optimizer then calls `optimise_partition_multiplex(665 partitions)`. Each
sweep, it loops over all 665 partitions × 10,624 membership slots — the vast majority
of which are *isolated padding nodes doing nothing*.

Think of it as paying a hotel for 664 rooms but only ever sleeping in one bed per room.

#### AFTER — supra-adjacency graph (fixed code)

Build **one graph** of 10,624 nodes. Node `t*16 + i` is ROI `i` in window `t`.

```
window 0's edges  →  vertices  0–15  (correlation weights)
window 1's edges  →  vertices 16–31  (correlation weights)
...
window 663's edges→  vertices 10608–10623  (correlation weights)
coupling          →  edge 0↔16, 1↔17 ... for each ROI, every adjacent pair (weight ω)
```

Same 10,624 nodes, same 73,103 edges — just one single graph. The optimizer calls
`find_partition(1 graph)`, and each sweep visits each node and each edge **once**.

You pay for exactly the beds that exist.

#### What is identical

- Same 16 ROIs per window
- Same correlation edges within each window
- Same ω-weight coupling between `ROI_i(t)` and `ROI_i(t+1)` for adjacent windows only
- Same flexibility calculation: read membership `[t*N + i]`, reshape to (T, N), count
  switches
- Same resolution parameter γ controlling community granularity

#### What changes (the one caveat)

CPM's resolution penalty `γ · n(C)²` now counts all nodes in a community **across all
time windows**, not just within a single slice. A community that persists across 100
windows will be penalized more than in the layered version, which slightly favors
smaller or more fragmented temporal communities. This is actually the canonical
Mucha 2010 supra-adjacency formulation — it is not wrong. The interslice coupling ω
counterbalances it: high ω keeps ROIs together across windows; low ω allows more
switching.

In practice, γ=0.1 and ω=0.5 produced biologically meaningful results with either
approach; the flexibility values shift by a small amount, not qualitatively.

### Empirical measurements (sub-ag230925a, 664 windows, 16 ROIs)

#### Actual supra-graph size

| Quantity | Value |
|---|---|
| Nodes per window | 16 |
| Windows (T) | 664 |
| Supra-graph nodes | 10,624 |
| Intra-layer edges | 62,495 |
| Inter-layer edges | 10,608  (= 16 × 663, adjacent-only, correct) |
| Total edges | 73,103 |

#### Scaling: 1 Louvain run vs T (layered, original)

```
   T   1 run (s)   x100 est    ratio per doubling
  25     0.03
  50     0.15      0.3m         4.8x
 100     1.08      1.8m         7.1x
 200    13.28     22.1m        12.3x
 400   168.63    281.1m        12.7x   (pure O(T²) would be 4x — actual ≈ T^3.7)
```

#### Head-to-head: same T=664, 1 run

| Approach | Per run | × 100 runs |
|---|---|---|
| Layered, `louvain` | ~1,080 s (extrapolated) | ~567–1298 min observed |
| Layered, `leidenalg` | ~250 s (4× better algorithm) | still hours |
| **Supra-adjacency, `leidenalg`** | **0.30 s** | **~30 s** |

Speedup: **~3,500×**. 193 subjects × ~30 s = **~1.6 hours total**, versus months.

### Why package swap alone (louvain → leidenalg) does not fix it

Both packages expose the identical `time_slices_to_layers` API and produce
byte-for-byte the same 665 graph objects. The Leiden algorithm is ~4× faster per
sweep because it has better local-moving guarantees, but it is still O(T²·N). The
construction is the bottleneck, not the algorithm variant.

### Resolution

Fixed by switching `scripts/04_run_community_detection.py` to build a single
supra-adjacency graph and run `leidenalg.find_partition_temporal` once per run (see
`docs/04_community_detection.md` for the current execution flow). This is the
implementation in use for all results from this date onward.

---

## 2026-06-13 — Audit: low statistical significance in EXP vs SHAM flexibility t-tests

### Starting point

T-tests on ROI-level flexibility (`scripts/06_t_tests.ipynb`) for `Bf_DTA_anes` and
`Bf_PV_anes` showed low statistical significance for almost every ROI/condition
comparison. Goal: determine whether this is a preprocessing/pipeline artifact or
reflects genuinely weak flexibility differences in the data.

### Finding 1 — Flexibility values are compressed into a narrow band

Across all 16 ROIs × 42 `Bf_DTA_anes` scans (`scripts/flexibility/flexibility_scores.csv`):
mean = 0.124, **std = 0.014**, range 0.08–0.17. Every node, every animal sits at ~0.12.
With this little variance in the outcome, no test can separate groups.

### Finding 2 — Root cause: 91% sliding-window overlap

`scripts/02_make_windows.py` uses `WINDOW_LENGTH=35`, `STEP_SIZE=3` → consecutive
windows share 32/35 TRs = **91% overlap**. Flexibility
(`scripts/04_run_community_detection.py`, `switches / (n_windows - 1)`) is computed
between *every* adjacent window pair, so 91% of the transitions compare windows that
are almost the same data.

Empirical confirmation on a real `Bf_DTA_anes` scan: correlated the flattened
upper-triangle connectivity vector between window pairs at different separations.

| comparison | edge-pattern correlation |
|---|---|
| adjacent windows (3 TR apart) — what flexibility is computed over | **0.94** |
| ~non-overlapping (12 steps apart, ~36 TR) | **0.06** |

Adjacent windows are 94% identical, so the community partition has little reason to
switch — flexibility collapses to ~0.12 with std 0.014. The 12-step decorrelation
length implies ~50 effective independent windows per scan, not ~660: the transition
denominator is inflated ~12× by redundant comparisons.

### Finding 3 — Baseline DTA_anes EXP vs SHAM (Welch t-test, n_EXP=22, n_SHAM=20)

| Node | EXP | SHAM | diff | p |
|---|---|---|---|---|
| DMNp | 0.1230 | 0.1313 | −0.0083 | 0.061 |
| OLF | 0.1187 | 0.1253 | −0.0066 | 0.090 |
| SAL | 0.1236 | 0.1305 | −0.0070 | 0.120 |
| SSs | 0.1263 | 0.1321 | −0.0058 | 0.123 |
| STR | 0.1327 | 0.1387 | −0.0060 | 0.187 |
| (remaining 11 nodes) | — | — | — | 0.35–0.91 |

EXP < SHAM in 14/16 ROIs (consistent direction, suggestive of a real but small
BF-lesion effect — reduced flexibility — masked by Finding 2's compression and by
run-to-run Leiden noise (`flexibility_std` ≈ 0.008–0.013, same order as the group
differences).

### Finding 4 — Bf_PV_anes CNO-phase EXP vs SHAM, and within-animal DiD

CNO-phase group comparison (n_EXP=21, n_SHAM=20): only **SUB** reached
Mann-Whitney p=0.008 (Welch p=0.187 — rank-test-only, fragile, and does not survive
FDR across 16 nodes).

Added a **difference-in-differences (DiD)** analysis to `06_t_tests.ipynb`: for each
animal with both `baseline` and `CNO` scans, Δ = flex(CNO) − flex(baseline), then
EXP vs SHAM on Δ (removes non-specific CNO/time drift common to both groups).

| Node | ΔEXP | ΔSHAM | DiD | p (Welch) |
|---|---|---|---|---|
| TH | −0.0032 | +0.0042 | −0.0074 | 0.050 |
| SUB | −0.0043 | +0.0049 | −0.0092 | 0.060 |
| STR | −0.0057 | +0.0025 | −0.0082 | 0.123 |
| HCa | −0.0030 | +0.0044 | −0.0074 | 0.121 |
| DMNp | +0.0004 | +0.0071 | −0.0067 | 0.139 |
| BF | −0.0015 | +0.0042 | −0.0058 | 0.217 |

Under CNO, EXP animals lose flexibility while SHAM animals gain slightly — a pattern
consistent with BF-projection targets (thalamus, subiculum, hippocampus), but nothing
survives 16-way FDR correction.

### Finding 5 — De-overlapping experiment confirms compression, but doesn't rescue the group effect

Added a step-size experiment to `06_t_tests.ipynb`: recomputed `Bf_PV_anes`
flexibility by subsampling existing connectivity windows (every k-th window, k=12 →
effective step = 36 TR ≈ window length ≈ non-overlapping), reusing the community
detection from script 04 (`n_runs=10`). Output saved to
`scripts/flexibility/flexibility_step36_Bf_PV_anes.csv`.

| | flex mean | spread (std) | range |
|---|---|---|---|
| step 3 (current pipeline, 91% overlap) | 0.124 | 0.016 | 0.06–0.17 |
| step 36 (k=12, ~non-overlapping) | **0.466** | **0.076** | 0.12–0.69 |

De-overlapping quadrupled flexibility and widened the spread ~5× — Finding 2's
compression is real and large.

However, re-running the DiD test at step 36 did **not** reveal a clean group effect:

| Node | DiD (step 3) | p (step 3) | DiD (step 36) | p (step 36) |
|---|---|---|---|---|
| TH | −0.0074 | 0.050 | −0.0436 | **0.035** |
| SUB | −0.0092 | 0.060 | −0.0030 | 0.899 |
| SSs | −0.0042 | 0.315 | +0.0480 | 0.011 |
| VIS | −0.0080 | 0.072 | −0.0465 | 0.058 |

- DiD nodes significant at uncorrected Welch p<0.05: step 3 = 0 → step 36 = 2.
  Nothing survives FDR at either step size.
- **TH (thalamus)** is the only node with a **consistent sign and borderline p across
  both window sizes** — the most credible candidate for a real BF→thalamus
  flexibility effect.
- **SUB**, the headline "hit" from Finding 4, **evaporates and flips sign** at step
  36 (p=0.90) — it was a compression/outlier artifact of the 91%-overlap windowing,
  not biology.
- SSs becomes nominally significant at step 36 but with a flipped sign vs step 3 —
  not trustworthy without further checks.

### Conclusion

Both factors are in play:

1. **Pipeline artifact (confirmed and worth fixing):** the 91%-overlap sliding window
   in `scripts/02_make_windows.py` compresses flexibility into a narrow band
   (std ≈ 0.014) and inflates the transition count ~12×, suppressing real variance.
2. **Genuinely weak group effect (data property):** even after removing the
   compression (step 36), the EXP vs SHAM difference in `Bf_PV_anes` remains weak and
   unstable — apparent "hits" reshuffle between window sizes, and only thalamic
   flexibility shows a consistent, borderline-significant reduction under CNO in EXP
   animals. Nothing survives multiple-comparison correction at either window size.

### Caveats on the step-36 result

- step-36 flex ≈ 0.47 is high for only ~40–90 near-independent windows per scan;
  `γ=0.35`/`ω=0.25` were tuned for the step-3 regime and likely need re-tuning at
  larger steps. Step 36 demonstrates the artifact but is not a final operating point.
- Used `n_runs=10` for the recompute vs. the pipeline's `n_runs=20`.
- These scans are anesthetized; anesthesia suppresses dynamic FC, so the **awake**
  cohorts (`Bf_DTA_awk`, `Bf_PV_awk`) are where a group effect is most likely to be
  detectable and have not yet been checked with this method.

### Recommended next steps

1. Re-tune `STEP_SIZE` (try an intermediate value, e.g. step ≈ 12–17 TR) together with
   `γ`/`ω` on `Bf_DTA_anes` and `Bf_PV_anes`, rather than jumping straight to fully
   non-overlapping windows.
2. Re-run the DiD analysis on the awake cohorts.
3. Add FDR correction and effect-size/CI reporting as the default in
   `06_t_tests.ipynb` (already partially done for the DiD section).
4. Treat TH (thalamus) as the leading a-priori ROI for the PV/BF circuit going
   forward; treat the original SUB "hit" as resolved/explained (windowing artifact).

---

## Related docs

- [04_community_detection.md](04_community_detection.md) — current execution flow,
  parameters, and output format of the community-detection step
- [pipeline_walkthrough.md](pipeline_walkthrough.md) — step-by-step trace with example
  values at each pipeline stage
- [community_detection_plan.md](community_detection_plan.md) — windowing and censoring
  design decisions
- [TO_DO.md](TO_DO.md) — open parameter-sweep and data-quality tasks
