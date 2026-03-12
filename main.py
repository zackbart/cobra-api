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
from sector_map import get_tiers, get_tiers_for_fuel, get_tiers_for_fuel_by_source

app = FastAPI(title="COBRA Proxy", docs_url="/")
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

    if fips == "00":
        fipscodes = ["36"]
        state_fips = "36"
        county_fips = None
    elif len(fips) == 2:
        fipscodes = [fips]
        state_fips = fips
        county_fips = None
    else:
        fipscodes = [fips]
        state_fips = fips[:2]
        county_fips = fips

    # Per-fuel mode: run sectors concurrently, sum results, add by_sector
    if req.emissions_by_fuel:
        async def run_one_fuel(fuel_key: str, em: dict):
            tiers = get_tiers_for_fuel_by_source(fuel_key, source)
            emissions = {"PM25": float(em.get("PM25", 0) or 0), "SO2": float(em.get("SO2", 0) or 0),
                        "NOx": float(em.get("NOx", 0) or 0), "VOC": float(em.get("VOC", 0) or 0)}
            token = await run_scenario(fipscodes, tiers, emissions)
            national = await get_result(token, "00" if fips == "00" else None)
            state = await get_result(token, state_fips)
            county = await get_result(token, county_fips) if county_fips else None
            return (fuel_key, {"national": national, "state": state, "county": county})

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
        fuels_data = []
        for r in results:
            if isinstance(r, Exception):
                raise HTTPException(502, str(r))
            fuels_data.append(r)

        # fuels_data: list of (fuel_key, {national, state, county})
        fuel_entries = [x[1] for x in fuels_data]
        fuel_keys = [x[0] for x in fuels_data]

        def sum_summary(data_list, geo):
            low = high = 0
            for d in data_list:
                s = d[geo].get("Summary", {}) if d[geo] else {}
                low += float(s.get("TotalHealthBenefitsValue_low") or 0)
                high += float(s.get("TotalHealthBenefitsValue_high") or 0)
            return {"TotalHealthBenefitsValue_low": low, "TotalHealthBenefitsValue_high": high}

        def build_by_sector(data_list, geo):
            return {
                fk: {
                    "TotalHealthBenefitsValue_low": float(d[geo].get("Summary", {}).get("TotalHealthBenefitsValue_low") or 0),
                    "TotalHealthBenefitsValue_high": float(d[geo].get("Summary", {}).get("TotalHealthBenefitsValue_high") or 0),
                }
                for fk, d in zip(fuel_keys, data_list) if d[geo]
            }

        national_merged = {"Summary": sum_summary(fuel_entries, "national"), "by_sector": build_by_sector(fuel_entries, "national")}
        state_merged = {"Summary": sum_summary(fuel_entries, "state"), "by_sector": build_by_sector(fuel_entries, "state")}
        county_merged = {"Summary": sum_summary(fuel_entries, "county"), "by_sector": build_by_sector(fuel_entries, "county")} if county_fips else None

        # Merge Impacts for combined HealthEndpoints; per-sector HealthEndpoints from each fuel
        if include_impacts or include_health_endpoints:
            def merge_impacts(data_list, geo):
                imps = [d[geo].get("Impacts", []) for d in data_list if d[geo] and d[geo].get("Impacts")]
                if not imps:
                    return []
                n = min(len(p) for p in imps)
                merged = []
                for i in range(n):
                    row = {}
                    for k in imps[0][i].keys():
                        if k in ("ID", "destindx", "FIPS", "COUNTY", "STATE"):
                            row[k] = imps[0][i].get(k)
                        else:
                            try:
                                row[k] = sum(float(p[i].get(k, 0) or 0) for p in imps if i < len(p) and p[i])
                            except (TypeError, ValueError, KeyError):
                                row[k] = imps[0][i].get(k, 0)
                    merged.append(row)
                return merged

            national_imps = merge_impacts(fuel_entries, "national")
            state_imps = merge_impacts(fuel_entries, "state")
            county_imps = merge_impacts(fuel_entries, "county") if county_fips else []

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
                        "national": aggregate_health_endpoints(d["national"].get("Impacts", [])),
                        "state": aggregate_health_endpoints(d["state"].get("Impacts", [])),
                        "county": aggregate_health_endpoints(d["county"].get("Impacts", [])) if county_fips and d["county"] else [],
                    }
                    for fk, d in fuels_data
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

    national = await get_result(token, "00" if fips == "00" else None)
    state = await get_result(token, state_fips)
    county = await get_result(token, county_fips) if county_fips else None

    def summary(data):
        s = data.get("Summary", {})
        return {
            "TotalHealthBenefitsValue_low": s.get("TotalHealthBenefitsValue_low"),
            "TotalHealthBenefitsValue_high": s.get("TotalHealthBenefitsValue_high"),
        }

    def format_result(data):
        out = {"Summary": summary(data)}
        if include_impacts:
            out["Impacts"] = data.get("Impacts", [])
        return out

    result = {
        "national": format_result(national),
        "state": format_result(state),
        "county": format_result(county) if county else None,
    }

    if include_health_endpoints:
        result["HealthEndpoints"] = {
            "national": aggregate_health_endpoints(national.get("Impacts", [])),
            "state": aggregate_health_endpoints(state.get("Impacts", [])),
            "county": aggregate_health_endpoints(county.get("Impacts", [])) if county else [],
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
