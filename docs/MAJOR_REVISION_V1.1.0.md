# Major revision v1.1.0

This release accompanies the major revision of manuscript `cleantechnol-4593298`.

Key changes:
- corrected IEA-PVPS reference reconstruction: `E_ref = 976 × 30 = 29,280 kWh/kWp`, `B_ref = 1,048.224 kg CO2-eq/kWp`;
- propagated corrected absolute GWP values throughout the LCA workflow;
- added end-of-service threshold and linear/compound degradation-trajectory sensitivity;
- added P90 heatwave-stress attribution;
- audited spatial provenance and quantified grid-cell/bilinear/25-cell thermal-yield sensitivity;
- added downstream temporal-aggregation propagation and GWP mechanism decomposition;
- retained the three-GCM set as a limited structural sample, not a probabilistic CMIP6 ensemble.

The compact outputs under `reference_results/major_revision/` are the values used in the revised manuscript and response to reviewers.
