# County electricity baselines

One-time export of EPA COBRA's electricity-utility baseline emissions (PM2.5, SO2, NOx, VOC) for every US county. Used as a reference dataset for spotting counties where COBRA reports zero baseline emissions (i.e. no electric utility activity attributable to the county in COBRA's model).

## Files

- `fetch_baselines.py` — async script that hits EPA COBRA `SummarizedControlEmissions` for each FIPS in `county_fips.COUNTY_FIPS` (tier `1,3,1`, "Electric Utility").
- `electricity_baselines.csv` — 3,235 counties + header. Columns: `State, County, FIPS, PM25, SO2, NOx, VOC, AllZero`.
- `electricity_errors.csv` — 20 counties whose request failed (mostly empty `Error` column, which means EPA returned an empty `baseline` array — typically rural counties with no utility data).

## Regenerate

```bash
python county-baselines/fetch_baselines.py
```

The script is re-run safe: it skips any FIPS already in `electricity_baselines.csv` and appends new rows. To start fresh, delete the two CSVs first. EPA tokens are ephemeral — the script fetches one at startup. Expect ~10–15 minutes at concurrency 5.

## Why this lives in the repo

The data is small (~150 KB) and not used by the runtime API. It's checked in so a future maintainer can see which counties have zero electric-utility baselines without re-running the multi-minute fetch. Nothing in `main.py` imports from here.
