# To-Do List

## Data Quality & Censoring

- [ ] Check how many mice were removed due to censoring
- [ ] For each mouse, record how many windows were removed and how many were retained

| Mouse ID | Windows Retained |
|----------|-----------------|
| ...      | ...             |

---

## Community Detection

### Louvain Algorithm (Non-Deterministic)
- [ ] Run Louvain 100 times per mouse and use the average as the final flexibility value

### Parameters to Use (Current Defaults)
| Parameter        | Value |
|------------------|-------|
| Gamma (γ)        | 1     |
| Interslice (ω)   | 0.5   |

> **Reference (PNAS):** Lower γ values lead to increased network switching.
> Node switching rates: 1.61% at γ=0.5 · 1.55% at γ=0.75 · 1.48% at γ=1 (constant ω=1).
> 
> Source: https://www.pnas.org/doi/10.1073/pnas.1814785115#sec-3

### Parameters to Explore Later
- [ ] Gamma (γ)
- [ ] Interslice coupling (ω)
- [ ] Time window width — try **45** and **60** (in addition to the current default)

---

## Technical Notes

### Temporal Community Detection — Membership Vectors
The `find_partition_temporal()` function returns **membership vectors** for each time slice, not actual partition objects. Example usage:

```python
membership, improvement = louvain.find_partition_temporal(
    [G_1, G_2, G_3],
    louvain.CPMVertexPartition,
    interslice_weight=0.1,
    resolution_parameter=gamma
)
```

> **Open question:** What are the implications of working with membership vectors rather than actual partitions?

---
