# Script 04 — Community Detection

**File:** `scripts/04_run_community_detection.py`

Runs temporal Leiden community detection across all sliding-window correlation matrices and produces a per-ROI flexibility score for each scan.

---

## Execution flow

When you run the script, functions execute in this order:

### 1. `parse_args()`
Reads command-line flags (`--n-runs`, `--scan-workers`, `--gamma`, etc.) and passes them to `run_all`. Defaults are defined as constants at the top of the file.

### 2. `run_all()`
The top-level coordinator. It:
- Finds all connectivity CSV files on disk under `window_connectivity/`
- Groups them by scan — all windows belonging to the same recording go into one group
- Prints the header banner with parameters
- Launches one `_run_scan_group` call per scan, either sequentially or in parallel depending on `scan_workers`
- Prints the footer with total elapsed time when everything finishes

### 3. `_run_scan_group()` *(once per scan)*
Handles one scan end-to-end. It:
- Prints the `[1/12] scan_name` header line
- Calls `run_community_detection` to do the actual computation
- Saves the result DataFrame to a CSV file under `outputs/community_detection/leiden_flex_<n_runs>_<timestamp>/`
- Prints the `saved →` and `total` lines

### 4. `run_community_detection()` *(once per scan)*
The main pipeline for a single scan. Runs three steps in sequence:

**Step 1 — Load windows**
Calls `read_window` and `build_igraph` for each of the T windows, building a list of T igraph graphs (16 nodes, ~94 edges each). Prints `loading  664 windows  0.8s`.

**Step 2 — Build supra-adjacency graph**
Assembles one igraph Graph of T×N = 10,624 vertices. Each window occupies a contiguous block of N vertices; intra-window correlation edges are offset into that block, and interslice chain edges connect each ROI to itself in the adjacent window with weight ω. The result is one graph with ~73,000 edges. Prints `building  supra-graph  0.05s`.

**Step 3 — Run Leiden**
Runs `leidenalg.find_partition` N times (either sequentially or via `ProcessPoolExecutor`), collects all results, and averages flexibility across runs. Prints `running  100 × Leiden  36s`.

### 5. `read_window()` *(T times, inside step 1)*
Loads one CSV file into a pandas DataFrame and zeroes the diagonal (self-connections).

### 6. `build_igraph()` *(T times, inside step 1)*
Converts one correlation matrix into a weighted igraph Graph. Uses numpy to extract the upper triangle in one vectorised operation, drops negative correlations, and adds the remaining pairs as weighted edges.

### 7. `_init_worker()` *(once per worker process)*
Stores the supra-graph and all shared metadata into module-level globals. With `fork` on Linux the graph is copy-on-write inherited — no data is actually copied to each worker.

### 8. `_leiden_single_run()` *(N_RUNS times, in parallel if run_workers > 1)*
Runs one complete Leiden optimisation. Reads the supra-graph from worker globals, calls `find_partition`, reshapes the flat 10,624-length membership vector to (T, N), and computes per-node flexibility using a vectorised numpy comparison across all T windows. Returns a list of N floats (one flexibility value per ROI).

### 9. Back in `run_community_detection`
Averages the N_RUNS flexibility lists across runs, packages everything into a DataFrame, and returns it to `_run_scan_group`, which saves it to disk.

---

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `--gamma` | `0.1` | CPM resolution parameter γ. Controls community granularity — lower values produce larger communities. γ=1 forces all nodes into singletons with Pearson correlations in [0,1]. |
| `--omega` | `0.5` | Interslice coupling ω. Penalises a node for switching communities between consecutive windows. Higher → more temporally stable partitions. |
| `--n-runs` | `100` | Number of independent Leiden runs per scan. Flexibility is averaged across all runs to reduce dependence on the random initialisation. |
| `--scan-workers` | `1` | Number of scans to process in parallel. |
| `--run-workers` | `1` | Number of parallel Leiden runs per scan. |

---

## Output

One CSV per scan saved to `outputs/community_detection/leiden_flex_<n_runs>_<timestamp>/<dataset>/<preproc>/<subject>/<scan_id>.csv`:

| Column | Description |
|---|---|
| `Node` | ROI name |
| `flexibility` | Mean fraction of consecutive-window pairs where the node changed community (0 = never switches, 1 = switches every window) |
| `gamma` | γ used for this run |
| `interslice_weight` | ω used for this run |
| `n_runs` | Number of Leiden runs averaged |
| `n_windows` | Number of windows in the scan |
| `last_run` | Timestamp of when the CSV was written |

---

## Example terminal output

```
════════════════════════════════════════════════════════════════
  Temporal Leiden  |  193 scans  |  γ=0.1  ω=0.5  |  100 runs
  scan_workers=1  run_workers=1
════════════════════════════════════════════════════════════════

[1/193] sub-ag230912d_SHAM_bold_parcellated  [Bf_DTA_anes/...]  664 windows
  loading    664 windows                                  0.8s
  building   supra-graph                                  0.05s
  running    100 × Leiden  (1 workers)                    36s
  saved      → outputs/community_detection/leiden_flex_<n_runs>_<timestamp>/.../sub-ag230912d_SHAM_bold_parcellated.csv
  total      37s

════════════════════════════════════════════════════════════════
  All done — 193 scans in ~2h
════════════════════════════════════════════════════════════════
```

> When `scan_workers > 1`, output lines from parallel scans will interleave. The `[i/N]` prefix on each scan header keeps them identifiable in logs.

---

## Related docs

- [pipeline_walkthrough.md](pipeline_walkthrough.md) — step-by-step trace with example values at each stage
- [pipeline_diagnostics_log.md](pipeline_diagnostics_log.md) — diagnosis of the original Louvain slowness and the supra-adjacency fix (2026-06-06 entry), plus other pipeline findings
- [community_detection_plan.md](community_detection_plan.md) — windowing and censoring decisions
