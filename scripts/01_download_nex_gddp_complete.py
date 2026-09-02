from pathlib import Path
import argparse, time, requests, zipfile

MODELS = ["MRI-ESM2-0", "NorESM2-MM", "MPI-ESM1-2-HR"]
MEMBER = "r1i1p1f1"
VARIABLES = ["tasmax", "sfcWind", "rsds"]
BBOX = dict(north=49.3, south=48.3, west=8.7, east=9.7)
BASE = "https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6"
PERIODS = [
    ("historical", 1991, 2014),
    ("ssp245", 2041, 2060),
    ("ssp245", 2081, 2100),
    ("ssp585", 2041, 2060),
    ("ssp585", 2081, 2100),
]

def url_for(model, scenario, variable, year):
    # NASA NEX-GDDP file-version suffix; unrelated to this repository release version.
    fn = f"{variable}_day_{model}_{scenario}_{MEMBER}_gn_{year}_v2.0.nc"
    return (
        f"{BASE}/{model}/{scenario}/{MEMBER}/{variable}/{fn}"
        f"?var={variable}&north={BBOX['north']}&south={BBOX['south']}"
        f"&west={BBOX['west']}&east={BBOX['east']}&horizStride=1"
        f"&time_start={year}-01-01T12:00:00Z&time_end={year}-12-31T12:00:00Z"
        "&accept=netcdf3&addLatLon=true"
    )

def get_one(model, scenario, variable, year, path, retries=3):
    if path.exists() and path.stat().st_size > 1000:
        print(path.name, "exists - skipped")
        return True
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url_for(model, scenario, variable, year), timeout=180)
            if r.status_code == 200 and len(r.content) > 1000:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                print(path.name, "OK")
                return True
            print(path.name, "attempt", attempt, "HTTP", r.status_code)
        except Exception as e:
            print(path.name, "attempt", attempt, "error:", e)
        time.sleep(5)
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='NEX_GDDP_CMIP6_Stuttgart')
    ap.add_argument('--zip', action='store_true', help='Also create a ZIP archive')
    args = ap.parse_args()
    out = Path(args.out)
    failed=[]
    for model in MODELS:
        for variable in VARIABLES:
            group = "MIP6_Stuttgart_Heatwave_Tasmax" if variable == "tasmax" else "NEX_GDDP_CMIP6_Stuttgart_Wind_Radiation"
            for scenario, start, end in PERIODS:
                folder = out/group/model/f"{model}_{scenario}_{variable}_{start}-{end}_Stuttgart"
                for year in range(start, end+1):
                    path = folder/f"{model}_{scenario}_{variable}_{year}_Stuttgart.nc"
                    if not get_one(model, scenario, variable, year, path):
                        failed.append((model, scenario, variable, year))
                    time.sleep(1)
    print("FAILED:", failed if failed else "None")
    if args.zip:
        zip_name = Path(str(out) + '.zip')
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in out.rglob('*'):
                if p.is_file(): z.write(p, arcname=p.relative_to(out.parent))
        print('ZIP:', zip_name)

if __name__ == '__main__':
    main()
