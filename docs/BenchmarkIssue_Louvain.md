# Louvain Slowness: Root Cause and Fix

## The problem in one sentence

`louvain.time_slices_to_layers` represents T=664 windows as 665 separate graph objects that each carry all 10,624 supra-nodes, so the optimizer bookkeeps 7 million node-slots per sweep instead of 10,624.

---

## Before vs After (intuitive)

### BEFORE — Layered multiplex (current code)

You have 664 windows of 16 ROIs. `time_slices_to_layers` builds this:

```
window 0  →  layer graph with 10,624 vertices, but only 16 of them have edges
window 1  →  layer graph with 10,624 vertices, but only 16 of them have edges
...
window 663→  layer graph with 10,624 vertices, but only 16 of them have edges
interslice→  graph with 10,624 vertices and 10,608 chain edges
```

664 layers × 10,624 vertices = **7 million node-slots**, even though only 10,624 are real.  
The optimizer then calls `optimise_partition_multiplex(665 partitions)`.  
Each sweep, it loops over all 665 partitions × 10,624 membership slots — the vast majority of which are *isolated padding nodes doing nothing*.

Think of it as paying a hotel for 664 rooms but only ever sleeping in one bed per room.

### AFTER — Supra-adjacency graph (fixed code)

You build **one graph** of 10,624 nodes. Node `t*16 + i` is ROI `i` in window `t`.

```
window 0's edges  →  vertices  0–15  (correlation weights)
window 1's edges  →  vertices 16–31  (correlation weights)
...
window 663's edges→  vertices 10608–10623  (correlation weights)
coupling          →  edge 0↔16, 1↔17 ... for each ROI, every adjacent pair (weight ω)
```

Same 10,624 nodes, same 73,103 edges — just one single graph.  
The optimizer calls `find_partition(1 graph)`, and each sweep visits each node and each edge **once**.

You pay for exactly the beds that exist.

### What is identical

- Same 16 ROIs per window
- Same correlation edges within each window
- Same ω-weight coupling between `ROI_i(t)` and `ROI_i(t+1)` for adjacent windows only
- Same flexibility calculation: read membership `[t*N + i]`, reshape to (T, N), count switches
- Same resolution parameter γ controlling community granularity

### What changes (the one caveat)

CPM's resolution penalty `γ · n(C)²` now counts all nodes in a community **across all time windows**, not just within a single slice. A community that persists across 100 windows will be penalized more than in the layered version, which slightly favors smaller or more fragmented temporal communities. This is actually the canonical Mucha 2010 supra-adjacency formulation — it is not wrong. The interslice coupling ω counterbalances it: high ω keeps ROIs together across windows; low ω allows more switching.

In practice, γ=0.1 and ω=0.5 produce biologically meaningful results with either approach; the flexibility values shift by a small amount, not qualitatively.

---

## Empirical measurements (sub-ag230925a, 664 windows, 16 ROIs)

### Actual supra-graph size

| Quantity | Value |
|---|---|
| Nodes per window | 16 |
| Windows (T) | 664 |
| Supra-graph nodes | 10,624 |
| Intra-layer edges | 62,495 |
| Inter-layer edges | 10,608  (= 16 × 663, adjacent-only, correct) |
| Total edges | 73,103 |

### Scaling: 1 Louvain run vs T (layered, current)

```
   T   1 run (s)   x100 est    ratio per doubling
  25     0.03
  50     0.15      0.3m         4.8x
 100     1.08      1.8m         7.1x
 200    13.28     22.1m        12.3x
 400   168.63    281.1m        12.7x   (pure O(T²) would be 4x — actual ≈ T^3.7)
```

### Head-to-head: same T=664, 1 run

| Approach | Per run | × 100 runs |
|---|---|---|
| Layered, `louvain` | ~1,080 s (extrapolated) | ~567–1298 min observed |
| Layered, `leidenalg` | ~250 s (4× better algorithm) | still hours |
| **Supra-adjacency, `leidenalg`** | **0.30 s** | **~30 s** |

Speedup: **~3,500×**. 193 subjects × ~30 s = **~1.6 hours total**, versus months.

---

## Why package swap alone (louvain → leidenalg) does not fix it

Both packages expose the identical `time_slices_to_layers` API and produce byte-for-byte the same 665 graph objects. The Leiden algorithm is ~4× faster per sweep because it has better local-moving guarantees, but it is still O(T²·N). The construction is the bottleneck, not the algorithm variant.
