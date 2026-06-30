1. PV baseline, EXP vs SHAM → expect NO difference. Before CNO is on board, the DREADD isn't activated, so EXP and SHAM should look the same. If this is significant, that's a red flag — surgery confound, leaky DREADD, or group-assignment bias, not a CNO effect.

2. PV CNO, EXP vs SHAM → expect a difference. This is the phase where silencing is actually active. This is what Finding 4 tested directly (only SUB hit p=0.008 uncorrected, didn't survive FDR).

3. Within EXP, baseline vs CNO → expect a drop (DREADD activates only with CNO).
Within SHAM, baseline vs CNO → expect no change (no functional DREADD; CNO alone shouldn't do anything) — though some shared drift from anesthesia depth/time is plausible, which is exactly what DiD subtracts out.

4. DiD (Δ_EXP vs Δ_SHAM) → the cleanest test, expect this to be significant if anything is real, since it removes shared baseline→CNO drift. This is what was found borderline for TH (p=0.050) and SUB (p=0.060), not surviving 16-way FDR.

5. DTA, EXP vs SHAM → expect EXP to show chronically reduced flexibility, since the lesion is permanent and present from the first scan (no baseline available for a within-animal comparison here — it's structural, so a pure between-group test is the only option). Finding 3 found EXP < SHAM in 14/16 ROIs, consistent direction but weak (p=0.06–0.9).

6. Awake vs anesthetized → expect awake cohorts to show a clearer/larger effect, since anesthesia is known to suppress dynamic FC reconfiguration generally. This prediction hasn't actually been checked yet — Bf_DTA_awk and Bf_PV_awk are flagged in the log as "not yet checked with this method" and are the natural next place to look if you want the best shot at a clean result.
