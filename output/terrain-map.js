/* ============================================================================
   TERRAIN MAP — live D3 county map logic
   ----------------------------------------------------------------------------
   Extracted verbatim from labor_organizing_national_dashboard.html (the live
   map path only). Dead v1 views (table, gallery, in-page methodology) and the
   panel-navigation system were intentionally excluded — see the merge PR notes.

   LENS (B2b): the state lens is a full peer to national. setLens() accepts
   'national' or 'state', recolors the map by getLensQuadrant(), updates the
   stats / top-10 / legend / badge, and broadcasts a 'lens-change' CustomEvent so
   peer components (the distribution scatter) re-render in lockstep. State fields
   (quadrant_state, p1_state, p2_state, state_strategy) are surfaced, not recomputed.

   DEPENDS ON (must exist in the DOM before this script runs):
     #map-svg #map-figure #detail-panel #close-detail #map-legend #tooltip
     #legend-title #legend-tiers #legend-lens-label #lens-badge
     #btn-national #btn-state #lens-desc
     #filter-state #filter-swing
     #stat-total #stat-tier1 #stat-tier2 #stat-tier3 #stat-tier4 #stat-visible
     #top10-list #finding-tier1
     #loading-indicator #status-msg #data-timestamp
     #mobile-filter-toggle #sidebar
   Requires d3.v7 + topojson.v3 loaded first. Fetches data/*.json (resolves
   relative to the root index.html document — repo-root /data/).
   ============================================================================ */

// ──────────────────────────────────────────────────────────────
// State
// ──────────────────────────────────────────────────────────────
let allCounties = [];
let filteredCounties = [];
let gl_msaSummaries = {};      // msa_name → {summary, news_headlines}  (kept: written by loadData)
let gl_countyExplanations = {}; // fips → explanation string            (kept: written by loadData)
let goalFilter = "power"; // locked — goal toggle removed; always "power" (Strategic Terrain)

let _currentLens = 'national';
const LENS_DESCRIPTIONS = {
  national: 'Federal electoral tipping points + federal incumbent alignment',
  state:    'State legislative chamber control + state incumbent alignment'
};
function setLens(lens) {
  // B2b: state lens is live. Accept only the two known lenses; ignore anything else.
  if (lens !== 'national' && lens !== 'state') return;
  _currentLens = lens;
  document.getElementById('btn-national').classList.toggle('active', lens === 'national');
  document.getElementById('btn-state').classList.toggle('active', lens === 'state');
  document.getElementById('lens-desc').textContent = LENS_DESCRIPTIONS[lens];
  const lensLabel = document.getElementById('legend-lens-label');
  if (lensLabel) lensLabel.textContent = lens === 'national' ? 'National lens' : 'State lens';
  const badge = document.getElementById('lens-badge');
  if (badge) badge.textContent = lens === 'national' ? 'Viewing: National lens' : 'Viewing: State lens';
  applyFilters();
  updateLegend();
  // Broadcast so peer components (the distribution scatter) switch lens in lockstep.
  window.dispatchEvent(new CustomEvent('lens-change', { detail: { lens: lens } }));
}
function getLens() { return _currentLens; }
function getLensQuadrant(county) {
  if (_currentLens === 'state' && county.quadrant_state) return county.quadrant_state;
  if (_currentLens === 'national' && county.quadrant_national) return county.quadrant_national;
  return county.quadrant || 'tier4';
}
let filters = { state: "", swingOnly: false };

// ──────────────────────────────────────────────────────────────
// Info Card v2.0 — Sector icons, tier helpers, narrative
// ──────────────────────────────────────────────────────────────
const _svg = p => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;

const SECTOR_ICONS = {
  hospitals: _svg(`<path d="M12 7v4"/><path d="M14 21v-3a2 2 0 0 0-4 0v3"/><path d="M14 9h-4"/><path d="M18 11h2a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2h2"/><path d="M18 21V5a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16"/>`),
  education: _svg(`<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>`),
  ports:     _svg(`<circle cx="12" cy="5" r="3"/><line x1="12" y1="8" x2="12" y2="21"/><path d="M5 12H2a10 10 0 0 0 20 0h-3"/>`),
  rail:      _svg(`<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 11h16"/><path d="M12 4v7"/><circle cx="8.5" cy="16" r="1.5"/><circle cx="15.5" cy="16" r="1.5"/><path d="M8 20l-2 2"/><path d="M16 20l2 2"/>`),
  transit:   _svg(`<path d="M8 6v6"/><path d="M15 6v6"/><path d="M2 12h19.6"/><path d="M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3"/><circle cx="7" cy="18" r="2"/><path d="M9 18h5"/><circle cx="16" cy="18" r="2"/>`),
  home_health: _svg(`<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/><line x1="12" y1="9" x2="12" y2="15"/><line x1="9" y1="12" x2="15" y2="12"/>`),
  warehousing: _svg(`<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>`),
  utilities:   _svg(`<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>`),
  manufacturing: _svg(`<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>`),
  higher_ed:   _svg(`<path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>`),
  public_admin: _svg(`<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>`),
  construction: _svg(`<path d="M2 18a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v2z"/><path d="M10 10V5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5"/><path d="M4 15v-3a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v3"/>`),
  default:     _svg(`<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>`)
};

const SECTOR_ICON_MAP = {
  "hospital": "hospitals", "medical": "hospitals",
  "k-12": "education", "elementary": "education", "school": "education",
  "port": "ports", "water transport": "ports", "maritime": "ports",
  "rail": "rail", "railroad": "rail", "freight": "rail",
  "transit": "transit", "bus": "transit", "subway": "transit",
  "home health": "home_health", "nursing": "home_health",
  "residential care": "home_health",
  "warehouse": "warehousing", "trucking": "warehousing",
  "courier": "warehousing", "logistics": "warehousing",
  "utilities": "utilities", "electric": "utilities", "gas": "utilities",
  "manufacturing": "manufacturing", "factory": "manufacturing",
  "university": "higher_ed", "college": "higher_ed",
  "public admin": "public_admin", "government": "public_admin",
  "construction": "construction", "building trades": "construction"
};

function getSectorIcon(sectorName) {
  if (!sectorName) return SECTOR_ICONS.default;
  const lower = sectorName.toLowerCase();
  for (const [key, iconKey] of Object.entries(SECTOR_ICON_MAP)) {
    if (lower.includes(key)) return SECTOR_ICONS[iconKey];
  }
  return SECTOR_ICONS.default;
}

function getTopStrategicSectors(county, n = 3) {
  if (!window._sectorReach || !window._countyEmployment) return [];
  const fips = String(county.fips || "").padStart(5, "0");
  const countyEmp = window._countyEmployment[fips] || {};
  const scores = [];
  for (const [sid, emp] of Object.entries(countyEmp)) {
    const sector = window._sectorReach.sectors?.[sid];
    if (!sector || !emp.total_employment) continue;
    scores.push({ name: sector.sector_name || sid, score: (sector.svs || 0) * emp.total_employment });
  }
  return scores.sort((a, b) => b.score - a.score).slice(0, n);
}

const _TIER_LABELS = {
  tier1_capital: "Tier 1 — Capital",
  tier1_community: "Tier 1 — Community",
  tier1_capital_community: "Tier 1 — Capital + Community",
  tier2_activate_capital: "Tier 2 — Capital",
  tier2_activate_community: "Tier 2 — Community",
  tier2_build_capital: "Tier 2 — Build Capital",
  tier2_build_community: "Tier 2 — Build Community",
  tier2_unknown_capital: "Tier 2 — Capital",
  tier2_unknown_community: "Tier 2 — Community",
  tier3_electoral: "Tier 3 — Electoral Terrain",
  tier4: "Tier 4",
  deploy_now_capital: "Tier 1 — Capital",
  deploy_now_community: "Tier 1 — Community",
  primary_target_capital: "Tier 2 — Capital",
  primary_target_community: "Tier 2 — Community",
  power_building: "Tier 3 — Electoral Terrain",
  lower_priority: "Tier 4"
};

const _TIER_DESCS = {
  tier1_capital: "High capital leverage + hostile incumbent",
  tier1_community: "High community leverage + hostile incumbent",
  tier2_activate_capital: "Capital leverage + aligned incumbent",
  tier2_activate_community: "Community leverage + aligned incumbent",
  tier2_build_capital: "High capital leverage — build electoral conditions",
  tier2_build_community: "High community leverage — build electoral conditions",
  tier3_electoral: "Decisive electoral terrain — build organizing base",
  tier4: "Below current strategic thresholds",
  deploy_now_capital: "High capital leverage + decisive electoral terrain",
  deploy_now_community: "High community leverage + decisive electoral terrain",
  primary_target_capital: "Capital leverage — build electoral conditions",
  primary_target_community: "Community leverage — build electoral conditions",
  power_building: "Decisive terrain — needs organizing infrastructure",
  lower_priority: "Below current strategic thresholds"
};

function _tierNum(q) {
  if (!q) return 4;
  if (q.startsWith("tier1") || q.startsWith("deploy_now")) return 1;
  if (q.startsWith("tier2") || q.startsWith("primary_target")) return 2;
  if (q.startsWith("tier3") || q === "power_building") return 3;
  return 4;
}

function _tierLabel(q) { return _TIER_LABELS[q] || q || "Unclassified"; }
function _tierDesc(q)  { return _TIER_DESCS[q]  || ""; }

function getTier4Narrative(county) {
  const p2 = county.federal_p2 ?? county.p2_alignment ?? null;
  const p1 = county.p1_presidential || 0;
  const name = county.county_name || "This county";

  if (p2 !== null && p2 >= 0.6 && p1 < 5) {
    return `${name} is low priority terrain — not because organizing here lacks value, ` +
           `but because the long-term work of building political alignment has already ` +
           `succeeded. Labor's political infrastructure is strong here. Resources are ` +
           `better deployed where that work remains undone.`;
  }
  if (p2 !== null && p2 < 0.4 && p1 < 5) {
    return `${name} has a hostile incumbent and limited electoral leverage under current ` +
           `conditions. Organizing here builds long-term worker power but is unlikely to ` +
           `shift electoral outcomes in the near term. A long-term investment lens applies.`;
  }
  if (p1 < 5) {
    return `${name} sits outside decisive electoral terrain. Organizing here builds ` +
           `organizational density and worker power without near-term electoral leverage. ` +
           `A long-term power-building frame applies.`;
  }
  return `${name} falls below current strategic thresholds. ` +
         `Review state lens for legislative terrain context.`;
}

function getTier3Narrative(county) {
  const stateTW = county.state_tipping_weight || 0;
  const name = county.county_name || "This county";
  const p1 = county.p1_presidential || 0;

  if (stateTW >= 0.05) {
    return `${name} is in decisive electoral terrain ` +
           `(P1: ${p1.toFixed(1)}) but does not yet have the organizing ` +
           `infrastructure to match its political importance. Building the base here ` +
           `— hospitals, schools, public sector workers — is the long-term strategic task.`;
  }
  return `${name} has significant state legislative leverage but limited presidential ` +
         `electoral weight. Check the State tab for chamber-level context.`;
}

function getCountyNarrative(county) {
  if (county.narrative) return county.narrative;

  const slsCap = county.sls_capital || 0;
  const slsComm = county.sls_community || 0;
  const p1 = county.p1_presidential || 0;
  const p2 = county.federal_p2 ?? county.p2_alignment;
  const name = county.county_name || "This county";
  const state = county.state || "";

  const capitalHigh = slsCap >= 2.5;
  // TODO(config): source these from config/thresholds.json (sls_capital_high_boundary=2.5,
  // sls_community_high_boundary=25, p1_high_boundary=5). 25 matches current config (was stale 35).
  const communityHigh = slsComm >= 25;
  const p1High = p1 >= 5;
  const p2Aligned = p2 != null && p2 >= 0.6;
  const p2Hostile = p2 != null && p2 < 0.4;

  // Tier 4 — neither leverage nor electoral
  if (!capitalHigh && !communityHigh && !p1High) {
    return getTier4Narrative(county);
  }

  // High SLS + high P1 + hostile incumbent (Tier 1)
  if ((capitalHigh || communityHigh) && p1High && p2Hostile) {
    const leverageType = capitalHigh ? "capital leverage" : "community leverage";
    return `${name} combines strong ${leverageType} with decisive ` +
           `electoral geography and a misaligned incumbent. ` +
           `Organizing here can build worker power and hold the ` +
           `incumbent accountable simultaneously.`;
  }

  // High SLS + high P1 + aligned incumbent (Tier 2 activate)
  if ((capitalHigh || communityHigh) && p1High && p2Aligned) {
    const leverageType = capitalHigh ? "capital leverage" : "community leverage";
    return `${name} has strong ${leverageType} in decisive electoral ` +
           `terrain with an already-aligned incumbent. The strategic ` +
           `posture here is to mobilize and protect — turn out organized ` +
           `workers and defend existing gains.`;
  }

  // High SLS + high P1 + P2 unknown
  if ((capitalHigh || communityHigh) && p1High) {
    const leverageType = capitalHigh ? "capital leverage" : "community leverage";
    return `${name} combines strong ${leverageType} with decisive ` +
           `electoral geography. Incumbent alignment data is pending.`;
  }

  // High capital + low P1 (safe state or wide margin)
  if (capitalHigh && !p1High) {
    return `${name} has significant capital leverage ` +
           `(SLS-Capital: ${slsCap.toFixed(1)}) through concentrated ` +
           `strategic workforce. Located in ${state}, which is not a ` +
           `current electoral tipping point — organizing here builds ` +
           `national labor power and long-term industry standards.`;
  }

  // High community + low P1 (safe state or wide margin)
  if (communityHigh && !p1High) {
    return `${name} has strong community leverage ` +
           `(SLS-Community: ${slsComm.toFixed(1)}) — essential service ` +
           `workers make up a significant share of the workforce. ` +
           `Located in ${state}, which is not a current tipping point — ` +
           `organizing here builds durable community power and ` +
           `labor movement density.`;
  }

  // Low SLS + high P1 (Tier 3 electoral)
  if (p1High && !capitalHigh && !communityHigh) {
    return getTier3Narrative(county);
  }

  return `${name} is classified based on its combination of ` +
         `strategic leverage and political terrain scores.`;
}

function getMsaNarrative(msa) {
  const slsType = (msa.capitalScore || 0) >= 2.5 ? "capital"
    : (msa.communityScore || 0) >= 25 ? "community" : null;  // 25 = current config (was stale 35)
  const p1High = (msa.presidential || 0) >= 5;
  if (!slsType && !p1High) {
    return `${msa.msaName} falls below current strategic thresholds `
      + `on leverage and electoral decisiveness.`;
  }
  if (slsType === "capital") {
    return `${msa.msaName} has significant capital leverage `
      + `(SLS-Capital: ${(msa.capitalScore || 0).toFixed(1)}) `
      + `through strategic workforce concentration. `
      + (p1High
        ? `Located in decisive swing geography (P1: ${(msa.presidential || 0).toFixed(1)}).`
        : `Electoral conditions need further development.`);
  }
  if (slsType === "community") {
    return `${msa.msaName} has strong community leverage `
      + `(SLS-Community: ${(msa.communityScore || 0).toFixed(1)}) — `
      + `essential service workers represent a significant share of the workforce. `
      + (p1High
        ? `Located in decisive swing geography (P1: ${(msa.presidential || 0).toFixed(1)}).`
        : `Electoral conditions need further development.`);
  }
  return `${msa.msaName} is in decisive electoral terrain `
    + `(P1: ${(msa.presidential || 0).toFixed(1)}) `
    + `with limited current organizing leverage. Build the base here.`;
}

// ──────────────────────────────────────────────────────────────
// Data loading
// ──────────────────────────────────────────────────────────────
async function loadData() {
  document.getElementById("loading-indicator").style.display = "block";
  setStatus("Loading county data…");
  const localUrl = "data/county_scores.json";
  try {
    const resp = await fetch(localUrl);
    if (resp.ok) {
      const data = await resp.json();
      const raw = data.counties || data;
      allCounties = raw.filter(c => c.sls_capital !== null && c.sls_capital !== undefined);
      // Hero headline: real national Tier-1 count (lens-independent, unfiltered)
      const _t1nat = allCounties.filter(c => (c.quadrant_national || "").startsWith("tier1")).length;
      const _t1el = document.getElementById("finding-tier1");
      if (_t1el) _t1el.textContent = _t1nat;
      setStatus(`Loaded ${allCounties.length} scored counties`);
      document.getElementById("loading-indicator").style.display = "none";
    } else {
      allCounties = [];
      setStatus("Could not load data/county_scores.json — run pipeline/build_v2_canonical.py --full first");
      document.getElementById("loading-indicator").style.display = "none";
      return;
    }
  } catch (e) {
    allCounties = [];
    setStatus("Could not load data/county_scores_v2_test.json — run pipeline/build_v2_scores_true.py first");
    document.getElementById("loading-indicator").style.display = "none";
    return;
  }
  // Load build-time MSA summaries (optional — generated by enrich_summaries.py)
  try {
    const sr = await fetch("data/msa_summaries.json");
    if (sr.ok) {
      const sd = await sr.json();
      // Index by msa_name for fast lookup
      for (const [, v] of Object.entries(sd.msa_summaries || {})) {
        if (v.msa_name && v.summary) gl_msaSummaries[v.msa_name] = v;
      }
      gl_countyExplanations = sd.county_explanations || {};
      console.log(`[Data] ${Object.keys(gl_msaSummaries).length} MSA summaries loaded`);
    }
  } catch (_) { /* msa_summaries.json not yet generated */ }

  // Merge MSA names from static Census CBSA lookup (fixes missing msa_name in county_scores.json)
  try {
    const mr = await fetch("data/msa_lookup.json");
    if (mr.ok) {
      const msaLookup = await mr.json();
      allCounties.forEach(c => { c.msa_name = msaLookup[c.fips] ?? "Non-Metro"; });
      console.log(`[Data] MSA lookup merged onto ${allCounties.length} counties`);
    }
  } catch (_) { /* msa_lookup.json missing — MSA grouping will be inactive */ }

  // Load legislators lookup (built by scripts/build_legislators_lookup.py)
  fetch('data/processed/county_legislators_lookup.json')
    .then(r => r.json())
    .then(data => { window._legislatorLookup = data.counties || {}; })
    .catch(() => { window._legislatorLookup = {}; });
}

// ──────────────────────────────────────────────────────────────
// Score display helpers
// ──────────────────────────────────────────────────────────────
function getDisplayScore(c) {
  if (goalFilter === "presidential") return c.p1_presidential || 0;
  if (goalFilter === "power")        return c.sls_capital || 0;
  return c.sls_capital || 0;
}

// Warm palette — quantile scales built after data loads
let oppColorScale, electoralColorScales = {};

const YLORRD       = ["#FFFFB2","#FED976","#FEB24C","#FD8D3C","#F03B20","#BD0026"];
// Recalibrated for v2.0 sls_capital distribution (median=0.23, p95=5.21, max=84.16)
const JENKS        = [0.5, 1.5, 3.0, 8.0, 20.0];
const JENKS_LABELS = ["0–0.5","0.5–1.5","1.5–3","3–8","8–20","20+"];
const NO_DATA_COLOR    = "#EDEAE3";
const FILTERED_COLOR   = "#F0EDE8";
const TYPE_COLORS = { A: "#2d6a4f", B: "#e76f51", C: "#457b9d" };
let activeLens = "default"; // "default" | "community" | "capital"

// ── Goal-view constants ───────────────────────────────────────
const SWING_STATES_PRES = new Set(["PA","WI","MI","AZ","GA","NV","NC"]);

const QUADRANT_COLORS = {
  "deploy_now_both":          "#6B0019",  // dark red — capital + community + electoral
  "deploy_now_capital":       "#BD0026",  // Terrain Red — capital leverage
  "deploy_now_community":     "#1a3a6b",  // deep blue — community leverage
  "primary_target_capital":   "#E8736B",  // muted red — capital, build phase
  "primary_target_community": "#4A7FB5",  // muted blue — community, build phase
  "power_building":           "#7B6B9E",  // muted purple — electoral leverage only
  "lower_priority":           "#E0DBD3"   // near-invisible warm gray
};

// ── Canonical tier palette ────────────────────────────────────
// EXACT hexes mirrored from the distribution scatter's tierColor() (index.html)
// and the static map key, so MAP == SCATTER == CARD. Family-based so it covers
// every tier* value quadrant_national can emit (tier1/2/3/4 × capital/community,
// including build/activate/unknown variants). This — not QUADRANT_COLORS (legacy
// deploy_now_*/primary_target_* keys) — drives the base-map fill.
const TIER_PALETTE = {
  tier1_capital:   "#BD0026", tier1_community: "#1a3a6b",
  tier2_capital:   "#E8736B", tier2_community: "#4A7FB5",
  tier3:           "#7B6B9E", tier4:           "#E0DBD3",
};
function tierColor(q) {
  if (!q) return NO_DATA_COLOR;          // genuinely absent/null -> no-data gray
  const tn = _tierNum(q);
  const comm = /community/.test(q), cap = /capital/.test(q);
  if (tn === 1) return (comm && !cap) ? TIER_PALETTE.tier1_community : TIER_PALETTE.tier1_capital;
  if (tn === 2) return (comm && !cap) ? TIER_PALETTE.tier2_community : TIER_PALETTE.tier2_capital;
  if (tn === 3) return TIER_PALETTE.tier3;
  return TIER_PALETTE.tier4;
}

const QUADRANT_LABELS = {
  // v2.0 Agent G tier fields
  "tier1_capital":            "Tier 1 — Capital",
  "tier1_community":          "Tier 1 — Community",
  "tier1_capital_community":  "Tier 1 — Capital + Community",
  "tier2_activate_capital":   "Tier 2 — Capital",
  "tier2_activate_community": "Tier 2 — Community",
  "tier2_build_capital":      "Tier 2 — Capital",
  "tier2_build_community":    "Tier 2 — Community",
  "tier2_unknown_capital":    "Tier 2 — Capital",
  "tier2_unknown_community":  "Tier 2 — Community",
  "tier3_electoral":          "Tier 3 — Electoral",
  "tier4":                    "Tier 4",
  // Current fields (before Agent G)
  "deploy_now_capital":       "Tier 1 — Capital",
  "deploy_now_community":     "Tier 1 — Community",
  "deploy_now_both":          "Tier 1 — Capital + Community",
  "primary_target_capital":   "Tier 2 — Capital",
  "primary_target_community": "Tier 2 — Community",
  "power_building":           "Tier 3 — Electoral",
  "lower_priority":           "Tier 4"
};
const NON_SWING_COLOR = "#E0DBD3";

const SENATE_TIERS = {
  NC: 1,
  ME: 2, MI: 2, OH: 2,
  AK: 3, GA: 3, NH: 3,
  IA: 4, MN: 4,
  TX: 5
};
const SENATE_TIER_COLORS = { 1:"#bd0026", 2:"#f03b20", 3:"#fd8d3c", 4:"#fecc5c", 5:"#ffffb2" };
const SENATE_TIER_LABELS = { 1:"Most likely to flip", 2:"Toss-up", 3:"Reach", 4:"Longer shot", 5:"Watch" };

let globalPowerMin = 0, globalPowerMax = 100;

function computeRawPowerScore(c) {
  // DEPRECATED v1 — kept for MSA aggregation fallback only
  const oos = c.v1_organizing_opportunity_score || 0;
  const swing_bonus = c.swing_state ? 20 : 0;
  return oos * 0.60 + swing_bonus * 0.40;
}

function buildGlobalPowerRange() {
  if (!allCounties.length) return;
  const raws = allCounties.map(computeRawPowerScore);
  globalPowerMin = Math.min(...raws);
  globalPowerMax = Math.max(...raws);
}

function getCountyPowerScore(c) {
  const raw = computeRawPowerScore(c);
  if (globalPowerMax === globalPowerMin) return 50;
  return (raw - globalPowerMin) / (globalPowerMax - globalPowerMin) * 100;
}

function getSenateColor(state) {
  const tier = SENATE_TIERS[state];
  return tier ? SENATE_TIER_COLORS[tier] : NON_SWING_COLOR;
}

function getGoalFill(c) {
  if (goalFilter === "presidential") {
    return SWING_STATES_PRES.has(c.state)
      ? getFillByScore(c.p1_presidential || 0)
      : NON_SWING_COLOR;
  }
  if (goalFilter === "power") {
    // One color path for ALL counties: the county's own quadrant_national
    // (via getLensQuadrant), colored by the shared tier palette. No MSA
    // re-classification — see the un-merge note in initMap().
    return tierColor(getLensQuadrant(c));
  }
  if (goalFilter === "senate") return getSenateColor(c.state);
  return NO_DATA_COLOR;
}

function getMsaLensScore(msa) {
  if (activeLens === "community") return msa.communityScore;
  if (activeLens === "capital")   return msa.capitalScore;
  return msa.opp;
}

function getMsaGoalFill(msa) {
  if (goalFilter === "presidential") {
    return msa.hasSwingers ? getFillByScore(msa.presidential || 0) : NON_SWING_COLOR;
  }
  if (goalFilter === "power") {
    return QUADRANT_COLORS[msa.dominantQuadrant] || NO_DATA_COLOR;
  }
  if (goalFilter === "senate") {
    const tierNums = msa.counties.map(c => SENATE_TIERS[c.state]).filter(Boolean);
    if (!tierNums.length) return NON_SWING_COLOR;
    return SENATE_TIER_COLORS[Math.min(...tierNums)];
  }
  return NO_DATA_COLOR;
}

function getFillByType(typeLetter) {
  return TYPE_COLORS[typeLetter] || "#d4d4d4";
}

function getCountyLensScore(c, lens) {
  if (lens === "community") return c.sls_community || 0;
  if (lens === "capital")   return c.sls_capital || 0;
  return c.sls_capital || 0; // default lens uses capital as primary score
}

function getFillByScore(score) {
  return scoreColor(score, null);
}

function buildColorScales() {
  const thresh = d3.scaleThreshold().domain(JENKS).range(YLORRD);
  oppColorScale = thresh;
  // v2.0 electoral fields use same color scale
  for (const key of ["p1_presidential","p1_congressional","p2_alignment"])
    electoralColorScales[key] = thresh;
}

function scoreColor(score, scoreKey) {
  if (score === null || score === undefined) return NO_DATA_COLOR;
  if (scoreKey && electoralColorScales[scoreKey]) return electoralColorScales[scoreKey](score);
  return oppColorScale ? oppColorScale(score) : NO_DATA_COLOR;
}

const TYPE_LEGEND = [
  { letter: "A", color: "#2d6a4f", label: "Build New Power",             desc: "Few/no unions — high potential for new organizing" },
  { letter: "B", color: "#e76f51", label: "Wake the Giant",              desc: "Unions exist but under-activated politically" },
  { letter: "C", color: "#457b9d", label: "Move Together",               desc: "Strong organized base — coordinate campaigns" },
];

function updateLegend() {
  if (goalFilter === "senate") {
    document.getElementById("legend-title").textContent = "Senate Competitiveness";
    const rows = [
      { color: "#bd0026", label: "Most likely to flip" },
      { color: "#f03b20", label: "Toss-up" },
      { color: "#fd8d3c", label: "Reach" },
      { color: "#fecc5c", label: "Longer shot" },
      { color: "#ffffb2", label: "Watch" },
      { color: "#2a2a2a", label: "Not competitive" },
    ];
    document.getElementById("legend-tiers").innerHTML = rows.map(t =>
      `<div class="legend-tier">
        <div class="legend-tier-swatch" style="background:${t.color}"></div>
        <div class="legend-tier-label">${t.label}</div>
      </div>`
    ).join("");
    return;
  }
  if (goalFilter === "presidential") {
    document.getElementById("legend-title").textContent = "Electoral Leverage (P1 Presidential)";
    document.getElementById("legend-tiers").innerHTML =
      YLORRD.map((color, i) =>
        `<div class="legend-tier">
          <div class="legend-tier-swatch" style="background:${color}"></div>
          <div class="legend-tier-label">${JENKS_LABELS[i]}</div>
        </div>`
      ).join("") +
      `<div class="legend-tier">
        <div class="legend-tier-swatch" style="background:#2a2a2a"></div>
        <div class="legend-tier-label">Not competitive</div>
      </div>`;
    return;
  }
  if (goalFilter === "power") {
    document.getElementById("legend-title").textContent = "Strategic Terrain";
    // Canonical tiers, colored by the shared tier palette (matches map + scatter + card).
    const rows = [
      { color: TIER_PALETTE.tier1_capital,   label: "Tier 1 — Capital" },
      { color: TIER_PALETTE.tier1_community, label: "Tier 1 — Community" },
      { color: TIER_PALETTE.tier2_capital,   label: "Tier 2 — Capital" },
      { color: TIER_PALETTE.tier2_community, label: "Tier 2 — Community" },
      { color: TIER_PALETTE.tier3,           label: "Tier 3 — Electoral" },
      { color: TIER_PALETTE.tier4,           label: "Tier 4 — Lower priority" },
    ];
    document.getElementById("legend-tiers").innerHTML = rows.map(t =>
      `<div class="legend-tier">
        <div class="legend-tier-swatch" style="background:${t.color}"></div>
        <div class="legend-tier-label" style="font-size:9px">${t.label}</div>
      </div>`
    ).join("");
    return;
  }
  document.getElementById("legend-title").textContent = "Score";
  document.getElementById("legend-tiers").innerHTML = "";
}

// ──────────────────────────────────────────────────────────────
// Map
// ──────────────────────────────────────────────────────────────
const svg = d3.select("#map-svg");
let g;
let zoomToCounty = () => {};

function highlightSelection(fips, _msaName) {
  // Base map is per-county now; always highlight the county shape by fips.
  svg.selectAll(".map-selected").classed("map-selected", false);
  if (fips) {
    svg.selectAll(`.county-path[data-fips="${fips}"]`).classed("map-selected", true);
  }
}

// MSA aggregate score lookup: fips → msaScore obj, name → msaScore obj
// Built once at map init; used by both fill and updateMapColors.
let msaScoreByFips = {};
let msaScoreByName = {};

// Classify an MSA into the 7-quadrant system using MSA-level aggregated scores.
// NOTE: this legacy MSA rollup NO LONGER drives base-map color (the base map is an
// honest per-county choropleth keyed on quadrant_national — see initMap()). It is
// retained only for the non-visual MSA aggregate (msaScoreByName) and emits LEGACY
// quadrant strings; it does not reproduce the canonical national two-pathway lens.
// TODO(config): community boundary is 25 (current config); was a stale 35.
function classifyMsaQuadrant(msa) {
  const capHigh  = msa.sls_capital      >= 2.5;
  const comHigh  = msa.sls_community    >= 25;
  const presHigh = msa.p1_presidential  >= 5;
  if (capHigh && comHigh && presHigh) return "deploy_now_both";
  if (capHigh && presHigh)            return "deploy_now_capital";
  if (comHigh && presHigh)            return "deploy_now_community";
  if (capHigh)                        return "primary_target_capital";
  if (comHigh)                        return "primary_target_community";
  if (presHigh)                       return "power_building";
  return "lower_priority";
}

function buildMsaScoreLookup() {
  // Group counties by MSA
  const msaGroups = {};
  for (const c of allCounties) {
    const key = (c.msa_name && c.msa_name !== "Non-Metro") ? c.msa_name : null;
    if (!key) continue;
    if (!msaGroups[key]) msaGroups[key] = [];
    msaGroups[key].push(c);
  }
  // Compute population-weighted average scores per MSA
  msaScoreByFips = {};
  msaScoreByName = {};
  for (const [msaName, counties] of Object.entries(msaGroups)) {
    const totalPop = counties.reduce((s, c) => s + (c.population || 1), 0);
    const wavg = f => Math.round(counties.reduce((s, c) => s + (+(c[f] || 0)) * (c.population || 1), 0) / totalPop);
    // Dominant intervention type by population weight (uses v1_intervention_type carried forward in v2.0)
    const tw = {A:0, B:0, C:0};
    for (const c of counties) { const t = (c.v1_intervention_type || "").charAt(5); if (tw[t] !== undefined) tw[t] += (c.population || 1); }
    const domLetter = Object.entries(tw).sort((a,b) => b[1]-a[1])[0][0];
    const domType = domLetter === "A" ? "Type A: Organize the Unorganized"
                  : domLetter === "B" ? "Type B: Politically Activate Existing Unions"
                  : "Type C: Partner with Activated Unions";
    // Swing states in this MSA
    const swingStates = [...new Set(counties.filter(c => c.swing_state).map(c => c.state))].sort().join(", ");
    const states = [...new Set(counties.map(c => c.state))].sort().join(", ");
    const totalPowerRaw = counties.reduce((s, c) => s + computeRawPowerScore(c) * (c.population || 1), 0);
    const powerRaw = totalPowerRaw / totalPop;
    const powerScaled = (globalPowerMax === globalPowerMin) ? 50
      : (powerRaw - globalPowerMin) / (globalPowerMax - globalPowerMin) * 100;
    // v2.0: read sls_community and sls_capital directly
    const communityScore = counties.reduce((s, c) => s + (c.sls_community || 0) * (c.population || 1), 0) / totalPop;
    const capitalScore   = counties.reduce((s, c) => s + (c.sls_capital   || 0) * (c.population || 1), 0) / totalPop;
    // Classify MSA into 7-quadrant system using threshold comparison on aggregated scores
    const presScore = wavg("p1_presidential");
    const dominantQuadrant = classifyMsaQuadrant({
      sls_capital: capitalScore, sls_community: communityScore, p1_presidential: presScore,
    });
    const msaScore = {
      opp:              communityScore, // MSA "opp" = community avg for legacy tooltip
      communityScore,
      capitalScore,
      sls_capital:      capitalScore,
      sls_community:    communityScore,
      p1_presidential:  presScore,
      presidential:     presScore,
      statewide:        null, // DEPRECATED v1 — no v2 equivalent
      congressional:    wavg("p1_congressional"),
      organizing:       null, // DEPRECATED v1
      sectoral:         null, // DEPRECATED v1
      infra:            null, // DEPRECATED v1
      p2Alignment:      wavg("p2_alignment"),
      unionCulture:     null, // DEPRECATED v1
      organizedScale:   null, // DEPRECATED v1
      dominantQuadrant,
      power:            Math.round(powerScaled),
      hasSwingers:      counties.some(c => SWING_STATES_PRES.has(c.state)),
      totalPop,
      countyCount:      counties.length,
      dominantType:     domType,
      dominantLetter:   domLetter,
      swingStates,
      states,
      counties,
      msaName,
    };
    msaScoreByName[msaName] = msaScore;
    for (const c of counties) {
      msaScoreByFips[c.fips] = msaScore;
    }
  }
}

function getMsaDisplayScore(c) {
  const msa = msaScoreByFips[c.fips];
  if (!msa) return getDisplayScore(c); // non-metro: fall back to county score
  if (goalFilter === "presidential")  return getMsaLensScore(msa);
  if (goalFilter === "power")         return getMsaLensScore(msa);
  if (goalFilter === "senate")        return msa.power; // unused for senate (tier-based)
  return msa.opp;
}

async function initMap() {
  // us-atlas counties-albers-10m.json is already projected in a 960×600 Albers pixel space.
  // Use geoIdentity + fitSize — applying geoAlbersUsa() on top garbles shapes into lines.
  const W = 960, H = 600;
  svg.attr("viewBox", `0 0 ${W} ${H}`).attr("preserveAspectRatio", "xMidYMid meet");
  g = svg.append("g");

  const zoom = d3.zoom().scaleExtent([1, 12])
    // DISPLAY-ONLY gating (explorer): wheel/drag/dblclick zoom-pan is live only when the
    // map is the PRIMARY explorer view; in split/PiP it's a glance, so wheel events fall
    // through to page scroll. Single click + hover are NOT zoom gestures and stay active
    // in every layout (so synced-hover + click-readout work in the side-by-side view).
    .filter(function (event) {
      var ex = document.getElementById('explorer');
      var primary = ex && ex.getAttribute('data-layout') === 'map-primary';
      if (!primary && (event.type === 'wheel' || event.type === 'mousedown' ||
                       event.type === 'dblclick' || event.type === 'touchstart')) return false;
      return (!event.ctrlKey || event.type === 'wheel') && !event.button;
    })
    .on("zoom", e => g.attr("transform", e.transform));
  svg.call(zoom);

  buildMsaScoreLookup();

  const loadingMsg = svg.append("text")
    .attr("x", 480).attr("y", 305)
    .attr("text-anchor", "middle").attr("dominant-baseline", "middle")
    .attr("fill", "#7A6F64").attr("font-size", "14")
    .text("Loading map…");

  try {
    const us = await d3.json("https://cdn.jsdelivr.net/npm/us-atlas@3/counties-albers-10m.json");
    loadingMsg.remove();
    const allCountyFeatures = topojson.feature(us, us.objects.counties);
    const stateMesh = topojson.mesh(us, us.objects.states, (a, b) => a !== b);

    const countyByFips = {};
    allCounties.forEach(c => { countyByFips[c.fips] = c; });

    // ── HONEST PER-COUNTY CHOROPLETH (metros un-merged) ──────────
    // Every county (metro + non-metro) renders as its own shape, colored by its
    // own quadrant_national. We no longer topojson.merge metro counties into a
    // single MSA polygon — that merge was what forced the separate, stale
    // classifyMsaQuadrant color path. Now MAP color == SCATTER color == CARD tier
    // for all 3,143 counties. Only counties present in the data are drawn.
    //
    // BOOKMARK (future, do NOT build now): an optional "MSA merge" toggle/overlay
    // could re-group metro counties into a metro rollup view ON TOP OF this honest
    // per-county base map (a lens, not the default). The MSA aggregation in
    // buildMsaScoreLookup()/msaScoreByName is retained for that and for non-visual
    // use; it must not drive base-map color.
    const countyFeatures = allCountyFeatures.features.filter(f => countyByFips[f.id]);

    const path = d3.geoPath().projection(d3.geoIdentity().fitSize([W, H], allCountyFeatures));

    zoomToCounty = (fips) => {
      const f = allCountyFeatures.features.find(f => String(f.id) === String(fips));
      if (!f) return;
      const [[x0, y0], [x1, y1]] = path.bounds(f);
      const scale = Math.min(8, 0.85 / Math.max((x1 - x0) / W, (y1 - y0) / H));
      svg.transition().duration(750).call(
        zoom.transform,
        d3.zoomIdentity.translate(W / 2 - scale * (x0 + x1) / 2, H / 2 - scale * (y0 + y1) / 2).scale(scale)
      );
    };

    const tt = document.getElementById("tooltip");

    // ── Draw ALL counties as individual shapes (single color path) ──
    g.append("g").attr("class", "county-regions")
      .selectAll("path")
      .data(countyFeatures)
      .join("path")
      .attr("class", "county-path")
      .attr("d", path)
      .attr("stroke", "#C8BFB5")
      .attr("stroke-width", "0.3")
      .attr("fill", d => {
        const c = countyByFips[d.id];
        if (!c) return NO_DATA_COLOR;
        return getGoalFill(c);
      })
      .attr("data-fips", d => d.id)
      .on("mousemove", (event, d) => {
        const c = countyByFips[d.id];
        if (!c) return;
        tt.style.opacity = "1";
        tt.style.left = (event.offsetX + 12) + "px";
        tt.style.top = (event.offsetY - 10) + "px";
        const _tc = t => t===1?"#bd0026":t===2?"#1a3a6b":t===3?"#6b4f9e":"#999";
        const msa = msaScoreByFips[c.fips];
        const place = msa ? msa.msaName : "Non-Metro";
        let scoreHtml = "";
        if (goalFilter === "presidential") {
          if (SWING_STATES_PRES.has(c.state)) {
            const pres = (c.p1_presidential || 0).toFixed(1);
            const com  = (c.sls_community  || 0).toFixed(1);
            const cap  = (c.sls_capital    || 0).toFixed(1);
            scoreHtml = `<br><span class="tt-opp">P1: ${pres} · Cap: ${cap} · Comm: ${com}</span>`;
          } else {
            scoreHtml = `<br><span style="color:#888;font-size:10px">Not a presidential battleground</span>`;
          }
        } else if (goalFilter === "power") {
          const q  = getLensQuadrant(c);
          scoreHtml = `<br><span style="font-size:11px;font-weight:600;color:${tierColor(q)}">${_tierLabel(q)}</span>`
            + `<br><span style="font-size:10px;color:#A09385">Cap: ${(c.sls_capital||0).toFixed(1)} · Comm: ${(c.sls_community||0).toFixed(1)}</span>`;
        } else if (goalFilter === "senate") {
          const tier = SENATE_TIERS[c.state];
          scoreHtml = tier
            ? `<br><span class="tt-opp">${SENATE_TIER_LABELS[tier]}</span>`
            : `<br><span style="color:#888;font-size:10px">Not competitive</span>`;
        }
        tt.innerHTML = `<strong>${c.county_name}, ${c.state}</strong>`
          + `<br><span style="font-size:10px;color:#A09385">${place}</span>`
          + scoreHtml;
      })
      .on("mouseleave", () => { tt.style.opacity = "0"; })
      .on("click", (event, d) => {
        const c = countyByFips[d.id];
        if (c) showDetail(c);
      });

    g.append("path").datum(stateMesh).attr("class", "state-boundary").attr("d", path);

    // ── Intervention-type symbol overlay ─────────────────────────
    const symGen = d3.symbol().size(28);
    const intG = g.append("g").attr("id", "int-type-overlay").style("display", "none").style("pointer-events", "none");

    function addIntSymbol(cx, cy, letter) {
      if (isNaN(cx) || isNaN(cy)) return;
      const symType = letter === "A" ? d3.symbolTriangle
                    : letter === "B" ? d3.symbolCircle
                    : d3.symbolSquare;
      intG.append("path")
        .attr("d", symGen.type(symType)())
        .attr("transform", `translate(${cx},${cy})`)
        .attr("fill", TYPE_COLORS[letter])
        .attr("fill-opacity", 0.78)
        .attr("stroke", "#fff")
        .attr("stroke-width", 0.5);
    }

    for (const f of countyFeatures) {
      const c = countyByFips[f.id];
      if (!c) continue;
      const letter = (c.v1_intervention_type || "").charAt(5);
      if (!["A","B","C"].includes(letter)) continue;
      const [cx, cy] = path.centroid(f);
      addIntSymbol(cx, cy, letter);
    }

    setStatus(`Map loaded · ${countyFeatures.length} counties`);
  } catch (e) {
    loadingMsg.text("Map failed to load — check internet connection and reload.");
    setStatus("Map topology failed to load. Check internet connection.");
    console.error(e);
  }
}

function updateMapColors() {
  if (!g) return;
  const visibleFips = new Set(filteredCounties.map(c => c.fips));

  const countyByFips = {};
  allCounties.forEach(c => { countyByFips[c.fips] = c; });
  g.selectAll(".county-path").attr("fill", function() {
    const fips = this.dataset.fips;
    const c = countyByFips[fips];
    if (!c) return NO_DATA_COLOR;
    if (!visibleFips.has(fips)) return FILTERED_COLOR;
    return getGoalFill(c);
  });
}

// ──────────────────────────────────────────────────────────────
// Detail panel
// ──────────────────────────────────────────────────────────────
function _setBar(barId, valId, lblId, score, highlighted, nullLabel) {
  const bar = document.getElementById(barId);
  const val = document.getElementById(valId);
  const lbl = document.getElementById(lblId);
  if (!bar || !val || !lbl) return; // element removed in v2.0 — skip silently
  const hasScore = score !== null && score !== undefined && !isNaN(score);
  const pct = hasScore ? Math.min(100, Math.max(0, score)) : 0;
  bar.style.width = pct + "%";
  val.textContent = hasScore ? (Number.isInteger(score) ? score : score.toFixed(2)) : (nullLabel || "–");
  val.className = "score-bar-val" + (highlighted ? " highlighted" : "");
  lbl.className = "score-bar-label" + (highlighted ? " highlighted" : "");
}

function _setQuadrantBadge(quadrant) {
  const badge = document.getElementById("dp-quadrant-badge");
  if (!badge) return;
  badge.textContent = QUADRANT_LABELS[quadrant] || quadrant || "–";
  badge.className = "badge badge-int-b";
  if (quadrant && quadrant.startsWith("deploy_now")) badge.className = "badge badge-int-c";
  else if (quadrant && quadrant.startsWith("primary_target")) badge.className = "badge badge-int-b";
  else if (quadrant === "power_building") badge.className = "badge badge-tier-a";
  else badge.className = "badge badge-tier-c";
}

// DEPRECATED v1 — kept for MSA fallback compatibility only
function _setIntBadge(intType) {
  _setQuadrantBadge(null);
}

// MSA panel — shown when clicking a merged metro region
function showMsaDetail(msaName) {
  const msa = msaScoreByName[msaName];
  if (!msa) return;
  highlightSelection(null, msaName);
  const panel = document.getElementById("detail-panel");
  panel.scrollTop = 0;

  const q = msa.dominantQuadrant || "tier4";
  const tn = _tierNum(q);
  const slsCap   = msa.capitalScore;
  const slsComm  = msa.communityScore;
  const p1       = msa.presidential;
  const p2Raw    = msa.p2Alignment;
  const cacheKey = "msa_" + msaName.replace(/\W+/g, "_");

  const fmt1   = v => v != null ? (+v).toFixed(1) : "—";
  const fmtPct = v => v != null ? (v * 100).toFixed(0) + "%" : "Data pending";
  const barW   = (v, max) => v != null ? Math.min(100, parseFloat(v) / max * 100).toFixed(1) + "%" : "0%";

  const sorted = [...msa.counties].sort((a, b) => (b.sls_capital || 0) - (a.sls_capital || 0));
  const countyRows = sorted.map(c => {
    const cq = c.quadrant || "lower_priority";
    return `<div class="card-more-row">
      <span class="card-more-key">${c.county_name}, ${c.state}</span>
      <span>${_tierLabel(cq).replace("Tier ", "T")} · ${(c.sls_capital || 0).toFixed(1)}</span>
    </div>`;
  }).join("");

  panel.innerHTML = `
    <button onclick="document.getElementById('detail-panel').style.display='none'"
            style="position:absolute;top:10px;right:12px;background:none;border:none;
                   font-size:18px;cursor:pointer;color:var(--color-text-muted);line-height:1;">×</button>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                margin-bottom:var(--space-3);">
      <div>
        <span class="card-tier-badge" style="background:${tierColor(q)};color:${tn >= 4 ? 'var(--color-text)' : '#fff'};border:none">${_tierLabel(q)}</span>
        <h3 style="font-family:var(--font-serif);font-size:var(--text-lg);
                   color:var(--color-text);margin:0 0 2px;">${msaName}</h3>
        <div style="font-family:var(--font-mono);font-size:var(--text-xs);
                    color:var(--color-text-muted);">
          ${msa.states}&nbsp;·&nbsp;${msa.countyCount} ${msa.countyCount === 1 ? "county" : "counties"}
          &nbsp;·&nbsp;Pop.&nbsp;${msa.totalPop ? msa.totalPop.toLocaleString() : "—"}
        </div>
        <div style="font-size:var(--text-xs);color:var(--color-text-muted);margin-top:4px;">
          ${_tierDesc(q)}
        </div>
      </div>
    </div>

    <div class="card-narrative">${getMsaNarrative(msa)}</div>

    <div class="card-section-head">Strategic Leverage</div>

    <div class="card-score-row">
      <div class="card-score-label">Capital Leverage</div>
      <div class="card-bar-wrap">
        <div class="card-bar-fill card-bar-capital" style="width:${barW(slsCap, 100)}"></div>
      </div>
      <div class="card-score-val">${fmt1(slsCap)}</div>
    </div>
    <div class="card-score-hint">Pop.-weighted avg · crisis-creating power against capital flows</div>

    <div class="card-score-row">
      <div class="card-score-label">Community Leverage</div>
      <div class="card-bar-wrap">
        <div class="card-bar-fill card-bar-community" style="width:${barW(slsComm, 100)}"></div>
      </div>
      <div class="card-score-val">${fmt1(slsComm)}</div>
    </div>
    <div class="card-score-hint">Share of workforce in essential community roles</div>

    <div class="card-section-head">Political Terrain</div>

    <div class="card-score-row">
      <div class="card-score-label">Electoral Leverage (P1)</div>
      <div class="card-bar-wrap">
        <div class="card-bar-fill card-bar-electoral" style="width:${barW(p1, 100)}"></div>
      </div>
      <div class="card-score-val">${fmt1(p1)}</div>
    </div>
    <div class="card-score-hint">Swing states in metro: ${msa.swingStates || "None"}</div>

    <div class="card-score-row">
      <div class="card-score-label">Federal Alignment (P2)</div>
      <div class="card-bar-wrap">
        <div class="card-bar-fill card-bar-alignment"
             style="width:${p2Raw != null ? barW(p2Raw * 100, 100) : "0%"}"></div>
      </div>
      <div class="card-score-val">${fmtPct(p2Raw)}</div>
    </div>
    <div class="card-score-hint">Incumbent alignment on 4 federal labor key votes</div>

    <div class="card-more-toggle"
         onclick="this.nextElementSibling.classList.toggle('open');
         this.querySelector('span').textContent =
         this.nextElementSibling.classList.contains('open') ? '▼ ' : '▶ ';">
      <span>▶ </span>Member counties (${msa.countyCount})
    </div>
    <div class="card-more-body">${countyRows}</div>

    <div class="card-section-head" style="margin-top:var(--space-4);">
      Current Legislators
      <span style="font-family:var(--font-body);font-size:10px;
                   color:var(--color-text-muted);font-weight:400;
                   text-transform:none;letter-spacing:0;">
        · updated monthly
      </span>
    </div>
    ${buildMsaLegislatorsHTML(msa.counties)}
  `;

  panel.style.display = "block";
}

// ──────────────────────────────────────────────────────────────
// Legislators section helpers
// ──────────────────────────────────────────────────────────────
function _legCard(leg) {
  const p2Display = leg.p2_combined != null
    ? (leg.p2_combined * 100).toFixed(0) + "% aligned"
    : "score pending";
  const partyColor = leg.party === "D" ? "#2c6fad"
                   : leg.party === "R" ? "#bd0026"
                   : "var(--color-text-muted)";
  const p2Color = leg.p2_combined != null
    ? leg.p2_combined >= 0.6 ? "#2c6fad"
      : leg.p2_combined <= 0.4 ? "#bd0026"
      : "var(--color-text-muted)"
    : "var(--color-text-muted)";
  return `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                padding:var(--space-2) 0;border-bottom:1px solid var(--color-border);">
      <div>
        <div style="font-size:var(--text-sm);color:var(--color-text);
                    font-weight:500;">${leg.name}</div>
        <div style="font-family:var(--font-mono);font-size:10px;
                    color:${partyColor};margin-top:2px;">
          ${leg.party} · ${leg.title}
        </div>
      </div>
      <div style="text-align:right;">
        <div style="font-family:var(--font-mono);font-size:10px;
                    color:${p2Color};">${p2Display}</div>
        ${leg.key_vote_score != null ? `
        <div style="font-size:9px;color:var(--color-text-muted);margin-top:2px;">
          ${(leg.key_vote_score * 4).toFixed(0)}/4 key votes pro-labor
        </div>` : ""}
      </div>
    </div>`;
}

function buildLegislatorsHTML(fips, state) {
  const data = window._legislatorLookup?.[fips];
  if (!data) {
    return `<div style="font-size:var(--text-xs);color:var(--color-text-muted);">
      Legislator data loading…
    </div>`;
  }
  const all = [...(data.federal || []), ...(data.state || [])];
  if (!all.length) {
    return `<div style="font-size:var(--text-xs);color:var(--color-text-muted);">
      No legislator data available for this county.
    </div>`;
  }
  return all.map(_legCard).join("");
}

function buildMsaLegislatorsHTML(msaCounties) {
  if (!window._legislatorLookup) {
    return `<div style="font-size:var(--text-xs);color:var(--color-text-muted);">
      Legislator data loading…
    </div>`;
  }
  const seen = new Set();
  const all = [];
  for (const c of msaCounties) {
    const fips = String(c.fips || "").padStart(5, "0");
    const data = window._legislatorLookup[fips];
    if (!data) continue;
    for (const leg of [...(data.federal || []), ...(data.state || [])]) {
      // deduplicate by bioguide_id, fall back to name+chamber+district
      const key = leg.bioguide_id || `${leg.name}|${leg.chamber}|${leg.district}`;
      if (!seen.has(key)) { seen.add(key); all.push(leg); }
    }
  }
  if (!all.length) {
    return `<div style="font-size:var(--text-xs);color:var(--color-text-muted);">
      No legislator data available for this metro area.
    </div>`;
  }
  // Senators first, then House by P2 descending
  all.sort((a, b) => (a.chamber === "senate" ? 0 : 1) - (b.chamber === "senate" ? 0 : 1)
                     || (b.p2_combined || 0) - (a.p2_combined || 0));
  return all.map(_legCard).join("");
}

// County detail panel (v2.0 — all counties, not just non-metro)
function showDetail(county) {
  highlightSelection(county.fips, null);
  const panel = document.getElementById("detail-panel");
  panel.scrollTop = 0;

  const lens   = _currentLens;
  const q      = getLensQuadrant(county);
  const tn     = _tierNum(q);
  const slsCap = county.sls_capital;
  const slsComm= county.sls_community;
  const p1     = lens === 'state'
                   ? county.p1_state
                   : (county.p1_national ?? county.p1_presidential);
  const p2Raw  = lens === 'state'
                   ? county.p2_state
                   : (county.p2_national ?? county.federal_p2 ?? county.p2_alignment);
  const p2Cov  = lens === 'state' ? county.state_p2_coverage : county.p2_coverage;
  const margin = county.margin_2024;
  const sw     = county.state_tipping_weight;
  const pop    = county.population;
  const fips   = String(county.fips || "").padStart(5, "0");

  const fmt1     = v => v != null ? (+v).toFixed(1) : "—";
  const fmtPct   = v => v != null ? (v * 100).toFixed(0) + "%" : "Data pending";
  const fmtMargin= v => v != null ? (v >= 0 ? "D+" : "R+") + Math.abs(v).toFixed(1) : "unknown";
  const barW     = (v, max) => v != null ? Math.min(100, parseFloat(v) / max * 100).toFixed(1) + "%" : "0%";

  const topSectors = getTopStrategicSectors(county);

  panel.innerHTML = `
    <button onclick="document.getElementById('detail-panel').style.display='none'"
            style="position:absolute;top:10px;right:12px;background:none;border:none;
                   font-size:18px;cursor:pointer;color:var(--color-text-muted);line-height:1;">×</button>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                margin-bottom:var(--space-3);">
      <div>
        <span class="card-tier-badge" style="background:${tierColor(q)};color:${tn >= 4 ? 'var(--color-text)' : '#fff'};border:none">${_tierLabel(q)}</span>
        <h3 style="font-family:var(--font-serif);font-size:var(--text-xl);
                   color:var(--color-text);margin:0 0 2px;">
          ${county.county_name || "County"}
        </h3>
        <div style="font-family:var(--font-mono);font-size:var(--text-xs);
                    color:var(--color-text-muted);">
          ${county.state || ""}&nbsp;·&nbsp;Pop.&nbsp;${pop ? pop.toLocaleString() : "—"}
        </div>
        <div style="font-family:var(--font-mono);font-size:var(--text-xs);
                    color:var(--color-text-muted);margin-top:var(--space-1);">
          2024 presidential: ${margin != null
            ? (margin >= 0
               ? `<span style="color:#2c6fad">D+${Math.abs(margin).toFixed(1)}</span>`
               : `<span style="color:#bd0026">R+${Math.abs(margin).toFixed(1)}</span>`)
            : "—"}
          &nbsp;·&nbsp;State tipping: ${sw != null ? (sw * 100).toFixed(0) + "%" : "—"}
        </div>
        <div style="font-size:var(--text-xs);color:var(--color-text-muted);margin-top:4px;">
          ${_tierDesc(q)}
        </div>
      </div>
      ${topSectors.length ? `
      <div class="card-icons-row">
        ${topSectors.map(s => `
          <div class="card-icon-item">
            <div class="card-icon-svg">${getSectorIcon(s.name)}</div>
            <div class="card-icon-label">${s.name.split(/\s+/)[0]}</div>
          </div>`).join("")}
      </div>` : ""}
    </div>

    <div class="card-narrative">${getCountyNarrative(county)}</div>

    <div class="card-section-head">Strategic Leverage</div>

    <div class="card-score-row">
      <div class="card-score-label">Capital Leverage</div>
      <div class="card-bar-wrap">
        <div class="card-bar-fill card-bar-capital" style="width:${barW(slsCap, 100)}"></div>
      </div>
      <div class="card-score-val">${fmt1(slsCap)}</div>
    </div>
    <div class="card-score-hint">Crisis-creating power against capital flows</div>

    <div class="card-score-row">
      <div class="card-score-label">Community Leverage</div>
      <div class="card-bar-wrap">
        <div class="card-bar-fill card-bar-community" style="width:${barW(slsComm, 100)}"></div>
      </div>
      <div class="card-score-val">${fmt1(slsComm)}</div>
    </div>
    <div class="card-score-hint">Share of workforce in essential community roles</div>

    <div class="card-section-head">Political Terrain</div>

    <div class="card-score-row">
      <div class="card-score-label">Electoral Leverage (P1)</div>
      <div class="card-bar-wrap">
        <div class="card-bar-fill card-bar-electoral" style="width:${barW(p1, 100)}"></div>
      </div>
      <div class="card-score-val">${fmt1(p1)}</div>
    </div>
    <div class="card-score-hint">
      2024 margin: ${fmtMargin(margin)}&nbsp;pts
      · ${lens === 'state'
            ? `Chamber competitiveness: ${county.chamber_tipping_weight != null ? (county.chamber_tipping_weight * 100).toFixed(0) + "%" : "—"}`
            : `State decisive: ${sw != null ? (sw * 100).toFixed(0) + "%" : "—"}`}
    </div>

    <div class="card-score-row">
      <div class="card-score-label">${lens === 'state' ? 'State Alignment (P2)' : 'Federal Alignment (P2)'}</div>
      <div class="card-bar-wrap">
        <div class="card-bar-fill card-bar-alignment"
             style="width:${p2Raw != null ? barW(p2Raw * 100, 100) : "0%"}"></div>
      </div>
      <div class="card-score-val">${fmtPct(p2Raw)}</div>
    </div>
    <div class="card-score-hint">
      ${lens === 'state'
        ? `State legislature alignment · confidence: ${p2Cov || "—"}`
        : `Incumbent alignment on 4 federal labor key votes${p2Cov ? ` · ${p2Cov}` : ""}`}
    </div>

    <div class="card-more-toggle"
         onclick="this.nextElementSibling.classList.toggle('open');
         this.querySelector('span').textContent =
         this.nextElementSibling.classList.contains('open') ? '▼ ' : '▶ ';">
      <span>▶ </span>Additional data
    </div>
    <div class="card-more-body">
      <div class="card-more-row">
        <span class="card-more-key">State electoral leverage (P1)</span>
        <span>${county.p1_state != null ? county.p1_state.toFixed(2) : "Data pending"}</span>
      </div>
      <div class="card-more-row">
        <span class="card-more-key">State alignment (P2)</span>
        <span>${fmtPct(county.p2_state)}${county.state_p2_coverage ? ` (${county.state_p2_coverage})` : ""}</span>
      </div>
      <div class="card-more-row">
        <span class="card-more-key">National electoral leverage (P1)</span>
        <span>${county.p1_national != null ? county.p1_national.toFixed(2) : "Data pending"}</span>
      </div>
      <div class="card-more-row">
        <span class="card-more-key">National alignment (P2)</span>
        <span>${fmtPct(county.p2_national)}</span>
      </div>
      <div class="card-more-row">
        <span class="card-more-key">State lens tier</span>
        <span>${county.quadrant_state ? _tierLabel(county.quadrant_state) : "Data pending"}</span>
      </div>
      <div class="card-more-row">
        <span class="card-more-key">v1 OOS (reference only)</span>
        <span>${county.v1_organizing_opportunity_score != null
               ? county.v1_organizing_opportunity_score.toFixed(1) : "—"}</span>
      </div>
    </div>

    <div class="card-section-head" style="margin-top:var(--space-4);">
      Current Legislators
      <span style="font-family:var(--font-body);font-size:10px;
                   color:var(--color-text-muted);font-weight:400;
                   text-transform:none;letter-spacing:0;">
        · updated monthly
      </span>
    </div>
    ${buildLegislatorsHTML(fips, county.state)}
  `;

  panel.style.display = "block";
}

// close button uses inline onclick in v2.0 templates; this handles the static fallback
document.getElementById("close-detail").addEventListener("click", () => {
  document.getElementById("detail-panel").style.display = "none";
});

// ──────────────────────────────────────────────────────────────
// Filters
// ──────────────────────────────────────────────────────────────
function applyFilters() {
  filteredCounties = allCounties.filter(c => {
    if (filters.state && c.state !== filters.state) return false;
    if (filters.swingOnly && !c.swing_state) return false;
    return true;
  });

  updateStats();
  updateTop10();
  updateMapColors();
}

function updateStats() {
  document.getElementById("stat-total").textContent = allCounties.length.toLocaleString();
  const counts = { tier1: 0, tier2: 0, tier3: 0, tier4: 0 };
  filteredCounties.forEach(c => {
    const n = _tierNum(getLensQuadrant(c));
    if (n === 1) counts.tier1++;
    else if (n === 2) counts.tier2++;
    else if (n === 3) counts.tier3++;
    else counts.tier4++;
  });
  document.getElementById("stat-tier1").textContent = counts.tier1.toLocaleString();
  document.getElementById("stat-tier2").textContent = counts.tier2.toLocaleString();
  document.getElementById("stat-tier3").textContent = counts.tier3.toLocaleString();
  document.getElementById("stat-tier4").textContent = counts.tier4.toLocaleString();
  document.getElementById("stat-visible").textContent = filteredCounties.length.toLocaleString();
}

function updateTop10() {
  const top = [...filteredCounties]
    .sort((a, b) => (b.sls_capital ?? 0) - (a.sls_capital ?? 0))
    .slice(0, 10);
  const container = document.getElementById("top10-list");
  container.innerHTML = top.map((c, i) => {
    const scoreColor = tierColor(getLensQuadrant(c));
    return `<div class="top10-row" onclick="showDetail(${JSON.stringify(c).replace(/"/g, '&quot;')}); zoomToCounty('${c.fips}')">
      <span class="top10-name">${i+1}. ${c.county_name}, ${c.state}</span>
      <span class="top10-score" style="color:${scoreColor}">${(c.sls_capital || 0).toFixed(2)}</span>
    </div>`;
  }).join("");
}

function populateStateFilter() {
  const states = [...new Set(allCounties.map(c => c.state).filter(Boolean))].sort();
  const sel = document.getElementById("filter-state");
  states.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s; opt.textContent = s;
    sel.appendChild(opt);
  });
}

document.getElementById("filter-state").addEventListener("change", e => { filters.state = e.target.value; applyFilters(); });
document.getElementById("filter-swing").addEventListener("change", e => { filters.swingOnly = e.target.checked; applyFilters(); });

// ──────────────────────────────────────────────────────────────
// Legend + mobile filter toggles (referenced by inline onclick in markup)
// ──────────────────────────────────────────────────────────────
function toggleLegend() {
  const legend = document.getElementById("map-legend");
  const btn = document.getElementById("legend-toggle-btn");
  if (!legend || !btn) return;
  legend.classList.toggle("collapsed");
}

function mobileToggleFilters() {
  const sb = document.getElementById("sidebar");
  const btn = document.getElementById("mobile-filter-toggle");
  if (!sb || !btn) return;
  const collapsed = sb.classList.toggle("mobile-collapsed");
  btn.classList.toggle("open", !collapsed);
}

// ──────────────────────────────────────────────────────────────
// Utility
// ──────────────────────────────────────────────────────────────
function setStatus(msg) {
  const el = document.getElementById("status-msg");
  if (el) el.textContent = msg;
}

// ──────────────────────────────────────────────────────────────
// Map figure expand / collapse (inline-with-margin ↔ fullscreen)
// ──────────────────────────────────────────────────────────────
function expandMap() {
  const fig = document.getElementById('map-figure');
  const btn = document.querySelector('.map-expand-btn');
  const sidebar = document.getElementById('sidebar');
  if (!fig) return;
  const isExpanded = fig.classList.toggle('expanded');
  if (btn) btn.textContent = isExpanded ? '↙ Collapse' : '↗ Expand';
  document.body.style.overflow = isExpanded ? 'hidden' : '';
  if (sidebar) {
    sidebar.style.cssText = isExpanded
      ? 'display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;width:320px;z-index:501;overflow-y:auto;background:var(--color-bg);border-right:1px solid var(--color-border);padding:1rem;'
      : 'display:none;';
  }
  setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const fig = document.getElementById('map-figure');
    if (fig && fig.classList.contains('expanded')) expandMap();
  }
});

// ──────────────────────────────────────────────────────────────
// Public hook for the page content layer (top-target cards, etc.)
// flyToCounty(fips) opens a county's panel and zooms the map to it.
// ──────────────────────────────────────────────────────────────
function flyToCounty(fips) {
  const key = String(fips);
  const county = allCounties.find(c => String(c.fips) === key
                                     || String(c.fips).padStart(5, "0") === key.padStart(5, "0"));
  if (!county) return;
  showDetail(county);
  zoomToCounty(county.fips);
}
window.TerrainMap = {
  flyToCounty,
  getCounties: () => allCounties,
  showDetail,
  zoomToCounty: (f) => zoomToCounty(f),
  setLens,
  getLens,
};

// ──────────────────────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────────────────────
(async () => {
  await loadData();
  buildColorScales();
  buildGlobalPowerRange();
  filteredCounties = [...allCounties];
  populateStateFilter();
  updateStats();
  updateTop10();
  updateLegend();
  await initMap();
  applyFilters();
  const ts = document.getElementById("data-timestamp");
  if (ts) ts.textContent = "Terrain v2.0 · Data: 2024";
  // Notify the page content layer that county data + map are ready.
  window.dispatchEvent(new CustomEvent('terrain-map-ready', { detail: { counties: allCounties } }));
})();
