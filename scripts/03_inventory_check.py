from pathlib import Path
import argparse, re, pandas as pd

MODELS=["MPI-ESM1-2-HR","MRI-ESM2-0","NorESM2-MM"]
VARS=['tasmax','rsds','sfcWind']
GROUPS=[('historical','1991-2014'),('ssp245','2041-2060'),('ssp245','2081-2100'),('ssp585','2041-2060'),('ssp585','2081-2100')]

def infer(path):
    s=str(path).replace('\\','/')
    model=next((m for m in MODELS if m in s), None)
    var=next((v for v in VARS if v.lower() in s.lower()), None)
    scenario=next((x for x in ['historical','ssp245','ssp585'] if x in s.lower()), None)
    years=re.findall(r'(?<!\d)(19\d{2}|20\d{2}|2100)(?!\d)', s)
    return model,scenario,var,years

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data-root',default='data'); ap.add_argument('--out',default='processed/00_Inventory_Check'); args=ap.parse_args()
    root=Path(args.data_root); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for p in root.rglob('*'):
        if not p.is_file(): continue
        model,scenario,var,years=infer(p)
        rows.append({'relative_path':str(p.relative_to(root)),'name':p.name,'suffix':p.suffix.lower(),'size_bytes':p.stat().st_size,'model':model,'scenario':scenario,'variable':var,'years_in_name':';'.join(years)})
    inv=pd.DataFrame(rows)
    inv.to_csv(out/'FULL_DATA_INVENTORY.csv',index=False)
    if len(inv): inv.groupby('suffix').agg(files=('name','size'),bytes=('size_bytes','sum')).reset_index().to_csv(out/'FILE_TYPE_SUMMARY.csv',index=False)
    checks=[]
    for model in MODELS:
        for scenario,period in GROUPS:
            for var in VARS:
                sub=inv[(inv.model==model)&(inv.scenario==scenario)&(inv.variable==var)]
                # tolerate the historical wind/radiation single-CSV files and annual NC files
                start,end=map(int,period.split('-'))
                years=set()
                for txt in sub['years_in_name'].fillna(''):
                    for y in txt.split(';'):
                        if y.isdigit(): years.add(int(y))
                has_range = any((str(start) in x and str(end) in x) for x in sub['relative_path'].astype(str))
                complete = (len(sub)>0) and (has_range or all(y in years for y in [start,end]))
                checks.append({'model':model,'scenario':scenario,'period':period,'variable':var,'files_found':len(sub),'status':'YES' if complete else 'NO'})
    pd.DataFrame(checks).to_csv(out/'CLIMATE_COMPLETENESS_CHECK.csv',index=False)
    tocheck=inv[(inv.size_bytes<=0)|inv.suffix.isin(['.tmp','.part'])].copy()
    tocheck.to_csv(out/'FILES_TO_CHECK.csv',index=False)
    print('Inventory:',len(inv),'files ->',out)

if __name__=='__main__': main()
