# Validation and sensitivity notes — repository v1.0.0

Version 1.0.0 is the first public reproducibility release accompanying the manuscript. It consolidates the baseline workflow together with the additional validation, sensitivity, attribution, and structural-uncertainty analyses used in the final study.

## Key changes

1. **Spatial-method correction/audit** — `scripts/04_clean_merge_climate.py` now explicitly selects the Stuttgart grid cell for primary `tasmax`. The raw 5×5 grid is used separately for bilinear and regional-mean sensitivity.
2. **Hourly Arrhenius validation** — new script 11 quantifies the absolute bias of daily-max Arrhenius stress and derives monthly hourly calibration factors.
3. **Meteorological temporal coincidence** — script 11 quantifies whether air-temperature maximum, irradiance maximum, and module-temperature maximum occur at the same hour.
4. **Energy-index validation** — script 11 compares daily-index normalized annual ratios against an hourly irradiance–temperature calculation and tests capped versus uncapped temperature factors.
5. **Heatwave decomposition** — script 12 partitions future-minus-historical modeled stress change into heatwave-day and non-heatwave-day contributions and adds a non-heatwave counterfactual service-life calculation.
6. **Spatial heatwave sensitivity** — script 13 compares grid-cell, bilinear, and 25-cell regional extraction.
7. **Joint uncertainty** — script 14 generates a factorial structural scenario envelope rather than treating one-at-a-time sensitivity as complete uncertainty propagation.
8. **Replacement accounting framing** — repository documentation treats integer and residual-service-life allocation as parallel accounting cases.
9. **Prospective-LCA framing** — documentation states explicitly that the environmental assessment perturbs a fixed contemporary characterized LCA reference rather than modeling future PV supply chains/technology.
10. **Reporting precision** — compact reference results retain calculation precision for reproducibility; manuscript-facing reporting should use uncertainty-aware significant figures.

## Data not included

Large raw data remain excluded from Git. In particular, the raw 5×5 `tasmax` NetCDF set is required to rerun script 13. The large daily spatial comparison table is not committed; compact spatial summaries are included under `reference_results/extended_validation/`.
