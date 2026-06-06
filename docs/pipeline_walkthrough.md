# Pipeline walkthrough — CSV to flexibility score

Full trace of `scripts/04_run_community_detection.py` from reading a raw connectivity CSV through to the final flexibility value for each ROI.

---

## Step 1 — Read a single window CSV (`read_window`, line 54)

Each window is stored as a 16×16 correlation matrix on disk.

```python
df = pd.read_csv(connectivity_path, index_col=0)
for col in df.columns:
    df.loc[col, col] = 0   # zero diagonal: no self-edges
```

```
# df.shape      → (16, 16)
# df.columns    → ['DMNa','DMNp','SAL','OLF','STR','AUD','VIS',
#                   'TH','MOp','SSp','SSs','HCa','SUB','CTXsp','BF','HY']
# df.iloc[0, 1] → 0.545   (DMNa–DMNp Pearson r)
# df.iloc[0, 0] → 0.0     (diagonal, zeroed)
```

---

## Step 2 — Convert to a sparse graph (`build_igraph`, line 64)

The 16×16 matrix becomes a sparse igraph object. Only positive correlations become edges; the upper triangle is used so each pair appears once.

```python
corr_array = df.to_numpy(dtype=float)
row_indices, col_indices = np.triu_indices(len(roi_names), k=1)  # 120 candidate pairs
edge_weights = corr_array[row_indices, col_indices]
positive_mask = edge_weights > 0

graph.add_edges(zip(row_indices[positive_mask], col_indices[positive_mask]))
graph.es["weight"] = edge_weights[positive_mask].tolist()
```

```
# graph.vcount()         → 16      (one vertex per ROI)
# graph.ecount()         → ~94     (positive correlations only, varies per window)
# graph.vs["name"]       → ['DMNa', 'DMNp', ..., 'HY']
# graph.es["weight"][:3] → [0.545, 0.182, 0.408]
```

This runs **664 times** — once per window.

---

## Step 3 — Load all windows (step 1 in `run_community_detection`, line 193)

```python
for _, (window_id, path) in enumerate(sorted_windows, start=1):
    df = read_window(path)
    graphs.append(build_igraph(df))
```

```
# len(graphs)            → 664
# graphs[0].vcount()     → 16
# graphs[0].ecount()     → ~94
# graphs[663].ecount()   → ~91     (different window, different edge count)
```

---

## Step 4 — Build the supra-adjacency graph (step 2, line 209)

All 664 windows are packed into **one graph**. ROI `i` in window `t` lives at vertex `t * 16 + i`.

**Intra-window edges** — each window's correlation edges are offset into its block:

```python
for window_idx, window_graph in enumerate(graphs):
    vertex_offset = window_idx * n_nodes      # window 5 → offset 80
    for edge in window_graph.es:
        intra_sources.append(vertex_offset + edge.source)
        intra_targets.append(vertex_offset + edge.target)
        intra_weights.append(edge["weight"])
```

**Interslice chain edges** — each ROI is connected to itself in the adjacent window:

```python
window_indices = np.repeat(np.arange(n_transitions), n_nodes)  # [0,0..0, 1,1..1, ...]
roi_indices    = np.tile(np.arange(n_nodes), n_transitions)    # [0,1..15, 0,1..15, ...]
interslice_src = (window_indices * n_nodes + roi_indices)       # ROI i at window t
interslice_tgt = ((window_indices + 1) * n_nodes + roi_indices) # ROI i at window t+1
```

```
# supra.vcount()     → 10,624   (664 windows × 16 ROIs)
# supra.ecount()     → ~73,000  (62,495 intra + 10,608 interslice)
#
# Vertex layout:
#   0–15   → window 0  (ROIs 0–15)
#   16–31  → window 1  (ROIs 0–15)
#   ...
#   10608–10623 → window 663
#
# Example: vertex 80 = ROI 0 (DMNa) in window 5
#   interslice edges on DMNa: 0↔16↔32↔...↔10608  (weight ω=0.5 each)
```

---

## Step 5 — Run Leiden (`_leiden_single_run`, line 126)

A single `find_partition` call on the full supra-graph. Called 100 times with different seeds.

```python
partition = la.find_partition(
    supra_graph,
    la.CPMVertexPartition,
    weights="weight",
    resolution_parameter=gamma,  # γ=0.1
    seed=seed,
)
```

```
# len(partition.membership)   → 10,624   (one label per supra-vertex)
# partition.membership[:5]    → [0, 0, 1, 0, 2]   (example community labels)
# partition.membership[10608] → 0   (DMNa window 663, same or different community)
```

Leiden's local-moving phase visits each vertex and moves it to whichever neighbouring community maximises CPM quality. Intra-window edges cluster correlated ROIs together; interslice edges penalise a ROI for landing in a different community than its copy one window earlier.

---

## Step 6 — Extract per-ROI community labels and compute flexibility (line 151)

The flat membership vector is reshaped into a (T, N) matrix, one row per window.

```python
membership_matrix = np.array(partition.membership, dtype=np.int32).reshape(n_windows, n_nodes)
```

```
# membership_matrix.shape   → (664, 16)
# membership_matrix[0]      → [0, 0, 1, 0, 2, 1, 0, 3, 0, 0, 1, 2, 2, 1, 3, 0]
# membership_matrix[1]      → [0, 0, 1, 0, 2, 1, 0, 3, 0, 0, 1, 2, 2, 1, 3, 0]  (stable)
# membership_matrix[200]    → [1, 1, 0, 1, 0, 2, 1, 0, 1, 1, 0, 3, 3, 0, 0, 1]  (switched)
```

Switches are counted across adjacent rows, then normalised:

```python
switches = np.sum(membership_matrix[1:] != membership_matrix[:-1], axis=0)  # (16,)
return (switches / n_transitions).tolist()
```

```
# switches      → [591, 631, 645, 643, 655, ...]    (raw switch counts per ROI)
# flexibility   → [0.89, 0.95, 0.97, ...]           (divided by 663 transitions)
```

---

## Step 7 — Average over 100 runs (back in `run_community_detection`, line 263)

```python
flexibility_sum = [sum(run[i] for run in all_runs) for i in range(n_nodes)]
"flexibility": [s / len(all_runs) for s in flexibility_sum]
```

```
# Final output per ROI (example):
#   DMNa   → 0.897
#   DMNp   → 0.953
#   SAL    → 0.972
#   BF     → 0.943   ← low = temporally stable community membership
#   CTXsp  → 0.987   ← high = frequently switches community
```

---

## Data shape summary

| Stage | Object | Shape / size |
|---|---|---|
| Raw CSV | DataFrame | 16 × 16 |
| Per-window graph | igraph.Graph | 16 nodes, ~94 edges |
| All windows loaded | list of graphs | 664 graphs |
| Supra-graph | igraph.Graph | 10,624 nodes, ~73,000 edges |
| Leiden output | membership list | 10,624 ints |
| Reshaped | np.ndarray | (664, 16) |
| Per-run flexibility | list of floats | 16 values in [0, 1] |
| Final output | DataFrame | 16 rows × 7 columns |
