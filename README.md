# COBRA Proxy API

> Proxy API for the EPA [COBRA (CO-Benefits Risk Assessment)](https://www.epa.gov/cobra) screening tool. Calculates health impacts from changes in air pollutant emissions (PM2.5, SO2, NOx, VOC) and powers 4 Tableau dashboard extensions.

[![Deploy](https://img.shields.io/badge/deploy-Railway-blueviolet)](https://cobra-api.up.railway.app)

**Production:** https://cobra-api.up.railway.app
**Docs:** [Architecture](docs/arch.md) | [Tableau Extensions](docs/tableau.md) | [Troubleshooting](docs/troubleshooting.md)

---

## How It Works

Tableau dashboards contain worksheets with pollutant emission data. Each extension reads pollutant values (PM2.5, SO2, NOx, VOC) + location (state/county/eGRID region) from the dashboard, sends them to this proxy API, which calls the EPA COBRA API to calculate health impacts (mortality, morbidity, monetary value). Results are displayed in the extension and cached for the detail dashboard.

---

## Extensions

| Extension | .trex | Dashboard | Purpose |
|-----------|-------|-----------|---------|
| Code Comparison | `CodeComparison.trex` | Dashboard 1 | Electricity vs fuel pollutant comparison |
| Custom Module | `CustomModule.trex` | Dashboard 2 | 5 fuel sources (grid, natural gas, propane, fuel oil, biomass) |
| Policy Module | `PolicyModule.trex` | Dashboard 3 | Policy-driven pollutant reductions (fuel + grid) |
| Detailed Health | `DetailedHealth.trex` | Dashboard 4 | Full health endpoint table from cached results |

Legacy extension `HealthResults.trex` / `index.html` still exists for backward compatibility.

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health-effects` | POST | Run COBRA scenarios, return national/state/county totals + per-fuel breakdown |
| `/store-results` | POST | Cache response (called by extensions after Calculate) |
| `/latest-results` | GET | Return cached results (used by Detail dashboard) |
| `/health` | GET | Health check |

### Request Format

```json
{
  "state": "AR",
  "county_name": "Benton County",
  "emissions_by_fuel": {
    "grid": { "PM25": 1.0, "SO2": 0.5, "NOx": 0.3, "VOC": 0.1 },
    "natural_gas": { "PM25": 0.5, "SO2": 0.2, "NOx": 0.1, "VOC": 0.05 }
  }
}
```

Location can be specified as:
- `state` + optional `county_name` (preferred, used by extensions)
- `region` (state abbrev, eGRID code, FIPS code, or "national")

Add `?include_health_endpoints=true` for full health endpoint tables. Add `?source=code_comparison` (or `custom_module`, `policy_module`) for per-extension COBRA tier mapping so each dashboard uses the correct sector/subsector.

### Response Structure

```
national/state/county:
  Summary: { TotalHealthBenefitsValue_low, TotalHealthBenefitsValue_high }
  by_sector: { grid: {...}, natural_gas: {...}, ... }
HealthEndpoints: { national: [...], state: [...], county: [...] }
HealthEndpoints_by_sector: { grid: { national: [...], ... }, ... }
```

---

## Project Structure

```
main.py                  # FastAPI app, /health-effects endpoint
cobra_client.py          # EPA COBRA API client (token, baseline, update, result)
sector_map.py            # Fuel key -> COBRA tier mapping
region_map.py            # State/eGRID/FIPS region resolution
county_fips.py           # County name -> 5-digit FIPS (3,235 counties)
health_endpoints.py      # Aggregate COBRA Impacts into health endpoint table

static/extension/
  shared.js              # Common JS: Tableau init, worksheet reading, API calls
  shared.css             # Common styles
  code-comparison.html   # Extension: electricity + fuel
  custom-module.html     # Extension: 5 fuel sources
  policy-module.html     # Extension: policy fuel + grid
  detailed-health.html   # Extension: cached results viewer
  CodeComparison.trex    # Tableau manifest
  CustomModule.trex
  PolicyModule.trex
  DetailedHealth.trex
  index.html             # Legacy extension (keep for compatibility)
  HealthResults.trex     # Legacy manifest
```

---

## Deploy

**Railway** (production):
1. Deploy from CLI (`railway up`). Uses `Procfile`.
2. Health check path: `/health`
3. `/health-effects` takes 1-2 min (EPA API is slow); Railway allows 15 min timeout.

**Local:**
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://localhost:8000 for FastAPI docs.

---

## Tech Stack

- **Runtime:** Python 3 + [FastAPI](https://fastapi.tiangolo.com/)
- **HTTP client:** [httpx](https://www.python-httpx.org/) (async calls to EPA COBRA API)
- **Hosting:** [Railway](https://railway.app/) with Uvicorn
- **Frontend:** Vanilla JS Tableau Extensions (no build step)

## Known Issues / Active Work

- **Fuel oil missing SO2/NOx/VOC**: The custom module's fuel oil worksheet sometimes returns 0 for SO2/NOx/VOC despite the dashboard showing values. Enhanced pollutant name matching (including full names like "Sulfur Dioxide", "Nitrogen") was added but needs Tableau testing. Check browser console for `[COBRA]` debug logs.
- **Debug logging**: All 3 input extensions currently have verbose debug logging enabled (visible in collapsible "Debug info" section and browser console). Remove once all worksheets read correctly.
- **Result cache is in-memory**: Cleared on server restart. Single-slot per source.
