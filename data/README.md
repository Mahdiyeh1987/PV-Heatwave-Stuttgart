# Data directory (not distributed)

Raw datasets are intentionally not bundled with the code repository. Expected source groups are:

- NASA NEX-GDDP-CMIP6 raw `tasmax` 5×5 Stuttgart subsets for the three selected GCMs; these raw grids are required for the spatial sensitivity analysis.
- NASA NEX-GDDP-CMIP6 `rsds` and `sfcWind` inputs used in the archived thermal/yield workflow.
- DWD Climate Data Center Stuttgart station 04928 hourly air temperature for historical validation.
- PVGIS/JRC Stuttgart hourly reference, 1 kWp crystalline-Si, fixed 30° tilt, south-facing, 2005–2023.
- IEA-PVPS fixed characterized LCA reference and 2026 supply-chain LCI workbook used as documented in the manuscript.
- Degradation/service-life literature parameter tables cited by the manuscript.

See `docs/DATA_AND_OUTPUT_MAP.md` for expected paths and extended-validation dependencies.
