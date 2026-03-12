"""Regression checks for state normalization in region/county resolution."""

import sys
import unittest
from pathlib import Path

# Ensure project root is on path when run from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from region_map import normalize_state_abbrev, region_to_fips, resolve_state_county
from county_fips import resolve_county_fips


class TestStateResolution(unittest.TestCase):
    def test_region_to_fips_accepts_state_name(self):
        self.assertEqual(region_to_fips("Arkansas"), "05")
        self.assertEqual(region_to_fips("new york"), "36")

    def test_resolve_state_county_accepts_state_name(self):
        self.assertEqual(resolve_state_county("Arkansas", "Benton County"), "05007")

    def test_unknown_state_name_still_rejected(self):
        with self.assertRaises(ValueError):
            region_to_fips("Atlantis")

    # --- FIPS code as state input ---

    def test_normalize_state_abbrev_fips_code(self):
        """2-digit FIPS code should resolve to state abbreviation."""
        self.assertEqual(normalize_state_abbrev("36"), "NY")
        self.assertEqual(normalize_state_abbrev("05"), "AR")
        self.assertEqual(normalize_state_abbrev("48"), "TX")

    def test_normalize_state_abbrev_invalid_fips(self):
        """Invalid FIPS codes should return None."""
        self.assertIsNone(normalize_state_abbrev("99"))
        self.assertIsNone(normalize_state_abbrev("00"))

    def test_resolve_state_county_with_fips_state(self):
        """State as FIPS code + county name should resolve correctly."""
        self.assertEqual(resolve_state_county("36", "Kings County"), "36047")
        self.assertEqual(resolve_state_county("05", "Benton County"), "05007")

    # --- County fuzzy matching edge cases ---

    def test_county_clay_not_clayton(self):
        """'Clay County' in GA must match Clay (13061), not Clayton (13063)."""
        self.assertEqual(resolve_county_fips("GA", "Clay County"), "13061")

    def test_county_clayton_exact(self):
        """'Clayton County' in GA must match Clayton (13063)."""
        self.assertEqual(resolve_county_fips("GA", "Clayton County"), "13063")

    def test_county_base_name_only(self):
        """Just 'Benton' (no suffix) should match 'Benton County'."""
        self.assertEqual(resolve_county_fips("AR", "Benton"), "05007")

    def test_county_base_name_no_false_prefix(self):
        """'Clay' (no suffix) in GA must not match 'Clayton County'."""
        result = resolve_county_fips("GA", "Clay")
        self.assertEqual(result, "13061")

    def test_county_case_insensitive(self):
        """County matching should be case-insensitive."""
        self.assertEqual(resolve_county_fips("AR", "benton county"), "05007")
        self.assertEqual(resolve_county_fips("AR", "BENTON COUNTY"), "05007")


if __name__ == "__main__":
    unittest.main()
