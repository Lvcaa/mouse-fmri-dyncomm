## Docker Setup

Build the Docker image from the repository root:

```bash
docker compose build
```

The first build may take a few minutes while dependencies (igraph, leidenalg)
are installed for Python 3.12.13.

Start an interactive shell inside a new container:

```bash
docker compose run --rm pipeline bash
```

The repository is mounted at `/app`, which is also the working directory inside
the container. Run the analysis scripts in order:

```bash
python scripts/02_make_windows.py
python scripts/03_compute_window_connectivity.py
python scripts/04_run_community_detection.py
python scripts/05_compute_flexibilty.py
```

Type `exit` to leave the container. Generated files remain available on the host
because the repository is mounted into the container.

To run one script directly without entering an interactive shell:

```bash
docker compose run --rm pipeline python scripts/04_run_community_detection.py
```

`docker compose exec pipeline bash` is also available, but only when the
`pipeline` service is already running.

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
│   ├── 04_run_community_detection.py      # Leiden community detection per window
│   ├── 05_compute_flexibilty.py          # ROI-level flexibility across windows
│   ├── censor_check/                # Censoring diagnostics
│   ├── window_summary.csv           # Window inventory: keep/discard flags per scan
│   ├── window_connectivity/         # Output of script 03, nested by dataset/preproc/subject
│   │   └── <dataset>/<preproc_pipeline>/sub-<subject>/
│   │       └── <scan_id>_window_0000.csv
│   └── window_communities/          # Output of script 04, nested by dataset/preproc/subject
│       └── <dataset>/<preproc_pipeline>/sub-<subject>/
│           └── <scan_id>.csv        # Columns: Node, flexibility, gamma, interslice_weight, n_runs, n_windows
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

2. **`03_compute_window_connectivity.py`** — For each kept window, removes censored rows, computes the 16×16 ROI Pearson correlation matrix, and zeroes the diagonal. Negative correlations are retained in the saved matrix but ignored later by the positive-edge graph builder. Outputs one CSV per window under `window_connectivity/<dataset>/<preproc_pipeline>/<subject>/`.

3. **`04_run_community_detection.py`** — Builds a weighted undirected graph from each correlation matrix and runs temporal Leiden community detection. Mean per-ROI flexibility is saved to `window_communities/<dataset>/<preproc_pipeline>/<subject>/<scan_id>.csv`. See [`docs/04_community_detection.md`](docs/04_community_detection.md) for a full walkthrough of the execution flow, parameters, and output format.

4. **`05_compute_flexibilty.py`** — Aggregates per-scan flexibility outputs into `scripts/flexibility/flexibility_scores.csv`, preserving dataset, preprocessing, cohort, state, subject, condition, and phase metadata.

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

For the Docker workflow, see [Docker Setup](#docker-setup) at the top of this
README.
