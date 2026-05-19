# Parcellated timeseries CSV — format and naming

This document describes the CSV files under `for_ludo/`. It matches `for_ludo/README.txt`, `for_ludo/extract_parcellated_timeseries.py`, and the shipped data layout.

## File layout (directories)

```
for_ludo/
  <dataset>/                    # Bf_PV_awk | Bf_PV_anes | Bf_DTA_awk | Bf_DTA_anes
    <preproc_pipeline>/         # e.g. FD_cut30frames_bandpass0.01-0.1_cut30edges_mot6_CSF_smooth6
      sub-*.csv
```

- **`<dataset>`** — Experimental cohort and state (awake `awk` vs anesthetized `anes`); see `for_ludo/README.txt`.
- **`<preproc_pipeline>`** — Human-readable slug for the RABIES confound-correction output: FD censoring, bandpass 0.01–0.1 Hz, edge trimming, motion regressors (`mot6` = 6 for anesthetized, `mot24` for awake), CSF regression, 0.6 mm smoothing (`smooth6`).

## CSV table format

- **Encoding**: plain CSV with header row; `index=False` (no row index column).
- **Delimiter**: comma.
- **First column**: `Time (sec)` — float seconds on the TR grid (**TR = 1.0 s** in the extraction script).
- **Remaining columns**: one float column per **network / parcel aggregate** (mean signal over voxels in that label from the N16 atlas). Column names and order:

  `Time (sec)`, `DMNa`, `DMNp`, `SAL`, `OLF`, `STR`, `AUD`, `VIS`, `TH`, `MOp`, `SSp`, `SSs`, `HCa`, `SUB`, `CTXsp`, `BF`, `HY`

- **Censoring**: For censored frames, **parcel cells are empty** (missing fields in the CSV, not the string `"nan"`). `Time (sec)` is still present for those rows. Example: leading rows can be all-empty parcel fields until non-censored volumes begin.

- **Semantics**: Values are confound-corrected, bandpassed, smoothed parcel means (see README for full preprocessing).

## Filename patterns

Names are derived from the source `*cleaned.nii.gz` filename in RABIES by replacing the suffix (see `export_csv` and the `replace('cleaned.nii.gz', ...)` calls in `extract_parcellated_timeseries.py`).

### PV datasets (`Bf_PV_awk`, `Bf_PV_anes`)

Two CSVs per run (split at **22 minutes** after injection timing, with the script’s 30 s / 30-frame offset applied to the cutoff — see script comments).

Pattern:

```text
sub-<subject_id>_<EXP|SHAM>_bold_<baseline|CNO>_parcellated.csv
```

Examples:

- `sub-ag240729a_EXP_bold_CNO_parcellated.csv`
- `sub-ag240808c_SHAM_bold_baseline_parcellated.csv`

- **`EXP` / `SHAM`** — experimental vs sham group (README).
- **`baseline`** — pre-CNO segment; **`CNO`** — post-injection segment.

### DTA datasets (`Bf_DTA_awk`, `Bf_DTA_anes`)

One CSV per run (no baseline/CNO split in the filename).

Pattern:

```text
sub-<subject_id>_<EXP|SHAM>_bold_parcellated.csv
```

Example:

- `sub-ag231113c_SHAM_bold_parcellated.csv`

### Filename quirks

A few files may contain **double underscores** (e.g. `SHAM__bold`) from upstream naming; treat them as the same BIDS-like token sequence when parsing.

## Related files

| File | Role |
|------|------|
| `for_ludo/README.txt` | Dataset descriptions and preprocessing summary |
| `for_ludo/parcellation.csv` | `label ID`, `Network`, `Allen parcels` for each column region |
| `for_ludo/extract_parcellated_timeseries.py` | Authoritative logic for columns, time axis, splits, and output names |
