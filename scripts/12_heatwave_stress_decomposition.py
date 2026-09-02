from pathlib import Path
import argparse
import numpy as np
import pandas as pd

RD0=0.66
THRESHOLD=20
HORIZON=30


def service_life(rd_pct):
    y=np.arange(1,HORIZON+1)
    return int((rd_pct*(y-1)<THRESHOLD).sum())


def main():
    ap=argparse.ArgumentParser(description='Decompose future thermal-stress change into heatwave and non-heatwave contributions.')
    ap.add_argument('--daily',required=True,help='HOURLY_CALIBRATED_DAILY.csv from script 11')
    ap.add_argument('--out',default='processed/08_Extended_Validation')
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(args.daily,low_memory=False)
    df['date']=pd.to_datetime(df.date)
    df['is_heatwave_day']=df.is_heatwave_day.astype(str).str.lower().isin(['true','1','yes'])
    stress_col='stress_hourlycal' if 'stress_hourlycal' in df.columns else 'stress_original'

    rows=[]; cf=[]
    for model in sorted(df.model.unique()):
        h=df[(df.model==model)&(df.scenario=='historical')].copy()
        htot=h[stress_col].mean()
        h_hw=(h[stress_col]*h.is_heatwave_day.astype(int)).mean()
        h_nhw=(h[stress_col]*(~h.is_heatwave_day).astype(int)).mean()
        for (s,p),g in df[(df.model==model)&(df.scenario!='historical')].groupby(['scenario','period']):
            ftot=g[stress_col].mean()
            f_hw=(g[stress_col]*g.is_heatwave_day.astype(int)).mean()
            f_nhw=(g[stress_col]*(~g.is_heatwave_day).astype(int)).mean()
            delta=ftot-htot
            dhw=f_hw-h_hw; dnhw=f_nhw-h_nhw
            hw_share=100*dhw/delta if delta!=0 else np.nan
            nhw_share=100*dnhw/delta if delta!=0 else np.nan
            total_ratio=ftot/htot
            rows.append({'model':model,'scenario':s,'period':p,'total_ratio':total_ratio,'hw_share_pct':hw_share,'nonhw_share_pct':nhw_share})
            # Counterfactual: future non-HW contribution retained; HW contribution fixed at historical.
            af_nonhw=(h_hw+f_nhw)/htot
            rd_full=RD0*total_ratio; rd_non=RD0*af_nonhw
            lf=service_life(rd_full); ln=service_life(rd_non)
            cf.append({'model':model,'scenario':s,'period':p,'AF_full':total_ratio,'AF_counterfactual_nonHW_only':af_nonhw,'Rd_full':rd_full,'Rd_counterfactual_nonHW_only':rd_non,'life_full':lf,'life_counterfactual_nonHW_only':ln,'heatwave_increment_life_years':ln-lf})

    model=pd.DataFrame(rows)
    model.to_csv(out/'HEATWAVE_STRESS_DECOMPOSITION_MODEL.csv',index=False)
    ens=model.groupby(['scenario','period']).agg(total_ratio_mean=('total_ratio','mean'),hw_share_mean=('hw_share_pct','mean'),hw_share_min=('hw_share_pct','min'),hw_share_max=('hw_share_pct','max'),nonhw_share_mean=('nonhw_share_pct','mean')).reset_index()
    ens.to_csv(out/'HEATWAVE_STRESS_DECOMPOSITION_ENSEMBLE.csv',index=False)

    cfm=pd.DataFrame(cf); cfm.to_csv(out/'HEATWAVE_COUNTERFACTUAL_LIFETIME_MODEL.csv',index=False)
    cfe=cfm.groupby(['scenario','period']).agg(AF_full_mean=('AF_full','mean'),AF_nonHW_mean=('AF_counterfactual_nonHW_only','mean'),Rd_full_mean=('Rd_full','mean'),Rd_nonHW_mean=('Rd_counterfactual_nonHW_only','mean'),life_full_mean=('life_full','mean'),life_nonHW_mean=('life_counterfactual_nonHW_only','mean'),heatwave_increment_life_years_mean=('heatwave_increment_life_years','mean'),life_full_min=('life_full','min'),life_full_max=('life_full','max'),life_nonHW_min=('life_counterfactual_nonHW_only','min'),life_nonHW_max=('life_counterfactual_nonHW_only','max')).reset_index()
    cfe.to_csv(out/'HEATWAVE_COUNTERFACTUAL_LIFETIME_ENSEMBLE.csv',index=False)
    (out/'HEATWAVE_DECOMPOSITION_METHOD_NOTE.txt').write_text(
        'The decomposition operates on unconditional daily contributions to the selected temperature-only Arrhenius stress proxy: mean(stress*HW_flag) and mean(stress*(1-HW_flag)). '
        'Future-minus-historical changes in these two components sum exactly to the total stress change. The reported heatwave percentage is therefore attribution within the modeled stress proxy, not the fraction of physical PV degradation caused by heatwaves. '
        'The counterfactual retains the future non-heatwave contribution while holding the heatwave contribution at its model-specific historical value.\n',encoding='utf-8')
    print('Done:',out)

if __name__=='__main__': main()
