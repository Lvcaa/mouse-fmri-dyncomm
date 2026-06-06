# Community Detection Plan

## 1. Scan-Level Censoring

Exclude any scan with more than 25% censored TRs.

This removes full time series that are too corrupted before dynamic connectivity is estimated.

Sensitivity check: repeat the main analysis with a stricter 20% scan-level threshold.

## 2. Sliding Windows

For each retained scan, use sliding windows over the original time series:

- Window length: 35 TR
- Step size: 3 TR

Example:

```text
Window 1: TR 1-35
Window 2: TR 4-39
Window 3: TR 7-42
```

## 3. Window-Level Censoring

For each 35-TR window, count censored TRs.

Using a 25% censoring threshold:

```text
25% of 35 TR = 8.75 TR
```

Operational rule:

```text
Exclude window if it has >=9 censored TRs.
Keep window if it has <=8 censored TRs.
```

Equivalently, keep only windows with at least 27 valid TRs.

## 4. Window-Wise Connectivity

For each retained window:

1. Remove censored rows.
2. Keep only ROI columns, excluding `Time (sec)`.
3. Compute the ROI-by-ROI correlation matrix.

The graph encoding is:

```text
Nodes = 16 parcels/networks
Edges = ROI-to-ROI correlations
```

Start with weighted positive edges:

```text
negative correlations set to 0
diagonal set to 0
```

## 5. Community Detection

Run community detection on each valid window-level graph.

Candidate methods:

- Louvain
- Leiden

Each valid window gives one community assignment for every ROI.

## 6. Flexibility

Compute flexibility as the community switch rate across valid windows.

For each ROI:

```text
flexibility = number of community switches / number of valid transitions
```

Example:

```text
Community sequence: A A B B A
Switches: 2
Transitions: 4
Flexibility: 0.5
```

Summarize flexibility:

- per ROI
- per scan
- per subject/group
- EXP vs SHAM
- DTA vs PV
- awake vs anesthetized

## 7. Sensitivity Analysis

Repeat key results using:

```text
20% scan-level censoring
20% window-level censoring
```

This checks whether the main findings depend strongly on the 25% censoring threshold.
