# Changelog

## 1.1.0 — 2026-10-01
- Corrected all compact archived GWP reference-result tables, including extended-validation and joint-factorial outputs, to the 29,280 kWh kWp^-1 / 1,048.224 kg CO2-eq kWp^-1 IEA-PVPS reference reconstruction.

Major-revision reproducibility update.

### Fixed
- Corrected double application of the IEA-PVPS 0.7%/yr degradation assumption in the reference lifetime-generation reconstruction.
- Updated LCA-dependent scripts 09, 10, 11, and 14.
- Corrected compact absolute GWP reference outputs affected by the common burden-anchor change.
- Corrected the future spatial-provenance description: future `tasmax`, `rsds`, and `sfcWind` archived inputs are co-located at the Stuttgart-containing grid cell.

### Added
- 10/20/30% end-of-service threshold and linear/compound degradation-trajectory sensitivity.
- P90 heatwave-stress attribution sensitivity and counterfactual lifetime outputs.
- Raw-grid grid-cell/bilinear/regional forcing sensitivity for module temperature and annual yield.
- Diagnostic GWP mechanism decomposition.
- Major-revision compact reference results and documentation.

### Interpretation
- Three GCMs remain a limited structural sample, not a full CMIP6 uncertainty distribution.
- The 20% loss threshold is a modeling end-of-service criterion, not a mandatory physical replacement rule.
- Scenario-conditioned service lives retain the stationary climate-state assumption.

## 1.0.0 — 2026-09-02
- First public reproducible release accompanying the manuscript.
