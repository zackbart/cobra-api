"""Fetch electricity baseline emissions for every US county from EPA COBRA API.

Usage:
    python county-baselines/fetch_baselines.py

Outputs:
    county-baselines/electricity_baselines.csv   — all results (appended as they come in)
    county-baselines/electricity_errors.csv      — failed FIPS codes (for re-run)

Re-run safe: skips any FIPS already present in the results CSV.
"""

import asyncio
import csv
import sys
import time
from pathlib import Path

import httpx

# Add project root so we can import county_fips
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from county_fips import COUNTY_FIPS

# --- Config ---
BASE = "https://cobraapi.app.cloud.gov/api"
TIER = "1,3,1"  # Electric Utility
CONCURRENCY = 5
TIMEOUT = httpx.Timeout(120)

OUT_DIR = Path(__file__).resolve().parent
RESULTS_CSV = OUT_DIR / "electricity_baselines.csv"
ERRORS_CSV = OUT_DIR / "electricity_errors.csv"

RESULTS_HEADER = ["State", "County", "FIPS", "PM25", "SO2", "NOx", "VOC", "AllZero"]
ERRORS_HEADER = ["FIPS", "State", "County", "Error", "Timestamp"]


def load_completed_fips() -> set[str]:
    """Read FIPS codes already in the results CSV to skip on re-run."""
    done = set()
    if RESULTS_CSV.exists():
        with open(RESULTS_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                done.add(row["FIPS"])
    return done


def build_county_list() -> list[tuple[str, str, str]]:
    """Return [(state_abbrev, county_name, fips), ...] sorted by state then county."""
    counties = []
    for (state, county), fips in COUNTY_FIPS.items():
        counties.append((state, county, fips))
    counties.sort(key=lambda x: (x[0], x[1]))
    return counties


async def get_token(client: httpx.AsyncClient) -> str:
    r = await client.get(f"{BASE}/token")
    r.raise_for_status()
    token = r.json()["value"]
    if token == "initializing":
        raise RuntimeError("COBRA API is initializing — try again in a minute")
    return token


async def get_baseline(client: httpx.AsyncClient, token: str, fips: str) -> dict:
    params = {"token": token, "fipscodes": fips, "tiers": TIER}
    r = await client.get(f"{BASE}/SummarizedControlEmissions", params=params)
    r.raise_for_status()
    data = r.json()
    return data["baseline"][0] if data.get("baseline") else {}


async def fetch_one(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    token: str,
    state: str,
    county: str,
    fips: str,
    results_writer,
    errors_writer,
    results_file,
    errors_file,
    progress: dict,
):
    async with sem:
        try:
            baseline = await get_baseline(client, token, fips)
            pm25 = float(baseline.get("PM25", 0))
            so2 = float(baseline.get("SO2", 0))
            nox = float(baseline.get("NOx", 0))
            voc = float(baseline.get("VOC", 0))
            all_zero = "Y" if (pm25 == 0 and so2 == 0 and nox == 0 and voc == 0) else "N"

            results_writer.writerow([state, county, fips, pm25, so2, nox, voc, all_zero])
            results_file.flush()

        except Exception as e:
            errors_writer.writerow([fips, state, county, str(e), time.strftime("%Y-%m-%d %H:%M:%S")])
            errors_file.flush()
            progress["errors"] += 1

        progress["done"] += 1
        total = progress["total"]
        done = progress["done"]
        errors = progress["errors"]
        if done % 25 == 0 or done == total:
            elapsed = time.time() - progress["start"]
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - done) / rate if rate > 0 else 0
            print(f"  [{done}/{total}] {errors} errors | {rate:.1f} req/s | ~{remaining/60:.1f} min remaining")


async def main():
    counties = build_county_list()
    completed = load_completed_fips()
    pending = [(st, cn, fips) for st, cn, fips in counties if fips not in completed]

    print(f"Total counties: {len(counties)}")
    print(f"Already completed: {len(completed)}")
    print(f"Pending: {len(pending)}")

    if not pending:
        print("Nothing to do — all counties already fetched.")
        print(f"Results: {RESULTS_CSV}")
        return

    # Open CSV files in append mode
    results_exists = RESULTS_CSV.exists() and RESULTS_CSV.stat().st_size > 0
    errors_exists = ERRORS_CSV.exists() and ERRORS_CSV.stat().st_size > 0

    results_file = open(RESULTS_CSV, "a", newline="")
    errors_file = open(ERRORS_CSV, "a", newline="")

    results_writer = csv.writer(results_file)
    errors_writer = csv.writer(errors_file)

    if not results_exists:
        results_writer.writerow(RESULTS_HEADER)
        results_file.flush()
    if not errors_exists:
        errors_writer.writerow(ERRORS_HEADER)
        errors_file.flush()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        print("Getting token...")
        token = await get_token(client)
        print(f"Token: {token}")
        print(f"Fetching baselines (concurrency={CONCURRENCY})...\n")

        sem = asyncio.Semaphore(CONCURRENCY)
        progress = {"done": 0, "total": len(pending), "errors": 0, "start": time.time()}

        tasks = [
            fetch_one(sem, client, token, st, cn, fips, results_writer, errors_writer,
                      results_file, errors_file, progress)
            for st, cn, fips in pending
        ]
        await asyncio.gather(*tasks)

    results_file.close()
    errors_file.close()

    elapsed = time.time() - progress["start"]
    print(f"\nDone in {elapsed/60:.1f} minutes.")
    print(f"Results: {RESULTS_CSV}")
    print(f"Errors: {ERRORS_CSV} ({progress['errors']} total)")


if __name__ == "__main__":
    asyncio.run(main())
