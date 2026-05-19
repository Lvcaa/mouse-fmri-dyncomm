# Progetto Gozzi — Dynamic Functional Connectivity Analysis

This repository implements a sliding-window community detection pipeline on resting-state fMRI data from mouse brain, studying basal forebrain (BF) neuromodulation and its effect on functional network flexibility.

## Experimental Design

Four cohorts are analysed:

| Dataset | Intervention | State |
|---|---|---|
| `Bf_DTA_awk` | BF lesion via DTA | Awake |
| `Bf_DTA_anes` | BF lesion via DTA | Anesthetized |
| `Bf_PV_awk` | BF DREADDs on PV neurons (CNO) | Awake |
| `Bf_PV_anes` | BF DREADDs on PV neurons (CNO) | Anesthetized |

Within each cohort, files labelled `EXP` are the experimental group and `SHAM` are controls.

## Repository Structure

```
.
├── for_ludo/                        # Raw input data (parcellated timeseries)
│   ├── Bf_DTA_awk/                  # DTA cohort, awake
│   ├── Bf_DTA_anes/                 # DTA cohort, anesthetized
│   ├── Bf_PV_awk/                   # PV cohort, awake
│   ├── Bf_PV_anes/                  # PV cohort, anesthetized
│   ├── extract_parcellated_timeseries.py
│   ├── final_atlas_N16_rabies_space_dta.nii.gz   # N16 atlas (DTA space)
│   ├── final_atlas_N16_rabies_space_pv.nii.gz    # N16 atlas (PV space)
│   ├── parcellation.csv             # Label ID, network name, Allen parcel composition
│   └── README.txt                   # Dataset and preprocessing description
│
├── scripts/                         # Analysis pipeline (run in order)
│   ├── 02_make_windows.py           # Sliding windows (35 TR, step 3) + censoring filter
│   ├── 03_compute_window_connectivity.py  # Per-window Pearson correlation matrix
│   ├── 04_run_community_detection.py      # Louvain community detection per window
│   ├── 05_compute_flexibilty.py          # ROI-level flexibility across windows
│   ├── censor_check/                # Censoring diagnostics
│   ├── window_summary.csv           # Window inventory: keep/discard flags per scan
│   ├── window_connectivity/         # Output of script 03 — one correlation matrix CSV per window
│   └── window_communities/          # Output of script 04 — one CSV per scan, organised by subject
│       └── sub-<subject>/
│           └── <scan_id>.csv        # Columns: window_id, Node, Community
│
├── reference/
│   └── CSV_FORMAT.md                # Detailed spec for the parcellated timeseries CSV format
│
├── community_detection_plan.md      # Analysis design document
├── requirements.txt                 # Python dependencies
├── Dockerfile
└── docker-compose.yml
```

## Pipeline Overview

1. **`02_make_windows.py`** — Slides a 35-TR window (step = 3 TR) over each scan. Windows with ≥9 censored TRs (>25% of 35) are flagged and excluded. Results are written to `window_summary.csv`.

2. **`03_compute_window_connectivity.py`** — For each kept window, removes censored rows, computes the 16×16 ROI Pearson correlation matrix, clips negative values to zero, and zeroes the diagonal. Outputs one CSV per window to `window_connectivity/`.

3. **`04_run_community_detection.py`** — Builds a weighted undirected graph from each correlation matrix and runs Louvain community detection (seed=123). Results are saved to `window_communities/<subject>/<scan_id>.csv` with columns `window_id, Node, Community`.

4. **`05_compute_flexibilty.py`** — Computes per-ROI flexibility (community switch rate across consecutive valid windows) and summarises results per scan, condition, and group.

## Data Format

Input timeseries CSVs have one row per TR and 17 columns:

```
Time (sec), DMNa, DMNp, SAL, OLF, STR, AUD, VIS, TH, MOp, SSp, SSs, HCa, SUB, CTXsp, BF, HY
```

Censored frames have empty parcel cells (not NaN strings). See `reference/CSV_FORMAT.md` for the full spec.

## Running the Pipeline

```bash
pip install -r requirements.txt

python scripts/02_make_windows.py
python scripts/03_compute_window_connectivity.py
python scripts/04_run_community_detection.py
python scripts/05_compute_flexibilty.py
```

Or with Docker:

```bash
docker-compose up
```
