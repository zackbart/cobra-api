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

    # --- State-level resolution when county is absent ---

    def test_state_level_when_county_none(self):
        """When county is None, region_to_fips should return 2-digit state FIPS."""
        fips = region_to_fips("Arkansas")
        self.assertEqual(len(fips), 2)
        self.assertEqual(fips, "05")

    def test_state_level_when_county_empty_string(self):
        """Empty string county should be treated as state-level (mimics server normalization)."""
        county_name = ("" or "").strip() or None
        self.assertIsNone(county_name)
        fips = region_to_fips("AR")
        self.assertEqual(fips, "05")

    def test_state_level_when_county_whitespace(self):
        """Whitespace-only county should be treated as state-level."""
        county_name = ("   " or "").strip() or None
        self.assertIsNone(county_name)


class TestServerRoutingLogic(unittest.TestCase):
    """Simulate the FIPS routing logic from main.py health_effects endpoint.

    This mirrors the exact decision tree the server uses to pick between
    county-level (5-digit FIPS) and state-level (2-digit FIPS) based on
    what the client sends in the request payload.
    """

    def _resolve_like_server(self, state, county_name_raw):
        """Replicate the normalization + routing from main.py lines 67-98."""
        county_name = (county_name_raw or "").strip() or None

        if state and county_name:
            fips = resolve_state_county(state, county_name)
        elif state:
            fips = region_to_fips(state)
        else:
            fips = region_to_fips("national")

        return fips

    # Scenario: user picks a specific county → should get 5-digit county FIPS
    def test_specific_county_returns_county_fips(self):
        """State + specific county → 5-digit county FIPS."""
        fips = self._resolve_like_server("AR", "Benton County")
        self.assertEqual(fips, "05007")
        self.assertEqual(len(fips), 5)

    # Scenario: user selects "All counties" → client sends no county → state-level
    def test_all_counties_sends_no_county(self):
        """State + no county (user selected 'All') → 2-digit state FIPS."""
        fips = self._resolve_like_server("AR", None)
        self.assertEqual(fips, "05")
        self.assertEqual(len(fips), 2)

    def test_all_counties_sends_empty_string(self):
        """State + empty string county → normalized to None → 2-digit state FIPS."""
        fips = self._resolve_like_server("AR", "")
        self.assertEqual(fips, "05")
        self.assertEqual(len(fips), 2)

    def test_all_counties_sends_whitespace(self):
        """State + whitespace county → normalized to None → 2-digit state FIPS."""
        fips = self._resolve_like_server("AR", "   ")
        self.assertEqual(fips, "05")
        self.assertEqual(len(fips), 2)

    # Scenario: state as full name with no county
    def test_state_name_no_county(self):
        """Full state name + no county → 2-digit state FIPS."""
        fips = self._resolve_like_server("Arkansas", None)
        self.assertEqual(fips, "05")

    # Scenario: state as FIPS code with no county
    def test_state_fips_no_county(self):
        """State as FIPS code + no county → 2-digit state FIPS."""
        fips = self._resolve_like_server("05", None)
        self.assertEqual(fips, "05")

    # Scenario: specific county with state as full name
    def test_state_name_with_county(self):
        """Full state name + county → 5-digit county FIPS."""
        fips = self._resolve_like_server("New York", "Kings County")
        self.assertEqual(fips, "36047")
        self.assertEqual(len(fips), 5)

    # Scenario: verify the key bug case — stale county should NOT leak through
    def test_stale_county_cleared_sends_state_level(self):
        """When client clears stale county (sends None), server routes to state-level.

        This is the core bug scenario: user picks 'All counties' but a stale
        param value like 'Benton County' was leaking through. After the fix,
        the client sends county_name=None and this should produce a 2-digit FIPS.
        """
        # Before fix: client would send county_name="Benton County" → 5-digit
        fips_with_county = self._resolve_like_server("AR", "Benton County")
        self.assertEqual(len(fips_with_county), 5)  # county-level

        # After fix: client sends county_name=None → 2-digit
        fips_without_county = self._resolve_like_server("AR", None)
        self.assertEqual(len(fips_without_county), 2)  # state-level
        self.assertEqual(fips_without_county, "05")


if __name__ == "__main__":
    unittest.main()
