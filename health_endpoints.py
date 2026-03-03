"""Map COBRA Impact columns to EPA-site health endpoint table format."""

# (incidence_low, incidence_high, monetary_low, monetary_high, label, pollutant)
# C__ = monetary (dollars), PM_/O3_ = incidence (cases)
HEALTH_ENDPOINT_MAP = [
    ("PM_Mortality_All_Cause__low_", "PM_Mortality_All_Cause__high_", "C__PM_Mortality_All_Cause__low_", "C__PM_Mortality_All_Cause__high_", "Mortality", "PM2.5 | O3"),
    ("PM_Acute_Myocardial_Infarction_Nonfatal", None, "C__PM_Acute_Myocardial_Infarction_Nonfatal", None, "Nonfatal Heart Attacks", "PM2.5"),
    ("PM_HA_All_Respiratory", None, "C__PM_HA_Respiratory2", None, "Hospital Admits, Respiratory (PM2.5)", "PM2.5"),
    ("O3_HA_All_Respiratory", None, "C__O3_HA_All_Respiratory", None, "Hospital Admits, Respiratory (O3)", "O3"),
    ("PM_HA_Alzheimers_Disease", None, "C__PM_HA_Alzheimers_Disease", None, "Hospital Admits, Alzheimer's", "PM2.5"),
    ("PM_HA_Parkinsons_Disease", None, "C__PM_HA_Parkinsons_Disease", None, "Hospital Admits, Parkinson's", "PM2.5"),
    ("PM_Incidence_Asthma", None, "C__PM_Incidence_Asthma", None, "Asthma Onset (PM2.5)", "PM2.5"),
    ("O3_Incidence_Asthma", None, "C__O3_Incidence_Asthma", None, "Asthma Onset (O3)", "O3"),
    ("PM_Asthma_Symptoms_Albuterol_use", None, "C__PM_Asthma_Symptoms_Albuterol_use", None, "Asthma Symptoms (PM2.5)", "PM2.5"),
    ("O3_Asthma_Symptoms_Cough", None, "C__O3_Asthma_Symptoms_Cough", None, "Asthma Symptoms (O3)", "O3"),
    ("PM_ER_visits_respiratory", None, "C__PM_ER_visits_respiratory", None, "ER Visits, Respiratory (PM2.5)", "PM2.5"),
    ("O3_ER_visits_respiratory", None, "C__O3_ER_visits_respiratory", None, "ER Visits, Respiratory (O3)", "O3"),
    ("PM_ER_visits_All_Cardiac_Outcomes", None, "C__PM_ER_visits_All_Cardiac_Outcomes", None, "ER Visits, Cardiac (PM2.5)", "PM2.5"),
    ("O3_ER_Visits_Asthma", None, "C__O3_ER_Visits_Asthma", None, "ER Visits, Asthma (O3)", "O3"),
    ("PM_Work_Loss_Days", None, "C__PM_Work_Loss_Days", None, "Work Loss Days", "PM2.5"),
    ("O3_School_Loss_Days", None, "C__O3_School_Loss_Days", None, "School Loss Days", "O3"),
    ("PM_Incidence_Lung_Cancer", None, "C__PM_Incidence_Lung_Cancer", None, "Lung Cancer", "PM2.5"),
    ("PM_Incidence_Stroke", None, "C__PM_Incidence_Stroke", None, "Stroke", "PM2.5"),
    ("PM_Incidence_Hay_Fever_Rhinitis", None, "C__PM_Incidence_Hay_Fever_Rhinitis", None, "Hay Fever/Rhinitis (PM2.5)", "PM2.5"),
    ("O3_Incidence_Hay_Fever_Rhinitis", None, "C__O3_Incidence_Hay_Fever_Rhinitis", None, "Hay Fever/Rhinitis (O3)", "O3"),
    ("PM_Minor_Restricted_Activity_Days", None, "C__PM_Minor_Restricted_Activity_Days", None, "Minor Restricted Activity Days", "PM2.5"),
    ("PM_Infant_Mortality", None, "C__PM_Infant_Mortality", None, "Infant Mortality", "PM2.5"),
]

TOTAL_PM_LOW = "C__Total_PM_Low_Value"
TOTAL_PM_HIGH = "C__Total_PM_High_Value"
TOTAL_O3 = "C__Total_O3_Value"
TOTAL_LOW = "C__Total_Health_Benefits_Low_Value"
TOTAL_HIGH = "C__Total_Health_Benefits_High_Value"


def aggregate_health_endpoints(impacts: list[dict]) -> list[dict]:
    """Sum Impacts across counties, reshape to EPA-site table format."""
    if not impacts:
        return []

    sums: dict[str, float] = {}
    for row in impacts:
        for k, v in row.items():
            if k in ("ID", "destindx", "FIPS", "COUNTY", "STATE") or not isinstance(v, (int, float)):
                continue
            try:
                sums[k] = sums.get(k, 0) + float(v)
            except (TypeError, ValueError):
                pass

    rows: list[dict] = []
    for inc_lo, inc_hi, mon_lo, mon_hi, label, pollutant in HEALTH_ENDPOINT_MAP:
        inc_l = sums.get(inc_lo) if inc_lo else None
        inc_h = sums.get(inc_hi) if inc_hi else inc_l
        mon_l = sums.get(mon_lo) if mon_lo else None
        mon_h = sums.get(mon_hi) if mon_hi else mon_l
        if inc_l is None and inc_h is None and mon_l is None and mon_h is None:
            continue
        rows.append({
            "HealthEndpoint": label,
            "Pollutant": pollutant,
            "IncidenceLow": round(inc_l or 0, 6) if inc_l is not None else None,
            "IncidenceHigh": round(inc_h or 0, 6) if inc_h is not None else None,
            "MonetaryLow": round(mon_l or 0, 2) if mon_l is not None else None,
            "MonetaryHigh": round(mon_h or 0, 2) if mon_h is not None else None,
        })

    # Totals
    pm_low, pm_high = sums.get(TOTAL_PM_LOW), sums.get(TOTAL_PM_HIGH)
    o3_val = sums.get(TOTAL_O3)
    tot_low, tot_high = sums.get(TOTAL_LOW), sums.get(TOTAL_HIGH)

    if pm_low is not None or pm_high is not None:
        rows.append({
            "HealthEndpoint": "Total Health Effects from PM2.5",
            "Pollutant": "PM2.5",
            "IncidenceLow": None, "IncidenceHigh": None,
            "MonetaryLow": round(pm_low or 0, 2), "MonetaryHigh": round(pm_high or 0, 2),
        })
    if o3_val is not None:
        rows.append({
            "HealthEndpoint": "Total Health Effects from O3",
            "Pollutant": "O3",
            "IncidenceLow": None, "IncidenceHigh": None,
            "MonetaryLow": round(o3_val, 2), "MonetaryHigh": round(o3_val, 2),
        })
    if tot_low is not None or tot_high is not None:
        rows.append({
            "HealthEndpoint": "Total Health Effects",
            "Pollutant": "PM2.5 | O3",
            "IncidenceLow": None, "IncidenceHigh": None,
            "MonetaryLow": round(tot_low or 0, 2), "MonetaryHigh": round(tot_high or 0, 2),
        })

    return rows
