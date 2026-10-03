#!/usr/bin/env python3
"""Solar-journal sensitivity and validation analyses for the Stuttgart PV study.

This script adds three post-baseline analyses without rerunning the full pipeline:

1. Model-specific historical warm-season P90 heatwave sensitivity (>=3 consecutive days).
2. Historical CMIP6 climatological validation against DWD Stuttgart station 04928.
3. LCA module-replacement allocation sensitivity (integer, residual-life, no replacement).

Inputs
------
--master
    MASTER_CLIMATE_STUTTGART.csv
--dwd
    Either the raw DWD hourly air-temperature ZIP/TXT/CSV containing MESS_DATUM and
    TT_TU, or a preprocessed daily CSV containing date and tasmax_C.
--lifetime
    LIFETIME_GENERATION_PERIOD_SUMMARY.csv
--out
    Output directory.

The script reproduces the historical validation and sensitivity workflow used in the
manuscript analysis. It intentionally validates free-running historical climate model
simulations using climatological/distributional statistics rather than date-matched
weather correlations.
"""

from __future__ import annotations

import argparse
import io
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd


ABS_THRESHOLD_C = 30.0
MIN_HW_DAYS = 3
PERCENTILE = 90
WARM_MONTHS = [5, 6, 7, 8, 9]
DWD_START_YEAR = 1991
DWD_END_YEAR = 2014
MIN_DWD_HOURS_PER_DAY = 18

# IEA-PVPS LCIA anchor used by the baseline LCA script.
IEA_GWP_G_PER_KWH = 35.8
IEA_ANNUAL_YIELD_KWH_PER_KWP = 976.0
IEA_DEGRADATION_PCT_PER_YEAR = 0.7
IEA_PANEL_LIFE_YR = 30
SYSTEM_HORIZON_YR = 30
SHARE_MODULE = 0.56
SHARE_INVERTER = 0.28
SHARE_OTHER = 0.16


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--master", required=True, help="MASTER_CLIMATE_STUTTGART.csv")
    p.add_argument("--dwd", required=True, help="DWD hourly ZIP/TXT/CSV or daily tasmax CSV")
    p.add_argument("--lifetime", required=True, help="LIFETIME_GENERATION_PERIOD_SUMMARY.csv")
    p.add_argument("--out", required=True, help="Output directory")
    return p.parse_args()


def identify_heatwaves(
    data: pd.DataFrame,
    threshold: float,
    min_days: int = 3,
    allowed_months: list[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = data.sort_values("date").copy()
    eligible = g["tasmax_C"] >= threshold
    if allowed_months is not None:
        eligible = eligible & g["date"].dt.month.isin(allowed_months)

    g["_above"] = eligible
    date_break = g["date"].diff().dt.days != 1
    state_break = g["_above"] != g["_above"].shift()
    g["_segment"] = (date_break | state_break).cumsum()
    g["is_heatwave_day"] = False
    g["heatwave_event_id"] = np.nan

    events: list[dict] = []
    event_no = 0
    for _, s in g[g["_above"]].groupby("_segment"):
        duration = len(s)
        if duration < min_days:
            continue
        event_no += 1
        idx = s.index
        g.loc[idx, "is_heatwave_day"] = True
        g.loc[idx, "heatwave_event_id"] = event_no
        events.append(
            {
                "event_id": event_no,
                "start_date": s["date"].min(),
                "end_date": s["date"].max(),
                "duration_days": duration,
                "mean_tasmax_C": s["tasmax_C"].mean(),
                "max_tasmax_C": s["tasmax_C"].max(),
                "threshold_C": threshold,
                "cumulative_excess_Cdays": (s["tasmax_C"] - threshold).clip(lower=0).sum(),
            }
        )

    return g.drop(columns=["_above", "_segment"]), pd.DataFrame(events)


def read_master(path: str | Path) -> pd.DataFrame:
    clim = pd.read_csv(path, low_memory=False)
    required = ["model", "scenario", "period", "date", "tasmax_C"]
    missing = [c for c in required if c not in clim.columns]
    if missing:
        raise ValueError(f"Missing climate columns: {missing}")
    clim["date"] = pd.to_datetime(clim["date"], errors="coerce")
    clim["tasmax_C"] = pd.to_numeric(clim["tasmax_C"], errors="coerce")
    clim = clim.dropna(subset=["date", "tasmax_C"]).copy()
    clim["year"] = clim["date"].dt.year
    clim["month"] = clim["date"].dt.month
    return clim


def run_percentile_heatwave(clim: pd.DataFrame, outdir: Path) -> None:
    hist = clim[clim["scenario"].astype(str).str.lower() == "historical"].copy()
    threshold_rows = []
    for model, g in hist.groupby("model"):
        warm = g[g["month"].isin(WARM_MONTHS)]
        threshold_rows.append(
            {
                "model": model,
                "historical_period": "1991-2014",
                "warm_months": "May-Sep",
                "percentile": PERCENTILE,
                "tasmax_threshold_C": np.percentile(warm["tasmax_C"], PERCENTILE),
            }
        )
    thresholds = pd.DataFrame(threshold_rows)
    thresholds.to_csv(outdir / "HEATWAVE_PERCENTILE_THRESHOLDS.csv", index=False)
    threshold_map = dict(zip(thresholds["model"], thresholds["tasmax_threshold_C"]))

    daily_list, event_list, summary_rows = [], [], []
    for (model, scenario, period), g in clim.groupby(["model", "scenario", "period"]):
        if model not in threshold_map:
            continue
        threshold = threshold_map[model]
        daily, events = identify_heatwaves(
            g[["date", "tasmax_C"]], threshold, MIN_HW_DAYS, WARM_MONTHS
        )
        daily["model"] = model
        daily["scenario"] = scenario
        daily["period"] = period
        daily["percentile_threshold_C"] = threshold
        daily_list.append(daily)
        if len(events):
            events["model"] = model
            events["scenario"] = scenario
            events["period"] = period
            event_list.append(events)
        n_years = g["date"].dt.year.nunique()
        n_events = len(events)
        n_hw_days = int(daily["is_heatwave_day"].sum())
        summary_rows.append(
            {
                "model": model,
                "scenario": scenario,
                "period": period,
                "P90_threshold_C": threshold,
                "years": n_years,
                "events_total": n_events,
                "events_per_year": n_events / n_years,
                "heatwave_days_total": n_hw_days,
                "heatwave_days_per_year": n_hw_days / n_years,
                "mean_event_duration_days": events["duration_days"].mean() if n_events else 0,
                "max_event_duration_days": events["duration_days"].max() if n_events else 0,
                "mean_event_max_tasmax_C": events["max_tasmax_C"].mean() if n_events else np.nan,
                "cumulative_excess_Cdays_per_year": (
                    events["cumulative_excess_Cdays"].sum() / n_years if n_events else 0
                ),
            }
        )

    percentile_daily = pd.concat(daily_list, ignore_index=True)
    percentile_events = pd.concat(event_list, ignore_index=True) if event_list else pd.DataFrame()
    percentile_summary = pd.DataFrame(summary_rows)
    percentile_daily.to_csv(outdir / "HEATWAVE_PERCENTILE_DAILY.csv", index=False)
    percentile_events.to_csv(outdir / "HEATWAVE_PERCENTILE_EVENTS.csv", index=False)
    percentile_summary.to_csv(outdir / "HEATWAVE_PERCENTILE_PERIOD_SUMMARY.csv", index=False)

    percentile_ensemble = (
        percentile_summary.groupby(["scenario", "period"])
        .agg(
            events_per_year_mean=("events_per_year", "mean"),
            events_per_year_std=("events_per_year", "std"),
            heatwave_days_per_year_mean=("heatwave_days_per_year", "mean"),
            heatwave_days_per_year_std=("heatwave_days_per_year", "std"),
            mean_event_duration_days_mean=("mean_event_duration_days", "mean"),
            max_event_duration_days_mean=("max_event_duration_days", "mean"),
            cumulative_excess_Cdays_per_year_mean=("cumulative_excess_Cdays_per_year", "mean"),
        )
        .reset_index()
    )
    percentile_ensemble.to_csv(outdir / "HEATWAVE_PERCENTILE_ENSEMBLE_SUMMARY.csv", index=False)

    absolute_rows = []
    for (model, scenario, period), g in clim.groupby(["model", "scenario", "period"]):
        daily, events = identify_heatwaves(
            g[["date", "tasmax_C"]], ABS_THRESHOLD_C, MIN_HW_DAYS
        )
        n_years = g["date"].dt.year.nunique()
        absolute_rows.append(
            {
                "model": model,
                "scenario": scenario,
                "period": period,
                "events_per_year": len(events) / n_years,
                "heatwave_days_per_year": daily["is_heatwave_day"].sum() / n_years,
            }
        )
    absolute = pd.DataFrame(absolute_rows)
    comparison = percentile_summary[
        ["model", "scenario", "period", "events_per_year", "heatwave_days_per_year"]
    ].rename(
        columns={
            "events_per_year": "P90_events_per_year",
            "heatwave_days_per_year": "P90_heatwave_days_per_year",
        }
    )
    comparison = comparison.merge(
        absolute.rename(
            columns={
                "events_per_year": "ABS30_events_per_year",
                "heatwave_days_per_year": "ABS30_heatwave_days_per_year",
            }
        ),
        on=["model", "scenario", "period"],
        how="left",
    )
    comparison.to_csv(outdir / "HEATWAVE_DEFINITION_COMPARISON.csv", index=False)


def _clean_dwd_hourly(raw: pd.DataFrame) -> pd.DataFrame | None:
    raw.columns = [str(c).strip() for c in raw.columns]
    rename = {}
    for c in raw.columns:
        clean = c.replace(" ", "").strip().upper()
        if clean == "MESS_DATUM":
            rename[c] = "MESS_DATUM"
        elif clean == "TT_TU":
            rename[c] = "TT_TU"
    raw = raw.rename(columns=rename)
    if "MESS_DATUM" not in raw.columns or "TT_TU" not in raw.columns:
        return None
    out = raw[["MESS_DATUM", "TT_TU"]].copy()
    date_str = out["MESS_DATUM"].astype(str).str.replace(".0", "", regex=False).str.strip()
    out["datetime"] = pd.to_datetime(date_str, format="%Y%m%d%H", errors="coerce")
    out["temperature_C"] = pd.to_numeric(out["TT_TU"], errors="coerce")
    out.loc[out["temperature_C"] <= -900, "temperature_C"] = np.nan
    out.loc[(out["temperature_C"] < -50) | (out["temperature_C"] > 60), "temperature_C"] = np.nan
    return out.dropna(subset=["datetime", "temperature_C"])


def _read_delimited_dwd_bytes(content: bytes) -> pd.DataFrame | None:
    for sep in [";", ",", "\t"]:
        for encoding in ["latin1", "utf-8"]:
            try:
                raw = pd.read_csv(io.BytesIO(content), sep=sep, encoding=encoding, low_memory=False)
            except Exception:
                continue
            cleaned = _clean_dwd_hourly(raw)
            if cleaned is not None and len(cleaned):
                return cleaned
    return None


def read_dwd_daily(path: str | Path) -> pd.DataFrame:
    path = Path(path)

    # Reproducibility convenience: accept the already aggregated daily output.
    if path.suffix.lower() in {".csv", ".txt"}:
        try:
            test = pd.read_csv(path, low_memory=False)
            if {"date", "tasmax_C"}.issubset(test.columns):
                test["date"] = pd.to_datetime(test["date"], errors="coerce")
                test["tasmax_C"] = pd.to_numeric(test["tasmax_C"], errors="coerce")
                test = test.dropna(subset=["date", "tasmax_C"]).copy()
                if "valid_hours" not in test.columns:
                    test["valid_hours"] = np.nan
                return test[["date", "tasmax_C", "valid_hours"]]
        except Exception:
            pass

    hourly = None
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as z:
            candidates = [
                n for n in z.namelist() if n.lower().endswith((".txt", ".csv"))
            ]
            candidates = sorted(candidates, key=lambda n: ("produkt_tu_stunde" not in n.lower(), n))
            for name in candidates:
                try:
                    hourly = _read_delimited_dwd_bytes(z.read(name))
                except Exception:
                    hourly = None
                if hourly is not None and len(hourly):
                    break
    else:
        content = path.read_bytes()
        hourly = _read_delimited_dwd_bytes(content)

    if hourly is None or not len(hourly):
        raise ValueError(
            "Could not parse DWD input. Expected raw hourly MESS_DATUM/TT_TU data "
            "or a daily CSV containing date and tasmax_C."
        )

    hourly = hourly[
        hourly["datetime"].dt.year.between(DWD_START_YEAR, DWD_END_YEAR)
    ].copy()
    hourly["date"] = hourly["datetime"].dt.floor("D")
    daily = (
        hourly.groupby("date")
        .agg(tasmax_C=("temperature_C", "max"), valid_hours=("temperature_C", "count"))
        .reset_index()
    )
    return daily[daily["valid_hours"] >= MIN_DWD_HOURS_PER_DAY].copy()


def run_dwd_validation(clim: pd.DataFrame, dwd_path: str | Path, outdir: Path) -> None:
    dwd_daily = read_dwd_daily(dwd_path)
    dwd_daily = dwd_daily[dwd_daily["date"].dt.year.between(DWD_START_YEAR, DWD_END_YEAR)].copy()
    dwd_daily["year"] = dwd_daily["date"].dt.year
    dwd_daily["month"] = dwd_daily["date"].dt.month
    dwd_daily.to_csv(outdir / "DWD_STUTTGART_04928_DAILY_TASMAX_1991_2014.csv", index=False)

    dwd_hw_daily, dwd_hw_events = identify_heatwaves(
        dwd_daily[["date", "tasmax_C"]], ABS_THRESHOLD_C, MIN_HW_DAYS
    )
    dwd_years = dwd_daily["year"].nunique()
    dwd_warm = dwd_daily[dwd_daily["month"].isin(WARM_MONTHS)]
    dwd_p90 = np.percentile(dwd_warm["tasmax_C"], PERCENTILE)
    dwd_metrics = {
        "mean_tasmax_C": dwd_daily["tasmax_C"].mean(),
        "warmseason_mean_tasmax_C": dwd_warm["tasmax_C"].mean(),
        "warmseason_P90_tasmax_C": dwd_p90,
        "hot_days_30C_per_year": (dwd_daily["tasmax_C"] >= ABS_THRESHOLD_C).sum() / dwd_years,
        "heatwave_events_30C3d_per_year": len(dwd_hw_events) / dwd_years,
        "heatwave_days_30C3d_per_year": dwd_hw_daily["is_heatwave_day"].sum() / dwd_years,
    }
    dwd_monthly = (
        dwd_daily.groupby("month")
        .agg(DWD_mean_tasmax_C=("tasmax_C", "mean"))
        .reset_index()
    )

    hist = clim[
        (clim["scenario"].astype(str).str.lower() == "historical")
        & clim["year"].between(DWD_START_YEAR, DWD_END_YEAR)
    ].copy()
    validation_rows, monthly_rows = [], []
    for model, g in hist.groupby("model"):
        warm = g[g["month"].isin(WARM_MONTHS)]
        model_hw_daily, model_hw_events = identify_heatwaves(
            g[["date", "tasmax_C"]], ABS_THRESHOLD_C, MIN_HW_DAYS
        )
        n_years = g["year"].nunique()
        model_monthly = (
            g.groupby("month")
            .agg(CMIP6_mean_tasmax_C=("tasmax_C", "mean"))
            .reset_index()
        )
        m = dwd_monthly.merge(model_monthly, on="month", how="inner")
        m["model"] = model
        m["bias_C"] = m["CMIP6_mean_tasmax_C"] - m["DWD_mean_tasmax_C"]
        monthly_rows.append(m)
        model_p90 = np.percentile(warm["tasmax_C"], PERCENTILE)
        hot_days = (g["tasmax_C"] >= ABS_THRESHOLD_C).sum() / n_years
        hw_events = len(model_hw_events) / n_years
        hw_days = model_hw_daily["is_heatwave_day"].sum() / n_years
        validation_rows.append(
            {
                "model": model,
                "validation_period": "1991-2014",
                "DWD_station": "04928 Stuttgart",
                "CMIP_mean_tasmax_C": g["tasmax_C"].mean(),
                "DWD_mean_tasmax_C": dwd_metrics["mean_tasmax_C"],
                "mean_tasmax_bias_C": g["tasmax_C"].mean() - dwd_metrics["mean_tasmax_C"],
                "CMIP_warmseason_mean_tasmax_C": warm["tasmax_C"].mean(),
                "DWD_warmseason_mean_tasmax_C": dwd_metrics["warmseason_mean_tasmax_C"],
                "warmseason_mean_bias_C": warm["tasmax_C"].mean() - dwd_metrics["warmseason_mean_tasmax_C"],
                "CMIP_P90_tasmax_C": model_p90,
                "DWD_P90_tasmax_C": dwd_metrics["warmseason_P90_tasmax_C"],
                "P90_bias_C": model_p90 - dwd_metrics["warmseason_P90_tasmax_C"],
                "CMIP_hot_days_30C_per_year": hot_days,
                "DWD_hot_days_30C_per_year": dwd_metrics["hot_days_30C_per_year"],
                "hot_days_bias_days_per_year": hot_days - dwd_metrics["hot_days_30C_per_year"],
                "CMIP_heatwave_events_30C3d_per_year": hw_events,
                "DWD_heatwave_events_30C3d_per_year": dwd_metrics["heatwave_events_30C3d_per_year"],
                "heatwave_event_bias_per_year": hw_events - dwd_metrics["heatwave_events_30C3d_per_year"],
                "CMIP_heatwave_days_30C3d_per_year": hw_days,
                "DWD_heatwave_days_30C3d_per_year": dwd_metrics["heatwave_days_30C3d_per_year"],
                "heatwave_day_bias_days_per_year": hw_days - dwd_metrics["heatwave_days_30C3d_per_year"],
                "monthly_climatology_RMSE_C": np.sqrt(np.mean(m["bias_C"] ** 2)),
                "monthly_climatology_MAE_C": np.mean(np.abs(m["bias_C"])),
            }
        )

    validation = pd.DataFrame(validation_rows)
    monthly = pd.concat(monthly_rows, ignore_index=True)
    validation.to_csv(outdir / "DWD_CMIP6_HISTORICAL_VALIDATION_SUMMARY.csv", index=False)
    monthly.to_csv(outdir / "DWD_CMIP6_MONTHLY_CLIMATOLOGY.csv", index=False)

    metrics = [
        "mean_tasmax_bias_C",
        "warmseason_mean_bias_C",
        "P90_bias_C",
        "hot_days_bias_days_per_year",
        "heatwave_event_bias_per_year",
        "heatwave_day_bias_days_per_year",
        "monthly_climatology_RMSE_C",
        "monthly_climatology_MAE_C",
    ]
    ensemble = pd.DataFrame(
        {
            "metric": metrics,
            "ensemble_mean": [validation[m].mean() for m in metrics],
            "ensemble_std": [validation[m].std() for m in metrics],
        }
    )
    ensemble.to_csv(outdir / "DWD_CMIP6_VALIDATION_ENSEMBLE.csv", index=False)


def run_lca_allocation(lifetime_path: str | Path, outdir: Path) -> None:
    life = pd.read_csv(lifetime_path, low_memory=False)
    required = [
        "model",
        "scenario",
        "period",
        "service_life_years",
        "module_units_required_30y",
        "system30_generation_with_replacements_kWh_per_kWp",
        "fixed30_no_replacement_generation_kWh_per_kWp",
    ]
    missing = [c for c in required if c not in life.columns]
    if missing:
        raise ValueError(f"Missing lifetime columns: {missing}")
    for c in required[3:]:
        life[c] = pd.to_numeric(life[c], errors="coerce")

    iea_generation = IEA_ANNUAL_YIELD_KWH_PER_KWP * IEA_PANEL_LIFE_YR  # published annual reference yield already embodies the fact-sheet degradation assumption
    total_ref_kg = IEA_GWP_G_PER_KWH * iea_generation / 1000.0
    module_kg = total_ref_kg * SHARE_MODULE
    inverter_kg = total_ref_kg * SHARE_INVERTER
    other_kg = total_ref_kg * SHARE_OTHER

    rows = []
    for _, r in life.iterrows():
        sl = r["service_life_years"]
        common = {"model": r["model"], "scenario": r["scenario"], "period": r["period"], "service_life_years": sl}

        integer_units = r["module_units_required_30y"]
        integer_gen = r["system30_generation_with_replacements_kWh_per_kWp"]
        integer_burden = integer_units * module_kg + inverter_kg + other_kg
        rows.append({**common, "allocation_case": "A_Integer_replacement", "module_equivalents_30y": integer_units, "generation_kWh_per_kWp": integer_gen, "total_GWP_kgCO2eq_per_kWp": integer_burden, "GWP_gCO2eq_per_kWh": integer_burden * 1000 / integer_gen})

        frac_units = max(1.0, SYSTEM_HORIZON_YR / sl)
        frac_gen = integer_gen
        frac_burden = frac_units * module_kg + inverter_kg + other_kg
        rows.append({**common, "allocation_case": "B_Residual_service_life_allocation", "module_equivalents_30y": frac_units, "generation_kWh_per_kWp": frac_gen, "total_GWP_kgCO2eq_per_kWp": frac_burden, "GWP_gCO2eq_per_kWh": frac_burden * 1000 / frac_gen})

        no_gen = r["fixed30_no_replacement_generation_kWh_per_kWp"]
        no_burden = module_kg + inverter_kg + other_kg
        rows.append({**common, "allocation_case": "C_No_module_replacement", "module_equivalents_30y": 1.0, "generation_kWh_per_kWp": no_gen, "total_GWP_kgCO2eq_per_kWp": no_burden, "GWP_gCO2eq_per_kWh": no_burden * 1000 / no_gen})

    sens = pd.DataFrame(rows)
    sens.to_csv(outdir / "LCA_REPLACEMENT_ALLOCATION_SENSITIVITY.csv", index=False)
    ensemble = (
        sens.groupby(["scenario", "period", "allocation_case"])
        .agg(
            service_life_years_mean=("service_life_years", "mean"),
            module_equivalents_30y_mean=("module_equivalents_30y", "mean"),
            generation_kWh_per_kWp_mean=("generation_kWh_per_kWp", "mean"),
            GWP_gCO2eq_per_kWh_mean=("GWP_gCO2eq_per_kWh", "mean"),
            GWP_gCO2eq_per_kWh_std=("GWP_gCO2eq_per_kWh", "std"),
            GWP_gCO2eq_per_kWh_min=("GWP_gCO2eq_per_kWh", "min"),
            GWP_gCO2eq_per_kWh_max=("GWP_gCO2eq_per_kWh", "max"),
        )
        .reset_index()
    )
    ensemble.to_csv(outdir / "LCA_REPLACEMENT_ALLOCATION_ENSEMBLE.csv", index=False)

    change_rows = []
    for case, c in ensemble.groupby("allocation_case"):
        hist = c[c["scenario"].astype(str).str.lower() == "historical"]
        if len(hist) != 1:
            continue
        hist_gwp = float(hist.iloc[0]["GWP_gCO2eq_per_kWh_mean"])
        for _, r in c.iterrows():
            gwp = r["GWP_gCO2eq_per_kWh_mean"]
            change_rows.append(
                {
                    "scenario": r["scenario"],
                    "period": r["period"],
                    "allocation_case": case,
                    "GWP_gCO2eq_per_kWh_mean": gwp,
                    "historical_GWP_gCO2eq_per_kWh": hist_gwp,
                    "GWP_change_vs_historical_g_per_kWh": gwp - hist_gwp,
                    "GWP_change_vs_historical_pct": (gwp / hist_gwp - 1) * 100,
                }
            )
    pd.DataFrame(change_rows).to_csv(
        outdir / "LCA_REPLACEMENT_ALLOCATION_CHANGE_VS_HISTORICAL.csv", index=False
    )


def write_method_notes(outdir: Path) -> None:
    text = f"""SOLAR SENSITIVITY / VALIDATION METHODS\n\n1) Heatwave sensitivity\nPrimary definition: tasmax >= {ABS_THRESHOLD_C:.0f} °C for >= {MIN_HW_DAYS} consecutive days.\nSensitivity: model-specific historical {PERCENTILE}th percentile of May-September tasmax, held fixed for each model's future simulations, again for >= {MIN_HW_DAYS} consecutive days.\n\n2) DWD historical validation\nDWD Stuttgart station 04928 hourly air temperature is aggregated to daily maximum for 1991-2014. Raw hourly inputs require >= {MIN_DWD_HOURS_PER_DAY} valid hourly records/day. Validation uses climatological/distributional statistics, not date-matched daily correlation, because CMIP6 historical simulations are free-running realizations.\n\n3) LCA replacement allocation sensitivity\nA: integer physical replacement (baseline main case).\nB: residual-service-life allocation, module equivalents = 30/service_life.\nC: no-module-replacement counterfactual.\n\nThe three analyses quantify sensitivity to heatwave definition, historical temperature-distribution bias, and module replacement accounting.\n"""
    (outdir / "SOLAR_SENSITIVITY_METHOD_NOTES.txt").write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    clim = read_master(args.master)
    run_percentile_heatwave(clim, outdir)
    run_dwd_validation(clim, args.dwd, outdir)
    run_lca_allocation(args.lifetime, outdir)
    write_method_notes(outdir)
    print(f"All sensitivity/validation analyses completed: {outdir}")


if __name__ == "__main__":
    main()
