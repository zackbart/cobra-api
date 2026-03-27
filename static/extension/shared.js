/* Shared utilities for COBRA Tableau extensions */

var COBRA = (function () {
  var API_BASE = window.location.origin;

  function formatCurrency(n) {
    if (n == null || isNaN(n)) return "—";
    return "$" + Math.round(n).toLocaleString();
  }

  function sectorLabel(key) {
    var labels = {
      grid: "Grid / Electricity",
      natural_gas: "Natural Gas",
      propane: "Propane",
      fuel_oil: "Fuel Oil",
      biomass: "Biomass"
    };
    return labels[key] || String(key).replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  // Health endpoint categories for grouped display
  var ENDPOINT_CATEGORIES = {
    "Mortality": ["Mortality", "Infant Mortality"],
    "Heart Attacks": ["Nonfatal Heart Attacks"],
    "Hospital Admits": ["Hospital Admits"],
    "Asthma": ["Asthma Onset", "Asthma Symptoms"],
    "ER Visits": ["ER Visits"],
    "Work/School Loss": ["Work Loss Days", "School Loss Days"],
    "Other": ["Lung Cancer", "Stroke", "Hay Fever", "Minor Restricted Activity"]
  };

  function getEndpointCategory(endpointName) {
    for (var cat in ENDPOINT_CATEGORIES) {
      var patterns = ENDPOINT_CATEGORIES[cat];
      for (var i = 0; i < patterns.length; i++) {
        if (endpointName && endpointName.indexOf(patterns[i]) >= 0) return cat;
      }
    }
    if (endpointName && endpointName.indexOf("Total") >= 0) return "_total";
    return "Other";
  }

  function renderHealthTable(rows, options) {
    if (!rows || rows.length === 0) return "";
    options = options || {};
    var grouped = options.grouped !== false;

    var html = '<table class="health-table"><thead><tr>' +
      '<th>Health Endpoint</th><th>Pollutant</th>' +
      '<th class="num">Incidence Low</th><th class="num">Incidence High</th>' +
      '<th class="num">Monetary Low</th><th class="num">Monetary High</th>' +
      '</tr></thead><tbody>';

    if (grouped) {
      // Group by category
      var catRows = {};
      var totalRows = [];
      for (var i = 0; i < rows.length; i++) {
        var cat = getEndpointCategory(rows[i].HealthEndpoint);
        if (cat === "_total") {
          totalRows.push(rows[i]);
        } else {
          if (!catRows[cat]) catRows[cat] = [];
          catRows[cat].push(rows[i]);
        }
      }
      var catOrder = ["Mortality", "Heart Attacks", "Hospital Admits", "Asthma", "ER Visits", "Work/School Loss", "Other"];
      for (var ci = 0; ci < catOrder.length; ci++) {
        var c = catOrder[ci];
        if (!catRows[c] || catRows[c].length === 0) continue;
        html += '<tr class="category-header"><td colspan="6">' + c + '</td></tr>';
        for (var j = 0; j < catRows[c].length; j++) {
          html += renderHealthRow(catRows[c][j]);
        }
      }
      if (totalRows.length > 0) {
        html += '<tr class="category-header"><td colspan="6">Totals</td></tr>';
        for (var t = 0; t < totalRows.length; t++) {
          html += renderHealthRow(totalRows[t]);
        }
      }
    } else {
      for (var k = 0; k < rows.length; k++) {
        html += renderHealthRow(rows[k]);
      }
    }

    html += '</tbody></table>';
    return html;
  }

  function renderHealthRow(r) {
    var incLo = r.IncidenceLow != null ? r.IncidenceLow.toFixed(4) : "—";
    var incHi = r.IncidenceHigh != null ? r.IncidenceHigh.toFixed(4) : "—";
    var monLo = r.MonetaryLow != null ? formatCurrency(r.MonetaryLow) : "—";
    var monHi = r.MonetaryHigh != null ? formatCurrency(r.MonetaryHigh) : "—";
    return '<tr><td>' + (r.HealthEndpoint || "") + '</td><td>' + (r.Pollutant || "") +
      '</td><td class="num">' + incLo + '</td><td class="num">' + incHi +
      '</td><td class="num">' + monLo + '</td><td class="num">' + monHi + '</td></tr>';
  }

  function getParamValue(param) {
    var v = param.currentValue;
    if (!v) return null;
    return (v.nativeValue !== undefined ? v.nativeValue : v.value) ?? null;
  }

  function findParamValue(params, names) {
    for (var i = 0; i < names.length; i++) {
      var target = names[i].toLowerCase();
      var p = params.find(function (x) { return x.name.toLowerCase() === target; });
      if (p) {
        var v = getParamValue(p);
        if (v != null && v !== "") return v;
      }
    }
    return null;
  }

  /**
   * Match a column/measure name to a pollutant key.
   * Returns "PM25", "SO2", "NOx", "VOC", or null.
   */
  function matchPollutantName(name) {
    var upper = (name || "").toUpperCase();
    // PM2.5 variants: PM2.5, PM25, PM 2.5, Particulate Matter
    if (upper.indexOf("PM2") >= 0 || upper.indexOf("PM25") >= 0 || upper.indexOf("PARTICULATE") >= 0) return "PM25";
    // SO2 variants: SO2, Sulfur Dioxide, Sulphur Dioxide, SOX (but not NOX)
    if (upper.indexOf("SO2") >= 0 || upper.indexOf("SULFUR") >= 0 || upper.indexOf("SULPHUR") >= 0) return "SO2";
    // NOx variants: NOX, NO2, Nitrogen Oxide, Nitrogen Dioxide
    if (upper.indexOf("NOX") >= 0 || upper.indexOf("NO2") >= 0 || upper.indexOf("NITROGEN") >= 0) return "NOx";
    // VOC variants: VOC, Volatile Organic
    if (upper.indexOf("VOC") >= 0 || upper.indexOf("VOLATILE") >= 0) return "VOC";
    return null;
  }

  /**
   * If exactMeasureNames is provided, match name by containing the exact string for each pollutant.
   * exactMeasureNames: { PM25: "PM2.5 (Tons) - Electric (CodeComp)", SO2: "...", NOx: "...", VOC: "..." }
   * Returns "PM25"|"SO2"|"NOx"|"VOC" or null.
   */
  function matchPollutantByExactNames(name, exactMeasureNames) {
    if (!name || !exactMeasureNames) return null;
    var order = ["PM25", "SO2", "NOx", "VOC"];
    for (var i = 0; i < order.length; i++) {
      var key = order[i];
      var exact = exactMeasureNames[key];
      if (exact && String(name).indexOf(exact) >= 0) return key;
    }
    return null;
  }

  /**
   * Read pollutant values (PM2.5, SO2, NOx, VOC) from a Tableau worksheet.
   * options (optional): { exactMeasureNames: { PM25: "...", SO2: "...", NOx: "...", VOC: "..." } }
   *   When set, column/measure names are matched by containing that string (e.g. "PM2.5 (Tons) - Electric (CodeComp)").
   * Otherwise searches column names for substrings (case-insensitive).
   * Returns { PM25, SO2, NOx, VOC } with summed values across rows.
   */
  async function readWorksheetPollutants(worksheet, options) {
    var data = await worksheet.getSummaryDataAsync();
    if (!data || !data.columns || !data.data) return null;

    var exactMeasureNames = options && options.exactMeasureNames;
    var cols = data.columns;
    // Log all column names for debugging
    var colNames = cols.map(function (c) { return c.fieldName || "(unnamed)"; });
    console.log("[COBRA] Worksheet '" + worksheet.name + "' columns: " + JSON.stringify(colNames));
    if (exactMeasureNames) console.log("[COBRA] Using exact measure names for matching");
    console.log("[COBRA] Worksheet '" + worksheet.name + "' rows: " + data.data.length);
    // Log first row values for debugging
    if (data.data.length > 0) {
      var firstRow = data.data[0].map(function (cell, i) {
        var v = cell ? (cell.nativeValue !== undefined ? cell.nativeValue : cell.value) : null;
        var fv = cell ? (cell.formattedValue || "") : "";
        return colNames[i] + "=" + v + (fv ? " [fmt:" + fv + "]" : "");
      });
      console.log("[COBRA] First row: " + firstRow.join(", "));
    }

    function resolvePollutant(fieldName) {
      if (exactMeasureNames) {
        var exact = matchPollutantByExactNames(fieldName, exactMeasureNames);
        if (exact) return exact;
      }
      return matchPollutantName(fieldName);
    }

    // Try direct column matching first (one column per pollutant)
    var pm25Idx = cols.findIndex(function (c) { return resolvePollutant(c.fieldName) === "PM25"; });
    var so2Idx = cols.findIndex(function (c) { return resolvePollutant(c.fieldName) === "SO2"; });
    var noxIdx = cols.findIndex(function (c) { return resolvePollutant(c.fieldName) === "NOx"; });
    var vocIdx = cols.findIndex(function (c) { return resolvePollutant(c.fieldName) === "VOC"; });

    console.log("[COBRA] Direct column matches: PM25=" + pm25Idx + " SO2=" + so2Idx + " NOx=" + noxIdx + " VOC=" + vocIdx);

    function getCellVal(cell) {
      if (!cell) return 0;
      var v = cell.nativeValue !== undefined ? cell.nativeValue : cell.value;
      if (v == null || String(v).indexOf("%") >= 0) return 0;
      return parseFloat(v) || 0;
    }

    // Check for pivoted format: "Measure Names" + "Measure Values"
    var mnIdx = cols.findIndex(function (c) { return (c.fieldName || "").toLowerCase() === "measure names"; });
    var mvIdx = cols.findIndex(function (c) { return (c.fieldName || "").toLowerCase() === "measure values"; });

    if (mnIdx >= 0 && mvIdx >= 0) {
      console.log("[COBRA] Using pivoted Measure Names/Values format");
      var pm25 = 0, so2 = 0, nox = 0, voc = 0;
      var seenNames = {};
      for (var r = 0; r < data.data.length; r++) {
        var nameCell = data.data[r][mnIdx];
        // Try multiple sources for the measure name: formattedValue, value, nativeValue
        var measureName = "";
        if (nameCell) {
          measureName = nameCell.formattedValue || nameCell.value || "";
          // Fall back to nativeValue only if formattedValue is empty or looks like an internal ref
          if (!measureName || measureName.indexOf("[federated") >= 0) {
            measureName = String(nameCell.nativeValue !== undefined ? nameCell.nativeValue : nameCell.value);
          }
        }
        if (!seenNames[measureName]) { seenNames[measureName] = true; console.log("[COBRA] Measure name: '" + measureName + "' (fmt='" + (nameCell ? nameCell.formattedValue : "") + "' val='" + (nameCell ? nameCell.value : "") + "' native='" + (nameCell ? nameCell.nativeValue : "") + "')"); }
        var val = getCellVal(data.data[r][mvIdx]);
        var pollutant = resolvePollutant(measureName);

        if (pollutant === "PM25") pm25 += val;
        else if (pollutant === "SO2") so2 += val;
        else if (pollutant === "NOx") nox += val;
        else if (pollutant === "VOC") voc += val;
        else { console.log("[COBRA] Unmatched measure: '" + measureName + "' = " + val); }
      }
      console.log("[COBRA] Pivoted results: PM25=" + pm25 + " SO2=" + so2 + " NOx=" + nox + " VOC=" + voc);
      return { PM25: pm25, SO2: so2, NOx: nox, VOC: voc };
    }

    if (pm25Idx < 0 && so2Idx < 0 && noxIdx < 0 && vocIdx < 0) return null;

    var pm25 = 0, so2 = 0, nox = 0, voc = 0;
    for (var r = 0; r < data.data.length; r++) {
      var row = data.data[r];
      if (pm25Idx >= 0) pm25 += getCellVal(row[pm25Idx]);
      if (so2Idx >= 0) so2 += getCellVal(row[so2Idx]);
      if (noxIdx >= 0) nox += getCellVal(row[noxIdx]);
      if (vocIdx >= 0) voc += getCellVal(row[vocIdx]);
    }

    return { PM25: pm25, SO2: so2, NOx: nox, VOC: voc };
  }

  /**
   * Read pollutant values from a worksheet by matching column name substrings.
   * Used for policy module where columns have naming patterns like "Policy_Natural Gas_NOx".
   */
  async function readWorksheetPollutantsByColumns(worksheet) {
    var data = await worksheet.getSummaryDataAsync();
    if (!data || !data.columns || !data.data) return null;

    var cols = data.columns;
    var colNames = cols.map(function (c) { return c.fieldName || "(unnamed)"; });
    console.log("[COBRA] ByColumns '" + worksheet.name + "' columns: " + JSON.stringify(colNames));
    console.log("[COBRA] ByColumns '" + worksheet.name + "' rows: " + data.data.length);

    var result = { PM25: 0, SO2: 0, NOx: 0, VOC: 0 };

    // Try direct column matching first
    var foundDirect = false;
    for (var ci = 0; ci < cols.length; ci++) {
      var pollutant = matchPollutantName(cols[ci].fieldName);
      if (!pollutant) continue;
      foundDirect = true;

      for (var r = 0; r < data.data.length; r++) {
        var cell = data.data[r][ci];
        if (!cell) continue;
        var v = cell.nativeValue !== undefined ? cell.nativeValue : cell.value;
        if (v != null && String(v).indexOf("%") < 0) {
          result[pollutant] += parseFloat(v) || 0;
        }
      }
    }

    // Fall back to pivoted format if no direct columns found
    if (!foundDirect) {
      var mnIdx = cols.findIndex(function (c) { return (c.fieldName || "").toLowerCase() === "measure names"; });
      var mvIdx = cols.findIndex(function (c) { return (c.fieldName || "").toLowerCase() === "measure values"; });
      if (mnIdx >= 0 && mvIdx >= 0) {
        console.log("[COBRA] ByColumns falling back to pivoted format");
        for (var r = 0; r < data.data.length; r++) {
          var nameCell = data.data[r][mnIdx];
          var measureName = "";
          if (nameCell) {
            measureName = nameCell.formattedValue || nameCell.value || "";
            if (!measureName || measureName.indexOf("[federated") >= 0) {
              measureName = String(nameCell.nativeValue !== undefined ? nameCell.nativeValue : nameCell.value);
            }
          }
          var pollutant = matchPollutantName(measureName);
          if (!pollutant) continue;
          var cell = data.data[r][mvIdx];
          if (!cell) continue;
          var v = cell.nativeValue !== undefined ? cell.nativeValue : cell.value;
          if (v != null && String(v).indexOf("%") < 0) {
            result[pollutant] += parseFloat(v) || 0;
          }
        }
      }
    }

    console.log("[COBRA] ByColumns results: PM25=" + result.PM25 + " SO2=" + result.SO2 + " NOx=" + result.NOx + " VOC=" + result.VOC);
    return result;
  }

  /**
   * Treat "(All)" or "All" as no county selection (state-level). Returns null for those values.
   */
  function normalizeCountyForPayload(county) {
    if (!county) return null;
    var c = String(county).trim();
    if (c === "") return null;
    var lower = c.toLowerCase();
    // Treat common "no selection" sentinel values as null (state-level only)
    var noSelectionValues = [
      "(all)", "all", "(all values)", "all values",
      "all counties", "(all counties)", "all parishes", "(all parishes)",
      "none", "select", "select county", "select a county",
      "-- all --", "statewide", "entire state"
    ];
    if (noSelectionValues.indexOf(lower) >= 0) return null;
    // Also catch any value starting with "all " (e.g. "All Alabama Counties")
    if (lower.indexOf("all ") === 0) return null;
    return c;
  }

  /**
   * Check whether a filter field exists on any worksheet, regardless of applied values.
   * Returns true if the filter is found (even with 0 or multiple applied values).
   * Use this to distinguish "filter not present" from "filter set to all/multiple."
   */
  async function findFilterExists(dashboard, fieldNames) {
    var worksheets = dashboard.worksheets || [];
    for (var n = 0; n < fieldNames.length; n++) {
      var target = fieldNames[n].toLowerCase();
      for (var w = 0; w < worksheets.length; w++) {
        try {
          var filters = await worksheets[w].getFiltersAsync();
          for (var f = 0; f < filters.length; f++) {
            var fname = (filters[f].fieldName || "").toLowerCase();
            if (fname === target) return true;
          }
        } catch (e) { /* skip worksheet */ }
      }
    }
    return false;
  }

  /**
   * Read a single-select filter value from any worksheet on the dashboard.
   * Tries each field name in order so that preferred names (e.g. "County Selection")
   * win over others (e.g. "County?") when multiple filters match.
   * Returns the first matched single value, or null.
   */
  async function findFilterValue(dashboard, fieldNames) {
    var worksheets = dashboard.worksheets || [];
    for (var n = 0; n < fieldNames.length; n++) {
      var target = fieldNames[n].toLowerCase();
      for (var w = 0; w < worksheets.length; w++) {
        try {
          var filters = await worksheets[w].getFiltersAsync();
          for (var f = 0; f < filters.length; f++) {
            var filter = filters[f];
            var fname = (filter.fieldName || "").toLowerCase();
            if (fname === target) {
              if (filter.appliedValues && filter.appliedValues.length === 1) {
                var v = filter.appliedValues[0];
                var val = v.nativeValue !== undefined ? v.nativeValue : (v.value || v.formattedValue);
                if (val != null && val !== "") {
                  console.log("[COBRA] Filter '" + filter.fieldName + "' = " + val + " (from worksheet '" + worksheets[w].name + "')");
                  return String(val);
                }
              }
              // Filter exists but has 0 or >1 applied values — this means
              // "all" or multi-select. Stop searching immediately so we don't
              // pick up a stale single value from a different worksheet.
              if (filter.appliedValues) {
                console.log("[COBRA] Filter '" + filter.fieldName + "' has " + filter.appliedValues.length + " applied values (all/multi) on worksheet '" + worksheets[w].name + "' — treating as no selection");
              }
              return null;
            }
          }
        } catch (e) {
          console.log("[COBRA] Error reading filters from '" + worksheets[w].name + "': " + e.message);
        }
      }
    }
    return null;
  }

  /**
   * Initialize Tableau extension with fallback for non-Tableau testing.
   * callback(dashboard) is called on success, or callback(null) for non-Tableau mode.
   */
  function initExtension(callback) {
    var statusEl = document.getElementById("init-status");
    function showStatus(msg) {
      if (statusEl) statusEl.textContent = msg;
      console.log("[COBRA init] " + msg);
    }

    if (typeof tableau === "undefined") {
      showStatus("tableau object not found — not running inside Tableau");
      callback(null);
      return;
    }
    if (!tableau.extensions) {
      showStatus("tableau.extensions not available");
      callback(null);
      return;
    }

    showStatus("Calling initializeAsync...");
    tableau.extensions.initializeAsync().then(function () {
      var dashboard = tableau.extensions.dashboardContent
        ? tableau.extensions.dashboardContent.dashboard
        : null;
      if (dashboard) {
        showStatus("Connected to dashboard: " + dashboard.name + " (" + (dashboard.worksheets || []).length + " worksheets)");
      } else {
        showStatus("initializeAsync succeeded but no dashboardContent");
      }
      callback(dashboard);
    }).catch(function (err) {
      showStatus("initializeAsync FAILED: " + (err.message || err));
      callback(null);
    });
  }

  /**
   * Get or create a persistent session ID in localStorage.
   * Shared across all extensions from the same origin, so the Detail view
   * can retrieve results stored by any of the input extensions.
   * Falls back to an in-memory ID if localStorage is unavailable (private mode, sandboxed iframe).
   */
  var _fallbackSessionId = null;
  function getSessionId() {
    var key = "cobra_session_id";
    try {
      var id = localStorage.getItem(key);
      if (!id) {
        id = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
        localStorage.setItem(key, id);
      }
      return id;
    } catch (e) {
      if (!_fallbackSessionId) {
        _fallbackSessionId = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
      }
      return _fallbackSessionId;
    }
  }

  /**
   * Store results on the server for the detailed health dashboard.
   */
  async function storeResults(data, source) {
    try {
      var params = [];
      if (source) params.push("source=" + encodeURIComponent(source));
      params.push("session_id=" + encodeURIComponent(getSessionId()));
      var url = API_BASE + "/store-results?" + params.join("&");
      await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      });
    } catch (e) {
      console.warn("Failed to store results:", e);
    }
  }

  /**
   * Call the health-effects API.
   * source (optional): code_comparison, custom_module, policy_module — used for per-extension tier mapping.
   */
  async function callHealthEffects(payload, includeHealthEndpoints, source) {
    var url = API_BASE + "/health-effects";
    var params = [];
    if (includeHealthEndpoints) params.push("include_health_endpoints=true");
    if (source) params.push("source=" + encodeURIComponent(source));
    if (params.length > 0) url += "?" + params.join("&");

    var res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      var err = await res.json().catch(function () { return {}; });
      throw new Error(err.detail || res.statusText || "Request failed");
    }
    return await res.json();
  }

  /**
   * Render summary results (low/high totals) with optional sector breakdown.
   */
  function renderSummary(data, geo) {
    var d = data[geo];
    if (!d) return '<p class="loading">N/A for this geography</p>';
    var low = d.TotalHealthBenefitsValue_low ?? (d.Summary ? d.Summary.TotalHealthBenefitsValue_low : null);
    var high = d.TotalHealthBenefitsValue_high ?? (d.Summary ? d.Summary.TotalHealthBenefitsValue_high : null);
    var html = '<div class="result-row"><strong>Total Health Effects (Low):</strong> <span class="val">' +
      formatCurrency(low) + '</span></div>' +
      '<div class="result-row"><strong>Total Health Effects (High):</strong> <span class="val">' +
      formatCurrency(high) + '</span></div>';
    return html;
  }

  function renderSectorBreakdown(data, geo) {
    var d = data[geo];
    if (!d || !d.by_sector) return "";
    var bySector = d.by_sector;
    var keys = Object.keys(bySector);
    if (keys.length === 0) return "";
    var html = '<div class="sector-breakdown"><h4>Per-Fuel Breakdown</h4>';
    for (var i = 0; i < keys.length; i++) {
      var sk = keys[i];
      var sv = bySector[sk];
      html += '<div class="result-row"><strong>' + sectorLabel(sk) + ':</strong> <span class="val">' +
        formatCurrency(sv.TotalHealthBenefitsValue_low) + ' (Low) / ' +
        formatCurrency(sv.TotalHealthBenefitsValue_high) + ' (High)</span></div>';
    }
    html += '</div>';
    return html;
  }

  return {
    API_BASE: API_BASE,
    formatCurrency: formatCurrency,
    sectorLabel: sectorLabel,
    renderHealthTable: renderHealthTable,
    findParamValue: findParamValue,
    findFilterExists: findFilterExists,
    findFilterValue: findFilterValue,
    normalizeCountyForPayload: normalizeCountyForPayload,
    readWorksheetPollutants: readWorksheetPollutants,
    readWorksheetPollutantsByColumns: readWorksheetPollutantsByColumns,
    initExtension: initExtension,
    getSessionId: getSessionId,
    storeResults: storeResults,
    callHealthEffects: callHealthEffects,
    renderSummary: renderSummary,
    renderSectorBreakdown: renderSectorBreakdown
  };
})();
