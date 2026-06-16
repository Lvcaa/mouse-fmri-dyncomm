# Gozzi analysis report - 15 June 2026

## 1. Window-connectivity summary

Reference: [`outputs/window_connectivity/connectivity_summary.csv`](outputs/window_connectivity/connectivity_summary.csv)

This file is a scan-level quality-control summary produced after sliding-window
connectivity calculation. Each row represents one scan and reports:

- `dataset`: experimental dataset (`Bf_DTA_anes`, `Bf_DTA_awk`, `Bf_PV_anes`, or
  `Bf_PV_awk`);
- `preproc_pipeline`: preprocessing configuration used for that scan;
- `scan_id`, `subject_id`, and `animal_id`: scan and animal identifiers;
- `csv_path`: source parcellated BOLD time-series file;
- `total_windows`: number of candidate 35-TR windows;
- `valid_windows_count`: windows retained after censoring-based quality control;
- `valid_window_ratio`: retained windows divided by total candidate windows.

The windowing procedure uses a 35-TR window and a 3-TR step. A window is
excluded when it contains at least 9 censored TRs; therefore, a valid window
contains no more than 8 censored TRs. For implementation details, see
[`scripts/02_make_windows.py`](scripts/02_make_windows.py) and
[`scripts/03_compute_window_connectivity.py`](scripts/03_compute_window_connectivity.py).

The file contains 193 scans, with 135,183 of 145,477 candidate windows retained
overall (92.92%).

| Dataset | Scans | Candidate windows | Valid windows | Valid windows (%) | Minimum scan ratio | Maximum scan ratio |
|---|---:|---:|---:|---:|---:|---:|
| `Bf_DTA_anes` | 42 | 28,518 | 27,751 | 97.31 | 93.37 | 97.79 |
| `Bf_DTA_awk` | 33 | 23,727 | 21,169 | 89.22 | 66.62 | 97.91 |
| `Bf_PV_anes` | 80 | 63,450 | 61,249 | 96.53 | 74.46 | 99.39 |
| `Bf_PV_awk` | 38 | 29,782 | 25,014 | 83.99 | 55.42 | 98.09 |

The anesthetized datasets retained a larger proportion of windows than the
awake datasets, particularly compared with `Bf_PV_awk`.

## 2. Skipped scans

Reference: [`outputs/report_mouse_censoring/skipped_scans.csv`](outputs/report_mouse_censoring/skipped_scans.csv)

This file lists scans that were excluded before window generation because more
than 25% of all scan TRs were censored. Its columns identify the dataset,
preprocessing pipeline, scan, source file, censored/total TR count, and
censoring percentage.

Six scans were excluded:

| Dataset | Scan | Censored TRs | Censored (%) |
|---|---|---:|---:|
| `Bf_PV_anes` | `sub-ag240724a_SHAM_bold_baseline_parcellated` | 594 / 1,290 | 46.0 |
| `Bf_PV_anes` | `sub-ag240801c_SHAM_bold_baseline_parcellated` | 1,003 / 1,290 | 77.8 |
| `Bf_PV_awk` | `sub-ag240924b_EXP_bold_CNO_parcellated` | 1,040 / 3,600 | 28.9 |
| `Bf_PV_awk` | `sub-ag240924b_EXP_bold_baseline_parcellated` | 378 / 1,290 | 29.3 |
| `Bf_PV_awk` | `sub-ag240924c_EXP_bold_CNO_parcellated` | 1,047 / 3,600 | 29.1 |
| `Bf_PV_awk` | `sub-ag240927d_EXP_bold_CNO_parcellated` | 1,217 / 3,600 | 33.8 |

Thus, no `Bf_DTA_anes` or `Bf_DTA_awk` scans were removed by the scan-level
criterion. Two `Bf_PV_anes` baseline scans and four `Bf_PV_awk` scans were
removed.

## 3. Temporal Leiden production parameters

References:
[`outputs/community_detection/`](outputs/community_detection/),
[`scripts/04_run_community_detection.py`](scripts/04_run_community_detection.py),
and
[`scripts/inspect_output_communities_param.ipynb`](scripts/inspect_output_communities_param.ipynb).

The three timestamped `leiden_flex_20` production directories were launched
with the same temporal Leiden configuration:

- resolution parameter: `gamma = 0.35`;
- interslice coupling: `omega = 0.25`;
- independent Leiden repetitions per scan: `n_runs = 20`.

Gamma controls the granularity of the CPM partition: increasing gamma generally
produces a larger number of smaller communities. Omega connects each node to
itself in consecutive windows and therefore controls temporal persistence:
larger omega values penalize changes in community membership more strongly.

| Run timestamp | Dataset | Result CSVs | Status | Gamma | Omega | Runs |
|---|---|---:|---|---:|---:|---:|
| `20260611_121947` | `Bf_DTA_anes` | 42 | Complete | 0.35 | 0.25 | 20 |
| `20260612_042319` | `Bf_PV_anes` | 80 | Complete | 0.35 | 0.25 | 20 |

The parameter values in the completed runs are recorded in every result CSV as
`gamma = 0.35`, `interslice_weight = 0.25`, and `n_runs = 20`. The
`20260612_042021` directory contains the initial subject folders but no result
CSVs, indicating that this launch stopped before producing outputs and was
restarted approximately three minutes later as `20260612_042319`.

The production pair was selected after inspecting a temporal Leiden parameter
sweep. For `gamma = 0.35` and `omega = 0.25`, the sweep produced a mean of
approximately 6.36 communities, within the target range of roughly 5–7
communities. Its six-community consensus reproduced the expected broad
functional organization of the mouse brain:

1. salience/anterior default-mode network: DMNa and SAL;
2. posterior default-mode network: DMNp, VIS, and SUB;
3. basal ganglia/olfactory-basal-forebrain network: OLF, STR, CTXsp, and BF;
4. auditory-somatosensory/hippocampal network: AUD, SSs, and HCa;
5. diencephalic network: TH and HY;
6. somatomotor network: MOp and SSp.

Therefore, `gamma = 0.35` and `omega = 0.25` were the only parameter values
retained for the three production launches because they jointly provided a
plausible community count and biologically interpretable grouping of the 16
mouse-brain nodes. This should not be read as meaning that no other tested pair
ever produced a numerical mean between 5 and 7: several neighboring settings
did. Rather, this was the selected production pair after considering both the
target community count and correspondence with the expected functional
networks.

## 4. EXP versus SHAM t-tests

Reference: [`scripts/06_t_tests.ipynb`](scripts/06_t_tests.ipynb)

The notebook compares flexibility between EXP and SHAM independently for each
of the 16 brain-network nodes using both:

- a parametric, two-sided Welch independent-samples t-test
  (`scipy.stats.ttest_ind(..., equal_var=False)`), which does not assume equal
  group variances; and
- a non-parametric, two-sided Mann-Whitney U test
  (`scipy.stats.mannwhitneyu`).

For paired baseline-CNO comparisons in `Bf_PV_anes`, the corresponding tests
are a paired t-test and the non-parametric Wilcoxon signed-rank test. The tables
below report the Welch t-test results, followed by a summary of the
non-parametric results. Unless stated otherwise, p-values are raw and
uncorrected for the 16 node comparisons.

### Bf_DTA_anes

The analysis included 22 EXP scans and 20 SHAM scans. None of the 16 nodes
showed a statistically significant EXP-SHAM difference at the uncorrected
`p < 0.05` threshold.

| Node | Mean EXP | Mean SHAM | t | p |
|---|---:|---:|---:|---:|
| AUD | 0.116486 | 0.118607 | -0.588 | 0.5600 |
| BF | 0.120697 | 0.119823 | 0.305 | 0.7622 |
| CTXsp | 0.124450 | 0.124908 | -0.116 | 0.9083 |
| DMNa | 0.119487 | 0.122377 | -0.617 | 0.5408 |
| DMNp | 0.123041 | 0.131345 | -1.904 | 0.0650 |
| HCa | 0.130295 | 0.133892 | -0.686 | 0.4967 |
| HY | 0.111328 | 0.114540 | -0.805 | 0.4255 |
| MOp | 0.126074 | 0.127067 | -0.217 | 0.8296 |
| OLF | 0.118676 | 0.125322 | -1.738 | 0.0900 |
| SAL | 0.123577 | 0.130545 | -1.578 | 0.1231 |
| SSp | 0.125246 | 0.129140 | -0.941 | 0.3531 |
| SSs | 0.126295 | 0.132076 | -1.570 | 0.1246 |
| STR | 0.132723 | 0.138681 | -1.331 | 0.1915 |
| SUB | 0.124652 | 0.121727 | 0.719 | 0.4763 |
| TH | 0.124812 | 0.127310 | -0.534 | 0.5963 |
| VIS | 0.117817 | 0.118873 | -0.306 | 0.7610 |

The smallest p-value was observed in DMNp (`t = -1.904`, `p = 0.0650`), where
mean flexibility was lower in EXP than SHAM. OLF showed the next-lowest
p-value (`p = 0.0900`). These are trends only and do not meet the conventional
significance threshold.

The Mann-Whitney U test produced raw `p < 0.05` results for DMNp
(`U = 130.0`, `p = 0.0242`) and OLF (`U = 128.5`, `p = 0.0219`), with lower
mean flexibility in EXP than SHAM for both nodes. These are uncorrected
node-wise findings and should not be interpreted as surviving correction for
the 16 comparisons.

### Bf_PV_anes

The initial notebook analysis pooled baseline and CNO files, giving 42 EXP and
38 SHAM observations. None of the 16 nodes showed a statistically significant
EXP-SHAM difference (`p < 0.05`).

| Node | Mean EXP | Mean SHAM | t | p |
|---|---:|---:|---:|---:|
| AUD | 0.122093 | 0.120551 | 0.424 | 0.6729 |
| BF | 0.121369 | 0.123693 | -0.685 | 0.4955 |
| CTXsp | 0.123159 | 0.123114 | 0.014 | 0.9892 |
| DMNa | 0.128909 | 0.125962 | 0.722 | 0.4727 |
| DMNp | 0.124759 | 0.124756 | 0.001 | 0.9992 |
| HCa | 0.130534 | 0.130413 | 0.032 | 0.9749 |
| HY | 0.120470 | 0.119715 | 0.235 | 0.8145 |
| MOp | 0.121345 | 0.122373 | -0.281 | 0.7797 |
| OLF | 0.125639 | 0.125508 | 0.037 | 0.9709 |
| SAL | 0.120349 | 0.118671 | 0.478 | 0.6340 |
| SSp | 0.120790 | 0.118534 | 0.639 | 0.5251 |
| SSs | 0.119605 | 0.119143 | 0.141 | 0.8880 |
| STR | 0.131240 | 0.127645 | 0.843 | 0.4023 |
| SUB | 0.123931 | 0.125738 | -0.492 | 0.6247 |
| TH | 0.131924 | 0.128193 | 1.031 | 0.3060 |
| VIS | 0.120517 | 0.117997 | 0.762 | 0.4484 |

The smallest p-value was for TH (`t = 1.031`, `p = 0.3060`), providing no
evidence of an EXP-SHAM difference.

The pooled Mann-Whitney U tests also found no node with raw `p < 0.05`; the
smallest p-value was for SUB (`U = 661.0`, `p = 0.1885`).

This pooled test must be interpreted cautiously: each animal can contribute
both a baseline and a CNO observation, so the 42 and 38 observations are not
fully independent. The notebook therefore also performs phase-aware analyses:

#### Definition of the paired CNO-versus-baseline analysis

The paired analysis is performed separately within the EXP and SHAM groups and
independently for each brain-network node. For a given animal and node, its CNO
flexibility value is paired with the baseline flexibility value from the same
animal:

`difference = flexibility_CNO - flexibility_baseline`.

Only animals with both phases available are included; animals missing either
the baseline or CNO observation are removed before testing. This gives 21
paired animals per node in the EXP group and 18 paired animals per node in the
SHAM group. The smaller SHAM sample reflects the two baseline scans excluded
because of excessive censoring.

For each node and condition, the parametric paired t-test
(`scipy.stats.ttest_rel(CNO, baseline)`) tests whether the mean within-animal
difference is zero. The non-parametric Wilcoxon signed-rank test evaluates the
corresponding paired differences without assuming normality. A positive mean
difference indicates higher flexibility during CNO than baseline, whereas
a negative mean difference indicates lower flexibility during CNO. These tests
assess phase changes within EXP or SHAM animals; they are distinct from the
independent EXP-versus-SHAM tests and from the difference-in-differences analysis
comparing phase changes between groups.

- Paired baseline-CNO t-tests found no raw `p < 0.05` effects in EXP animals.
  In SHAM animals, DMNp (`p = 0.0492`) and VIS (`p = 0.0425`) crossed the raw
  threshold, but these values were not corrected for the 16 node comparisons.
- The paired Wilcoxon tests found no raw `p < 0.05` effects in EXP animals.
  In SHAM animals, VIS crossed the raw threshold (`p = 0.0304`).
- In the CNO phase alone, no node differed significantly between EXP and SHAM;
  the smallest Welch p-value was for SUB (`p = 0.1868`). The Mann-Whitney test
  for SUB gave a raw `p = 0.0081`, but this was an uncorrected result.
- The difference-in-differences analysis found no significant node with the
  original 3-TR step according to Welch's test; TH was closest to the threshold
  (`p = 0.0503`). The Mann-Whitney test gave a raw `p = 0.0358` for VIS, but no
  result from either test survived Benjamini-Hochberg FDR correction.

Overall, the parametric tests provide no statistically significant evidence of
an EXP-SHAM difference in node flexibility for either `Bf_DTA_anes` or
`Bf_PV_anes`. Some non-parametric tests produced raw node-wise `p < 0.05`
results, but these require cautious interpretation because of multiple
comparisons and, for the pooled `Bf_PV_anes` analysis, non-independent
baseline/CNO observations.
