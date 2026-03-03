"""Map user sector + fuel to COBRA tier string (TIER1,TIER2,TIER3)."""

# Sector+fuel -> COBRA tier (validated against EPA API)
SECTOR_TIERS = {
    "commercial_electricity": "1,3,1",   # Fuel Combustion: Electric Utility
    "commercial_natural_gas": "3,3,99",  # Fuel Combustion: Other, Commercial/Institutional Gas
    "residential_electricity": "1,3,1",
    "residential_natural_gas": "3,6,2",   # Fuel Combustion: Other, Residential, Natural Gas
}

# Per-fuel tiers (dashboard pollutant sections -> COBRA tier)
# Validated: 1,3,1 3,3,99 3,6,2 3,4,99 3,5,1 3,2,99
FUEL_TIERS = {
    "grid": "1,3,1",           # Electricity
    "natural_gas": "3,3,99",   # Commercial/Institutional Gas
    "propane": "3,4,99",       # Fuel Combustion Other (LPG)
    "fuel_oil": "3,5,1",       # Fuel Combustion Other (Distillate)
    "biomass": "3,2,99",       # Fuel Combustion Other (Wood/Biomass)
}

# Per-extension fuel -> tier (overrides FUEL_TIERS when source is set on /health-effects)
TIERS_BY_SOURCE = {
    "code_comparison": {
        "grid": "1,3,1",  # Electric Utility
    },
    "custom_module": {
        "grid": "1,3,1",
        "natural_gas": "3,3,99",   # Commercial/Institutional Gas
        "propane": "3,3,99",      # Commercial/Institutional Gas
        "fuel_oil": "3,5,1",      # Commercial/Institutional Oil
        "biomass": "3,2,99",      # Residential Wood
    },
    "policy_module": {
        "grid": "1,3,1",
        "natural_gas": "3,5,1",   # Commercial/Institutional Oil
    },
}

# Worksheet name patterns -> fuel key (case-insensitive)
WORKSHEET_FUEL_PATTERNS = [
    ("grid", ["grid", "electric", "electricity"]),
    ("natural_gas", ["ng", "natural gas", "naturalgas"]),
    ("propane", ["lpg", "propane"]),
    ("fuel_oil", ["fuel oil", "distillate", "dfo"]),
    ("biomass", ["biomass", "wood"]),
]

# Dashboard display values -> canonical sector
SECTOR_ALIASES = {
    "commercial_electricity": "commercial_electricity",
    "commercial_natural_gas": "commercial_natural_gas",
    "residential_electricity": "residential_electricity",
    "residential_natural_gas": "residential_natural_gas",
    "commercial/institutional": "commercial_electricity",
    "commercial/institutional - electricity": "commercial_electricity",
    "commercial/institutional - natural gas": "commercial_natural_gas",
    "residential": "residential_electricity",
    "residential - electricity": "residential_electricity",
    "residential - natural gas": "residential_natural_gas",
}


def get_tiers(sector: str) -> str:
    """Get tier string for sector (legacy single-sector mode)."""
    s = sector.strip().lower()
    canonical = SECTOR_ALIASES.get(s) or SECTOR_TIERS.get(s)
    if canonical:
        return SECTOR_TIERS[canonical]
    tier = SECTOR_TIERS.get(s)
    if tier:
        return tier
    raise ValueError(f"Unknown sector: {sector}. Use: {list(SECTOR_TIERS.keys())}")


def get_tiers_for_fuel(fuel: str) -> str:
    """Get tier string for fuel key (grid, natural_gas, propane, fuel_oil, biomass)."""
    f = fuel.strip().lower().replace(" ", "_")
    tier = FUEL_TIERS.get(f)
    if tier:
        return tier
    # Aliases
    if f in ("electric", "electricity"): return FUEL_TIERS["grid"]
    if f in ("ng", "gas"): return FUEL_TIERS["natural_gas"]
    if f in ("lpg",): return FUEL_TIERS["propane"]
    if f in ("dfo", "distillate"): return FUEL_TIERS["fuel_oil"]
    if f in ("wood",): return FUEL_TIERS["biomass"]
    raise ValueError(f"Unknown fuel: {fuel}. Use: {list(FUEL_TIERS.keys())}")


def get_tiers_for_fuel_by_source(fuel: str, source: str | None) -> str:
    """Get tier string for fuel, using per-extension mapping when source is set."""
    if source:
        src = source.strip().lower()
        if src in TIERS_BY_SOURCE:
            fuels = TIERS_BY_SOURCE[src]
            f = fuel.strip().lower().replace(" ", "_")
            if f in fuels:
                return fuels[f]
    return get_tiers_for_fuel(fuel)


def worksheet_to_fuel(name: str) -> str | None:
    """Map worksheet name to fuel key, or None if no match."""
    n = (name or "").lower()
    for fuel, patterns in WORKSHEET_FUEL_PATTERNS:
        if any(p in n for p in patterns):
            return fuel
    return None
