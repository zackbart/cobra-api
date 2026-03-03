#!/usr/bin/env python3
"""Test deployed API: simulate each dashboard, store results, verify Detail view data."""

import json
import sys
from pathlib import Path

import httpx

API_BASE = "https://cobra-api.up.railway.app"
TIMEOUT = httpx.Timeout(120)  # EPA COBRA can be slow


def post_health_effects(payload: dict) -> dict:
    """POST /health-effects with include_health_endpoints=true."""
    r = httpx.post(
        f"{API_BASE}/health-effects",
        params={"include_health_endpoints": "true"},
        json=payload,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def store_results(data: dict) -> None:
    """POST /store-results (simulates extension after Calculate)."""
    r = httpx.post(f"{API_BASE}/store-results", json=data, timeout=30)
    r.raise_for_status()


def get_latest_results() -> dict:
    """GET /latest-results (what Detail view fetches)."""
    r = httpx.get(f"{API_BASE}/latest-results", timeout=30)
    r.raise_for_status()
    return r.json()


def verify_detail_view_data(data: dict, expected_sectors: list[str], label: str) -> bool:
    """Verify response has structure needed for Detail view."""
    ok = True
    for geo in ["national", "state", "county"]:
        if geo not in data:
            continue
        g = data[geo]
        if not g:
            continue
        if "Summary" not in g:
            print(f"  {label}: {geo} missing Summary")
            ok = False
        if "by_sector" not in g:
            print(f"  {label}: {geo} missing by_sector")
            ok = False
        else:
            for sk in expected_sectors:
                if sk not in g["by_sector"]:
                    print(f"  {label}: {geo} by_sector missing {sk}")
                    ok = False

    if "HealthEndpoints" not in data:
        print(f"  {label}: missing HealthEndpoints")
        ok = False
    if "HealthEndpoints_by_sector" not in data:
        print(f"  {label}: missing HealthEndpoints_by_sector")
        ok = False
    else:
        for sk in expected_sectors:
            if sk not in data["HealthEndpoints_by_sector"]:
                print(f"  {label}: HealthEndpoints_by_sector missing {sk}")
                ok = False
            else:
                for geo in ["national", "state", "county"]:
                    if geo in data and data[geo]:
                        rows = data["HealthEndpoints_by_sector"][sk].get(geo, [])
                        if not isinstance(rows, list):
                            print(f"  {label}: HealthEndpoints_by_sector[{sk}][{geo}] not a list")
                            ok = False
    return ok


def main():
    dashboards = [
        (
            "Code Comparison",
            {"region": "36061", "emissions_by_fuel": {"grid": {"PM25": 0.1, "SO2": 0, "NOx": 0, "VOC": 0}, "natural_gas": {"PM25": 0.05, "SO2": 0, "NOx": 0, "VOC": 0}}},
            ["grid", "natural_gas"],
        ),
        (
            "Custom Scenario",
            {
                "region": "NY",
                "emissions_by_fuel": {
                    "grid": {"PM25": 0.2, "SO2": 0.1, "NOx": 0.1, "VOC": 0},
                    "natural_gas": {"PM25": 0.1, "SO2": 0, "NOx": 0, "VOC": 0},
                    "propane": {"PM25": 0.02, "SO2": 0, "NOx": 0, "VOC": 0},
                    "fuel_oil": {"PM25": 0.03, "SO2": 0, "NOx": 0, "VOC": 0},
                    "biomass": {"PM25": 0.05, "SO2": 0, "NOx": 0, "VOC": 0},
                },
            },
            ["grid", "natural_gas", "propane", "fuel_oil", "biomass"],
        ),
        (
            "Policy Scenario",
            {"region": "AZ", "emissions_by_fuel": {"grid": {"PM25": 0.15, "SO2": 0.05, "NOx": 0.08, "VOC": 0}, "natural_gas": {"PM25": 0.08, "SO2": 0, "NOx": 0, "VOC": 0}}},
            ["grid", "natural_gas"],
        ),
    ]

    all_ok = True
    for name, payload, expected_sectors in dashboards:
        print(f"\n--- {name} ---")
        try:
            print("  Calling /health-effects...")
            data = post_health_effects(payload)
            print("  Storing results...")
            store_results(data)
            print("  Fetching /latest-results...")
            latest = get_latest_results()
            if verify_detail_view_data(latest, expected_sectors, name):
                print(f"  OK: Detail view will show {len(expected_sectors)} sector(s)")
                low = latest.get("national", {}).get("Summary", {}).get("TotalHealthBenefitsValue_low")
                high = latest.get("national", {}).get("Summary", {}).get("TotalHealthBenefitsValue_high")
                print(f"  National total: ${low:,.0f} (low) / ${high:,.0f} (high)")
            else:
                all_ok = False
        except httpx.HTTPStatusError as e:
            print(f"  FAIL: {e.response.status_code} - {e.response.text[:200]}")
            all_ok = False
        except Exception as e:
            print(f"  FAIL: {e}")
            all_ok = False

    print("\n" + ("All dashboards OK." if all_ok else "Some checks failed."))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
