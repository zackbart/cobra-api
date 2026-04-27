# COBRA Proxy API

> Proxy API for the EPA [COBRA (CO-Benefits Risk Assessment)](https://www.epa.gov/cobra) screening tool. Calculates health impacts from changes in air pollutant emissions (PM2.5, SO2, NOx, VOC) and powers 4 Tableau dashboard extensions.

[![Deploy](https://img.shields.io/badge/deploy-Railway-blueviolet)](https://web-production-5bcd2.up.railway.app)

**Production:** https://web-production-5bcd2.up.railway.app
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

- **Fuel oil missing SO2/NOx/VOC** _(open, unverified)_: The custom module's fuel oil worksheet sometimes returns 0 for SO2/NOx/VOC despite the dashboard showing values. Enhanced pollutant name matching (full names like "Sulfur Dioxide", "Nitrogen") is in place but has not been verified end-to-end in a real Tableau dashboard. Tracked as Issue 6 in `docs/troubleshooting.md`.
- **Verbose debug surface** _(intentional, tied to Issue 6)_: All 3 input extensions render a collapsible "Debug info" panel and emit `[COBRA] …` console logs. This is **deliberately retained** until a maintainer verifies Issue 6 is resolved in production — it's the only practical way to diagnose worksheet-name mismatches in deployed Tableau. Removal criteria: Issue 6 confirmed fixed end-to-end, then strip the panel from the three input extensions and remove the `console.log` calls in `shared.js`.
- **Result cache is in-memory**: Cleared on server restart. Single-slot per source extension, 5-min TTL.

---

## Maintainer Notes

> **Audience split:** This README is the human onboarding doc — what the project is, how to run it, who has access. `CLAUDE.md` is for AI coding assistants — structure, conventions, gotchas. If you're handing this off, point your collaborator here first.

### Where things live
- **Code:** flat layout at the project root. Key modules in the table at [Project Structure](#project-structure).
- **Docs:** [`docs/arch.md`](docs/arch.md) (data flow, components, performance), [`docs/tableau.md`](docs/tableau.md) (extension dev workflow), [`docs/troubleshooting.md`](docs/troubleshooting.md) (numbered issue history).
- **Tests:** `scripts/` — see [Tests](#tests) below.
- **Reference data:** `county-baselines/` — per-county electricity baselines pulled from EPA COBRA. Not used at runtime; included so a maintainer can spot zero-baseline counties without re-running a multi-minute fetch. See `county-baselines/README.md`.

### Tests

```bash
python scripts/test_implementation.py    # unit tests (mocked, no EPA calls — fastest)
python scripts/test_state_resolution.py  # state/county resolution
python scripts/test_deployed.py          # smoke test against the deployed Railway URL
```

There is no test framework configured (no pytest config) — each script is runnable directly.

### EPA COBRA API quirks

- **No client-side auth.** EPA returns a per-session "token" that is really a workspace ID. `cobra_client.run_scenario()` fetches one per fuel and reuses it through baseline → update → result.
- **Slow.** Cold-start token fetch can take 1.5–170s; each result fetch is ~15s; the EPA backend serializes result fetches even when called concurrently. Budget 1–2 min per `/health-effects` call. Railway's timeout is set to 15 min for this reason.
- **Initialization state.** A token of `"initializing"` means EPA's service is warming up — wait a minute and retry. `cobra_client` raises a clear error in this case.
- **Filtering is client-side.** EPA's `/Result/{token}` returns national + every state + every county. We filter to the requested FIPS in `cobra_client._filter_impacts`. There is no server-side FIPS filter parameter.

### Railway / deploy

- Production URL: https://web-production-5bcd2.up.railway.app
- Deploy: `railway up` from the project root. The repo has both `Procfile` and `railway.json` — they specify the same start command (`uvicorn main:app --host 0.0.0.0 --port $PORT`).
- Health check: `GET /health`.
- Timeout: 15 min (set in Railway service settings to accommodate slow EPA calls).
- **Access:** ask Zack for Railway project access. There are no environment secrets to transfer — the EPA COBRA API requires no client credentials.

### Local development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000 for the auto-generated FastAPI docs. `requirements.txt` is fully pinned (top-level + transitives) so a fresh install reproduces the deployed environment exactly. To upgrade: edit, run `pip install -U -r requirements.txt && pip freeze > requirements.txt` in a clean venv, then re-add the header comment.

### Tableau extension workflow

See [`docs/tableau.md`](docs/tableau.md). The `.trex` manifests in `static/extension/` point at the production URL — to test a local edit against a live dashboard, either run `ngrok` (or similar) over `localhost:8000` and edit the `.trex` `url` element, or push a branch to a Railway PR environment.

## Changelog

- **2026-03-30**: Fixed state filter reading stuck on wrong state. `findFilterValue` in shared.js now checks ALL worksheets for each filter name and uses majority vote, instead of short-circuiting on the first worksheet match (which could return a stale value from a non-interactive worksheet).
