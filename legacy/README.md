# PV Heatwave Climate Data Workflow

GitHub-ready code for the Stuttgart PV heatwave study.

## Dataset
NASA NEX-GDDP-CMIP6

Models:
- MRI-ESM2-0
- NorESM2-MM
- MPI-ESM1-2-HR

Variables:
- `tasmax`
- `sfcWind`
- `rsds`

Study-area bounding box:
- North 49.3
- South 48.3
- West 8.7
- East 9.7

Periods:
- Historical: 1991-2014
- SSP2-4.5: 2041-2060 and 2081-2100
- SSP5-8.5: 2041-2060 and 2081-2100

## Scripts
- `check_nex_availability.py`: checks required catalog availability.
- `download_nex_gddp.py`: one general downloader replacing the many separate Colab cells.

## Google Colab
In Colab:

```python
!pip install requests
!python download_nex_gddp.py
```

Then download the generated ZIP:

```python
from google.colab import files
files.download("NEX_GDDP_CMIP6_Stuttgart_ALL.zip")
```

## Reproducibility
Do not upload the NetCDF data to GitHub unless necessary. Usually the repository should contain code, README, environment information, and exact data-source metadata. Cite the NASA NEX-GDDP-CMIP6 dataset in the paper.

Google Colab may be mentioned as the execution environment, but it is normally not necessary to treat it as a scientific data reference.
