"""EPA COBRA API client."""

import httpx

BASE = "https://cobraapi.app.cloud.gov/api"
TIMEOUT = httpx.Timeout(120)  # EPA Result calls can take 30s+; Railway needs headroom

# Shared client for connection reuse (avoids connection churn on Railway)
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT)
    return _client


async def get_token() -> str:
    r = await _get_client().get(f"{BASE}/token")
    r.raise_for_status()
    return r.json()["value"]


async def get_baseline(token: str, fipscodes: list[str], tiers: str) -> dict:
    params = {"token": token, "fipscodes": ",".join(fipscodes), "tiers": tiers}
    r = await _get_client().get(f"{BASE}/SummarizedControlEmissions", params=params)
    r.raise_for_status()
    data = r.json()
    return data["baseline"][0] if data["baseline"] else {}


async def update_emissions(token: str, fipscodes: list[str], tiers: str, payload: dict) -> None:
    body = {
        "spec": {"token": token, "fipscodes": fipscodes, "tiers": tiers},
        "payload": payload,
    }
    r = await _get_client().post(f"{BASE}/EmissionsUpdate", json=body)
    r.raise_for_status()


async def get_result(token: str, filter_fips: str | None = None, discount_rate: float = 3) -> dict:
    url = f"{BASE}/Result/{token}" + (f"/{filter_fips}" if filter_fips else "")
    r = await _get_client().get(url, params={"discountrate": discount_rate})
    r.raise_for_status()
    return r.json()


async def run_scenario(fipscodes: list[str], tiers: str, reductions: dict) -> str:
    """Create token, apply emissions reductions, return token for result fetch."""
    token = await get_token()
    if token == "initializing":
        raise RuntimeError("COBRA API is initializing, retry in a minute")

    baseline = await get_baseline(token, fipscodes, tiers)
    control = {
        "PM25": float(baseline.get("PM25", 0)) - float(reductions.get("PM25", 0)),
        "SO2": float(baseline.get("SO2", 0)) - float(reductions.get("SO2", 0)),
        "NOx": float(baseline.get("NOx", 0)) - float(reductions.get("NOx", 0)),
        "VOC": float(baseline.get("VOC", 0)) - float(reductions.get("VOC", 0)),
        "NH3": float(baseline.get("NH3", 0)),
        "SOA": float(baseline.get("SOA", 0)),
    }
    await update_emissions(token, fipscodes, tiers, control)
    return token
