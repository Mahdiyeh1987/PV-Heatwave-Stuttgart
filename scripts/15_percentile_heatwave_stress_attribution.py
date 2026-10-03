from pathlib import Path
import argparse
import numpy as np
import pandas as pd

EA=0.89
KB=8.617333262e-5
STRESS_MULT={1:0.20197618817717056,2:0.16362395747653566,3:0.14186146547832187,4:0.15829074940367827,5:0.16185021904752914,6:0.17560795477348967,7:0.17504134312319058,8:0.16643828425923754,9:0.16437100479943476,10:0.15409580600791434,11:0.17148527950779613,12:0.21498539191306262}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--thermal",required=True)
    ap.add_argument("--p90-daily",required=True)
    ap.add_argument("--out",default="processed/09_Reviewer_Revision")
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    th=pd.read_csv(args.thermal,low_memory=False)
    th["date"]=pd.to_datetime(th.date); th["month"]=th.date.dt.month
    th["stress_original"]=np.exp(-EA/(KB*(pd.to_numeric(th.Tmodule_max_proxy_C)+273.15)))
    th["stress_hourlycal"]=th.stress_original*th.month.map(STRESS_MULT)

    p=pd.read_csv(args.p90_daily,low_memory=False)
    p["date"]=pd.to_datetime(p.date)
    p=p[["model","scenario","period","date","is_heatwave_day","percentile_threshold_C"]].rename(columns={"is_heatwave_day":"is_p90_hw"})
    df=th.merge(p,on=["model","scenario","period","date"],how="inner",validate="one_to_one")
    df["is_p90_hw"]=df.is_p90_hw.astype(bool)

    rows=[]
    for model in sorted(df.model.unique()):
        h=df[(df.model==model)&(df.scenario=="historical")]
        htot=h.stress_hourlycal.mean()
        hhw=(h.stress_hourlycal*h.is_p90_hw.astype(int)).mean()
        hnon=(h.stress_hourlycal*(~h.is_p90_hw).astype(int)).mean()
        for (s,pd_),g in df[(df.model==model)&(df.scenario!="historical")].groupby(["scenario","period"]):
            ftot=g.stress_hourlycal.mean()
            fhw=(g.stress_hourlycal*g.is_p90_hw.astype(int)).mean()
            fnon=(g.stress_hourlycal*(~g.is_p90_hw).astype(int)).mean()
            delta=ftot-htot
            rows.append({
                "model":model,"scenario":s,"period":pd_,"total_ratio":ftot/htot,
                "p90_hw_share_pct":100*(fhw-hhw)/delta,
                "p90_nonhw_share_pct":100*(fnon-hnon)/delta,
                "p90_threshold_C":g.percentile_threshold_C.iloc[0]
            })
    m=pd.DataFrame(rows)
    m.to_csv(out/"P90_HEATWAVE_STRESS_DECOMPOSITION_MODEL.csv",index=False)
    e=m.groupby(["scenario","period"]).agg(
        total_ratio_mean=("total_ratio","mean"),
        p90_hw_share_mean=("p90_hw_share_pct","mean"),
        p90_hw_share_min=("p90_hw_share_pct","min"),
        p90_hw_share_max=("p90_hw_share_pct","max"),
        p90_nonhw_share_mean=("p90_nonhw_share_pct","mean")
    ).reset_index()
    e.to_csv(out/"P90_HEATWAVE_STRESS_DECOMPOSITION_ENSEMBLE.csv",index=False)
    print(e.to_string(index=False))

if __name__=="__main__":
    main()
