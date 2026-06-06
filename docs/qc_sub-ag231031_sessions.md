# QC Report: sub-ag231031 — Window Communities

**Date:** 2026-05-30
**Sessions analysed:** b_SHAM, c_EXP, d_SHAM
**Pipeline:** `FD_cut30frames_bandpass0.01-0.1_cut30edges_mot24_CSF_smooth6`

---

## Summary

Sessions b and c show flexibility values in a plausible range. Session d returns near-zero flexibility across all ROIs, which is a valid algorithmic output but reflects an anomalous input: the BOLD time series for session d is dominated by a strong global oscillation that inflates all pairwise correlations and causes Louvain to assign all nodes to a single community at nearly every time window.

---

## Flexibility results

Parameters: γ = 0.1, ω = 0.5, n_runs = 1 (multiprocessing disabled; see note below).

### Session b — SHAM (688 windows)

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

### Session c — EXP (631 windows)

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

### Session d — SHAM (676 windows) ⚠️

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

14 of 16 ROIs switched community exactly **2 times** across 675 transitions (= 2/675). VIS and TH switched 4 times. This uniformity indicates a near-static single-community partition throughout the session.

---

## Input data inspection

### Session-level connectivity statistics

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

Session d has no negative correlations anywhere in the full-session matrix. The minimum pairwise r (+0.155) is higher than the mean pairwise r for sessions b and c.

### Sliding-window edge density (200-frame chunks)

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

Session d maintains near-100% positive connectivity uniformly across the entire recording — this is not confined to any particular segment.

### ROI correlation with global mean signal

The global mean signal (average across all 16 ROIs at each timepoint) was used as a proxy for global BOLD activity.

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

In session b, SUB (r = 0.10) and VIS (r = 0.17) are nearly independent of the global mean, indicating distinct network dynamics. In session d, every ROI is strongly coupled to the global mean (minimum r = 0.637), and the global mean itself has twice the variance. This is the signature of a large, unattenuated global oscillation driving all ROIs in concert.

---

## Interpretation

The near-zero flexibility in session d is not a bug in the community detection code. It is the correct output given the input connectivity structure. Because all ROIs are positively and strongly correlated at every window, the Louvain algorithm places all nodes in a single community at nearly every time step, leaving almost no room for community switching.

### Possible causes

1. **Residual global signal.** The preprocessing pipeline (`mot24_CSF_smooth6`) includes motion and CSF regression but does not explicitly include global signal regression (GSR). If the global signal removal step was run for sessions b and c but not d — or ran but failed — this would produce exactly the observed pattern.

2. **Different brain state / anesthesia depth.** Under deep anaesthesia, slow and highly synchronous BOLD oscillations are common and can produce globally coherent signals. If session d was recorded at a different anaesthesia depth or phase, the global synchrony could be genuinely biological. The censoring rate (6.9%) and signal variance are not out of range by themselves, so the data is not obviously corrupted.

### Recommendation

Check the preprocessing history of session d:
- Was GSR applied uniformly across all three sessions?
- Are motion summary statistics (mean FD, max FD) for session d comparable to b and c?
- Are there acquisition notes indicating anaesthesia changes during session d?

Until this is resolved, **session d should be excluded from group-level flexibility comparisons** involving sessions b and c.

---

## Notes on analysis parameters

- **n_runs = 1.** The parallel multi-run loop is currently commented out in `scripts/04_run_community_detection.py` (line 192). Only one Louvain run is executed per scan, so reported flexibility is not averaged across runs. Variability between runs is not captured, and values for sessions b and c may shift when the full n_runs=100 is enabled.
- **γ = 0.1, ω = 0.5.** These were chosen to avoid the CPMVertexPartition singleton collapse that occurs at γ = 1 with Pearson correlations in [0, 1]. Values are provisional and should be validated against a parameter sweep.
