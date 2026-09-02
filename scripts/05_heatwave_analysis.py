from pathlib import Path
import argparse, numpy as np, pandas as pd

THRESHOLD_C=30.0
MIN_DURATION=3

def detect(group, threshold=THRESHOLD_C, min_duration=MIN_DURATION):
    g=group.sort_values('date').reset_index(drop=True); events=[]; dates=[]; temps=[]; prev=None
    def save():
        nonlocal dates,temps
        if len(dates)>=min_duration:
            a=np.asarray(temps,float)
            events.append({'start_date':dates[0],'end_date':dates[-1],'duration_days':len(dates),'mean_tasmax_C':a.mean(),'peak_tasmax_C':a.max(),'mean_excess_C':(a-threshold).mean(),'cumulative_excess_Cdays':(a-threshold).sum()})
        dates=[]; temps=[]
    for _,r in g.iterrows():
        d=r.date; t=r.tasmax_C; hot=pd.notna(t) and t>=threshold; cons=prev is not None and (d-prev).days==1
        if hot:
            if not dates: dates=[d]; temps=[t]
            elif cons: dates.append(d); temps.append(t)
            else: save(); dates=[d]; temps=[t]
        else: save()
        prev=d
    save(); return events

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--master',required=True); ap.add_argument('--out',default='processed/02_Heatwave_Analysis'); ap.add_argument('--threshold',type=float,default=30.0); ap.add_argument('--min-days',type=int,default=3); args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(args.master); df['date']=pd.to_datetime(df.date)
    er=[]
    for (m,s,p),g in df.groupby(['model','scenario','period']):
        for i,e in enumerate(detect(g,args.threshold,args.min_days),1): er.append({'model':m,'scenario':s,'period':p,'event_id':f'{m}_{s}_{p}_HW{i:03d}',**e})
    ev=pd.DataFrame(er); ev.to_csv(out/'HEATWAVE_EVENTS_30C_3D.csv',index=False)
    annual=[]
    for (m,s,p),g in df.groupby(['model','scenario','period']):
        for y in sorted(g.date.dt.year.unique()):
            sub=ev[(ev.model==m)&(ev.scenario==s)&(ev.period==p)]
            if len(sub): sub=sub[pd.to_datetime(sub.start_date).dt.year==y]
            annual.append({'model':m,'scenario':s,'period':p,'year':y,'heatwave_events':len(sub),'heatwave_days':int(sub.duration_days.sum()) if len(sub) else 0,'mean_duration_days':sub.duration_days.mean() if len(sub) else 0,'max_duration_days':sub.duration_days.max() if len(sub) else 0,'mean_peak_tasmax_C':sub.peak_tasmax_C.mean() if len(sub) else np.nan,'maximum_tasmax_C':sub.peak_tasmax_C.max() if len(sub) else np.nan,'cumulative_excess_Cdays':sub.cumulative_excess_Cdays.sum() if len(sub) else 0})
    annual=pd.DataFrame(annual); annual.to_csv(out/'HEATWAVE_ANNUAL_METRICS_30C_3D.csv',index=False)
    sr=[]
    for (m,s,p),g in annual.groupby(['model','scenario','period']):
        e=ev[(ev.model==m)&(ev.scenario==s)&(ev.period==p)]
        sr.append({'model':m,'scenario':s,'period':p,'number_of_years':g.year.nunique(),'total_events':len(e),'events_per_year':g.heatwave_events.mean(),'heatwave_days_per_year':g.heatwave_days.mean(),'mean_event_duration_days':e.duration_days.mean() if len(e) else 0,'maximum_event_duration_days':e.duration_days.max() if len(e) else 0,'mean_event_peak_C':e.peak_tasmax_C.mean() if len(e) else np.nan,'absolute_max_tasmax_C':e.peak_tasmax_C.max() if len(e) else np.nan,'mean_excess_C':e.mean_excess_C.mean() if len(e) else 0,'cumulative_excess_Cdays_per_year':g.cumulative_excess_Cdays.mean()})
    summary=pd.DataFrame(sr); summary.to_csv(out/'HEATWAVE_PERIOD_SUMMARY_30C_3D.csv',index=False)
    metrics=['events_per_year','heatwave_days_per_year','mean_event_duration_days','maximum_event_duration_days','mean_event_peak_C','absolute_max_tasmax_C','mean_excess_C','cumulative_excess_Cdays_per_year']
    ch=[]
    for m in summary.model.unique():
        h=summary[(summary.model==m)&(summary.scenario=='historical')]
        if h.empty: continue
        h=h.iloc[0]
        for _,r in summary[(summary.model==m)&(summary.scenario!='historical')].iterrows():
            o={'model':m,'scenario':r.scenario,'period':r.period}
            for k in metrics:
                o[k+'_change']=r[k]-h[k]; o[k+'_percent_change']=((r[k]-h[k])/h[k]*100) if pd.notna(h[k]) and h[k]!=0 else np.nan
            ch.append(o)
    pd.DataFrame(ch).to_csv(out/'HEATWAVE_CHANGE_FROM_HISTORICAL.csv',index=False)
    ens=[]
    for (s,p),g in summary[summary.scenario!='historical'].groupby(['scenario','period']):
        o={'scenario':s,'period':p}
        for k in metrics:
            o[k+'_ensemble_mean']=g[k].mean(); o[k+'_ensemble_std']=g[k].std(); o[k+'_ensemble_min']=g[k].min(); o[k+'_ensemble_max']=g[k].max()
        ens.append(o)
    pd.DataFrame(ens).to_csv(out/'HEATWAVE_ENSEMBLE_SUMMARY.csv',index=False)
    (out/'HEATWAVE_METHOD.txt').write_text(f'Primary heatwave: tasmax >= {args.threshold:.1f} °C for at least {args.min_days} consecutive days. Historical reference: 1991–2014.')
    print('Events:',len(ev),'->',out)

if __name__=='__main__': main()
