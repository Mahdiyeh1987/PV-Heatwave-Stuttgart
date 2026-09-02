from pathlib import Path
import argparse, numpy as np, pandas as pd

U0=25.0; U1=6.84; GAMMA_P=-0.004; HW_THRESHOLD=30.0; HW_MIN_DAYS=3

def read_pvgis(path):
    lines=Path(path).read_text(encoding='utf-8',errors='ignore').splitlines()
    idx=next((i for i,x in enumerate(lines) if x.startswith('time,')),None)
    if idx is None: raise ValueError('PVGIS hourly header not found')
    pv=pd.read_csv(path,skiprows=idx,low_memory=False)
    pv=pv[pv['time'].astype(str).str.match(r'^\d{8}:\d{4}$',na=False)].copy()
    pv['datetime']=pd.to_datetime(pv.time,format='%Y%m%d:%H%M',errors='coerce')
    return pv.dropna(subset=['datetime'])

def mark_heatwave(g):
    g=g.sort_values('date').reset_index(drop=True).copy(); hot=(g.tasmax_C>=HW_THRESHOLD).to_numpy(); dates=g.date.to_numpy(); flags=np.zeros(len(g),bool); start=None
    for i in range(len(g)):
        if hot[i]:
            if start is None: start=i
            elif i>0 and (pd.Timestamp(dates[i])-pd.Timestamp(dates[i-1])).days!=1:
                if i-start>=HW_MIN_DAYS: flags[start:i]=True
                start=i
        elif start is not None:
            if i-start>=HW_MIN_DAYS: flags[start:i]=True
            start=None
    if start is not None and len(g)-start>=HW_MIN_DAYS: flags[start:]=True
    g['is_heatwave_day']=flags; return g

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--master',required=True); ap.add_argument('--pvgis',required=True); ap.add_argument('--out',default='processed/03_PV_Thermal_Model'); args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    clim=pd.read_csv(args.master,low_memory=False); clim['date']=pd.to_datetime(clim.date); clim['month']=clim.date.dt.month; clim['year']=clim.date.dt.year
    pv=read_pvgis(args.pvgis)
    need=['Gb(i)','Gd(i)','Gr(i)','T2m','WS10m']
    for c in need: pv[c]=pd.to_numeric(pv[c],errors='coerce')
    pv['poa_Wm2']=pv['Gb(i)']+pv['Gd(i)']+pv['Gr(i)']; pv['Tmodule_Faiman_C']=pv.T2m+pv.poa_Wm2/(U0+U1*pv.WS10m); pv['date']=pv.datetime.dt.floor('D'); pv['month']=pv.datetime.dt.month
    pvd=pv.groupby('date').agg(poa_daily_mean_Wm2=('poa_Wm2','mean'),poa_daily_max_Wm2=('poa_Wm2','max'),tair_daily_max_C=('T2m','max'),wind_daily_mean_ms=('WS10m','mean'),Tmodule_true_daily_max_C=('Tmodule_Faiman_C','max')).reset_index(); pvd['month']=pvd.date.dt.month
    pm=pvd.groupby('month').agg(pvgis_poa_daily_mean=('poa_daily_mean_Wm2','mean'),pvgis_poa_daily_max=('poa_daily_max_Wm2','mean')).reset_index(); pm['k_peak']=pm.pvgis_poa_daily_max/pm.pvgis_poa_daily_mean
    hist=clim[clim.scenario=='historical']; hm=hist.groupby(['model','month']).rsds_Wm2.mean().reset_index(); he=hm.groupby('month').rsds_Wm2.mean().reset_index(name='historical_rsds_mean_Wm2'); factors=he.merge(pm,on='month'); factors['k_POA']=factors.pvgis_poa_daily_mean/factors.historical_rsds_mean_Wm2; factors.to_csv(out/'MONTHLY_POA_AND_PEAK_FACTORS.csv',index=False)
    peak=factors.set_index('month').k_peak.to_dict(); pvd['poa_peak_proxy_Wm2']=pvd.poa_daily_mean_Wm2*pvd.month.map(peak); pvd['Tmodule_proxy_daily_max_C']=pvd.tair_daily_max_C+pvd.poa_peak_proxy_Wm2/(U0+U1*pvd.wind_daily_mean_ms)
    v=pvd[['Tmodule_proxy_daily_max_C','Tmodule_true_daily_max_C']].dropna(); err=v.iloc[:,0]-v.iloc[:,1]; MAE=np.mean(np.abs(err)); RMSE=np.sqrt(np.mean(err**2)); BIAS=np.mean(err); R2=np.corrcoef(v.iloc[:,0],v.iloc[:,1])[0,1]**2
    pd.DataFrame({'metric':['MAE_C','RMSE_C','Bias_C','R2'],'value':[MAE,RMSE,BIAS,R2]}).to_csv(out/'FAIMAN_DAILY_PROXY_VALIDATION.csv',index=False); pvd.to_csv(out/'PVGIS_DAILY_FAIMAN_VALIDATION_DATA.csv',index=False)
    poa=factors.set_index('month').k_POA.to_dict(); clim['poa_daily_mean_Wm2']=clim.rsds_Wm2*clim.month.map(poa); clim['poa_peak_proxy_Wm2']=clim.poa_daily_mean_Wm2*clim.month.map(peak); clim['Tmodule_max_proxy_C']=clim.tasmax_C+clim.poa_peak_proxy_Wm2/(U0+U1*clim.sfcWind_ms); clim['module_air_delta_C']=clim.Tmodule_max_proxy_C-clim.tasmax_C; clim['temp_power_factor']=1+GAMMA_P*(clim.Tmodule_max_proxy_C-25); clim['reversible_temp_loss_pct']=np.maximum(0,(1-clim.temp_power_factor)*100)
    clim=pd.concat([mark_heatwave(g) for _,g in clim.groupby(['model','scenario','period'],sort=False)],ignore_index=True)
    cols=['model','scenario','period','date','tasmax_C','rsds_Wm2','sfcWind_ms','poa_daily_mean_Wm2','poa_peak_proxy_Wm2','Tmodule_max_proxy_C','module_air_delta_C','reversible_temp_loss_pct','is_heatwave_day']; td=clim[cols].copy(); td.to_csv(out/'THERMAL_DAILY_STUTTGART.csv',index=False)
    sr=[]
    for (m,s,p),g in td.groupby(['model','scenario','period']):
        years=g.date.dt.year.nunique(); hw=g[g.is_heatwave_day]; nhw=g[~g.is_heatwave_day]
        sr.append({'model':m,'scenario':s,'period':p,'years':years,'mean_daily_Tmodule_max_proxy_C':g.Tmodule_max_proxy_C.mean(),'p95_Tmodule_max_proxy_C':g.Tmodule_max_proxy_C.quantile(.95),'absolute_max_Tmodule_C':g.Tmodule_max_proxy_C.max(),'mean_heatwave_Tmodule_C':hw.Tmodule_max_proxy_C.mean(),'mean_nonheatwave_Tmodule_C':nhw.Tmodule_max_proxy_C.mean(),'mean_heatwave_module_air_delta_C':hw.module_air_delta_C.mean(),'heatwave_thermal_loss_pct':hw.reversible_temp_loss_pct.mean(),'days_Tmodule_gt_50_per_year':(g.Tmodule_max_proxy_C>50).sum()/years,'days_Tmodule_gt_60_per_year':(g.Tmodule_max_proxy_C>60).sum()/years,'days_Tmodule_gt_70_per_year':(g.Tmodule_max_proxy_C>70).sum()/years})
    summary=pd.DataFrame(sr); summary.to_csv(out/'THERMAL_PERIOD_SUMMARY.csv',index=False)
    metrics=['mean_daily_Tmodule_max_proxy_C','p95_Tmodule_max_proxy_C','absolute_max_Tmodule_C','mean_heatwave_Tmodule_C','heatwave_thermal_loss_pct','days_Tmodule_gt_50_per_year','days_Tmodule_gt_60_per_year','days_Tmodule_gt_70_per_year']
    ch=[]
    for m in summary.model.unique():
        h=summary[(summary.model==m)&(summary.scenario=='historical')]
        if h.empty: continue
        h=h.iloc[0]
        for _,r in summary[(summary.model==m)&(summary.scenario!='historical')].iterrows():
            o={'model':m,'scenario':r.scenario,'period':r.period}
            for k in metrics: o[k+'_historical']=h[k]; o[k+'_future']=r[k]; o[k+'_change']=r[k]-h[k]
            ch.append(o)
    pd.DataFrame(ch).to_csv(out/'THERMAL_CHANGE_FROM_HISTORICAL.csv',index=False)
    ens=summary[summary.scenario!='historical'].groupby(['scenario','period']).agg(mean_heatwave_Tmodule_C=('mean_heatwave_Tmodule_C','mean'),mean_absolute_max_Tmodule_C=('absolute_max_Tmodule_C','mean'),heatwave_thermal_loss_pct=('heatwave_thermal_loss_pct','mean'),days_gt50_per_year=('days_Tmodule_gt_50_per_year','mean'),days_gt60_per_year=('days_Tmodule_gt_60_per_year','mean'),days_gt70_per_year=('days_Tmodule_gt_70_per_year','mean')).reset_index(); ens.to_csv(out/'THERMAL_ENSEMBLE_SUMMARY.csv',index=False)
    pd.DataFrame({'item':['climate_rows','pvgis_hourly_rows','pvgis_daily_rows','thermal_missing_values','validation_MAE_C','validation_RMSE_C','validation_Bias_C','validation_R2'],'value':[len(clim),len(pv),len(pvd),clim.Tmodule_max_proxy_C.isna().sum(),MAE,RMSE,BIAS,R2]}).to_csv(out/'THERMAL_QC_SUMMARY.csv',index=False)
    (out/'THERMAL_METHOD_AND_ASSUMPTIONS.txt').write_text(f'Faiman: Tmodule = Tair + Gpoa/(U0+U1*wind), U0={U0}, U1={U1}. Daily future data imply Tmodule_max_proxy_C is a daily-maximum proxy. PVGIS hourly data provide monthly POA/peak scaling and validation. Heatwave={HW_THRESHOLD}C for >= {HW_MIN_DAYS} days.')
    print(f'Validation MAE={MAE:.2f} C RMSE={RMSE:.2f} C Bias={BIAS:.2f} C R2={R2:.3f}')

if __name__=='__main__': main()
