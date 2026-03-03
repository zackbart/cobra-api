"""Verify API response shape without hitting EPA API."""

import sys
from pathlib import Path

# Ensure project root is on path when run from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

MOCK_RESULT = {
    "Summary": {
        "TotalHealthBenefitsValue_low": 100000,
        "TotalHealthBenefitsValue_high": 200000,
    },
    "Impacts": [
        {"FIPS": "36061", "C__Total_Health_Benefits_Low_Value": 50000, "C__Total_Health_Benefits_High_Value": 100000}
    ],
}


def test_api_response_shape():
    """Verify per-fuel API returns by_sector and HealthEndpoints_by_sector."""
    with patch("main.run_scenario", AsyncMock(return_value="mock-token")), patch(
        "main.get_result", AsyncMock(return_value=MOCK_RESULT)
    ):
        from main import app

        client = TestClient(app)
        resp = client.post(
            "/health-effects?include_health_endpoints=true",
            json={
                "region": "36061",
                "emissions_by_fuel": {
                    "grid": {"PM25": 0.1, "SO2": 0, "NOx": 0, "VOC": 0},
                    "natural_gas": {"PM25": 0.05, "SO2": 0, "NOx": 0, "VOC": 0},
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # Top-level geographies
        for geo in ["national", "state", "county"]:
            assert geo in data
            g = data[geo]
            assert "Summary" in g
            assert "by_sector" in g
            assert "TotalHealthBenefitsValue_low" in g["Summary"]
            assert "TotalHealthBenefitsValue_high" in g["Summary"]
            assert "grid" in g["by_sector"]
            assert "natural_gas" in g["by_sector"]
            for sk, sv in g["by_sector"].items():
                assert "TotalHealthBenefitsValue_low" in sv
                assert "TotalHealthBenefitsValue_high" in sv

        # HealthEndpoints
        assert "HealthEndpoints" in data
        assert "HealthEndpoints_by_sector" in data
        for sector in ["grid", "natural_gas"]:
            assert sector in data["HealthEndpoints_by_sector"]
            for geo in ["national", "state", "county"]:
                assert geo in data["HealthEndpoints_by_sector"][sector]
                rows = data["HealthEndpoints_by_sector"][sector][geo]
                assert isinstance(rows, list)
        print("API response shape: OK")


def test_health_effects_with_source():
    """Verify /health-effects with source=code_comparison returns same response structure."""
    with patch("main.run_scenario", AsyncMock(return_value="mock-token")), patch(
        "main.get_result", AsyncMock(return_value=MOCK_RESULT)
    ):
        from main import app

        client = TestClient(app)
        resp = client.post(
            "/health-effects?include_health_endpoints=true&source=code_comparison",
            json={
                "region": "36061",
                "emissions_by_fuel": {
                    "grid": {"PM25": 0.1, "SO2": 0, "NOx": 0, "VOC": 0},
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        for geo in ["national", "state", "county"]:
            assert geo in data
            assert "by_sector" in data[geo]
            assert "grid" in data[geo]["by_sector"]
        print("Health-effects with source=code_comparison: OK")


def test_store_and_fetch():
    """Verify store-results and latest-results round-trip."""
    with patch("main.run_scenario", AsyncMock(return_value="t")), patch(
        "main.get_result",
        AsyncMock(
            return_value={
                "Summary": {"TotalHealthBenefitsValue_low": 1, "TotalHealthBenefitsValue_high": 2},
                "Impacts": [],
            }
        ),
    ):
        from main import app

        client = TestClient(app)
        payload = {
            "national": {
                "Summary": {"TotalHealthBenefitsValue_low": 100},
                "by_sector": {"grid": {"TotalHealthBenefitsValue_low": 50, "TotalHealthBenefitsValue_high": 100}},
            },
            "state": {},
            "county": {},
            "HealthEndpoints": {"national": [{"HealthEndpoint": "Mortality", "MonetaryLow": 50}]},
            "HealthEndpoints_by_sector": {"grid": {"national": [{"HealthEndpoint": "Mortality"}]}},
        }
        store_resp = client.post("/store-results", json=payload)
        assert store_resp.status_code == 200

        fetch_resp = client.get("/latest-results")
        assert fetch_resp.status_code == 200
        fetched = fetch_resp.json()
        assert fetched["HealthEndpoints_by_sector"]["grid"]["national"][0]["HealthEndpoint"] == "Mortality"
        assert fetched["national"]["by_sector"]["grid"]["TotalHealthBenefitsValue_low"] == 50
        print("Store/fetch round-trip: OK")


if __name__ == "__main__":
    test_api_response_shape()
    test_health_effects_with_source()
    test_store_and_fetch()
    print("All checks passed.")
