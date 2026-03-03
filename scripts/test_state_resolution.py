"""Regression checks for state normalization in region/county resolution."""

import sys
import unittest
from pathlib import Path

# Ensure project root is on path when run from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from region_map import region_to_fips, resolve_state_county


class TestStateResolution(unittest.TestCase):
    def test_region_to_fips_accepts_state_name(self):
        self.assertEqual(region_to_fips("Arkansas"), "05")
        self.assertEqual(region_to_fips("new york"), "36")

    def test_resolve_state_county_accepts_state_name(self):
        self.assertEqual(resolve_state_county("Arkansas", "Benton County"), "05007")

    def test_unknown_state_name_still_rejected(self):
        with self.assertRaises(ValueError):
            region_to_fips("Atlantis")


if __name__ == "__main__":
    unittest.main()
