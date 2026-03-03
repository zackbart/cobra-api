# Troubleshooting Guide

## Common Issues and Fixes Discovered During Development

This documents specific issues encountered during development and their solutions.

### 1. Worksheet pollutant values all going to PM2.5

**Symptom**: All 4 pollutant values sum into PM25, SO2/NOx/VOC are 0.

**Cause**: The code was using `nativeValue` from Tableau's Measure Names cells. In pivoted worksheets, `nativeValue` is an internal Tableau field reference like `[federated.06f4yba19qifmm14ty0nk02qhu6y].[sum:Fuel_PM2.5...]`. Every reference might contain "PM2" as a substring, causing all values to match PM2.5.

**Fix**: Use `formattedValue` (the display name like "PM2.5 (Tons)") instead. Fall back to `nativeValue` only if `formattedValue` is empty or contains `[federated`.

**Code**: `shared.js` → `readWorksheetPollutants()`, pivot detection branch.

### 2. County not being read from dashboard

**Symptom**: County always shows "(none)" even though the dashboard has a county selector.

**Cause**: The county was controlled by a worksheet filter, not a Tableau parameter. `getParametersAsync()` only returns parameters, not filters.

**Fix**: Added `findFilterValue()` in `shared.js` which iterates through all worksheets, calls `getFiltersAsync()`, and matches filter field names. County is read from filters after parameters. Extensions check for filter field names: "County", "County Selection", "County?". State filters: "State", "State Selection", "State/Grid Region". If your dropdowns use different field names, add them to the arrays in the extension or use matching names in Tableau.

**Code**: `shared.js` → `findFilterValue()`, called in code-comparison.html and policy-module.html.

### 2b. State/county sent doesn't match what's selected (e.g. UI shows AZ and (All) but API gets KY and Abbeville County)

**Cause**: The visible State/County dropdowns are often **filters**; the extension also reads **parameters**. If the filters don't match our field names (or return no value when County is "(All)"), we fall back to parameter values, which can be stale or from another control.

**Fix**: (1) County "(All)" is now treated as no county (state-level only); we never send `county_name` when the value is "(All)" or "All". (2) Extensions now check additional filter names ("State/Grid Region", "County?") so the dropdowns that drive the view are more likely to be read. Check the extension "Debug info" to see "From filters" vs "From params" and "Using" — if "From filters" shows "(none)" for State or County, the dashboard's filter field names may not match; rename the filter in Tableau or add that name to the extension's filter list.

### 3. County resolution errors crashing the request

**Symptom**: `500 Internal Server Error: Unknown county: Abbeville County in KY`. Tableau parameters can hold stale values from previous interactions.

**Fix**: Made county resolution a soft fallback in `main.py`. If `resolve_state_county()` raises `ValueError`, the request falls back to state-level instead of returning an error.

**Code**: `main.py` → `health_effects()` function, state/county resolution block.

### 4. Electricity/grid returns $0 health impacts

**Symptom**: Grid fuel shows $0 for a specific county.

**Cause**: This is correct COBRA behavior. The grid tier (1,3,1 = Electric Utility) at certain counties may have zero baseline emissions (no power plants in that county). COBRA can't reduce emissions that don't exist.

**Not a bug** — verify by checking the COBRA baseline. State-level or national-level results for the same grid emissions will typically show non-zero values.

### 5. eGRID region not recognized

**Symptom**: `Unknown region: WECC California` or similar display names.

**Cause**: The custom module's "State/Grid Region" parameter contains a mix of state abbreviations, 4-letter eGRID codes (ERCT, CAMX), and full display names ("WECC California", "SERC Tennessee Valley"). Also includes alternate spellings like "ASSC" instead of "ASCC".

**Fix**: `region_map.py` has a `display_to_egrid` mapping covering all known display names. Also handles `FIPSST` and `PSTATABB` as national aliases.

### 6. Fuel oil or other fuel missing some pollutant values

**Symptom**: e.g., fuel_oil returns PM25=0.000234 but SO2=0, NOx=0, VOC=0 while the dashboard shows non-zero values for all.

**Potential causes**:
1. Measure Names in the worksheet don't contain the expected pollutant substrings
2. The worksheet uses full pollutant names ("Sulfur Dioxide" instead of "SO2")

**Investigation**: Check browser console for `[COBRA] Measure name:` and `[COBRA] Unmatched measure:` logs. These show exactly what names are seen.

**Fix applied**: `matchPollutantName()` now matches full names (Sulfur/Sulphur, Nitrogen, Particulate, Volatile) in addition to abbreviations. Also logs unmatched measures.

**Status**: Needs Tableau testing to confirm this resolves the issue.

---

## Debug Logging Reference

All extensions log to the browser console with `[COBRA]` prefix:

```
[COBRA] Worksheet 'Electricity Pollutants Impact' columns: ["Measure Names","Measure Values"]
[COBRA] Worksheet 'Electricity Pollutants Impact' rows: 4
[COBRA] First row: Measure Names=... [fmt:PM2.5 (Tons)], Measure Values=0.5
[COBRA] Using pivoted Measure Names/Values format
[COBRA] Measure name: 'PM2.5 (Tons)' (fmt='PM2.5 (Tons)' val='' native='[federated...]')
[COBRA] Pivoted results: PM25=0.5 SO2=0.3 NOx=0.2 VOC=0.1
[COBRA] Filter 'County' = Benton County (from worksheet 'Sheet1')
```

The in-extension debug panel (collapsible `<details>` section) shows:
- All Tableau parameters and their values
- Filter values found
- Worksheet names on the dashboard
- Column names per worksheet
- First row values
- Final payload sent to the API
