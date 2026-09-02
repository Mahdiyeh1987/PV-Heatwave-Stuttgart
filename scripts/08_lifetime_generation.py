from pathlib import Path
import argparse, numpy as np, pandas as pd
SYSTEM_HORIZON_YR=30

def read_pvgis(path):
    lines=Path(path).read_text(encoding='utf-8',errors='ignore').splitlines(); idx=next((i for i,x in enumerate(lines) if x.startswith('time,')),None)
    if idx is None: raise ValueError('PVGIS hourly header not found')
    pv=pd.read_csv(path,skiprows=idx,low_memory=False); pv=pv[pv.time.astype(str).str.match(r'^\d{8}:\d{4}$',na=False)].copy(); pv['datetime']=pd.to_datetime(pv.time,format='%Y%m%d:%H%M',errors='coerce'); return pv.dropna(subset=['datetime'])

def degraded_generation(yield0,rd_pct,years):
    rd=rd_pct/100; return sum(yield0*max(1-rd*(n-1),0) for n in range(1,int(round(years))+1))

def system_generation(yield0,rd_pct,life,horizon=30):
    life=int(round(life)); rem=horizon; total=0; units=0
    while rem>0:
        units+=1; yrs=min(life,rem); total+=degraded_generation(yield0,rd_pct,yrs); rem-=yrs
    return total,units-1

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--thermal',required=True); ap.add_argument('--degradation',required=True); ap.add_argument('--pvgis',required=True); ap.add_argument('--out',default='processed/05_Lifetime_Electricity_Generation'); args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    th=pd.read_csv(args.thermal,low_memory=False); th['date']=pd.to_datetime(th.date); th['year']=th.date.dt.year; deg=pd.read_csv(args.degradation)
    pv=read_pvgis(args.pvgis); pv['P']=pd.to_numeric(pv.P,errors='coerce'); pv=pv.dropna(subset=['P']); pv['year']=pv.datetime.dt.year; py=pv.groupby('year').P.sum().div(1000).reset_index(name='annual_yield_kWh_per_kWp'); base=py.annual_yield_kWh_per_kWp.mean(); sd=py.annual_yield_kWh_per_kWp.std(); py.to_csv(out/'PVGIS_BASELINE_ANNUAL_YIELD.csv',index=False)
    th['thermal_performance_factor']=(1-th.reversible_temp_loss_pct.fillna(0)/100).clip(0,1); th['daily_climate_energy_index']=th.poa_daily_mean_Wm2*24*th.thermal_performance_factor
    ai=th.groupby(['model','scenario','period','year']).agg(annual_energy_index=('daily_climate_energy_index','sum'),mean_Tmodule_C=('Tmodule_max_proxy_C','mean'),mean_reversible_loss_pct=('reversible_temp_loss_pct','mean')).reset_index(); hi=ai[ai.scenario=='historical'].groupby('model').annual_energy_index.mean().reset_index(name='historical_mean_energy_index'); ai=ai.merge(hi,on='model'); ai['climate_yield_ratio_vs_historical']=ai.annual_energy_index/ai.historical_mean_energy_index; ai['climate_adjusted_yield_kWh_per_kWp']=base*ai.climate_yield_ratio_vs_historical; ai.to_csv(out/'CLIMATE_ANNUAL_YIELD.csv',index=False)
    pyld=ai.groupby(['model','scenario','period']).agg(mean_annual_yield_kWh_per_kWp=('climate_adjusted_yield_kWh_per_kWp','mean'),annual_yield_sd_kWh_per_kWp=('climate_adjusted_yield_kWh_per_kWp','std'),mean_yield_ratio_vs_historical=('climate_yield_ratio_vs_historical','mean'),mean_reversible_loss_pct=('mean_reversible_loss_pct','mean'),mean_Tmodule_C=('mean_Tmodule_C','mean')).reset_index(); pyld['annual_yield_change_vs_PVGIS_pct']=(pyld.mean_annual_yield_kWh_per_kWp/base-1)*100; pyld.to_csv(out/'CLIMATE_PERIOD_YIELD_SUMMARY.csv',index=False)
    res=pyld.merge(deg[['model','scenario','period','mean_degradation_rate_pct_per_year','service_life_years','replacement_count_within_30y']],on=['model','scenario','period'])
    res['single_module_lifetime_generation_kWh_per_kWp']=[degraded_generation(r.mean_annual_yield_kWh_per_kWp,r.mean_degradation_rate_pct_per_year,r.service_life_years) for _,r in res.iterrows()]
    res['fixed30_no_replacement_generation_kWh_per_kWp']=[degraded_generation(r.mean_annual_yield_kWh_per_kWp,r.mean_degradation_rate_pct_per_year,SYSTEM_HORIZON_YR) for _,r in res.iterrows()]
    pairs=[system_generation(r.mean_annual_yield_kWh_per_kWp,r.mean_degradation_rate_pct_per_year,r.service_life_years,SYSTEM_HORIZON_YR) for _,r in res.iterrows()]; res['system30_generation_with_replacements_kWh_per_kWp']=[x[0] for x in pairs]; res['calculated_replacements_30y']=[x[1] for x in pairs]; res['module_units_required_30y']=res.calculated_replacements_30y+1; res['ideal_no_degradation_30y_kWh_per_kWp']=res.mean_annual_yield_kWh_per_kWp*SYSTEM_HORIZON_YR; res['degradation_generation_penalty_30y_pct']=(1-res.system30_generation_with_replacements_kWh_per_kWp/res.ideal_no_degradation_30y_kWh_per_kWp)*100; res.to_csv(out/'LIFETIME_GENERATION_PERIOD_SUMMARY.csv',index=False)
    ch=[]
    for m in res.model.unique():
        h=res[(res.model==m)&(res.scenario=='historical')].iloc[0]
        for _,r in res[(res.model==m)&(res.scenario!='historical')].iterrows(): ch.append({'model':m,'scenario':r.scenario,'period':r.period,'annual_yield_change_pct':(r.mean_annual_yield_kWh_per_kWp/h.mean_annual_yield_kWh_per_kWp-1)*100,'single_module_lifetime_generation_change_pct':(r.single_module_lifetime_generation_kWh_per_kWp/h.single_module_lifetime_generation_kWh_per_kWp-1)*100,'system30_generation_change_pct':(r.system30_generation_with_replacements_kWh_per_kWp/h.system30_generation_with_replacements_kWh_per_kWp-1)*100,'service_life_change_years':r.service_life_years-h.service_life_years,'additional_module_units_30y':r.module_units_required_30y-h.module_units_required_30y})
    pd.DataFrame(ch).to_csv(out/'LIFETIME_GENERATION_CHANGE_FROM_HISTORICAL.csv',index=False)
    res.groupby(['scenario','period']).agg(annual_yield_kWh_per_kWp_mean=('mean_annual_yield_kWh_per_kWp','mean'),annual_yield_kWh_per_kWp_std=('mean_annual_yield_kWh_per_kWp','std'),service_life_years_mean=('service_life_years','mean'),single_module_lifetime_generation_mean=('single_module_lifetime_generation_kWh_per_kWp','mean'),system30_generation_with_replacements_mean=('system30_generation_with_replacements_kWh_per_kWp','mean'),system30_generation_with_replacements_std=('system30_generation_with_replacements_kWh_per_kWp','std'),module_units_required_30y_mean=('module_units_required_30y','mean'),degradation_generation_penalty_30y_pct_mean=('degradation_generation_penalty_30y_pct','mean')).reset_index().to_csv(out/'LIFETIME_GENERATION_ENSEMBLE_SUMMARY.csv',index=False)
    pd.DataFrame({'item':['thermal_rows','PVGIS_hourly_rows','PVGIS_years','PVGIS_mean_annual_yield_kWh_per_kWp','PVGIS_annual_yield_SD','scenario_rows','missing_period_yields','missing_degradation_rates','missing_service_life'],'value':[len(th),len(pv),py.year.nunique(),base,sd,len(res),res.mean_annual_yield_kWh_per_kWp.isna().sum(),res.mean_degradation_rate_pct_per_year.isna().sum(),res.service_life_years.isna().sum()]}).to_csv(out/'LIFETIME_GENERATION_QC_SUMMARY.csv',index=False)
    (out/'LIFETIME_GENERATION_METHOD_AND_ASSUMPTIONS.txt').write_text('Absolute yield is anchored to PVGIS Stuttgart hourly P. Future annual yield uses a CMIP6/PVGIS-calibrated relative energy index. Annual module-year generation: En=Yclimate*[1-Rd*(n-1)]. Outputs include single-module lifetime generation and a fixed 30-year system horizon with integer module replacement.')
    print(f'PVGIS baseline={base:.1f} kWh/kWp/yr -> {out}')

if __name__=='__main__': main()
