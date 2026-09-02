from pathlib import Path
import argparse
import numpy as np
import pandas as pd

U0=25.0
U1=6.84
GAMMA=-0.004
EA=0.89
KB=8.617333262e-5
RD0=0.66
PVGIS_BASE_YIELD=1101.778297
IEA_GWP=35.8
IEA_YIELD=976.0
IEA_RD=0.7
SHARE_MODULE=.56
SHARE_INVERTER=.28
SHARE_OTHER=.16
HORIZON=30


def read_pvgis(path):
    lines=Path(path).read_text(encoding='utf-8',errors='ignore').splitlines()
    idx=next((i for i,x in enumerate(lines) if x.startswith('time,')),None)
    if idx is None: raise ValueError('PVGIS hourly header not found')
    pv=pd.read_csv(path,skiprows=idx,low_memory=False)
    pv=pv[pv['time'].astype(str).str.match(r'^\d{8}:\d{4}$',na=False)].copy()
    pv['datetime']=pd.to_datetime(pv.time,format='%Y%m%d:%H%M',errors='coerce')
    for c in ['P','Gb(i)','Gd(i)','Gr(i)','T2m','WS10m']:
        pv[c]=pd.to_numeric(pv[c],errors='coerce')
    return pv.dropna(subset=['datetime','Gb(i)','Gd(i)','Gr(i)','T2m','WS10m'])


def service_life(rd_pct,threshold=20,max_years=30):
    y=np.arange(1,max_years+1)
    return int((rd_pct*(y-1)<threshold).sum())


def degraded_generation(yield0,rd_pct,years):
    rd=rd_pct/100
    return sum(yield0*max(1-rd*(n-1),0) for n in range(1,int(years)+1))


def system_generation(yield0,rd_pct,life,horizon=30):
    rem=horizon; total=0.0; units=0
    while rem>0:
        units+=1; yrs=min(int(life),rem)
        total+=degraded_generation(yield0,rd_pct,yrs)
        rem-=yrs
    return total,units


def lca_constants():
    ref_gen=sum(IEA_YIELD*(1-IEA_RD/100*(n-1)) for n in range(1,31))
    total=IEA_GWP*ref_gen/1000
    return total,total*SHARE_MODULE,total*SHARE_INVERTER,total*SHARE_OTHER


def main():
    ap=argparse.ArgumentParser(description='Hourly temporal validation and calibration.')
    ap.add_argument('--pvgis',required=True)
    ap.add_argument('--thermal',required=True,help='THERMAL_DAILY_STUTTGART.csv')
    ap.add_argument('--out',default='processed/08_Extended_Validation')
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    pv=read_pvgis(args.pvgis)
    pv['POA']=pv['Gb(i)']+pv['Gd(i)']+pv['Gr(i)']
    pv['Tmod']=pv['T2m']+pv['POA']/(U0+U1*pv['WS10m'])
    pv['stress_hourly']=np.exp(-EA/(KB*(pv['Tmod']+273.15)))
    pv['fT_uncapped']=1+GAMMA*(pv['Tmod']-25)
    pv['fT_capped']=np.minimum(1,pv['fT_uncapped'])
    pv['energy_hourly_uncapped']=pv['POA']*pv['fT_uncapped']
    pv['energy_hourly_capped']=pv['POA']*pv['fT_capped']
    pv['date']=pv['datetime'].dt.floor('D'); pv['year']=pv.datetime.dt.year; pv['month']=pv.datetime.dt.month; pv['hour']=pv.datetime.dt.hour

    # Daily coincident reference and extrema timing.
    rows=[]
    for d,g in pv.groupby('date'):
        i_air=g['T2m'].idxmax(); i_poa=g['POA'].idxmax(); i_tm=g['Tmod'].idxmax()
        rows.append({
            'date':d,'year':d.year,'month':d.month,
            'tair_max_C':g.loc[i_air,'T2m'],'poa_max_Wm2':g.loc[i_poa,'POA'],
            'Tmod_true_max_C':g.loc[i_tm,'Tmod'],'hour_airmax':int(g.loc[i_air,'hour']),
            'hour_poamax':int(g.loc[i_poa,'hour']),'hour_Tmodmax':int(g.loc[i_tm,'hour']),
            'wind_at_Tmodmax_ms':g.loc[i_tm,'WS10m'],'POA_at_Tmodmax_Wm2':g.loc[i_tm,'POA'],
            'wind_daily_mean_ms':g.WS10m.mean(),'poa_daily_mean_Wm2':g.POA.mean(),
            'stress_hourly_mean':g.stress_hourly.mean(),
            'energy_hourly_uncapped':g.energy_hourly_uncapped.sum(),
            'energy_hourly_capped':g.energy_hourly_capped.sum(),
        })
    daily=pd.DataFrame(rows)
    mpeak=daily.groupby('month').agg(mean_poa=('poa_daily_mean_Wm2','mean'),mean_poa_max=('poa_max_Wm2','mean')).reset_index()
    mpeak['k_peak']=mpeak.mean_poa_max/mpeak.mean_poa
    kpeak=dict(zip(mpeak.month,mpeak.k_peak))
    daily['poa_peak_proxy_Wm2']=daily.poa_daily_mean_Wm2*daily.month.map(kpeak)
    daily['Tmod_proxy_C']=daily.tair_max_C+daily.poa_peak_proxy_Wm2/(U0+U1*daily.wind_daily_mean_ms)
    daily['stress_proxy']=np.exp(-EA/(KB*(daily.Tmod_proxy_C+273.15)))
    daily['Teq_C']=-EA/(KB*np.log(daily.stress_hourly_mean))-273.15
    daily['fT_daily_existing']=np.minimum(1,1+GAMMA*(daily.Tmod_proxy_C-25))
    daily['energy_daily_existing']=daily.poa_daily_mean_Wm2*24*daily.fT_daily_existing
    daily.to_csv(out/'PVGIS_HOURLY_VS_DAILY_VALIDATION_DAILY.csv',index=False)

    ratio=daily.stress_proxy.mean()/daily.stress_hourly_mean.mean()
    relbias=(ratio-1)*100
    r=np.corrcoef(daily.stress_proxy,daily.stress_hourly_mean)[0,1]
    arr=pd.DataFrame({'metric':['proxy_to_hourly_mean_ratio','relative_bias_pct','daily_Pearson_r','daily_Pearson_r2','median_proxy_to_hourly_ratio','mean_equiv_damage_T_C','mean_proxy_T_C','mean_equiv_minus_proxy_C','RMSE_equiv_vs_proxy_C'],
                      'value':[ratio,relbias,r,r*r,np.median(daily.stress_proxy/daily.stress_hourly_mean),daily.Teq_C.mean(),daily.Tmod_proxy_C.mean(),(daily.Teq_C-daily.Tmod_proxy_C).mean(),np.sqrt(np.mean((daily.Teq_C-daily.Tmod_proxy_C)**2))]})
    arr.to_csv(out/'HOURLY_ARRHENIUS_VALIDATION.csv',index=False)

    timing=pd.DataFrame({'metric':['airTmax_and_POAmax_same_hour_pct','airTmax_and_Tmodmax_same_hour_pct','POAmax_and_Tmodmax_same_hour_pct','median_abs_hour_difference_airTmax_POAmax','median_abs_hour_difference_airTmax_Tmodmax','median_abs_hour_difference_POAmax_Tmodmax','mean_wind_at_true_Tmodmax_ms','mean_daily_wind_ms','mean_difference_dailymeanWind_minus_windAtTmodmax_ms','mean_POA_at_true_Tmodmax_Wm2','mean_daily_POAmax_Wm2','mean_ratio_POAatTmodmax_to_dailyPOAmax'],
        'value':[
            (daily.hour_airmax==daily.hour_poamax).mean()*100,(daily.hour_airmax==daily.hour_Tmodmax).mean()*100,(daily.hour_poamax==daily.hour_Tmodmax).mean()*100,
            np.median(abs(daily.hour_airmax-daily.hour_poamax)),np.median(abs(daily.hour_airmax-daily.hour_Tmodmax)),np.median(abs(daily.hour_poamax-daily.hour_Tmodmax)),
            daily.wind_at_Tmodmax_ms.mean(),daily.wind_daily_mean_ms.mean(),(daily.wind_daily_mean_ms-daily.wind_at_Tmodmax_ms).mean(),daily.POA_at_Tmodmax_Wm2.mean(),daily.poa_max_Wm2.mean(),(daily.POA_at_Tmodmax_Wm2/daily.poa_max_Wm2.replace(0,np.nan)).mean()]})
    timing.to_csv(out/'TEMPORAL_COINCIDENCE_METRICS.csv',index=False)
    e=daily.Tmod_proxy_C-daily.Tmod_true_max_C
    pd.DataFrame({'metric':['MAE_C','RMSE_C','Bias_C','Pearson_r2'],'value':[abs(e).mean(),np.sqrt((e**2).mean()),e.mean(),np.corrcoef(daily.Tmod_proxy_C,daily.Tmod_true_max_C)[0,1]**2]}).to_csv(out/'TEMPERATURE_PROXY_METRICS.csv',index=False)

    annual=daily.groupby('year').agg(existing=('energy_daily_existing','sum'),hourly_capped=('energy_hourly_capped','sum'),hourly_uncapped=('energy_hourly_uncapped','sum')).reset_index()
    for c in ['existing','hourly_capped','hourly_uncapped']:
        annual[c+'_ratio']=annual[c]/annual[c].mean()
    annual['existing_minus_hourly_uncapped_ratio_pct']=(annual.existing_ratio/annual.hourly_uncapped_ratio-1)*100
    annual['existing_minus_hourly_capped_ratio_pct']=(annual.existing_ratio/annual.hourly_capped_ratio-1)*100
    annual.to_csv(out/'ANNUAL_ENERGY_INDEX_VALIDATION.csv',index=False)
    pd.DataFrame({'metric':['mean_existing_vs_hourly_uncapped_absolute_level_ratio','mean_existing_vs_hourly_capped_absolute_level_ratio','annual_ratio_RMSE_existing_vs_hourly_uncapped_pct','annual_ratio_max_abs_error_existing_vs_hourly_uncapped_pct','annual_ratio_corr_existing_vs_hourly_uncapped','annual_ratio_RMSE_existing_vs_hourly_capped_pct','mean_hourly_uncapped_gain_vs_capped_pct'],
                  'value':[annual.existing.mean()/annual.hourly_uncapped.mean(),annual.existing.mean()/annual.hourly_capped.mean(),np.sqrt(np.mean(annual.existing_minus_hourly_uncapped_ratio_pct**2)),abs(annual.existing_minus_hourly_uncapped_ratio_pct).max(),np.corrcoef(annual.existing_ratio,annual.hourly_uncapped_ratio)[0,1],np.sqrt(np.mean(annual.existing_minus_hourly_capped_ratio_pct**2)),(annual.hourly_uncapped.sum()/annual.hourly_capped.sum()-1)*100]}).to_csv(out/'ENERGY_INDEX_METRICS.csv',index=False)

    # Monthly correction factors derived from hourly reference.
    mf=daily.groupby('month').agg(mean_Teq=('Teq_C','mean'),mean_Tproxy=('Tmod_proxy_C','mean'),mean_stress_hourly=('stress_hourly_mean','mean'),mean_stress_proxy=('stress_proxy','mean'),mean_energy_hourly_uncapped=('energy_hourly_uncapped','mean'),mean_energy_hourly_capped=('energy_hourly_capped','mean'),mean_energy_daily_existing=('energy_daily_existing','mean')).reset_index()
    mf['Teq_offset_C']=mf.mean_Teq-mf.mean_Tproxy
    mf['stress_multiplier']=mf.mean_stress_hourly/mf.mean_stress_proxy
    mf['energy_multiplier_uncapped']=mf.mean_energy_hourly_uncapped/mf.mean_energy_daily_existing
    mf['energy_multiplier_capped']=mf.mean_energy_hourly_capped/mf.mean_energy_daily_existing
    mf.to_csv(out/'MONTHLY_HOURLY_CORRECTION_FACTORS.csv',index=False)

    # Apply monthly calibration to climate daily series; historical normalization makes the absolute level irrelevant.
    th=pd.read_csv(args.thermal,low_memory=False); th['date']=pd.to_datetime(th.date); th['month']=th.date.dt.month
    th['is_heatwave_day']=th.is_heatwave_day.astype(str).str.lower().isin(['true','1','yes'])
    th['stress_original']=np.exp(-EA/(KB*(pd.to_numeric(th.Tmodule_max_proxy_C)+273.15)))
    sm=dict(zip(mf.month,mf.stress_multiplier)); em=dict(zip(mf.month,mf.energy_multiplier_uncapped))
    th['stress_hourlycal']=th.stress_original*th.month.map(sm)
    # reconstruct existing energy index from daily thermal file
    f_existing=np.minimum(1,1+GAMMA*(pd.to_numeric(th.Tmodule_max_proxy_C)-25))
    th['energy_existing']=pd.to_numeric(th.poa_daily_mean_Wm2)*24*f_existing
    th['energy_hourlycal']=th.energy_existing*th.month.map(em)
    th.to_csv(out/'HOURLY_CALIBRATED_DAILY.csv',index=False)

    # Model-period calibrated AF/yield ratios and propagated base-case lifetime/GWP.
    period=th.groupby(['model','scenario','period']).agg(stress_original=('stress_original','mean'),stress_hourlycal=('stress_hourlycal','mean'),energy_existing=('energy_existing','sum'),energy_hourlycal=('energy_hourlycal','sum')).reset_index()
    # use annualized energy by dividing period total by number of distinct years, important for differing calendar lengths
    years=th.assign(year=th.date.dt.year).groupby(['model','scenario','period']).year.nunique().reset_index(name='nyears')
    period=period.merge(years,on=['model','scenario','period'])
    period['energy_existing']=period.energy_existing/period.nyears
    period['energy_hourlycal']=period.energy_hourlycal/period.nyears
    h=period[period.scenario=='historical'][['model','stress_original','stress_hourlycal','energy_existing','energy_hourlycal']].rename(columns={c:'hist_'+c for c in ['stress_original','stress_hourlycal','energy_existing','energy_hourlycal']})
    period=period.merge(h,on='model')
    period['AF_stress_original']=period.stress_original/period.hist_stress_original
    period['AF_stress_hourlycal']=period.stress_hourlycal/period.hist_stress_hourlycal
    period['YR_energy_existing']=period.energy_existing/period.hist_energy_existing
    period['YR_energy_hourlycal']=period.energy_hourlycal/period.hist_energy_hourlycal

    total_burden,mod_burden,inv_burden,other_burden=lca_constants()
    propagated=[]
    for _,r0 in period.iterrows():
        row=r0.to_dict()
        for label,afc,yrc in [('original','AF_stress_original','YR_energy_existing'),('hourlycal','AF_stress_hourlycal','YR_energy_hourlycal')]:
            af=float(r0[afc]); rd=RD0*af; life=service_life(rd); Y=PVGIS_BASE_YIELD*float(r0[yrc]); gen,units=system_generation(Y,rd,life)
            meq=max(1,30/life)
            gwpi=(units*mod_burden+inv_burden+other_burden)*1000/gen
            gwpr=(meq*mod_burden+inv_burden+other_burden)*1000/gen
            row[f'Rd_{label}']=rd; row[f'life_{label}']=life; row[f'Y_{label}']=Y; row[f'gen_{label}']=gen; row[f'units_{label}']=units; row[f'gwp_integer_{label}']=gwpi; row[f'meq_residual_{label}']=meq; row[f'gwp_residual_{label}']=gwpr
        propagated.append(row)
    pr=pd.DataFrame(propagated)
    pr.to_csv(out/'HOURLY_CALIBRATED_PERIOD_RESULTS.csv',index=False)

    ens=[]
    for case in ['original','hourlycal']:
      for allocation in ['integer','residual']:
        for (s,p),g in pr[pr.scenario!='historical'].groupby(['scenario','period']):
            gwpcol=f'gwp_{allocation}_{case}'; afcol=f'AF_stress_{case}'; rdcol=f'Rd_{case}'; lcol=f'life_{case}'; yrcol='YR_energy_existing' if case=='original' else 'YR_energy_hourlycal'
            hist_gwp=pr[pr.scenario=='historical'][gwpcol].mean()
            vals=(g[gwpcol]/hist_gwp-1)*100
            ens.append({'case':case,'allocation':allocation,'scenario':s,'period':p,'AF_mean':g[afcol].mean(),'Rd_mean':g[rdcol].mean(),'life_mean':g[lcol].mean(),'life_min':g[lcol].min(),'life_max':g[lcol].max(),'yield_ratio_mean':g[yrcol].mean(),'GWP_mean':g[gwpcol].mean(),'GWP_min':g[gwpcol].min(),'GWP_max':g[gwpcol].max(),'GWP_change_pct_mean':vals.mean(),'GWP_change_pct_min':vals.min(),'GWP_change_pct_max':vals.max()})
    pd.DataFrame(ens).to_csv(out/'HOURLY_CALIBRATED_ENSEMBLE.csv',index=False)
    (out/'TEMPORAL_VALIDATION_METHOD_NOTE.txt').write_text(
        'Hourly PVGIS data are used only as an aggregation benchmark/calibration reference. The comparison is not validation against measured module temperature. '
        'Daily-max Arrhenius stress substantially overstates absolute integrated stress; monthly correction factors are therefore applied to both historical and future daily proxy stress before model-specific normalization. '
        'The corrected relative future/historical AF is the quantity propagated in the extended temporal-aggregation sensitivity. Energy validation compares the existing daily index with hourly irradiance-temperature covariance, with capped and uncapped temperature factors.\n',encoding='utf-8')
    print('Done:',out)

if __name__=='__main__':
    main()
