"""Map dashboard region codes (state abbrev, eGRID) to COBRA FIPS codes."""

# State abbreviation -> 2-digit FIPS
STATE_TO_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56", "PR": "72",
}

# eGRID subregion acronym -> 2-digit state FIPS (primary state for multi-state regions)
EGRID_TO_FIPS = {
    "AKGD": "02",   # ASCC Alaska Grid
    "AKMS": "02",   # ASCC miscellaneous
    "AZNM": "04",   # WECC Southwest (Arizona primary)
    "CAMX": "06",   # WECC California
    "ERCT": "48",   # ERCOT all (Texas)
    "FRCC": "12",   # FRCC all (Florida)
    "HIMS": "15",   # HICC miscellaneous (Hawaii)
    "HIOA": "15",   # HICC Oahu (Hawaii)
    "MROE": "27",   # MRO East (Minnesota primary)
    "MROW": "56",   # MRO West (Wyoming primary)
    "NEWE": "25",   # NPCC New England (Massachusetts primary)
    "NWPP": "41",   # WECC Northwest (Oregon primary)
    "NYCW": "36",   # NPCC NYC/Westchester (NY)
    "NYLI": "36",   # NPCC Long Island (NY)
    "NYUP": "36",   # NPCC Upstate NY
    "PRMS": "72",   # Puerto Rico (72 is PR FIPS)
    "RFCE": "34",   # RFC East (NJ primary)
    "RFCM": "26",   # RFC Michigan
    "RFCW": "39",   # RFC West (OH primary)
    "RMPA": "08",   # WECC Rockies (CO primary)
    "SPNO": "31",   # SPP North (NE primary)
    "SPSO": "40",   # SPP South (OK primary)
    "SRMV": "28",   # SERC Mississippi Valley (MS primary)
    "SRMW": "17",   # SERC Midwest (IL primary)
    "SRSO": "45",   # SERC South (SC primary)
    "SRTV": "47",   # SERC Tennessee Valley
    "SRVC": "51",   # SERC Virginia/Carolina
}

# National / USA
NATIONAL_ALIASES = {"national", "usa", "00", "us", "fipsst", "pstatabb"}


def region_to_fips(region: str) -> str:
    """
    Convert dashboard region to COBRA FIPS.
    Accepts: 2-digit FIPS, 5-digit county FIPS, state abbrev (AL, NY), or eGRID code (ERCT, FRCC).
    Returns: 2-digit state FIPS or "00" for national.
    """
    r = region.strip().upper()
    if not r:
        raise ValueError("Region cannot be empty")

    # National / USA
    if r.lower() in NATIONAL_ALIASES:
        return "00"
    if len(r) == 2 and r.isdigit():
        return r
    if len(r) == 5 and r.isdigit():
        return r  # County FIPS - preserve full 5 digits

    # State abbreviation
    if r in STATE_TO_FIPS:
        return STATE_TO_FIPS[r]

    # eGRID subregion
    if r in EGRID_TO_FIPS:
        return EGRID_TO_FIPS[r]

    # Try without common suffixes (e.g. "ASCC Alaska Grid" -> extract "AKGD" from display name)
    # Dashboard may send display names; map common ones
    display_to_egrid = {
        "ASCC ALASKA GRID": "AKGD",
        "ASCC MISCELLANEOUS": "AKMS",
        "ASSC ALASKA GRID": "AKGD",   # alternate spelling
        "ASSC MISCELLANEOUS": "AKMS", # alternate spelling
        "ERCOT ALL": "ERCT",
        "FRCC ALL": "FRCC",
        "HICC MISCELLANEOUS": "HIMS",
        "HICC OAHU": "HIOA",
        "MRO EAST": "MROE",
        "MRO WEST": "MROW",
        "NPCC LONG ISLAND": "NYLI",
        "NPCC NEW ENGLAND": "NEWE",
        "NPCC NYC/WESTCHESTER": "NYCW",
        "NPCC UPSTATE NY": "NYUP",
        "PUERTO RICO MISCELLANEOUS": "PRMS",
        "RFC EAST": "RFCE",
        "RFC MICHIGAN": "RFCM",
        "RFC WEST": "RFCW",
        "SERC MIDWEST": "SRMW",
        "SERC MISSISSIPPI VALLEY": "SRMV",
        "SERC SOUTH": "SRSO",
        "SERC TENNESSEE VALLEY": "SRTV",
        "SERC VIRGINIA/CAROLINA": "SRVC",
        "SPP NORTH": "SPNO",
        "SPP SOUTH": "SPSO",
        "WECC CALIFORNIA": "CAMX",
        "WECC NORTHWEST": "NWPP",
        "WECC ROCKIES": "RMPA",
        "WECC SOUTHWEST": "AZNM",
    }
    if r in display_to_egrid:
        return EGRID_TO_FIPS[display_to_egrid[r]]

    raise ValueError(f"Unknown region: {region}. Use state abbrev (NY, CA), eGRID (ERCT, FRCC), or FIPS.")


def resolve_state_county(state: str, county_name: str) -> str:
    """Resolve state abbreviation + county display name to 5-digit FIPS code.

    Raises ValueError if state or county cannot be resolved.
    """
    from county_fips import resolve_county_fips

    st = state.strip().upper()
    if st not in STATE_TO_FIPS:
        raise ValueError(f"Unknown state: {state}")

    fips = resolve_county_fips(st, county_name)
    if fips is None:
        raise ValueError(f"Unknown county: {county_name} in {state}")
    return fips
