from pathlib import Path
import argparse, re
import pandas as pd
import numpy as np
import xarray as xr

MODELS=["MPI-ESM1-2-HR","MRI-ESM2-0","NorESM2-MM"]
VARIABLES=['tasmax','rsds','sfcWind']
GROUPS=[('historical','1991-2014'),('ssp245','2041-2060'),('ssp245','2081-2100'),('ssp585','2041-2060'),('ssp585','2081-2100')]
STUTTGART_LAT=48.7758
STUTTGART_LON=9.1829


def date_str(t):
    try:
        return f"{int(t.year):04d}-{int(t.month):02d}-{int(t.day):02d}"
    except Exception:
        return pd.to_datetime(t).strftime('%Y-%m-%d')

def decode_time_strings(ds):
    """Decode daily NEX time without requiring cftime at runtime."""
    vals=np.asarray(ds['time'].values,dtype=float).reshape(-1)
    attrs=ds['time'].attrs
    units=str(attrs.get('units',''))
    cal=str(attrs.get('calendar','standard')).lower()
    m=re.match(r'\s*days since (\d{1,4})-(\d{1,2})-(\d{1,2})',units)
    if not m:
        return [date_str(x) for x in ds['time'].values]
    by,bm,bd=map(int,m.groups())
    if cal in {'365_day','noleap','no_leap'}:
        md=[31,28,31,30,31,30,31,31,30,31,30,31]
        base=(by-1)*365+sum(md[:bm-1])+(bd-1)
        out=[]
        for v in vals:
            total=base+int(np.floor(v+1e-9))
            y=total//365+1; rem=total%365; mo=1
            for days in md:
                if rem<days: break
                rem-=days; mo+=1
            out.append(f'{y:04d}-{mo:02d}-{rem+1:02d}')
        return out
    base=pd.Timestamp(year=by,month=bm,day=bd)
    return [(base+pd.to_timedelta(float(v),unit='D')).strftime('%Y-%m-%d') for v in vals]


def _coord_name(da, candidates):
    for n in list(da.coords) + list(da.dims):
        if n.lower() in candidates:
            return n
    return None


def read_nc(path,var):
    """Read one NEX-GDDP file.

    Primary spatial treatment:
    - tasmax: primary Stuttgart-containing/nearest grid cell to 48.7758 N, 9.1829 E.
    - rsds and sfcWind: retain the archived workflow's spatial-mean treatment when gridded.

    A separate spatial-sensitivity script compares tasmax grid-cell, bilinear point,
    and 25-cell regional mean directly from the raw grids.
    """
    ds=xr.open_dataset(path, decode_times=False)
    if var not in ds.data_vars:
        cand=[k for k in ds.data_vars if k.lower()==var.lower()]
        if not cand:
            ds.close(); raise KeyError(f'{var} missing in {path}')
        var=cand[0]
    da=ds[var]
    lat=_coord_name(da, {'lat','latitude'})
    lon=_coord_name(da, {'lon','longitude'})

    spatial_method='none'
    if var.lower()=='tasmax' and lat and lon:
        da=da.sel({lat:STUTTGART_LAT,lon:STUTTGART_LON},method='nearest')
        spatial_method=f'nearest_gridcell_{float(da[lat].values):.3f}_{float(da[lon].values):.3f}'
    else:
        spatial=[d for d in da.dims if d.lower() in ['lat','latitude','lon','longitude']]
        if spatial:
            da=da.mean(dim=spatial, skipna=True)
            spatial_method='spatial_mean'

    vals=np.asarray(da.values).reshape(-1)
    times=decode_time_strings(ds)
    out=pd.DataFrame({'date':times,var:vals})
    ds.close()
    return out, spatial_method


def read_csv(path,var):
    df=pd.read_csv(path,low_memory=False)
    datecol=next((c for c in df.columns if c.lower() in ['date','time','datetime']),df.columns[0])
    valuecol=next((c for c in df.columns if c.lower()==var.lower()),None)
    if valuecol is None:
        nums=[c for c in df.columns if c!=datecol and pd.to_numeric(df[c],errors='coerce').notna().sum()>max(1,len(df)//2)]
        if not nums: raise ValueError(f'Cannot infer value column in {path}')
        valuecol=nums[-1]
    d=pd.to_datetime(df[datecol],errors='coerce')
    return pd.DataFrame({'date':d.dt.strftime('%Y-%m-%d'),var:pd.to_numeric(df[valuecol],errors='coerce')}).dropna(), 'preprocessed_csv'


def find_files(root,model,scenario,period,var):
    start,end=period.split('-')
    items=[]
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in ['.nc','.nc4','.csv']: continue
        s=str(p)
        if model not in s or scenario.lower() not in s.lower() or var.lower() not in s.lower(): continue
        if 'Backup_Copernicus' in s: continue
        items.append(p)
    chosen=[]
    for p in items:
        s=str(p)
        years=[int(x) for x in re.findall(r'(?<!\d)(?:19\d{2}|20\d{2}|2100)(?!\d)',s)]
        if not years or any(int(start)<=y<=int(end) for y in years): chosen.append(p)
    return sorted(set(chosen))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-root',default='data')
    ap.add_argument('--out',default='processed/01_Climate_Clean')
    args=ap.parse_args()
    root=Path(args.data_root); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    log=[]; manifest=[]; clean=[]; qc=[]

    for model in MODELS:
      for scenario,period in GROUPS:
        pieces={}
        spatial_methods={}
        for var in VARIABLES:
          frames=[]; methods=[]
          files=find_files(root,model,scenario,period,var)
          for p in files:
            try:
              f,method=read_nc(p,var) if p.suffix.lower() in ['.nc','.nc4'] else read_csv(p,var)
              frames.append(f); methods.append(method)
              log.append({'file':str(p),'status':'OK','message':'','spatial_method':method})
              manifest.append({'model':model,'scenario':scenario,'period':period,'variable':var,'file':str(p),'spatial_method':method})
            except Exception as e:
              log.append({'file':str(p),'status':'ERROR','message':repr(e),'spatial_method':''})
          if frames:
            x=pd.concat(frames,ignore_index=True).drop_duplicates('date').sort_values('date')
            years=pd.to_datetime(x.date,errors='coerce').dt.year
            a,b=map(int,period.split('-')); x=x[(years>=a)&(years<=b)]
            pieces[var]=x
            spatial_methods[var]=';'.join(sorted(set(methods)))
        if not all(v in pieces for v in VARIABLES):
            qc.append({'model':model,'scenario':scenario,'period':period,'status':'MISSING_INPUT','variables':','.join(pieces)})
            continue
        g=pieces['tasmax'].merge(pieces['rsds'],on='date',how='inner').merge(pieces['sfcWind'],on='date',how='inner')
        if g.tasmax.median()>100: g['tasmax']=g['tasmax']-273.15
        g=g.rename(columns={'tasmax':'tasmax_C','rsds':'rsds_Wm2','sfcWind':'sfcWind_ms'})
        g.insert(0,'period',period); g.insert(0,'scenario',scenario); g.insert(0,'model',model)
        fn=out/f'{model}_{scenario}_{period}_Stuttgart_clean.csv'; g.to_csv(fn,index=False); clean.append(g)
        qc.append({'model':model,'scenario':scenario,'period':period,'status':'OK','variables':'tasmax, rsds, sfcWind','rows':len(g),
                   'missing_tasmax':g.tasmax_C.isna().sum(),'missing_rsds':g.rsds_Wm2.isna().sum(),'missing_sfcWind':g.sfcWind_ms.isna().sum(),
                   'tasmax_spatial_method':spatial_methods.get('tasmax',''),'rsds_spatial_method':spatial_methods.get('rsds',''),'sfcWind_spatial_method':spatial_methods.get('sfcWind','')})

    if not clean: raise RuntimeError('No complete climate groups were produced.')
    pd.concat(clean,ignore_index=True).to_csv(out/'MASTER_CLIMATE_STUTTGART.csv',index=False)
    pd.DataFrame(qc).to_csv(out/'CLIMATE_QC_SUMMARY.csv',index=False)
    pd.DataFrame(log).to_csv(out/'PROCESSING_LOG.csv',index=False)
    pd.DataFrame(manifest).to_csv(out/'CLIMATE_INPUT_MANIFEST.csv',index=False)
    (out/'SPATIAL_METHOD_NOTE.txt').write_text(
        'Primary tasmax uses the NEX-GDDP grid cell nearest the Stuttgart reference coordinate '
        '(48.7758 N, 9.1829 E; archived raw grids resolve this as 48.875 N, 9.125 E). '
        'Raw 5x5 tasmax grids are retained for separate bilinear and 25-cell regional-mean sensitivity. '
        'rsds and sfcWind retain the archived cleaned-input treatment used in the thermal/yield workflow.\n',
        encoding='utf-8')
    print('Done:',out)

if __name__=='__main__': main()
