from pathlib import Path
import time, requests, zipfile

MODELS = ["MRI-ESM2-0", "NorESM2-MM", "MPI-ESM1-2-HR"]
MEMBER = "r1i1p1f1"
BBOX = dict(north=49.3, south=48.3, west=8.7, east=9.7)
BASE = "https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6"
OUT = Path("NEX_GDDP_CMIP6_Stuttgart")

TASMAX_PERIODS = [
    ("historical", 1991, 2014),
    ("ssp245", 2041, 2060),
    ("ssp245", 2081, 2100),
    ("ssp585", 2041, 2060),
    ("ssp585", 2081, 2100),
]
FUTURE_PERIODS = [
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
        f"?var={variable}"
        f"&north={BBOX['north']}&south={BBOX['south']}"
        f"&west={BBOX['west']}&east={BBOX['east']}"
        "&horizStride=1"
        f"&time_start={year}-01-01T12:00:00Z"
        f"&time_end={year}-12-31T12:00:00Z"
        "&accept=netcdf3&addLatLon=true"
    )

def get_one(model, scenario, variable, year, path):
    if path.exists() and path.stat().st_size > 1000:
        print(year, "exists - skipped")
        return True
    for attempt in range(1, 4):
        try:
            r = requests.get(url_for(model, scenario, variable, year), timeout=180)
            if r.status_code == 200 and len(r.content) > 1000:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                print(year, "OK")
                return True
            print(year, "attempt", attempt, "HTTP", r.status_code)
        except Exception as e:
            print(year, "attempt", attempt, "error:", e)
        time.sleep(5)
    return False

def run_period(model, scenario, variable, start, end, failed):
    group = "Heatwave_Tasmax" if variable == "tasmax" else "Wind_Radiation"
    folder = OUT / group / model / f"{model}_{scenario}_{variable}_{start}-{end}_Stuttgart"
    print("\n", model, scenario, variable, start, end)
    for year in range(start, end + 1):
        path = folder / f"{model}_{scenario}_{variable}_{year}_Stuttgart.nc"
        if not get_one(model, scenario, variable, year, path):
            failed.append((model, scenario, variable, year))
        time.sleep(2)

failed = []

for model in MODELS:
    for scenario, start, end in TASMAX_PERIODS:
        run_period(model, scenario, "tasmax", start, end, failed)

for model in MODELS:
    for variable in ["sfcWind", "rsds"]:
        for scenario, start, end in FUTURE_PERIODS:
            run_period(model, scenario, variable, start, end, failed)

print("\nFAILED:", failed if failed else "None")

zip_name = Path("NEX_GDDP_CMIP6_Stuttgart_ALL.zip")
with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob("*"):
        if p.is_file():
            z.write(p, arcname=p.relative_to(OUT.parent))
print("ZIP:", zip_name)
