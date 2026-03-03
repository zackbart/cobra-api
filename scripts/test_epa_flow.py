#!/usr/bin/env python3
"""Test EPA COBRA API flow - trace where it hangs."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cobra_client import get_result, run_scenario


async def main():
    fipscodes = ["36061"]
    tiers = "1,3,1"
    reductions = {"PM25": 0.1, "SO2": 0, "NOx": 0, "VOC": 0}

    print("1. run_scenario (token + baseline + update)...")
    t0 = time.monotonic()
    token = await run_scenario(fipscodes, tiers, reductions)
    print(f"   Done in {time.monotonic() - t0:.1f}s")

    print("2. get_result national (no filter)...")
    t0 = time.monotonic()
    national = await get_result(token, None)
    print(f"   Done in {time.monotonic() - t0:.1f}s, keys: {list(national.keys())[:5]}")

    print("3. get_result state (36)...")
    t0 = time.monotonic()
    state = await get_result(token, "36")
    print(f"   Done in {time.monotonic() - t0:.1f}s")

    print("4. get_result county (36061)...")
    t0 = time.monotonic()
    county = await get_result(token, "36061")
    print(f"   Done in {time.monotonic() - t0:.1f}s")

    s = national.get("Summary", {})
    print(f"\nOK - TotalHealthBenefitsValue_low: {s.get('TotalHealthBenefitsValue_low')}")


if __name__ == "__main__":
    asyncio.run(main())
