# Tableau Extensions Setup

## Adding Extensions to Dashboards

Each dashboard gets one extension. In Tableau Desktop:

1. **Dashboard** → **Objects** → drag **Extension** onto the dashboard
2. Choose **Access a Trex File** → enter the URL:

| Dashboard | Extension URL |
|-----------|---------------|
| Code Comparison | `https://cobra-api.up.railway.app/extension/CodeComparison.trex` |
| Custom Module | `https://cobra-api.up.railway.app/extension/CustomModule.trex` |
| Policy Module | `https://cobra-api.up.railway.app/extension/PolicyModule.trex` |
| Detailed Health | `https://cobra-api.up.railway.app/extension/DetailedHealth.trex` |

3. When prompted, allow the extension full data access.

---

## Extension Requirements by Dashboard

### Code Comparison (Dashboard 1)

**Location** — reads from (checked in order, first match wins):
- Parameters: `State`, `Select State`, `State_Abbr`, `State_Region`, `State/Grid Region`, `COBRA_State`
- Filters: `State`, `State Selection`
- County from filters: `County`, `County Selection`

**Pollutant data** — worksheets with these keywords in the name:
- `"electric"` in name → read as `grid` fuel
- `"fuel"` in name → read as `natural_gas` fuel

Worksheets must contain PM2.5, SO2, NOx, VOC values (as direct columns or pivoted Measure Names/Values).

### Custom Module (Dashboard 2)

**Location** — reads "State/Grid Region" parameter. Accepts:
- State abbreviations: `AL`, `NY`, `TX`, etc.
- eGRID codes: `ERCT`, `FRCC`, `CAMX`, etc.
- eGRID display names: `WECC California`, `ERCOT All`, etc.

**Pollutant data** — worksheets matched by keyword:
| Worksheet keyword | Fuel key |
|-------------------|----------|
| `grid`, `electric` | `grid` |
| `natural gas`, `ng` | `natural_gas` |
| `propane`, `lpg` | `propane` |
| `fuel oil`, `distillate`, `dfo` | `fuel_oil` |
| `biomass`, `wood` | `biomass` |

### Policy Module (Dashboard 3)

**Location** — same parameter/filter matching as Code Comparison (state + optional county).

**Pollutant data** — worksheets matched by keyword:
- `"pollutants reduced from fuel"`, `"fuel use"`, `"policy_natural"`, `"ps_pollu"` → `natural_gas`
- `"pollutants from grid"`, `"grid use"`, `"electric_gain"`, `"ps_grid"`, `"grid_pollu"` → `grid`

Column names are matched for pollutant substrings (e.g., `Policy_Natural Gas_NOx`).

### Detailed Health (Dashboard 4)

No worksheet or parameter requirements. Automatically loads cached results from the API.

- Use the source tabs to switch between Code Comparison / Custom Module / Policy Module results.
- Results are cached server-side after each calculation. A server restart clears the cache.

---

## Region Format Reference

The API accepts multiple region formats:

| Format | Examples | Notes |
|--------|----------|-------|
| State abbreviation | `NY`, `CA`, `TX` | Most common |
| 2-digit state FIPS | `36`, `06`, `48` | |
| 5-digit county FIPS | `36061`, `05007` | Enables county-level results |
| eGRID subregion code | `ERCT`, `FRCC`, `CAMX` | Maps to primary state |
| eGRID display name | `WECC California`, `ERCOT All` | Case-insensitive |
| National | `national`, `usa`, `us` | Returns national-level only |

State + county name resolution:
- `state: "AR"` + `county_name: "Benton County"` → FIPS `05007`
- If county can't be resolved, falls back to state-level (no error).

---

## Worksheet Data Format

Extensions read pollutant data from Tableau worksheets via `getSummaryDataAsync()`. Two formats are supported:

### Direct Columns
Separate column per pollutant. Column names matched by substring (case-insensitive):
- PM2.5: contains `PM2`, `PM25`, or `Particulate`
- SO2: contains `SO2`, `Sulfur`, or `Sulphur`
- NOx: contains `NOX`, `NO2`, or `Nitrogen`
- VOC: contains `VOC` or `Volatile`

### Pivoted Format (Measure Names / Measure Values)
Tableau's default when multiple measures are on a single axis. Two columns:
- `Measure Names` — string identifying the pollutant
- `Measure Values` — numeric value

The extension reads the `formattedValue` property of each Measure Names cell (the display name shown in Tableau). **Important**: do NOT use `nativeValue` — it contains internal Tableau field references that don't contain pollutant keywords.

---

## .trex Manifest Notes

When creating/editing `.trex` manifests:
- `<permissions>` must come AFTER `<icon>` in element order
- Permission value is `full data` (with a space), NOT `full-data` (with hyphen)
- Element order: `default-locale, name, description, author, min-api-version, source-location, icon, permissions, context-menu`
- Script URL: `https://extensions.tableauusercontent.com/resources/tableau.extensions.1.latest.min.js`
  - The old URL `https://extension.tableau.com/...` is dead (DNS doesn't resolve)

---

## Debugging

All 3 input extensions log detailed info:
- **In-extension**: Collapsible "Debug info" section after results show parameters, filters, worksheet columns, and the payload sent to the API.
- **Browser console**: Search for `[COBRA]` to see:
  - Worksheet column names and first row values
  - Measure name matching (shows `formattedValue`, `value`, and `nativeValue` for each)
  - Unmatched measures (logged so you can identify naming patterns)
  - Pivoted vs direct column detection
  - Filter values found

To access the browser console in Tableau Desktop: the extension runs in an embedded Chromium browser. Use remote debugging or test by opening the HTML file directly in Chrome (will run in "not in Tableau" test mode with hardcoded data).

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Calculate takes 2+ min | EPA API is slow | Normal. Token fetch can take up to 170s on cold start. |
| Extension won't load | HTTPS required | Ensure the URL uses HTTPS. Tableau Public may block extensions. |
| "No pollutant data found" | Worksheet names don't match expected patterns | Check worksheet names contain expected keywords (see per-extension tables above). Check "Debug info" for the worksheet list. |
| Pollutant values are 0 | Measure Names not matching | Check browser console for `[COBRA] Unmatched measure:` logs. The measure name may use a format not yet handled. |
| Region not found | Unknown region format | Use state abbrev (NY), eGRID code (ERCT), or FIPS. Check `region_map.py` for supported values. |
| County falls back to state | County name doesn't match | County resolution is soft — unknown counties fall back to state-level. Check `county_fips.py` for exact names. |
| 502 error | EPA API down or timeout | Retry. The EPA COBRA API can be intermittently unavailable. |
| Detail dashboard shows "No results" | No calculation has been run | Run a calculation on one of the 3 input dashboards first. Results are cached in server memory. |
| Detail dashboard lost data | Server restarted | Cache is in-memory only. Re-run calculations. |
