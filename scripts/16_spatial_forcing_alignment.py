from pathlib import Path
import argparse, re
import numpy as np
import pandas as pd
import xarray as xr

MODELS=["MPI-ESM1-2-HR","MRI-ESM2-0","NorESM2-MM"]
GROUPS=[("ssp245","2041-2060"),("ssp245","2081-2100"),
        ("ssp585","2041-2060"),("ssp585","2081-2100")]
LAT=48.7758
LON=9.1829
U0=25.0
U1=6.84
GAMMA=-0.004
PVGIS_BASE_YIELD=1101.778297

# Archived monthly hourly-to-daily energy correction factors.
ENERGY_MULT={
1:1.055723039946433,2:1.0501636122492817,3:1.0476697636449277,
4:1.0454996964080725,5:1.045264794530083,6:1.0448804359643338,
7:1.0454757788764304,8:1.0448708138352838,9:1.0414629835558038,
10:1.0405438977704542,11:1.0422444830703579,12:1.049390981125635}

def decode_time_strings(ds):
    vals=np.asarray(ds["time"].values,dtype=float).reshape(-1)
    attrs=ds["time"].attrs
    units=str(attrs.get("units",""))
    cal=str(attrs.get("calendar","standard")).lower()
    m=re.match(r"\s*days since (\d{1,4})-(\d{1,2})-(\d{1,2})",units)
    if not m:
        return [pd.to_datetime(x).strftime("%Y-%m-%d") for x in ds["time"].values]
    by,bm,bd=map(int,m.groups())
    if cal in {"365_day","noleap","no_leap"}:
        md=[31,28,31,30,31,30,31,31,30,31,30,31]
        base=(by-1)*365+sum(md[:bm-1])+(bd-1)
        out=[]
        for v in vals:
            total=base+int(np.floor(v+1e-9))
            y=total//365+1; rem=total%365; mo=1
            for days in md:
                if rem<days: break
                rem-=days; mo+=1
            out.append(f"{y:04d}-{mo:02d}-{rem+1:02d}")
        return out
    base=pd.Timestamp(year=by,month=bm,day=bd)
    return [(base+pd.to_timedelta(float(v),unit="D")).strftime("%Y-%m-%d") for v in vals]

def coord_name(da,names):
    for n in list(da.coords)+list(da.dims):
        if n.lower() in names:
            return n
    return None

def find_files(root,model,scenario,period,var):
    a,b=map(int,period.split("-"))
    out=[]
    for p in Path(root).rglob("*.nc"):
        s=str(p)
        if model not in s or scenario.lower() not in s.lower() or var.lower() not in s.lower():
            continue
        ys=[int(x) for x in re.findall(r"(?<!\d)(?:19\d{2}|20\d{2}|2100)(?!\d)",s)]
        if not ys or any(a<=y<=b for y in ys):
            out.append(p)
    return sorted(set(out))

def read_methods(files,var,period):
    frames=[]
    for p in files:
        ds=xr.open_dataset(p,decode_times=False)
        da=ds[var] if var in ds.data_vars else ds[next(k for k in ds.data_vars if k.lower()==var.lower())]
        lat=coord_name(da,{"lat","latitude"}); lon=coord_name(da,{"lon","longitude"})
        grid=da.sel({lat:LAT,lon:LON},method="nearest")
        bil=da.interp({lat:LAT,lon:LON},method="linear")
        reg=da.mean(dim=[lat,lon],skipna=True)
        def vals(x):
            v=np.asarray(x.values).reshape(-1).astype(float)
            if var=="tasmax" and np.nanmedian(v)>100:
                v=v-273.15
            return v
        frames.append(pd.DataFrame({
            "date":decode_time_strings(ds),
            f"{var}_gridcell":vals(grid),
            f"{var}_bilinear":vals(bil),
            f"{var}_regional":vals(reg)}))
        ds.close()
    x=pd.concat(frames,ignore_index=True).drop_duplicates("date").sort_values("date")
    x["date"]=pd.to_datetime(x.date)
    a,b=map(int,period.split("-"))
    return x[x.date.dt.year.between(a,b)].copy()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--tasmax-root",required=True)
    ap.add_argument("--wind-rad-root",required=True)
    ap.add_argument("--thermal-archive",required=True)
    ap.add_argument("--period-results",required=True,
                    help="HOURLY_CALIBRATED_RESULTS_REFERENCE.csv")
    ap.add_argument("--out",default="processed/09_Reviewer_Revision/spatial_alignment")
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    th=pd.read_csv(args.thermal_archive,low_memory=False)
    th["date"]=pd.to_datetime(th.date); th["month"]=th.date.dt.month
    th["k_POA"]=th.poa_daily_mean_Wm2/th.rsds_Wm2
    th["k_peak"]=th.poa_peak_proxy_Wm2/th.poa_daily_mean_Wm2
    f=th.groupby("month").agg(k_POA=("k_POA","median"),k_peak=("k_peak","median")).reset_index()
    kpoa=dict(zip(f.month,f.k_POA)); kpeak=dict(zip(f.month,f.k_peak))
    pr=pd.read_csv(args.period_results)

    rows=[]
    for model in MODELS:
        for scenario,period in GROUPS:
            pieces=[]
            for var,root in [("tasmax",args.tasmax_root),("rsds",args.wind_rad_root),("sfcWind",args.wind_rad_root)]:
                pieces.append(read_methods(find_files(root,model,scenario,period,var),var,period))
            g=pieces[0].merge(pieces[1],on="date").merge(pieces[2],on="date")
            g["month"]=g.date.dt.month
            tmp=[]
            for method in ["gridcell","bilinear","regional"]:
                tas=g[f"tasmax_{method}"]; rs=g[f"rsds_{method}"]; wind=g[f"sfcWind_{method}"]
                poa=rs*g.month.map(kpoa)
                peak=poa*g.month.map(kpeak)
                tmod=tas+peak/(U0+U1*wind)
                fT=1+GAMMA*(tmod-25)
                e=poa*24*fT*g.month.map(ENERGY_MULT)
                tmp.append({
                    "method":method,
                    "mean_Tmodule_C":tmod.mean(),
                    "p95_Tmodule_C":tmod.quantile(.95),
                    "max_Tmodule_C":tmod.max(),
                    "annual_energy_index":e.sum()/g.date.dt.year.nunique()})
            t=pd.DataFrame(tmp)
            base=t[t.method=="gridcell"].iloc[0]
            y0=float(pr[(pr.model==model)&(pr.scenario==scenario)&(pr.period==period)].Y_hourlycal.iloc[0])
            for _,r in t.iterrows():
                ratio=r.annual_energy_index/base.annual_energy_index
                rows.append({
                    "model":model,"scenario":scenario,"period":period,"method":r.method,
                    "mean_Tmodule_C":r.mean_Tmodule_C,
                    "p95_Tmodule_C":r.p95_Tmodule_C,
                    "max_Tmodule_C":r.max_Tmodule_C,
                    "delta_mean_Tmodule_C_vs_gridcell":r.mean_Tmodule_C-base.mean_Tmodule_C,
                    "delta_p95_Tmodule_C_vs_gridcell":r.p95_Tmodule_C-base.p95_Tmodule_C,
                    "energy_index_change_pct_vs_gridcell":(ratio-1)*100,
                    "submitted_Y_hourlycal_kWh_kWp_yr":y0,
                    "spatial_adjusted_Y_kWh_kWp_yr":y0*ratio,
                    "yield_delta_kWh_kWp_yr_vs_gridcell":y0*(ratio-1)})

    m=pd.DataFrame(rows)
    m.to_csv(out/"SPATIAL_FORCING_ALIGNMENT_MODEL.csv",index=False)
    e=m.groupby(["scenario","period","method"]).agg(
        delta_mean_Tmodule_C_vs_gridcell=("delta_mean_Tmodule_C_vs_gridcell","mean"),
        delta_p95_Tmodule_C_vs_gridcell=("delta_p95_Tmodule_C_vs_gridcell","mean"),
        energy_index_change_pct_vs_gridcell=("energy_index_change_pct_vs_gridcell","mean"),
        yield_delta_kWh_kWp_yr_vs_gridcell=("yield_delta_kWh_kWp_yr_vs_gridcell","mean")
    ).reset_index()
    e.to_csv(out/"SPATIAL_FORCING_ALIGNMENT_ENSEMBLE.csv",index=False)

if __name__=="__main__":
    main()
