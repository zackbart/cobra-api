# Architecture

## Data Flow

```
Tableau Dashboard
  ├── Worksheets (pollutant data: PM2.5, SO2, NOx, VOC)
  ├── Parameters (State, County)
  └── Filters (County selection)
        │
        ▼
Extension (shared.js)
  ├── readWorksheetPollutants() — extract pollutant values
  ├── findParamValue() — read Tableau parameters
  ├── findFilterValue() — read worksheet filters
  └── callHealthEffects() — POST to API
        │
        ▼
FastAPI Proxy (main.py)
  ├── Resolve location → FIPS (region_map.py, county_fips.py)
  ├── Map fuel → COBRA tier (sector_map.py)
  └── For each fuel with emissions:
        │
        ▼
  EPA COBRA API (cobra_client.py)
    1. GET /token → workspace ID
    2. GET /SummarizedControlEmissions → baseline
    3. POST /EmissionsUpdate → control = baseline - reductions
    4. GET /Result/{token}/{fips} → national, state, county
        │
        ▼
  Merge results across fuels
    ├── Summary (combined low/high totals)
    ├── by_sector (per-fuel totals)
    ├── HealthEndpoints (combined table)
    └── HealthEndpoints_by_sector (per-fuel tables)
        │
        ▼
Extension displays results + POST /store-results
        │
        ▼
Detail Extension → GET /latest-results → full table view
```

---

## Server-Side Components

### `main.py` — FastAPI Application
- `/health-effects` POST: Main endpoint. Accepts optional query param `source` (code_comparison, custom_module, policy_module). Resolves location to FIPS, runs one COBRA scenario per fuel concurrently via `asyncio.gather`, merges results. When `source` is set, tier selection uses per-extension mapping (see sector_map).
- `/store-results` POST: Caches full response in memory, keyed by source extension name (code_comparison, custom_module, policy_module).
- `/latest-results` GET: Returns cached results. Accepts `?source=` filter.
- Static files mounted at `/extension/`.

### `cobra_client.py` — EPA COBRA API Client
- Uses `httpx.AsyncClient` with 120s timeout.
- EPA API base: `https://cobraapi.app.cloud.gov/api`
- **Token**: Not auth — it's a workspace/session ID. Each token is a separate scenario workspace.
- **Scenario flow**: `get_token()` → `get_baseline()` → `update_emissions()` → `get_result()`
- `run_scenario()` creates a token, fetches baseline for the given FIPS+tiers, computes `control = baseline - reductions`, updates emissions, returns the token for result fetching.
- Result fetches take ~15-17s each. The EPA API processes them sequentially even when called concurrently. Token fetch can take 1.5s to 170s (cold start).

### `sector_map.py` — Fuel-to-Tier Mapping
Maps fuel keys to COBRA tier strings (TIER1,TIER2,TIER3). **Default** (when `source` is not provided) uses `FUEL_TIERS`:
| Fuel Key | Tier | COBRA Category |
|----------|------|----------------|
| `grid` | 1,3,1 | Electric Utility |
| `natural_gas` | 3,3,99 | Commercial/Institutional Gas |
| `propane` | 3,4,99 | Fuel Combustion Other (LPG) |
| `fuel_oil` | 3,5,1 | Fuel Combustion Other (Distillate) |
| `biomass` | 3,2,99 | Fuel Combustion Other (Wood/Biomass) |

**Per-extension mapping** (`TIERS_BY_SOURCE`): when `/health-effects` is called with query param `source=code_comparison` or `custom_module` or `policy_module`, `get_tiers_for_fuel_by_source(fuel, source)` returns the tier for that extension. Code Comparison: grid → Electric Utility. Custom Module: grid → Electric Utility; natural_gas, propane → Commercial/Institutional Gas; fuel_oil → Commercial/Institutional Oil; biomass → Residential Wood. Policy Module: grid → Electric Utility; natural_gas → Commercial/Institutional Oil. Unmapped fuels fall back to `FUEL_TIERS`.

### `region_map.py` — Region Resolution
Converts dashboard region values to COBRA FIPS codes:
- State abbreviations (NY → "36")
- eGRID subregion codes (ERCT → "48")
- eGRID display names ("WECC California" → "06")
- County FIPS (5-digit, passed through)
- National aliases: "national", "usa", "us", "00", "fipsst", "pstatabb"
- `resolve_state_county(state, county_name)` → 5-digit FIPS via `county_fips.py`

### `county_fips.py` — County Name Resolution
Static dict mapping `(state_abbrev, normalized_county_name) → 5-digit FIPS` for all ~3,235 US counties. Generated from Census Bureau data. Handles common suffixes (County, Parish, Borough).

### `health_endpoints.py` — Health Endpoint Aggregation
Maps raw COBRA Impact columns (e.g., `PM_Mortality_All_Cause__low_`, `C__PM_Mortality_All_Cause__low_`) to the EPA-site table format with human-readable labels. Aggregates per-county rows into totals. Categories: Mortality, Heart Attacks, Hospital Admits, Asthma, ER Visits, Work/School Loss, Lung Cancer, Stroke, etc.

---

## Client-Side Components

### `shared.js` — Common Extension Library

Exposed as `COBRA` global object. Key functions:

| Function | Purpose |
|----------|---------|
| `initExtension(callback)` | Init Tableau API with non-Tableau fallback |
| `readWorksheetPollutants(ws)` | Extract PM25/SO2/NOx/VOC from worksheet (handles direct columns and pivoted Measure Names/Values format) |
| `readWorksheetPollutantsByColumns(ws)` | Column-name-based pollutant extraction (for policy module), with pivoted fallback |
| `matchPollutantName(name)` | Match a name to "PM25", "SO2", "NOx", or "VOC" using multiple patterns (abbreviations + full names) |
| `findParamValue(params, names)` | Find first matching Tableau parameter by name |
| `findFilterValue(dashboard, fieldNames)` | Read single-select filter values from worksheet filters |
| `callHealthEffects(payload, includeHE)` | POST to `/health-effects` |
| `storeResults(data, source)` | POST to `/store-results` |
| `formatCurrency(n)` | Format number as `$1,234` |
| `sectorLabel(key)` | Human-readable fuel label |
| `renderSummary(data, geo)` | Render low/high total HTML |
| `renderHealthTable(rows, opts)` | Render grouped health endpoint table |

#### Worksheet Data Reading — Key Gotcha

Tableau worksheets use two data formats:

1. **Direct columns**: Separate columns named `PM2.5 (Tons)`, `SO2 (Tons)`, etc. → matched by column `fieldName`.
2. **Pivoted format**: Two columns — `Measure Names` (string) + `Measure Values` (number). Each row has one pollutant. The measure name's `formattedValue` contains the display name (e.g., "PM2.5 (Tons)"). **Do NOT use `nativeValue`** — it's an internal Tableau reference like `[federated.06f4yba19qifmm14ty0nk02qhu6y].[sum:Fuel_PM2.5...]`.

The `matchPollutantName()` function handles both formats with expanded patterns:
- PM2.5: `PM2`, `PM25`, `PARTICULATE`
- SO2: `SO2`, `SULFUR`, `SULPHUR`
- NOx: `NOX`, `NO2`, `NITROGEN`
- VOC: `VOC`, `VOLATILE`

### Extensions

#### Code Comparison (`code-comparison.html`)
- Reads worksheets with "electric" or "fuel" in the name
- Electric → `grid` fuel key, Fuel → `natural_gas` fuel key
- Location: State from params or filters, County from filters
- Stores results as `code_comparison`

#### Custom Module (`custom-module.html`)
- Reads 5 fuel worksheets by pattern matching: grid, natural_gas, propane, fuel_oil, biomass
- Location: "State/Grid Region" parameter (state abbrevs, eGRID codes, eGRID display names)
- No county support (grid regions don't map to counties)
- Stores results as `custom_module`

#### Policy Module (`policy-module.html`)
- Reads fuel worksheets → `natural_gas`, grid worksheets → `grid`
- Fuel patterns: `"pollutants reduced from fuel"`, `"fuel use"`, `"policy_natural"`, `"ps_pollu"`
- Grid patterns: `"pollutants from grid"`, `"grid use"`, `"electric_gain"`, `"ps_grid"`, `"grid_pollu"`
- Uses `readWorksheetPollutantsByColumns()` for column-name-based matching, with pivoted fallback
- Location: State + County (same as code comparison)
- Stores results as `policy_module`

#### Detailed Health (`detailed-health.html`)
- No calculation — reads cached results from `/latest-results`
- 3 source tabs (Code Comparison, Custom Module, Policy Module)
- National / State / County geo toggle
- Per-sector sub-tabs when sector data available
- CSV export of health endpoint table

---

## Performance Notes

- **EPA API is the bottleneck**. Token fetch: 1.5s–170s (cold start). Result fetches: ~15s each, 3 per fuel (national + state + county).
- Fuels run concurrently via `asyncio.gather`, but the EPA API processes result fetches sequentially.
- A COBRA token is a workspace/session ID, not authentication. One token could handle multiple tier updates (saving token fetch time), but this loses per-fuel breakdown.
- Total time per calculation: ~1-2 minutes for typical use (2-3 fuels).
