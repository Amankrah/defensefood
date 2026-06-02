# Local data (not in git)

Place large downloads here on each machine:

| Path | Source | Used for |
|------|--------|----------|
| `faostat/` | [FAOSTAT](https://www.fao.org/faostat/en/#data) QCL + FBS bulk CSVs; [FishStat Global Production](https://www.fao.org/fishery/static/Data/) zip for seafood P | Section 2 P/D, Section 3 CRS |
| `../script/output/comtrade_all_partners_*.csv` | `fetch_comtrade_pipeline.py --all-partners` | Section 2 OCS/HHI (preferred trade file) |

The API loads the newest `comtrade_all_partners_*.csv` from `script/output/` automatically.
