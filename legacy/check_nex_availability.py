import requests

MODELS = ["MRI-ESM2-0", "NorESM2-MM", "MPI-ESM1-2-HR"]
MEMBER = "r1i1p1f1"
VARIABLES = ["tasmax", "sfcWind", "rsds"]
CHECKS = {
    "historical": [1991, 2014],
    "ssp245": [2041, 2060, 2081, 2100],
    "ssp585": [2041, 2060, 2081, 2100],
}
BASE = "https://ds.nccs.nasa.gov/thredds/catalog/AMES/NEX/GDDP-CMIP6"

all_ok = True
for model in MODELS:
    print("\nMODEL:", model)
    for scenario, years in CHECKS.items():
        for variable in VARIABLES:
            u = f"{BASE}/{model}/{scenario}/{MEMBER}/{variable}/catalog.xml"
            try:
                r = requests.get(u, timeout=60)
                if r.status_code != 200:
                    print(scenario, variable, "CATALOG ERROR", r.status_code)
                    all_ok = False
                    continue
                for year in years:
                    ok = str(year) in r.text
                    print(scenario, variable, year, "OK" if ok else "MISSING")
                    all_ok &= ok
            except Exception as e:
                print(scenario, variable, "ERROR", e)
                all_ok = False

print("\nALL REQUIRED DATA AVAILABLE" if all_ok else "\nSOME DATA ARE MISSING")
