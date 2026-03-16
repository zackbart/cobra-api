"""Minimal COBRA proxy - no auth, callable from anywhere."""

import asyncio
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cobra_client import get_result, run_scenario
from health_endpoints import aggregate_health_endpoints
from region_map import normalize_state_abbrev, region_to_fips, resolve_state_county
from sector_map import get_tiers, get_tiers_for_fuel_by_source

app = FastAPI(title="COBRA Proxy", docs_url="/")


def _filter_impacts(impacts: list[dict], fips_prefix: str | None) -> list[dict]:
    """Filter Impacts rows by FIPS prefix (2-digit state, 5-digit county, or None for all)."""
    if not fips_prefix:
        return impacts
    return [r for r in impacts if str(r.get("FIPS", "")).startswith(fips_prefix)]


def _summarize_impacts(impacts: list[dict]) -> dict:
    """Sum C__Total_Health_Benefits values from Impacts rows into a Summary dict."""
    low = sum(float(r.get("C__Total_Health_Benefits_Low_Value", 0) or 0) for r in impacts)
    high = sum(float(r.get("C__Total_Health_Benefits_High_Value", 0) or 0) for r in impacts)
    return {"TotalHealthBenefitsValue_low": low, "TotalHealthBenefitsValue_high": high}
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    """Lightweight health check for Railway/proxy probes. Returns immediately."""
    return {"status": "ok"}


# Per-session, per-source cache for Detailed Health Impacts dashboard.
# Key: "{session_id}:{source}", Value: (payload, stored_at_timestamp)
_result_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 300  # seconds (5 minutes)


def _cache_key(session_id: str, source: str) -> str:
    return f"{session_id}:{source}"


def _evict_expired():
    """Remove entries older than TTL. Called on every store/retrieve."""
    cutoff = time.monotonic() - _CACHE_TTL
    expired = [k for k, (_, ts) in _result_cache.items() if ts < cutoff]
    for k in expired:
        del _result_cache[k]

# Mount Tableau extension static files
static_dir = Path(__file__).parent / "static" / "extension"
if static_dir.exists():
    app.mount("/extension", StaticFiles(directory=str(static_dir)), name="extension")


class HealthEffectsRequest(BaseModel):
    region: str | None = None
    state: str | None = None  # state abbreviation (e.g. "AR")
    county_name: str | None = None  # county display name (e.g. "Benton County")
    sector: str | None = None  # legacy single-sector mode
    emissions: dict | None = None  # legacy: single emissions payload
    emissions_by_fuel: dict | None = None  # per-fuel: {"grid": {...}, "natural_gas": {...}, ...}


@app.post("/health-effects")
async def health_effects(
    req: HealthEffectsRequest,
    include_impacts: bool = Query(False, description="Include full Impacts array (per-county rows)"),
    include_health_endpoints: bool = Query(False, description="Include aggregated health endpoint table"),
    source: str | None = Query(None, description="Extension: code_comparison, custom_module, policy_module"),
):
    """Run COBRA scenario(s), return National + State + County health effects."""
    # Normalize: treat blank or "all" county_name as no county (state-level only)
    county_name = (req.county_name or "").strip() or None
    if county_name:
        _lower = county_name.lower()
        _all_sentinels = {
            "(all)", "all", "(all values)", "all values",
            "all counties", "(all counties)", "all parishes", "(all parishes)",
            "none", "select", "select county", "select a county",
            "-- all --", "statewide", "entire state",
        }
        if _lower in _all_sentinels or _lower.startswith("all "):
            county_name = None

    # Resolve FIPS: prefer state/county_name if provided, fall back to region
    if req.state and county_name:
        try:
            fips = resolve_state_county(req.state, county_name)
        except ValueError:
            # State format may not be an abbreviation/name (e.g. FIPS code).
            # Resolve state first, then retry county lookup before giving up.
            try:
                state_fips_resolved = region_to_fips(req.state)
                st_abbrev = normalize_state_abbrev(req.state)
                if st_abbrev:
                    fips = resolve_state_county(st_abbrev, county_name)
                else:
                    # Can't determine abbreviation — fall back to state-level
                    fips = state_fips_resolved
            except ValueError as e:
                raise HTTPException(400, str(e))
    elif req.state:
        try:
            fips = region_to_fips(req.state)
        except ValueError as e:
            raise HTTPException(400, str(e))
    elif req.region:
        try:
            fips = region_to_fips(req.region)
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        raise HTTPException(400, "Provide region, or state (+ optional county_name)")

    # Always run scenarios at state level; county is a presentation filter only.
    if fips == "00":
        state_fips = "36"
        county_fips = None
    elif len(fips) == 2:
        state_fips = fips
        county_fips = None
    else:
        state_fips = fips[:2]
        county_fips = fips

    fipscodes = [state_fips]

    # Per-fuel mode: run sectors concurrently, sum results, add by_sector
    if req.emissions_by_fuel:
        async def run_one_fuel(fuel_key: str, em: dict):
            tiers = get_tiers_for_fuel_by_source(fuel_key, source)
            emissions = {"PM25": float(em.get("PM25", 0) or 0), "SO2": float(em.get("SO2", 0) or 0),
                        "NOx": float(em.get("NOx", 0) or 0), "VOC": float(em.get("VOC", 0) or 0)}
            token = await run_scenario(fipscodes, tiers, emissions)
            result = await get_result(token)
            impacts = result.get("Impacts", [])
            return (fuel_key, impacts)

        tasks = []
        for fuel_key, em in req.emissions_by_fuel.items():
            if not em or not isinstance(em, dict):
                continue
            pm25 = float(em.get("PM25", 0) or 0)
            so2 = float(em.get("SO2", 0) or 0)
            nox = float(em.get("NOx", 0) or 0)
            voc = float(em.get("VOC", 0) or 0)
            if pm25 == 0 and so2 == 0 and nox == 0 and voc == 0:
                continue
            try:
                tasks.append(run_one_fuel(fuel_key, em))
            except ValueError:
                continue

        if not tasks:
            raise HTTPException(400, "No emissions in emissions_by_fuel")

        results = await asyncio.gather(*tasks, return_exceptions=True)
        # fuels_data: list of (fuel_key, impacts_list)
        fuels_data = []
        for r in results:
            if isinstance(r, Exception):
                raise HTTPException(502, str(r))
            fuels_data.append(r)

        fuel_keys = [fk for fk, _ in fuels_data]
        fuel_impacts = [imps for _, imps in fuels_data]

        def geo_summary(impacts_list, fips_prefix):
            """Sum summaries across fuels for a given geography."""
            low = high = 0
            for imps in impacts_list:
                s = _summarize_impacts(_filter_impacts(imps, fips_prefix))
                low += s["TotalHealthBenefitsValue_low"]
                high += s["TotalHealthBenefitsValue_high"]
            return {"TotalHealthBenefitsValue_low": low, "TotalHealthBenefitsValue_high": high}

        def by_sector(impacts_list, fips_prefix):
            """Per-fuel summaries for a given geography."""
            return {
                fk: _summarize_impacts(_filter_impacts(imps, fips_prefix))
                for fk, imps in zip(fuel_keys, impacts_list)
            }

        national_merged = {"Summary": geo_summary(fuel_impacts, None), "by_sector": by_sector(fuel_impacts, None)}
        state_merged = {"Summary": geo_summary(fuel_impacts, state_fips), "by_sector": by_sector(fuel_impacts, state_fips)}
        county_merged = {"Summary": geo_summary(fuel_impacts, county_fips), "by_sector": by_sector(fuel_impacts, county_fips)} if county_fips else None

        # Merge Impacts across fuels for HealthEndpoints
        if include_impacts or include_health_endpoints:
            def merge_impacts(impacts_list, fips_prefix):
                filtered = [_filter_impacts(imps, fips_prefix) for imps in impacts_list]
                filtered = [f for f in filtered if f]
                if not filtered:
                    return []
                n = min(len(f) for f in filtered)
                merged = []
                for i in range(n):
                    row = {}
                    for k in filtered[0][i].keys():
                        if k in ("ID", "destindx", "FIPS", "COUNTY", "STATE"):
                            row[k] = filtered[0][i].get(k)
                        else:
                            try:
                                row[k] = sum(float(f[i].get(k, 0) or 0) for f in filtered if i < len(f) and f[i])
                            except (TypeError, ValueError, KeyError):
                                row[k] = filtered[0][i].get(k, 0)
                    merged.append(row)
                return merged

            national_imps = merge_impacts(fuel_impacts, None)
            state_imps = merge_impacts(fuel_impacts, state_fips)
            county_imps = merge_impacts(fuel_impacts, county_fips) if county_fips else []

            if include_impacts:
                national_merged["Impacts"] = national_imps
                state_merged["Impacts"] = state_imps
                if county_merged:
                    county_merged["Impacts"] = county_imps

            health_endpoints = None
            health_endpoints_by_sector = None
            if include_health_endpoints:
                health_endpoints = {
                    "national": aggregate_health_endpoints(national_imps),
                    "state": aggregate_health_endpoints(state_imps),
                    "county": aggregate_health_endpoints(county_imps) if county_fips else [],
                }
                health_endpoints_by_sector = {
                    fk: {
                        "national": aggregate_health_endpoints(_filter_impacts(imps, None)),
                        "state": aggregate_health_endpoints(_filter_impacts(imps, state_fips)),
                        "county": aggregate_health_endpoints(_filter_impacts(imps, county_fips)) if county_fips else [],
                    }
                    for fk, imps in fuels_data
                }

        result = {
            "national": national_merged,
            "state": state_merged,
            "county": county_merged,
        }
        if include_health_endpoints and health_endpoints:
            result["HealthEndpoints"] = health_endpoints
        if include_health_endpoints and health_endpoints_by_sector:
            result["HealthEndpoints_by_sector"] = health_endpoints_by_sector
        return result

    # Legacy single-sector mode
    if not req.emissions or not req.sector:
        raise HTTPException(400, "Provide sector + emissions, or emissions_by_fuel")

    try:
        tiers = get_tiers(req.sector)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        token = await run_scenario(fipscodes, tiers, req.emissions)
    except Exception as e:
        raise HTTPException(502, f"COBRA API error: {e}")

    raw = await get_result(token)
    impacts = raw.get("Impacts", [])

    national_imps = _filter_impacts(impacts, None)
    state_imps = _filter_impacts(impacts, state_fips)
    county_imps = _filter_impacts(impacts, county_fips) if county_fips else []

    def format_result(filtered_imps):
        out = {"Summary": _summarize_impacts(filtered_imps)}
        if include_impacts:
            out["Impacts"] = filtered_imps
        return out

    result = {
        "national": format_result(national_imps),
        "state": format_result(state_imps),
        "county": format_result(county_imps) if county_fips else None,
    }

    if include_health_endpoints:
        result["HealthEndpoints"] = {
            "national": aggregate_health_endpoints(national_imps),
            "state": aggregate_health_endpoints(state_imps),
            "county": aggregate_health_endpoints(county_imps) if county_fips else [],
        }

    return result


# --- Lightweight cache for Detailed Health Impacts dashboard ---

@app.post("/store-results")
async def store_results(
    payload: dict = Body(...),
    source: str = Query("default", description="Source extension (code_comparison, custom_module, policy_module)"),
    session_id: str = Query("default", description="Client session ID (from localStorage)"),
):
    """Store full health-effects response, keyed by session + source."""
    _evict_expired()
    _result_cache[_cache_key(session_id, source)] = (payload, time.monotonic())
    return {"ok": True}


@app.get("/latest-results")
async def latest_results(
    source: str = Query(None, description="Source extension to retrieve. Omit to get all sources."),
    session_id: str = Query("default", description="Client session ID (from localStorage)"),
):
    """Return stored results for this session. Specify source for one extension, or omit for all."""
    _evict_expired()
    if source:
        key = _cache_key(session_id, source)
        if key not in _result_cache:
            raise HTTPException(404, f"No results for '{source}'. Run a calculation first.")
        return _result_cache[key][0]
    # Return all sources for this session
    session_results = {
        k.split(":", 1)[1]: v[0]
        for k, v in _result_cache.items()
        if k.startswith(f"{session_id}:")
    }
    if not session_results:
        raise HTTPException(404, "No results yet. Run a calculation on any input dashboard first.")
    return session_results
