from pathlib import Path
import argparse, requests

URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out', default='PVGIS_Stuttgart_1kWp_CrystSi_Tilt30_South_2005_2023.csv')
    args=ap.parse_args()
    params = {
        'lat': 48.7758,
        'lon': 9.1829,
        'startyear': 2005,
        'endyear': 2023,
        'pvcalculation': 1,
        'peakpower': 1,
        'loss': 14,
        'pvtechchoice': 'crystSi',
        'mountingplace': 'free',
        'angle': 30,
        'aspect': 0,
        'components': 1,
        'outputformat': 'csv',
        'browser': 0,
    }
    r=requests.get(URL, params=params, timeout=180)
    r.raise_for_status()
    Path(args.out).write_bytes(r.content)
    print('Saved:', args.out, len(r.content), 'bytes')

if __name__=='__main__': main()
