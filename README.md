# Climate-Driven PV Heatwave LCA — Stuttgart

Reproducible analysis code for the Stuttgart case study linking future climate and explicitly characterized heatwaves to photovoltaic module thermal exposure, temperature-only Arrhenius stress, scenario-conditioned modeled service life, electricity generation, module replacement, and fixed-reference life-cycle GWP per kWh.

**Repository version: 1.0.0 — First public reproducible release**

This release includes extended validation and sensitivity analyses: hourly Arrhenius integration benchmarking, temporal-coincidence testing, hourly energy-index validation, heatwave/non-heatwave stress decomposition, spatial heatwave sensitivity, residual-service-life replacement accounting as a co-primary case, and factorial structural uncertainty propagation.

## End-to-end study chain

1. Check/download NASA NEX-GDDP-CMIP6 inputs.
2. Retrieve the Stuttgart PVGIS hourly reference.
3. Inventory/QC raw datasets.
4. Clean and merge daily `tasmax`, `rsds`, and `sfcWind`.
5. Detect primary heatwaves (`tasmax >= 30 °C` for >=3 consecutive days).
6. Estimate a PVGIS-informed Faiman daily-maximum module-temperature proxy.
7. Estimate relative temperature-driven Arrhenius stress and scenario-conditioned modeled service life.
8. Estimate climate-adjusted annual and lifetime electricity generation.
9. Calculate fixed-reference GWP/kWh with climate-dependent module replacement.
10. Run threshold, DWD historical, and replacement-accounting sensitivity analyses.
11. Benchmark daily-max Arrhenius stress and the daily energy index against hourly PVGIS reference calculations.
12. Decompose modeled thermal-stress changes into heatwave-day and non-heatwave-day contributions.
13. Compare Stuttgart grid-cell, bilinear-point, and 25-cell regional-mean heatwave metrics.
14. Propagate structural uncertainty jointly across GCM, thermal treatment, durability parameters, yield treatment, and replacement accounting.

## Climate ensemble

- MPI-ESM1-2-HR
- MRI-ESM2-0
- NorESM2-MM

Historical: 1991–2014.  
Future: SSP2-4.5 and SSP5-8.5 for 2041–2060 and 2081–2100.

The three-model set is a selected ensemble. It is **not** presented as the full CMIP6 uncertainty distribution.

## Spatial treatment

The raw Stuttgart `tasmax` subset is a 5 × 5 NEX-GDDP grid (25 cells). Audit of the archived processed outputs showed that the primary heatwave results correspond to the Stuttgart-containing grid cell centered at approximately **48.875° N, 9.125° E**. The primary cleaning workflow therefore makes that spatial treatment explicit.

The spatial sensitivity analysis compares:

- Stuttgart grid cell — primary heatwave series;
- bilinear interpolation at 48.7758° N, 9.1829° E;
- 25-cell regional mean.

The direction and scenario ranking of the late-century heatwave increase are preserved across these extraction methods, while absolute threshold-exceedance counts differ.

## Repository structure

```text
.
├── scripts/              # numbered executable analysis stages (00–14)
├── docs/                 # method parameters, maps, validation notes
├── reference_results/    # compact successful-run summaries
│   └── extended_validation/ # extended validation reference outputs
├── data/                 # README only; raw data are not distributed
├── processed/            # README only; generated outputs are not distributed
├── legacy/               # earliest downloader/checker archive preserved for provenance
├── CITATION.cff
├── VERSION
├── requirements.txt
└── .gitignore
```

## Scripts

| Script | Purpose |
|---|---|
| `00_check_nex_availability.py` | Check NASA catalog availability for the selected models. |
| `01_download_nex_gddp_complete.py` | Download required NEX-GDDP-CMIP6 variables/periods. |
| `02_download_pvgis_baseline.py` | Download the Stuttgart PVGIS reference. |
| `03_inventory_check.py` | Raw-data inventory/completeness QC. |
| `04_clean_merge_climate.py` | Build `MASTER_CLIMATE_STUTTGART.csv`; uses Stuttgart grid-cell `tasmax` as primary. |
| `05_heatwave_analysis.py` | Primary heatwave events and summaries. |
| `06_thermal_analysis.py` | Faiman daily-max proxy and basic PVGIS aggregation benchmark. |
| `07_degradation_service_life.py` | Relative Arrhenius degradation/service life and durability sensitivity. |
| `08_lifetime_generation.py` | Annual yield and lifetime/30-year generation. |
| `09_lca_gwp.py` | Fixed-reference GWP with integer and residual-service-life accounting outputs. |
| `10_solar_sensitivity_validation.py` | P90 heatwave sensitivity, DWD validation, and replacement-allocation sensitivity. |
| `11_hourly_temporal_validation.py` | Hourly Arrhenius, temporal-coincidence, and energy-index validation/calibration. |
| `12_heatwave_stress_decomposition.py` | Heatwave vs non-heatwave modeled stress decomposition and counterfactual. |
| `13_spatial_heatwave_sensitivity.py` | Grid-cell vs bilinear vs 25-cell regional heatwave sensitivity. |
| `14_joint_uncertainty.py` | Factorial structural uncertainty envelope. |

## Baseline execution

```bash
python scripts/03_inventory_check.py --data-root data --out processed/00_Inventory_Check
python scripts/04_clean_merge_climate.py --data-root data --out processed/01_Climate_Clean
python scripts/05_heatwave_analysis.py --master processed/01_Climate_Clean/MASTER_CLIMATE_STUTTGART.csv --out processed/02_Heatwave_Analysis
python scripts/06_thermal_analysis.py --master processed/01_Climate_Clean/MASTER_CLIMATE_STUTTGART.csv --pvgis data/PVGIS_Stuttgart_PV_Baseline/PVGIS_Stuttgart_1kWp_CrystSi_Tilt30_South_2005_2023.csv --out processed/03_PV_Thermal_Model
python scripts/07_degradation_service_life.py --thermal processed/03_PV_Thermal_Model/THERMAL_DAILY_STUTTGART.csv --out processed/04_Degradation_Service_Life
python scripts/08_lifetime_generation.py --thermal processed/03_PV_Thermal_Model/THERMAL_DAILY_STUTTGART.csv --degradation processed/04_Degradation_Service_Life/DEGRADATION_SERVICE_LIFE_PERIOD_SUMMARY_BASE.csv --pvgis data/PVGIS_Stuttgart_PV_Baseline/PVGIS_Stuttgart_1kWp_CrystSi_Tilt30_South_2005_2023.csv --out processed/05_Lifetime_Electricity_Generation
python scripts/09_lca_gwp.py --lifetime processed/05_Lifetime_Electricity_Generation/LIFETIME_GENERATION_PERIOD_SUMMARY.csv --out processed/06_LCA_GWP
```

## Extended validation and sensitivity execution

After the baseline thermal file has been generated:

```bash
python scripts/11_hourly_temporal_validation.py \
  --pvgis data/PVGIS_Stuttgart_PV_Baseline/PVGIS_Stuttgart_1kWp_CrystSi_Tilt30_South_2005_2023.csv \
  --thermal processed/03_PV_Thermal_Model/THERMAL_DAILY_STUTTGART.csv \
  --out processed/08_Extended_Validation

python scripts/12_heatwave_stress_decomposition.py \
  --daily processed/08_Extended_Validation/HOURLY_CALIBRATED_DAILY.csv \
  --out processed/08_Extended_Validation

python scripts/13_spatial_heatwave_sensitivity.py \
  --tasmax-root data/MIP6_Stuttgart_Heatwave_Tasmax \
  --out processed/08_Extended_Validation/spatial

python scripts/14_joint_uncertainty.py \
  --pvgis data/PVGIS_Stuttgart_PV_Baseline/PVGIS_Stuttgart_1kWp_CrystSi_Tilt30_South_2005_2023.csv \
  --thermal processed/03_PV_Thermal_Model/THERMAL_DAILY_STUTTGART.csv \
  --period-results processed/08_Extended_Validation/HOURLY_CALIBRATED_PERIOD_RESULTS.csv \
  --out processed/08_Extended_Validation
```

## Important scientific interpretation

- Heatwave attribution is defined within the **selected temperature-only Arrhenius stress proxy**, not a causal partition of real PV degradation.
- Daily-max Arrhenius stress substantially overstates the **absolute** integrated stress compared with an hourly reference. The analysis therefore uses hourly-derived monthly calibration as a sensitivity and emphasizes model-specific future/historical normalized acceleration factors.
- The PVGIS comparison is an aggregation benchmark, **not validation against measured module temperature**.
- The service-life outputs are **scenario-conditioned modeled service lives under stationary climate-state assumptions**, not chronological lifetimes of modules installed in particular future years.
- The environmental calculation is a **climate perturbation of a fixed contemporary characterized PV LCA reference**, not a prospective LCA of late-century PV technology.
- Integer and residual-service-life replacement accounting are both retained because the integer rule creates a threshold discontinuity.
- The joint uncertainty output is a **structural scenario envelope**, not a probability interval.

## Reference results

`reference_results/` contains compact baseline summaries. `reference_results/extended_validation/` contains compact tables from the extended validation and sensitivity workflow, including temporal validation, heatwave decomposition, spatial sensitivity summaries, and factorial uncertainty results. Large raw and daily intermediate datasets remain outside Git.

## Citation and archive

`CITATION.cff` is included. Before final manuscript submission, publish a GitHub release and archive the release in a permanent repository such as Zenodo. Add the final repository URL/DOI to `CITATION.cff` and the manuscript Data Availability statement. Do not invent a DOI before the archive exists.
