# Main parameters used in the manuscript workflow — v1.0

## Climate and heatwaves
- Historical period: 1991–2014.
- Future periods: 2041–2060 and 2081–2100.
- Scenarios: SSP2-4.5 and SSP5-8.5.
- Selected climate models: MPI-ESM1-2-HR, MRI-ESM2-0, NorESM2-MM.
- Ensemble member: `r1i1p1f1`.
- Primary heatwave: `tasmax >= 30 °C` for >=3 consecutive days.
- Sensitivity heatwave: model-specific historical May–September P90, held fixed for future periods, >=3 consecutive days.
- Raw Stuttgart `tasmax` subset: 5×5 grid (25 cells), approximately 0.25°.
- Primary `tasmax`: Stuttgart-containing/nearest grid cell, approximately 48.875° N, 9.125° E.
- Spatial sensitivity: bilinear point at 48.7758° N, 9.1829° E and 25-cell regional mean.
- DWD validation station: Stuttgart 04928; historical 1991–2014; raw hourly days require >=18 valid hourly records.

## PV thermal model
- Faiman `U0 = 25.0 W m-2 K-1`.
- Faiman `U1 = 6.84 W m-2 K-1 per m s-1`.
- Representative c-Si reversible temperature coefficient: `-0.004 /°C`.
- Future module temperature is a daily-maximum proxy; it is not an hourly CMIP6 simulation.
- PVGIS hourly data provide aggregation benchmarking/calibration, not measured module-temperature validation.

## Arrhenius temporal calibration
- Base activation energy: `Ea = 0.89 eV`.
- Boltzmann constant: `8.617333262e-5 eV/K`.
- Hourly reference stress: hourly Faiman `Tmod` integrated/averaged over time.
- Daily approximation: Arrhenius stress evaluated at the daily module-temperature proxy.
- Monthly stress multipliers are derived as hourly-integrated stress / daily-proxy stress for each calendar month and applied consistently to historical and future proxy stress before historical normalization.

## Degradation/service life
- Base `Rd0 = 0.66 %/yr`, `Ea = 0.89 eV`.
- Alternative structural cases: 0.40%/1.10 eV; 0.40%/0.89 eV; 0.66%/0.79 eV; 0.80%/0.89 eV.
- End-of-service threshold: 20% nameplate loss.
- Common assessment horizon: 30 years.
- Service-life outputs are scenario-conditioned stationary-climate estimates, not chronological future installation trajectories.
- The model is temperature-only and does not reproduce a full temperature–relative-humidity degradation model.

## PVGIS reference and energy validation
- Stuttgart, 1 kWp crystalline silicon.
- Fixed 30° tilt, south-facing, free mounting.
- 14% system loss.
- Hourly reference: 2005–2023.
- Energy validation compares the daily climate-energy index with hourly POA × temperature-factor integration.
- Both capped and uncapped temperature factors are evaluated; the uncapped case retains physically plausible cool-temperature gains.

## LCA/GWP
- Fixed contemporary characterized IEA-PVPS reference used by the manuscript: `35.8 g CO2-eq/kWh`.
- Reference contribution shares for scenario adjustment: 56% module, 28% inverter, 16% other.
- Integer replacement: `ceil(30/service_life)` module units.
- Residual-service-life allocation: `max(1, 30/service_life)` module equivalents.
- The environmental result is a climate perturbation of the fixed reference, not a prospective LCA of future PV technology.

## Joint uncertainty
- Structural factorial dimensions: GCM, temporal thermal treatment, durability parameter set, yield treatment, replacement allocation.
- Results are min–max structural scenario envelopes, not probability/confidence intervals.
