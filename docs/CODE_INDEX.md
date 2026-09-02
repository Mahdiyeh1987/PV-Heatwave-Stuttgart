# Code index and provenance — v1.0

The repository contains the consolidated end-to-end workflow used for the Stuttgart climate–PV–degradation–GWP manuscript plus the extended validation and sensitivity analyses used in the final workflow.

| Script | Stage |
|---|---|
| `00_check_nex_availability.py` | NASA NEX-GDDP-CMIP6 availability check for the selected models |
| `01_download_nex_gddp_complete.py` | Climate-data retrieval |
| `02_download_pvgis_baseline.py` | PVGIS hourly reference retrieval |
| `03_inventory_check.py` | Raw-data inventory and completeness QC |
| `04_clean_merge_climate.py` | Climate merge; primary `tasmax` explicitly uses the Stuttgart grid cell as the primary series |
| `05_heatwave_analysis.py` | Primary 30 °C / 3-day heatwave analysis |
| `06_thermal_analysis.py` | PVGIS-informed Faiman daily maximum module-temperature proxy |
| `07_degradation_service_life.py` | Relative temperature-only Arrhenius degradation and service life |
| `08_lifetime_generation.py` | Climate-adjusted annual and lifetime generation |
| `09_lca_gwp.py` | Fixed-reference GWP with baseline integer replacement |
| `10_solar_sensitivity_validation.py` | P90 threshold, DWD historical validation, replacement accounting |
| `11_hourly_temporal_validation.py` | Hourly Arrhenius integration, temporal-coincidence diagnostics, energy-index validation/calibration |
| `12_heatwave_stress_decomposition.py` | Heatwave/non-heatwave stress attribution and counterfactual service life |
| `13_spatial_heatwave_sensitivity.py` | Grid-cell, bilinear-point and 25-cell regional heatwave comparison |
| `14_joint_uncertainty.py` | Factorial structural uncertainty propagation |

`legacy/` preserves the earliest downloader/availability-checker archive that preceded the consolidated pipeline.

`reference_results/extended_validation/` contains compact outputs from the extended validation and sensitivity analyses. The large daily spatial series is intentionally excluded.
