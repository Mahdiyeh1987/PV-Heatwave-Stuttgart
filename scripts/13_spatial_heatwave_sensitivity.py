from pathlib import Path
import argparse, re
import numpy as np
import pandas as pd
import xarray as xr

MODELS=['MPI-ESM1-2-HR','MRI-ESM2-0','NorESM2-MM']
GROUPS=[('historical','1991-2014'),('ssp245','2041-2060'),('ssp245','2081-2100'),('ssp585','2041-2060'),('ssp585','2081-2100')]
LAT=48.7758; LON=9.1829; THRESH=30.0; MIN_DAYS=3


def dstr(t):
    try: return f'{int(t.year):04d}-{int(t.month):02d}-{int(t.day):02d}'
    except Exception: return pd.to_datetime(t).strftime('%Y-%m-%d')

def decode_time_strings(ds):
    vals=np.asarray(ds['time'].values,dtype=float).reshape(-1)
    attrs=ds['time'].attrs; units=str(attrs.get('units','')); cal=str(attrs.get('calendar','standard')).lower()
    m=re.match(r'\s*days since (\d{1,4})-(\d{1,2})-(\d{1,2})',units)
    if not m: return [dstr(x) for x in ds['time'].values]
    by,bm,bd=map(int,m.groups())
    if cal in {'365_day','noleap','no_leap'}:
        md=[31,28,31,30,31,30,31,31,30,31,30,31]
        base=(by-1)*365+sum(md[:bm-1])+(bd-1); out=[]
        for v in vals:
            total=base+int(np.floor(v+1e-9)); y=total//365+1; rem=total%365; mo=1
            for days in md:
                if rem<days: break
                rem-=days; mo+=1
            out.append(f'{y:04d}-{mo:02d}-{rem+1:02d}')
        return out
    base=pd.Timestamp(year=by,month=bm,day=bd)
    return [(base+pd.to_timedelta(float(v),unit='D')).strftime('%Y-%m-%d') for v in vals]


def coord_name(da,names):
    for n in list(da.coords)+list(da.dims):
        if n.lower() in names: return n
    return None


def find_files(root,model,scenario,period):
    a,b=map(int,period.split('-')); out=[]
    for p in Path(root).rglob('*'):
        if not p.is_file() or p.suffix.lower() not in ['.nc','.nc4']: continue
        s=str(p)
        if model not in s or scenario.lower() not in s.lower() or 'tasmax' not in s.lower() or 'Backup_Copernicus' in s: continue
        ys=[int(x) for x in re.findall(r'(?<!\d)(?:19\d{2}|20\d{2}|2100)(?!\d)',s)]
        if not ys or any(a<=y<=b for y in ys): out.append(p)
    return sorted(set(out))


def read_methods(files,period):
    frames=[]; meta=None
    for p in files:
        ds=xr.open_dataset(p,decode_times=False)
        var='tasmax' if 'tasmax' in ds.data_vars else next(k for k in ds.data_vars if k.lower()=='tasmax')
        da=ds[var]; lat=coord_name(da,{'lat','latitude'}); lon=coord_name(da,{'lon','longitude'})
        if not lat or not lon: ds.close(); raise ValueError(f'No lat/lon in {p}')
        lats=np.asarray(da[lat].values,dtype=float); lons=np.asarray(da[lon].values,dtype=float)
        nearest=da.sel({lat:LAT,lon:LON},method='nearest')
        regional=da.mean(dim=[lat,lon],skipna=True)
        # xarray linear interpolation; if target lies within the grid this is bilinear in space.
        bilinear=da.interp({lat:LAT,lon:LON},method='linear')
        times=decode_time_strings(ds)
        def vals(x):
            v=np.asarray(x.values).reshape(-1).astype(float)
            if np.nanmedian(v)>100: v=v-273.15
            return v
        f=pd.DataFrame({'date':times,'gridcell':vals(nearest),'bilinear':vals(bilinear),'regional':vals(regional)})
        frames.append(f)
        if meta is None:
            # brackets and interpolation fractions for traceability
            la=np.sort(lats); lo=np.sort(lons)
            la0=la[la<=LAT].max(); la1=la[la>=LAT].min(); lo0=lo[lo<=LON].max(); lo1=lo[lo>=LON].min()
            meta={'nlat':len(lats),'nlon':len(lons),'ngrid':len(lats)*len(lons),'lats':';'.join(f'{x:.3f}' for x in lats),'lons':';'.join(f'{x:.3f}' for x in lons),'nearest_lat':float(nearest[lat].values),'nearest_lon':float(nearest[lon].values),'lat_bracket':f'{la0:.3f},{la1:.3f}','lon_bracket':f'{lo0:.3f},{lo1:.3f}','wx':(LON-lo0)/(lo1-lo0) if lo1!=lo0 else 0,'wy':(LAT-la0)/(la1-la0) if la1!=la0 else 0}
        ds.close()
    x=pd.concat(frames,ignore_index=True).drop_duplicates('date').sort_values('date')
    yrs=pd.to_datetime(x.date).dt.year; a,b=map(int,period.split('-')); return x[(yrs>=a)&(yrs<=b)].copy(),meta


def mark_events(df,value_col):
    x=df[['date',value_col]].copy().sort_values('date').reset_index(drop=True)
    x['date']=pd.to_datetime(x.date); hot=(x[value_col]>=THRESH).to_numpy(); flags=np.zeros(len(x),bool); eid=np.zeros(len(x),int); events=[]; start=None; num=0
    for i in range(len(x)+1):
        ishot=(i<len(x) and hot[i])
        consecutive=(i==0 or (x.date.iloc[i]-x.date.iloc[i-1]).days==1) if i<len(x) else False
        if ishot:
            if start is None: start=i
            elif not consecutive:
                if i-start>=MIN_DAYS:
                    num+=1; flags[start:i]=True; eid[start:i]=num
                    g=x.iloc[start:i]; events.append((num,g.date.iloc[0],g.date.iloc[-1],len(g),g[value_col].max(),(g[value_col]-THRESH).sum()))
                start=i
        elif start is not None:
            if i-start>=MIN_DAYS:
                num+=1; flags[start:i]=True; eid[start:i]=num
                g=x.iloc[start:i]; events.append((num,g.date.iloc[0],g.date.iloc[-1],len(g),g[value_col].max(),(g[value_col]-THRESH).sum()))
            start=None
    x['is_heatwave_day']=flags; x['event_id']=eid
    ev=pd.DataFrame(events,columns=['event_id','start','end','duration','peak','cum_excess'])
    return x,ev


def summarize(model,scenario,period,method,x):
    d,e=mark_events(x,method); d['year']=d.date.dt.year
    ny=d.year.nunique(); warm=d[d.date.dt.month.isin([5,6,7,8,9])]
    return {
        'model':model,'scenario':scenario,'period':period,'method':method,
        'hot_days_yr':(d[method]>=THRESH).sum()/ny,
        'events_yr':len(e)/ny,
        'hw_days_yr':d.is_heatwave_day.sum()/ny,
        'mean_duration_days':e.duration.mean() if len(e) else 0,
        'max_duration_days':e.duration.max() if len(e) else 0,
        'cum_excess_Cdays_yr':e.cum_excess.sum()/ny if len(e) else 0,
        'p90_C':np.percentile(warm[method],90),'p95_C':np.percentile(warm[method],95),'abs_tmax_C':d[method].max()
    }


def main():
    ap=argparse.ArgumentParser(description='Spatial sensitivity for Stuttgart tasmax heatwaves.')
    ap.add_argument('--tasmax-root',required=True)
    ap.add_argument('--out',default='processed/08_Extended_Validation/spatial')
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    rows=[]; metadata=None
    for model in MODELS:
      for scenario,period in GROUPS:
        files=find_files(args.tasmax_root,model,scenario,period)
        if not files: raise FileNotFoundError(f'No tasmax files: {model} {scenario} {period}')
        x,meta=read_methods(files,period); metadata=metadata or meta
        for method in ['gridcell','bilinear','regional']:
            rows.append(summarize(model,scenario,period,method,x))
    model=pd.DataFrame(rows); model.to_csv(out/'SPATIAL_HEATWAVE_MODEL_METHOD_SUMMARY.csv',index=False)
    pd.DataFrame([metadata]).to_csv(out/'SPATIAL_GRID_METADATA.csv',index=False)

    agg={}
    for c in ['hot_days_yr','events_yr','hw_days_yr','mean_duration_days','max_duration_days','cum_excess_Cdays_yr','p90_C','p95_C','abs_tmax_C']:
        agg[c+'_mean']=(c,'mean'); agg[c+'_min']=(c,'min'); agg[c+'_max']=(c,'max')
    ens=model.groupby(['scenario','period','method']).agg(**agg).reset_index()
    ens.to_csv(out/'SPATIAL_HEATWAVE_ENSEMBLE_METHOD_SUMMARY.csv',index=False)

    # Ratios to each method's own historical baseline, model-specific and ensemble.
    r=[]
    for (m,method),g in model.groupby(['model','method']):
        h=g[g.scenario=='historical'].iloc[0]
        for _,z in g[g.scenario!='historical'].iterrows():
            r.append({'model':m,'method':method,'scenario':z.scenario,'period':z.period,'events_ratio':z.events_yr/h.events_yr if h.events_yr else np.nan,'hw_days_ratio':z.hw_days_yr/h.hw_days_yr if h.hw_days_yr else np.nan,'cum_excess_ratio':z.cum_excess_Cdays_yr/h.cum_excess_Cdays_yr if h.cum_excess_Cdays_yr else np.nan})
    rr=pd.DataFrame(r); rr.to_csv(out/'SPATIAL_FUTURE_HISTORICAL_RATIOS.csv',index=False)
    rr.groupby(['method','scenario','period']).agg(events_ratio_mean=('events_ratio','mean'),hw_days_ratio_mean=('hw_days_ratio','mean'),cum_excess_ratio_mean=('cum_excess_ratio','mean')).reset_index().to_csv(out/'SPATIAL_FUTURE_HISTORICAL_RATIOS_ENSEMBLE.csv',index=False)
    (out/'SPATIAL_SENSITIVITY_METHOD_NOTE.txt').write_text(
        'The raw Stuttgart tasmax subset is a 5x5 grid (25 cells). The manuscript primary series uses the grid cell containing/nearest the Stuttgart reference coordinate. '
        'This sensitivity compares that grid cell with xarray bilinear interpolation at 48.7758 N, 9.1829 E and the 25-cell regional mean. Absolute threshold-exceedance metrics may differ, but robustness is judged from direction, scenario ranking, and future/historical amplification.\n',encoding='utf-8')
    print('Done:',out)

if __name__=='__main__': main()
