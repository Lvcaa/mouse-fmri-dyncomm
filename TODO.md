# Community Detection Follow-Up

## Priority Overview

| Priority | Status | Task |
|---|---|---|
| P0 - Critical | Open | Handle gaps between retained windows correctly |
| P1 - High | Open | Run community-detection parameter sensitivity analyses |
| P1 - High | Open | Investigate scans with extreme global synchrony |
| P1 - High | Open | Control for global connectivity in group comparisons |
| P2 - Medium | Open | Report scan exclusions and retained-window fractions |
| Verified | Complete | Confirm pipeline and output integrity |

## P0 - Handle Censoring Gaps

**Status:** Open

Discarded windows currently disappear from the temporal graph. The remaining
windows are then treated as consecutive even when their original window IDs
contain gaps. This can couple windows separated by many TRs and can deflate
flexibility.

### The Issue

Leiden is encouraged to preserve the ROI’s community across an interval with no usable observations, potentially deflating flexibility.

### Actions

- Split each scan into contiguous blocks of retained window IDs.
- Do not add temporal coupling across a discarded-window gap.
- Count flexibility transitions only within contiguous blocks.
- Combine block-level switch counts using the total number of valid
  within-block transitions.
- Record the number of blocks, gap events, and valid transitions per scan.
- Recompute all community and flexibility outputs after implementing the fix.

### Completion Criteria

- No transition is counted when consecutive retained window IDs differ by more
  than one.
- Tests cover scans with no gaps, one gap, multiple gaps, and one-window blocks.
- Recomputed outputs document the difference from the current results.

## P1 - Parameter Sensitivity

**Status:** Open

The absolute flexibility scale is highly sensitive to the CPM resolution
parameter, interslice coupling, and window configuration. The current
`gamma=0.1` and `omega=0.5` values are plausible but not yet validated.

### Actions

- Test a justified grid of `gamma` values around the current setting.
- Test multiple `omega` values, including weaker and stronger coupling.
- Repeat key analyses with window lengths of 45 and 60 TR.
- Compare scan rankings, group effects, community sizes, and flexibility.
- Select parameters using documented methodological criteria rather than the
  size or significance of group differences.

### Completion Criteria

- Main conclusions are stable across a reasonable parameter range, or their
  dependence on parameters is explicitly reported.
- The final parameter choice and rationale are documented.

## P1 - Global Synchrony QC

**Status:** Open

Several scans show near-zero flexibility together with unusually high global
correlation. These may be valid biological observations, but they could also
reflect residual global signal, motion, acquisition differences, or failed
preprocessing.

### Actions

- Review the most extreme low-flexibility, high-correlation scans.
- Compare motion and censoring summaries with the rest of their cohorts.
- Verify that preprocessing and nuisance regression completed consistently.
- Review acquisition and anesthesia notes where available.
- Define an objective QC flag or exclusion rule before group-level testing.

### Completion Criteria

- Every flagged scan has a documented keep, exclude, or sensitivity-only
  decision with a stated reason.

## P1 - Control Global Connectivity

**Status:** Open

Flexibility is strongly inversely related to overall correlation strength and
positive-edge density. Cohort differences may therefore reflect global
connectivity or preprocessing differences in addition to network dynamics.

### Actions

- Calculate mean connectivity, positive-edge density, and global-signal metrics
  for every scan.
- Compare these metrics across cohorts, conditions, and phases.
- Include appropriate connectivity or global-signal metrics as QC variables or
  covariates.
- Repeat group comparisons after excluding extreme global-synchrony scans.
- Consider sensitivity analyses for the current positive-edge-only graph.

### Completion Criteria

- Report whether flexibility effects remain after accounting for global
  connectivity.

## P2 - Report Censoring and Exclusions

**Status:** Open

Censoring and retained-window fractions differ across cohorts, especially in
the awake PV data.

### Actions

- Report all scan-level exclusions and their censoring fractions.
- Report total, retained, and discarded windows for every scan.
- Report gap counts, contiguous block counts, and valid transitions.
- Summarize these measures by cohort, condition, and phase.
- Include censoring sensitivity analyses using stricter thresholds.

### Completion Criteria

- The final analysis contains a reproducible QC table covering every raw scan.

## Verified Pipeline Integrity

**Status:** Complete

- Raw data consistently contains the expected 16 ROIs.
- No partial-NaN rows, infinite values, constant ROIs, or exact duplicate raw
  files were detected.
- The six missing raw scans were correctly excluded by the scan-level censoring
  threshold.
- All 193 eligible scans have matching connectivity and community outputs.
- Output ROI names, parameters, window counts, and flexibility arithmetic are
  internally consistent.
- Independently recomputed connectivity matrices matched the saved matrices to
  numerical precision.

