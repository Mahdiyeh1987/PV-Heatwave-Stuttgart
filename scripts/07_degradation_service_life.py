from pathlib import Path
import argparse, numpy as np, pandas as pd
K_B=8.617333262e-5; RD0_BASE=0.66; EA_BASE=0.89; EOL_THRESHOLD=20.0; DESIGN_LIFE=30
SCENARIOS={'Base':(0.66,0.89),'Optimistic_1':(0.40,1.10),'Optimistic_2':(0.40,0.89),'Optimistic_3':(0.66,0.79),'Pessimistic':(0.80,0.89)}

def service_life(rd,threshold=20,max_years=30):
    if pd.isna(rd) or rd<=0: return np.nan
    y=np.arange(1,max_years+1); return int((rd*(y-1)<threshold).sum())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--thermal',required=True); ap.add_argument('--out',default='processed/04_Degradation_Service_Life'); args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(args.thermal,low_memory=False); df['date']=pd.to_datetime(df.date); df['Tmodule_max_proxy_C']=pd.to_numeric(df.Tmodule_max_proxy_C,errors='coerce'); df=df.dropna(subset=['date','Tmodule_max_proxy_C']); df['is_heatwave_day']=df.is_heatwave_day.astype(str).str.lower().isin(['true','1','yes']); df['year']=df.date.dt.year; df['Tmodule_K']=df.Tmodule_max_proxy_C+273.15; df['arrhenius_stress_proxy']=np.exp(-EA_BASE/(K_B*df.Tmodule_K))
    h=df[df.scenario=='historical'].groupby(['model','year']).arrhenius_stress_proxy.mean().reset_index(name='annual_stress_proxy'); hb=h.groupby('model').annual_stress_proxy.mean().reset_index(name='historical_stress_baseline')
    ar=[]
    for (m,s,p,y),g in df.groupby(['model','scenario','period','year']):
        hw=g[g.is_heatwave_day]; total=g.arrhenius_stress_proxy.sum(); hs=hw.arrhenius_stress_proxy.sum()
        ar.append({'model':m,'scenario':s,'period':p,'year':y,'days':len(g),'heatwave_days':int(g.is_heatwave_day.sum()),'annual_mean_Tmodule_C':g.Tmodule_max_proxy_C.mean(),'annual_max_Tmodule_C':g.Tmodule_max_proxy_C.max(),'annual_stress_proxy':g.arrhenius_stress_proxy.mean(),'heatwave_stress_share_pct':hs/total*100 if total>0 else np.nan,'mean_heatwave_stress':hw.arrhenius_stress_proxy.mean() if len(hw) else np.nan,'mean_nonheatwave_stress':g[~g.is_heatwave_day].arrhenius_stress_proxy.mean()})
    annual=pd.DataFrame(ar).merge(hb,on='model'); annual['acceleration_factor_AF']=annual.annual_stress_proxy/annual.historical_stress_baseline; annual['degradation_rate_pct_per_year']=RD0_BASE*annual.acceleration_factor_AF; annual.to_csv(out/'DEGRADATION_ANNUAL_BASE.csv',index=False)
    sr=[]
    for (m,s,p),g in annual.groupby(['model','scenario','period']):
        af=g.acceleration_factor_AF.mean(); rd=g.degradation_rate_pct_per_year.mean(); life=service_life(rd); lost=DESIGN_LIFE-life; repl=max(0,int(np.ceil(DESIGN_LIFE/life)-1)); sr.append({'model':m,'scenario':s,'period':p,'number_of_years':g.year.nunique(),'mean_acceleration_factor_AF':af,'mean_degradation_rate_pct_per_year':rd,'mean_heatwave_stress_share_pct':g.heatwave_stress_share_pct.mean(),'mean_annual_Tmodule_C':g.annual_mean_Tmodule_C.mean(),'mean_annual_max_Tmodule_C':g.annual_max_Tmodule_C.mean(),'service_life_years':life,'years_lost_vs_30':lost,'replacement_count_within_30y':repl,'projected_nameplate_loss_at_year30_pct_no_replacement':rd*(DESIGN_LIFE-1)})
    summary=pd.DataFrame(sr); summary.to_csv(out/'DEGRADATION_SERVICE_LIFE_PERIOD_SUMMARY_BASE.csv',index=False)
    ch=[]
    for m in summary.model.unique():
        h=summary[(summary.model==m)&(summary.scenario=='historical')].iloc[0]
        for _,r in summary[(summary.model==m)&(summary.scenario!='historical')].iterrows(): ch.append({'model':m,'scenario':r.scenario,'period':r.period,'AF_change':r.mean_acceleration_factor_AF-h.mean_acceleration_factor_AF,'degradation_rate_change_pct_points_per_year':r.mean_degradation_rate_pct_per_year-h.mean_degradation_rate_pct_per_year,'service_life_change_years':r.service_life_years-h.service_life_years,'additional_replacements_within_30y':r.replacement_count_within_30y-h.replacement_count_within_30y,'heatwave_stress_share_change_pct_points':r.mean_heatwave_stress_share_pct-h.mean_heatwave_stress_share_pct})
    pd.DataFrame(ch).to_csv(out/'DEGRADATION_CHANGE_FROM_HISTORICAL_BASE.csv',index=False)
    summary.groupby(['scenario','period']).agg(AF_ensemble_mean=('mean_acceleration_factor_AF','mean'),AF_ensemble_std=('mean_acceleration_factor_AF','std'),degradation_rate_pctyr_mean=('mean_degradation_rate_pct_per_year','mean'),degradation_rate_pctyr_std=('mean_degradation_rate_pct_per_year','std'),heatwave_stress_share_pct_mean=('mean_heatwave_stress_share_pct','mean'),service_life_years_mean=('service_life_years','mean'),service_life_years_min=('service_life_years','min'),service_life_years_max=('service_life_years','max'),replacements_30y_mean=('replacement_count_within_30y','mean')).reset_index().to_csv(out/'DEGRADATION_ENSEMBLE_SUMMARY_BASE.csv',index=False)
    daily=df[['model','scenario','period','date','Tmodule_max_proxy_C','is_heatwave_day','arrhenius_stress_proxy']].merge(hb,on='model'); daily['daily_relative_stress_AF']=daily.arrhenius_stress_proxy/daily.historical_stress_baseline; daily.to_csv(out/'DEGRADATION_DAILY_STRESS_BASE.csv',index=False)
    sens=[]
    for name,(rd0,ea) in SCENARIOS.items():
        t=df[['model','scenario','period','year','Tmodule_K']].copy(); t['stress']=np.exp(-ea/(K_B*t.Tmodule_K)); a=t.groupby(['model','scenario','period','year']).stress.mean().reset_index(name='annual_stress'); hs=a[a.scenario=='historical'].groupby('model').annual_stress.mean().reset_index(name='hist_stress'); a=a.merge(hs,on='model'); a['AF']=a.annual_stress/a.hist_stress; a['Rd']=rd0*a.AF
        ps=a.groupby(['model','scenario','period']).agg(mean_AF=('AF','mean'),mean_Rd=('Rd','mean')).reset_index()
        for _,r in ps.iterrows(): sens.append({'durability_scenario':name,'Rd0_pct_per_year':rd0,'Ea_eV':ea,'model':r.model,'scenario':r.scenario,'period':r.period,'mean_AF':r.mean_AF,'mean_degradation_rate_pct_per_year':r.mean_Rd,'service_life_years_within_30y_design':service_life(r.mean_Rd)})
    pd.DataFrame(sens).to_csv(out/'DEGRADATION_DURABILITY_SENSITIVITY.csv',index=False)
    pd.DataFrame({'item':['input_rows','missing_Tmodule','historical_models','base_Rd0_pct_per_year','base_Ea_eV','EOL_threshold_pct','design_life_years','minimum_AF','maximum_AF'],'value':[len(df),df.Tmodule_max_proxy_C.isna().sum(),df[df.scenario=='historical'].model.nunique(),RD0_BASE,EA_BASE,EOL_THRESHOLD,DESIGN_LIFE,annual.acceleration_factor_AF.min(),annual.acceleration_factor_AF.max()]}).to_csv(out/'DEGRADATION_QC_SUMMARY.csv',index=False)
    (out/'DEGRADATION_METHOD_AND_ASSUMPTIONS.txt').write_text('Temperature-only relative Arrhenius stress S(T)=exp[-Ea/(kT)], normalized to each GCM historical Stuttgart baseline. Rd=AF*Rd0. Base Rd0=0.66%/yr, Ea=0.89 eV, EOL=20%, design horizon=30 yr. Future RH is not included; this is not an exact reproduction of a full T-RH model.')
    print('Done:',out)

if __name__=='__main__': main()
