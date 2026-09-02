from pathlib import Path
import argparse
import numpy as np
import pandas as pd

U0=25.0; U1=6.84; KB=8.617333262e-5
PVGIS_BASE_YIELD=1101.778297
IEA_GWP=35.8; IEA_YIELD=976.0; IEA_RD=0.7
SHARE_MODULE=.56; SHARE_INVERTER=.28; SHARE_OTHER=.16
HORIZON=30; EOL=20
DURABILITY={
    'Base':(0.66,0.89),
    'Optimistic_1':(0.40,1.10),
    'Optimistic_2':(0.40,0.89),
    'Optimistic_3':(0.66,0.79),
    'Pessimistic':(0.80,0.89),
}


def read_pvgis(path):
    lines=Path(path).read_text(encoding='utf-8',errors='ignore').splitlines()
    idx=next(i for i,x in enumerate(lines) if x.startswith('time,'))
    pv=pd.read_csv(path,skiprows=idx,low_memory=False)
    pv=pv[pv.time.astype(str).str.match(r'^\d{8}:\d{4}$',na=False)].copy()
    pv['datetime']=pd.to_datetime(pv.time,format='%Y%m%d:%H%M',errors='coerce')
    for c in ['Gb(i)','Gd(i)','Gr(i)','T2m','WS10m']:
        pv[c]=pd.to_numeric(pv[c],errors='coerce')
    pv=pv.dropna(subset=['datetime','Gb(i)','Gd(i)','Gr(i)','T2m','WS10m'])
    pv['POA']=pv['Gb(i)']+pv['Gd(i)']+pv['Gr(i)']
    pv['Tmod']=pv.T2m+pv.POA/(U0+U1*pv.WS10m)
    pv['date']=pv.datetime.dt.floor('D'); pv['month']=pv.datetime.dt.month
    return pv


def service_life(rd):
    y=np.arange(1,HORIZON+1)
    return int((rd*(y-1)<EOL).sum())


def generation(Y,rd,life):
    rem=HORIZON; total=0.0
    while rem>0:
        yrs=min(life,rem)
        total += sum(Y*max(1-rd/100*(n-1),0) for n in range(1,yrs+1))
        rem-=yrs
    return total


def burdens():
    refgen=sum(IEA_YIELD*(1-IEA_RD/100*(n-1)) for n in range(1,31))
    total=IEA_GWP*refgen/1000
    return total*SHARE_MODULE,total*SHARE_INVERTER,total*SHARE_OTHER


def monthly_stress_multiplier(pv,ea,kpeak):
    pv=pv.copy(); pv['stress']=np.exp(-ea/(KB*(pv.Tmod+273.15)))
    hs=pv.groupby(['date','month']).stress.mean().reset_index(name='stress_hourly_mean')
    d=pv.groupby('date').agg(poa_mean=('POA','mean'),tairmax=('T2m','max'),windmean=('WS10m','mean')).reset_index(); d['month']=d.date.dt.month
    d['Tproxy']=d.tairmax+d.poa_mean*d.month.map(kpeak)/(U0+U1*d.windmean)
    d['stress_proxy']=np.exp(-ea/(KB*(d.Tproxy+273.15)))
    d=d.merge(hs,on=['date','month'])
    m=d.groupby('month').agg(sh=('stress_hourly_mean','mean'),sp=('stress_proxy','mean'))
    return (m.sh/m.sp).to_dict()


def main():
    ap=argparse.ArgumentParser(description='Factorial structural uncertainty propagation.')
    ap.add_argument('--pvgis',required=True)
    ap.add_argument('--thermal',required=True)
    ap.add_argument('--period-results',required=True,help='HOURLY_CALIBRATED_PERIOD_RESULTS.csv from script 11')
    ap.add_argument('--out',default='processed/08_Extended_Validation')
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    pv=read_pvgis(args.pvgis)
    # k_peak exactly as in the daily thermal proxy benchmark
    d=pv.groupby('date').agg(poa_mean=('POA','mean'),poa_max=('POA','max')).reset_index(); d['month']=d.date.dt.month
    km=d.groupby('month').agg(a=('poa_mean','mean'),b=('poa_max','mean')); kpeak=(km.b/km.a).to_dict()

    th=pd.read_csv(args.thermal,low_memory=False); th['date']=pd.to_datetime(th.date); th['month']=th.date.dt.month
    periods=pd.read_csv(args.period_results,low_memory=False)
    mod_b,inv_b,other_b=burdens()

    # Direct climate-forcing checks for irradiance and wind.
    clim_rows=[]
    for model in sorted(th.model.unique()):
        hist=th[(th.model==model)&(th.scenario=='historical')]
        h_rs=hist.rsds_Wm2.mean(); h_w=hist.sfcWind_ms.mean()
        h_rs95=np.percentile(hist.rsds_Wm2,95); h_w95=np.percentile(hist.sfcWind_ms,95)
        for (sc,pe),g in th[(th.model==model)&(th.scenario!='historical')].groupby(['scenario','period']):
            clim_rows.append({'model':model,'scenario':sc,'period':pe,
                'rsds_change_pct':(g.rsds_Wm2.mean()/h_rs-1)*100,
                'wind_change_pct':(g.sfcWind_ms.mean()/h_w-1)*100,
                'p95_rsds_change_pct':(np.percentile(g.rsds_Wm2,95)/h_rs95-1)*100,
                'p95_wind_change_pct':(np.percentile(g.sfcWind_ms,95)/h_w95-1)*100})
    pd.DataFrame(clim_rows).to_csv(out/'CLIMATE_FORCING_RSDS_WIND_CHANGES.csv',index=False)


    # Yield ratios from the base temporal validation are independent of durability parameters.
    yr=periods[['model','scenario','period','YR_energy_existing','YR_energy_hourlycal']].copy()

    allrows=[]
    for dname,(rd0,ea) in DURABILITY.items():
        mult=monthly_stress_multiplier(pv,ea,kpeak)
        t=th[['model','scenario','period','date','month','Tmodule_max_proxy_C']].copy()
        t['stress_dailymax']=np.exp(-ea/(KB*(pd.to_numeric(t.Tmodule_max_proxy_C)+273.15)))
        t['stress_hourlycal']=t.stress_dailymax*t.month.map(mult)
        ps=t.groupby(['model','scenario','period']).agg(daily_max=('stress_dailymax','mean'),hourly_calibrated=('stress_hourlycal','mean')).reset_index()
        h=ps[ps.scenario=='historical'][['model','daily_max','hourly_calibrated']].rename(columns={'daily_max':'hist_daily_max','hourly_calibrated':'hist_hourly_calibrated'})
        ps=ps.merge(h,on='model').merge(yr,on=['model','scenario','period'])
        ps['AF_daily_max']=ps.daily_max/ps.hist_daily_max
        ps['AF_hourly_calibrated']=ps.hourly_calibrated/ps.hist_hourly_calibrated

        for _,r in ps.iterrows():
            for thermal_case,afcol in [('daily_max','AF_daily_max'),('hourly_calibrated','AF_hourly_calibrated')]:
                AF=float(r[afcol]); rd=rd0*AF; life=service_life(rd)
                for yield_case,yrcol in [('original','YR_energy_existing'),('hourlycal','YR_energy_hourlycal')]:
                    Y=PVGIS_BASE_YIELD*float(r[yrcol]); gen=generation(Y,rd,life)
                    for alloc in ['integer','residual']:
                        meq=float(np.ceil(HORIZON/life)) if alloc=='integer' else max(1,HORIZON/life)
                        gwp=(meq*mod_b+inv_b+other_b)*1000/gen
                        allrows.append({'thermal_case':thermal_case,'durability_case':dname,'yield_case':yield_case,'allocation_case':alloc,'model':r.model,'scenario':r.scenario,'period':r.period,'AF':AF,'Rd':rd,'life':life,'Y':Y,'GWP':gwp})

    fac=pd.DataFrame(allrows)
    # Historical-conditioned change metrics for each structural combination and model.
    key=['thermal_case','durability_case','yield_case','allocation_case','model']
    hist=fac[fac.scenario=='historical'][key+['Rd','life','Y','GWP']].rename(columns={'Rd':'hist_Rd','life':'hist_life','Y':'hist_Y','GWP':'hist_GWP'})
    fac=fac.merge(hist,on=key,how='left')
    fac['GWP_change_pct']=(fac.GWP/fac.hist_GWP-1)*100
    fac['life_change_y']=fac.life-fac.hist_life
    fac['Rd_change']=fac.Rd-fac.hist_Rd
    fac['yield_change_pct']=(fac.Y/fac.hist_Y-1)*100
    fac.to_csv(out/'JOINT_FACTORIAL_UNCERTAINTY.csv',index=False)

    fut=fac[fac.scenario!='historical']
    env=fut.groupby(['scenario','period']).agg(Rd_min=('Rd','min'),Rd_max=('Rd','max'),life_min=('life','min'),life_max=('life','max'),life_change_min=('life_change_y','min'),life_change_max=('life_change_y','max'),yield_change_min_pct=('yield_change_pct','min'),yield_change_max_pct=('yield_change_pct','max'),GWP_min=('GWP','min'),GWP_max=('GWP','max'),GWP_change_min_pct=('GWP_change_pct','min'),GWP_change_max_pct=('GWP_change_pct','max')).reset_index()
    env.to_csv(out/'JOINT_FACTORIAL_SCENARIO_ENVELOPE.csv',index=False)
    (out/'JOINT_UNCERTAINTY_METHOD_NOTE.txt').write_text(
        'This is a factorial structural scenario envelope, not a probabilistic Monte Carlo interval. It jointly varies GCM, temporal thermal treatment (daily maximum versus hourly-calibrated), '
        'durability parameter set, annual-yield treatment (original daily index versus hourly-calibrated uncapped covariance correction), and replacement accounting (integer versus residual-service-life allocation). '
        'No probability distributions are assigned because defensible distributions are not available for all parameters.\n',encoding='utf-8')
    print('Done:',out)

if __name__=='__main__': main()
