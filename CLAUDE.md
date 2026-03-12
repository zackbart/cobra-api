# CLAUDE.md — COBRA Proxy API

## What this project is

A FastAPI proxy that sits between Tableau dashboard extensions and the EPA COBRA (CO-Benefits Risk Assessment) API. Extensions send pollutant emission changes (PM2.5, SO2, NOx, VOC) for a location; this API calls EPA COBRA to calculate health impacts (mortality, morbidity, monetary value) and returns aggregated results.

## Quick start

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
# Open http://localhost:8000 for interactive API docs
```

## Key files

| File | Role |
|------|------|
| `main.py` | FastAPI app — `/health-effects`, `/store-results`, `/latest-results`, `/health` |
| `cobra_client.py` | Async EPA COBRA API client (token, baseline, scenario, result) |
| `sector_map.py` | Maps fuel keys to COBRA tier1/tier2/tier3 sectors |
| `region_map.py` | Resolves state abbrevs, eGRID codes, FIPS codes to COBRA regions |
| `county_fips.py` | County name → 5-digit FIPS lookup (3,235 counties) |
| `health_endpoints.py` | Aggregates COBRA Impacts into health endpoint tables |
| `static/extension/shared.js` | Common JS for all Tableau extensions |
| `static/extension/*.html` | Individual extension UIs (code-comparison, custom-module, policy-module, detailed-health) |

## Architecture notes

- **No auth** — the proxy is open (CORS `*`). EPA COBRA API handles its own auth tokens internally via `cobra_client.py`.
- **In-memory cache** — `/store-results` and `/latest-results` use a dict keyed by `session_id:source` with 5-min TTL. Cleared on restart.
- **Async flow** — each fuel in `emissions_by_fuel` runs a separate COBRA scenario via `asyncio.gather`. EPA API is slow (1-2 min per scenario).
- **Source-specific tier mapping** — the `?source=` query param selects which COBRA sector/subsector mapping to use (code_comparison, custom_module, policy_module).

## Deploy

Production runs on **Railway** (`Procfile`: `uvicorn main:app --host 0.0.0.0 --port $PORT`). Health check at `/health`. Railway timeout is 15 min to accommodate slow EPA API responses.

## Testing

Test scripts live in `scripts/`. They are integration tests that hit the deployed or local API:
```bash
python scripts/test_deployed.py       # smoke test against production
python scripts/test_state_resolution.py  # state/county routing tests
```

## Conventions

- Python files at project root (flat structure, no `src/` directory)
- Tableau extension files in `static/extension/`
- Docs in `docs/` (arch.md, tableau.md, troubleshooting.md)
- No `.env` file — no secrets needed locally (EPA COBRA API tokens are ephemeral, fetched at runtime)
