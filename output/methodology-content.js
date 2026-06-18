/* ════════════════════════════════════════════════════════════════════════════
   METHODOLOGY CONTENT — data-driven section architecture (Architecture A + C)
   ════════════════════════════════════════════════════════════════════════════

   HOW THIS WORKS
   --------------
   Every methodology FACTOR / VARIABLE section is a DATA OBJECT (below, in
   METHODOLOGY_SECTIONS). ONE render function (renderMethodologySection) turns a
   data object into the rendered HTML of the LOCKED TEMPLATE:

       title (static in HTML) → one-sentence summary → mini-flowchart
       (data sources as live links) → expandable Details (formulas, monospace) →
       expandable Rationale & Limitations → "See also" cross-links.

   EDITING
   -------
     • To change a section's PROSE  → edit its data object here. Never hand-edit
       the rendered HTML in index.html (the body is generated into a placeholder
       <div class="method-render" data-section="ID">).
     • To change a NUMBER the prose cites → change it at its real source
       (config/*.json or pipeline/*.py) and re-run pipeline/emit_model_spec.py.
       The template resolves every constant from model_spec.json by specKey, so a
       number can never silently drift from the model. A {{specKey}} token in any
       formula/cleaning/notes string is substituted with the spec's display value;
       a `constants: [{specKey, label}]` list renders a "live from spec" line.
       A missing specKey renders a visible "[value missing from spec]" marker.

   SECTION STATUS (the `status` field)
   -----------------------------------
     • 'populated' — fully written to the locked template (Electoral Leverage,
                     the worked example).
     • 'migrated'  — existing prose RE-HOMED into the data structure verbatim,
                     NOT yet rewritten to the locked template/voice. Flagged with a
                     banner so we know it still needs the spec-grounded treatment.
     • 'stub'      — genuinely empty; structure only, TODO placeholders.

   The Theory sections (m-stakes, m-assumptions, m-model) and the back matter
   (m-limitations, m-data, m-literature, m-research, m-about) are narrative prose
   that does NOT fit this locked template; they are intentionally left as static
   HTML in index.html and are NOT rendered by this system.
   ════════════════════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  /* ──────────────────────────────────────────────────────────────────────────
     SECTION DATA OBJECTS
     Each follows the LOCKED TEMPLATE shape:
       { id, title, status, summary,
         flowchart: { inputs:[…], outputs:[…], dataSources:[{label, href}] },
         details:   [ { variant, inputs, cleaning, formula,
                        constants:[{specKey, label}], outputField, notes, html } ],
         rationale:   [ … paragraphs (may contain HTML) ],
         limitations: [ … bullets (may contain HTML) ],
         seeAlso:     [ {label, href} ] }
     inputs/outputs entries may be a {label, href} (renders a live link) or a
     plain string (renders a label). `html` on a details variant is raw migrated
     HTML carried verbatim (used by 'migrated' sections for zero content loss).
     ────────────────────────────────────────────────────────────────────────── */
  var METHODOLOGY_SECTIONS = [

    /* ════════════════════ INPUTS — genuinely empty stubs ════════════════════ */
    {
      id: "input-sectoral",
      title: "Inputs: Sectoral",
      status: "stub",
      summary: "",
      flowchart: { inputs: [], outputs: [], dataSources: [] },
      details: [],
      rationale: [],
      limitations: [],
      seeAlso: [{ label: "Sectoral Leverage", href: "#factor-sectoral-leverage" }]
      /* TODO(prose): County employment + Sector strategic score (the SVS rubric). */
    },
    {
      id: "input-electoral",
      title: "Inputs: Electoral",
      status: "stub",
      summary: "",
      flowchart: { inputs: [], outputs: [], dataSources: [] },
      details: [],
      rationale: [],
      limitations: [],
      seeAlso: [{ label: "Electoral Leverage", href: "#factor-electoral-leverage" }]
      /* TODO(prose): Vote margin + State decisiveness. */
    },
    {
      id: "input-alignment",
      title: "Inputs: Alignment",
      status: "stub",
      summary: "",
      flowchart: { inputs: [], outputs: [], dataSources: [] },
      details: [],
      rationale: [],
      limitations: [],
      seeAlso: [{ label: "Incumbent Alignment", href: "#factor-incumbent-alignment" }]
      /* TODO(prose): Key votes + Ideology score + Party ID. */
    },

    /* ═══════════════ SECTORAL LEVERAGE — MIGRATED (verbatim) ═══════════════ */
    {
      id: "factor-sectoral-leverage",
      title: "Sectoral Leverage",
      status: "migrated",
      summary: "Strategic leverage is the structural capacity of workers to disrupt the conditions that matter to their employer or to the broader political economy.",
      flowchart: {
        inputs: [
          { label: "County employment", href: "#input-sectoral" },
          { label: "Sector strategic score", href: "#input-sectoral" }
        ],
        outputs: [
          { label: "Federal lens", href: "#lens-federal" },
          { label: "State lens", href: "#lens-state" }
        ],
        dataSources: [
          { label: "Census County Business Patterns", href: "#m-data" },
          { label: "BLS QCEW", href: "#m-data" },
          { label: "Sector SVS rubric (repo)", href: "#m-data" }
        ]
      },
      details: [
        {
          variant: "Sector Strategic Value Score (SVS)",
          gloss: "Per-sector rubric: how much structural leverage a sector carries, max 80 points.",
          formula: "SVS = Capital Reach + Community Reach + Community-Facing Reach\n      + Non-Offshoreable + Dual-Crisis Bonus + Whole-Worker Bonus\nMaximum: 80 points",
          html: '<p>Four components plus two bonuses. Dual-Crisis bonus (+5) applies when Capital Reach &gt; 0 and Community Reach &gt; 0; the Whole-Worker bonus (+5) applies when Community Reach &gt; 0 and Community-Facing Reach &gt; 0.</p>'
              + '<div class="method-table-wrap"><table class="method-table">'
              + '<thead><tr><th>Variable</th><th>None</th><th>Local</th><th>State</th><th>National</th></tr></thead>'
              + '<tbody>'
              + '<tr><td>Capital Crisis-Creating Reach</td><td>0</td><td>10</td><td>15</td><td>25</td></tr>'
              + '<tr><td>Community Crisis-Creating Reach</td><td>0</td><td>10</td><td>15</td><td>25</td></tr>'
              + '<tr><td>Community-Facing Reach</td><td>0</td><td>5</td><td>10</td><td>15</td></tr>'
              + '<tr><td>Non-Offshoreable</td><td>0</td><td>3</td><td>—</td><td>5</td></tr>'
              + '<tr><td>Dual-Crisis Bonus</td><td>—</td><td>—</td><td>—</td><td>+5 if Cap&gt;0 &amp; Comm&gt;0</td></tr>'
              + '<tr><td>Whole-Worker Bonus</td><td>—</td><td>—</td><td>—</td><td>+5 if Comm&gt;0 &amp; Facing&gt;0</td></tr>'
              + '</tbody></table></div>'
              + '<p>Sector scoring was conducted by human researchers based on best judgment, case study review, and existing labor literature. All 42 sector codings are documented in the project repository and are subject to review and challenge; future work will add cross-coding by multiple independent experts.</p>'
              + '<div class="citation">Silver, B. (2003). Forces of Labor: Workers\' Movements and Globalization since 1870. Cambridge University Press.</div>'
        },
        {
          variant: "SLS-Capital",
          gloss: "Absolute crisis potential against capital flows — scale matters.",
          formula: "SLS-Capital = Σ(cap_reach_score[sector] × employment[sector]) / {{capital_divisor}}\n[Calibrated to LA County's raw sum (17,673,345) → score 84.2]",
          constants: [{ specKey: "capital_divisor", label: "Capital normalization divisor" }],
          html: '<p>Each sector\'s Capital Crisis Reach score is multiplied by the raw number of workers in that sector in that county, then summed. The 210,000 normalization benchmark places Los Angeles County (the national maximum) at 84.2 on a 0–100 scale. Counties with major port, logistics, or energy workforces score highest.</p>'
              + '<div class="citation-review">Womack, J. (2005). Working the Machine — technically strategic positions.</div>'
              + '<div class="citation">Silver, B. (2003). Forces of Labor. Cambridge University Press — workplace bargaining power and spatial fixes.</div>'
        },
        {
          variant: "SLS-Community",
          gloss: "Relative crisis potential within the community — share matters.",
          formula: "SLS-Community = Σ(comm_reach_score[sector] × (employment[sector] / total_employment)) × {{community_share_mult}}",
          constants: [{ specKey: "community_share_mult", label: "Share → 0–100 multiplier" }],
          html: '<p>Each sector\'s Community Crisis Reach score is multiplied by that sector\'s share of the county\'s total workforce, then summed. A hospital employing 40% of a rural county\'s workforce is structurally central in a way the same hospital cannot be at 2% of a large metro. The ×4 normalization scales to 0–100. Counties with concentrated healthcare, education, or public transit workforces score highest.</p>'
              + '<div class="citation">McAlevey, J. (2016). No Shortcuts. Oxford University Press — whole-worker organizing.</div>'
              + '<div class="citation-review">Fox-Hodess, K. (2023). On social contingency in dockworker organizing.</div>'
        }
      ],
      rationale: [
        "<strong>Why two scores rather than one.</strong> Collapsing these into a single number would obscure a distinction that matters strategically. A county can score high on SLS-Capital and low on SLS-Community — a logistics hub in a large metro — or the reverse, such as a rural county where the hospital is the dominant employer. Those are different types of terrain requiring different organizing approaches. The model keeps them separate so users can see both dimensions independently."
      ],
      limitations: [],
      seeAlso: [
        { label: "Inputs: Sectoral", href: "#input-sectoral" },
        { label: "The 2×2", href: "#output-2x2" },
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" }
      ]
    },

    /* ═══════ ELECTORAL LEVERAGE — POPULATED (locked template example) ═══════ */
    {
      id: "factor-electoral-leverage",
      title: "Electoral Leverage",
      status: "populated",
      summary: "Is this county's election close enough — and consequential enough — that organizing here could help move real political outcomes?",
      flowchart: {
        inputs: [
          { label: "Vote margin", href: "#input-vote-margin" },
          { label: "State decisiveness", href: "#input-state-decisiveness" },
          { label: "Seat margin (state)" },
          { label: "Chamber pivotality (state)" }
        ],
        outputs: [
          { label: "Federal lens", href: "#lens-federal" },
          { label: "State lens", href: "#lens-state" }
        ],
        dataSources: [
          { label: "County vote margins (2024)", href: "#m-data" },
          { label: "State tipping weights (2024)", href: "#m-data" },
          { label: "State-leg competitiveness", href: "#m-data" },
          { label: "Chamber seat counts", href: "#m-data" }
        ]
      },
      details: [
        {
          variant: "National variant",
          gloss: "Presidential decisiveness × closeness → p1_national.",
          inputs: "County <strong>Vote margin</strong> (2024); <strong>State decisiveness</strong> (presidential tipping weight, 0.28 PA max … {{default_tip}} floor).",
          cleaning: "Missing margin → 15.0 (non-competitive); abs_margin = max({{min_margin}}, |margin|).",
          formula: "raw         = state_tipping_weight × (1 / abs_margin)\nP1_national = min(100, raw × NORM)",
          constants: [
            { specKey: "NORM", label: "NORM" },
            { specKey: "min_margin", label: "min_margin" },
            { specKey: "default_tip", label: "default_tip" },
            { specKey: "p1_high", label: "Tier-1 capital pathway treats decisive at p1_national ≥" }
          ],
          outputField: "p1_national",
          notes: "The national capital pathway is gated on Electoral Leverage (p1_national ≥ {{p1_high}}), not on incumbent hostility — the logic is about decisive environments, not replacing a specific official."
        },
        {
          variant: "State variant",
          gloss: "Chamber pivotality × seat-margin competitiveness → p1_state.",
          inputs: "State-leg <strong>Seat margin</strong> (two-party); <strong>Chamber pivotality</strong> (chamber_flip_proximity).",
          cleaning: "Missing prox/margin → 0 floor (DC/DE); backfill rows replace base rows by county.",
          formula: "P1_state = 100 × chamber_pivotality × comp(seat_margin)\ncomp(m) = 1.0           for |m| ≤ plateau_edge\n        = linear fade  from plateau_edge to zero_edge\n        = 0            beyond zero_edge",
          constants: [
            { specKey: "plateau_edge", label: "plateau_edge" },
            { specKey: "zero_edge", label: "zero_edge" },
            { specKey: "p1_high_state", label: "p1_high_state" }
          ],
          outputField: "p1_state",
          notes: "Two-stage — the main build writes a provisional value; rebuild_state_lens overwrites it with the plateau formula above (the shipped one)."
        }
      ],
      rationale: [
        "<strong>Why decisiveness, not just closeness (national).</strong> A close race in a state with little bearing on the national balance tends to be less strategically valuable than one in a pivotal state; folding in decisiveness tends to compound the return. This is why the national capital pathway is gated on Electoral Leverage rather than incumbent hostility — the logic is about decisive environments, not replacing a specific official.",
        "<strong>Why a different state formula.</strong> State-leg math is local and distributed; the question is whether a specific seat is flippable, not whether the state tips a national outcome. National and state Electoral Leverage sit on DIFFERENT scales and are not directly comparable (national “high” = {{p1_high}}, state “high” = {{p1_high_state}})."
      ],
      limitations: [
        "Tipping weights are presidential (2024) — not midterm-specific (Senate/Gov/House); a 2026-cycle input would be a future enhancement.",
        "NORM is hardcoded (derived from PA's 2024 tipping); if that reference changed, the constant would need recomputing — it does not auto-update. (Emitting it to the spec is the first step toward fixing this.)",
        "Margins are a single-cycle snapshot (2024); state-leg margins carry mixed vintages (mostly 2022 districts; some 2021 gubernatorial, 2024 presidential backfill), flagged but not discounted."
      ],
      seeAlso: [
        { label: "Vote margin", href: "#input-vote-margin" },
        { label: "State decisiveness", href: "#input-state-decisiveness" },
        { label: "Federal lens", href: "#lens-federal" },
        { label: "State lens", href: "#lens-state" },
        { label: "Incumbent Alignment", href: "#factor-incumbent-alignment" }
      ]
    },

    /* ═══════════ INCUMBENT ALIGNMENT — MIGRATED (verbatim) ═══════════ */
    {
      id: "factor-incumbent-alignment",
      // "THIS VARIABLE" flow-box label (the static section heading stays "Incumbent Alignment").
      title: "Incumbent Alignment Score",
      status: "migrated",
      summary: "How aligned are current elected officials with labor's legislative agenda?",
      flowchart: {
        inputs: [
          { label: "Key votes", href: "#input-alignment" },
          { label: "Ideology score", href: "#input-alignment" },
          { label: "Party ID", href: "#input-alignment" }
        ],
        outputs: [
          { label: "Federal lens", href: "#lens-federal" },
          { label: "State lens", href: "#lens-state" }
        ],
        dataSources: [
          { label: "Congress.gov / House Clerk + Senate.gov XML", href: "#m-data" },
          { label: "GovTrack (ideology)", href: "#m-data" },
          { label: "DIME CFscores (state)", href: "#m-data" }
        ]
      },
      details: [
        {
          variant: "P2 — Incumbent Alignment",
          gloss: "How aligned are current elected officials with labor's legislative agenda?",
          formula: "P2 = key_vote_score × 0.60 + inverse_ideology_score × 0.40",
          constants: [
            { specKey: "p2_hostile_ceiling", label: "Hostile incumbent (Transform): P2 <" },
            { specKey: "p2_aligned_floor", label: "Aligned incumbent (Activate): P2 ≥" }
          ],
          html: '<p>The key-vote component (60%) scores each legislator on 4 federal key votes relevant to labor organizing rights; all roll-call numbers are verified against House Clerk XML and Senate.gov records. The ideology component (40%) uses legislative-behavior ideology scores from bill sponsorship and cosponsorship patterns (GovTrack, 119th Congress), normalized so progressive = high signal. County P2 aggregates legislator scores weighted by district-county overlap.</p>'
              + '<div class="method-table-wrap"><table class="method-table">'
              + '<thead><tr><th>Vote</th><th>Chamber / Roll Call</th><th>Date</th></tr></thead>'
              + '<tbody>'
              + '<tr><td>PRO Act</td><td>House Roll Call 70</td><td>March 9, 2021</td></tr>'
              + '<tr><td>Sanders $15 Minimum Wage Amendment</td><td>Senate Roll Call 74</td><td>March 5, 2021</td></tr>'
              + '<tr><td>Abruzzo NLRB General Counsel Confirmation</td><td>Senate Roll Call 273</td><td>July 21, 2021</td></tr>'
              + '<tr><td>National Apprenticeship Act</td><td>House Roll Call 31</td><td>February 5, 2021</td></tr>'
              + '</tbody></table></div>'
              + '<p>Coverage: Federal P2 — 533 legislators scored, 3,142 counties with alignment data. State P2 — in progress, using DIME CFscores (Stanford) for current state legislators where available. Low P2 + high SLS + high P1 identifies the highest-value organizing targets: leverage, decisive geography, and a hostile incumbent.</p>'
              + '<p><strong>Sources considered and rejected:</strong> AFL-CIO legislative scorecards (they encode the institutional AFL-CIO\'s strategic priorities) and labor PAC contributions as a positive signal (they reflect existing labor leadership targeting — the status quo this model complements and occasionally challenges).</p>'
              + '<div class="citation">Harvard Center for Labor and a Just Economy (2024). The Varied Voice of Labor. clje.law.harvard.edu</div>'
        }
      ],
      rationale: [],
      limitations: [],
      seeAlso: [
        { label: "Inputs: Alignment", href: "#input-alignment" },
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "The 2×2", href: "#output-2x2" }
      ]
    },

    /* ════════════════ LENSES — genuinely empty stubs ════════════════ */
    {
      id: "lens-federal",
      title: "Federal lens",
      status: "stub",
      summary: "",
      flowchart: { inputs: [], outputs: [], dataSources: [] },
      details: [],
      rationale: [],
      limitations: [],
      seeAlso: [
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "State lens", href: "#lens-state" }
      ]
      /* TODO(prose): federal electoral tipping weights + federal incumbent alignment. */
    },
    {
      id: "lens-state",
      title: "State lens",
      status: "stub",
      summary: "",
      flowchart: { inputs: [], outputs: [], dataSources: [] },
      details: [],
      rationale: [],
      limitations: [],
      seeAlso: [
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "Federal lens", href: "#lens-federal" }
      ]
      /* TODO(prose): state legislative chamber control + state incumbent alignment. */
    },

    /* ═══════════════ THE 2×2 — MIGRATED (verbatim) ═══════════════ */
    {
      id: "output-2x2",
      title: "The 2×2",
      status: "migrated",
      summary: "The model classifies every county into one of six categories based on the combination of SLS, P1, and P2.",
      flowchart: {
        // The 2×2's axes ARE electoral leverage (X) × labor/sectoral leverage (Y).
        inputs: [
          { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
          { label: "Labor-Sectoral leverage", href: "#factor-sectoral-leverage" }
        ],
        outputs: [
          { label: "6 Tier Distribution", href: "#output-tiers" },
          { label: "Scatter Plot Distribution", href: "#output-scatter" }
        ],
        dataSources: []
      },
      details: [
        {
          variant: "Six-tier classification",
          gloss: "How much leverage exists here, and what strategic posture the terrain requires.",
          constants: [
            { specKey: "sls_capital_high_boundary", label: "High SLS-Capital ≥" },
            { specKey: "sls_community_high_boundary", label: "High SLS-Community ≥" },
            { specKey: "p1_high", label: "High P1 ≥" }
          ],
          html: '<p>The classification answers two questions at once: how much organizing leverage exists here, and what strategic posture does the political terrain require?</p>'
              + '<div class="method-table-wrap"><table class="method-table">'
              + '<thead><tr><th>Tier</th><th>Condition</th><th>Strategic posture</th></tr></thead>'
              + '<tbody>'
              + '<tr><td>Tier 1 — Transform</td><td>High SLS + High P1 + Low P2 (hostile incumbent)</td><td>Highest priority. Build worker power and hold a misaligned incumbent accountable simultaneously. Split into Capital and Community.</td></tr>'
              + '<tr><td>Tier 2 — Activate</td><td>High SLS + High P1 + High P2 (aligned incumbent)</td><td>Mobilize and protect — turn out members, defend gains. Split into Capital and Community.</td></tr>'
              + '<tr><td>Tier 3 — Electoral Terrain</td><td>Low SLS + High P1</td><td>Decisive geography without an organizing base at scale. Long-term investment — build the worker organization that isn\'t there yet.</td></tr>'
              + '<tr><td>Tier 4 — Lower Priority</td><td>Neither SLS nor P1 threshold met</td><td>Not a current priority under finite resources. Every worker still deserves representation.</td></tr>'
              + '</tbody></table></div>'
        }
      ],
      rationale: [
        /* NOTE(migration): this callout hardcodes "SLS-Community ≥ 35" — STALE vs the
           live spec (sls_community_high_boundary = 25, recalibrated 35→25). Carried
           verbatim per migration rules; the "live from spec" line above shows the
           current value. To be corrected in the locked-template rewrite. */
        '<div class="method-callout"><p><strong>Critical finding: no county is Tier 1 in both dimensions.</strong> Across all 3,143 counties, none simultaneously cleared all three thresholds (SLS-Capital ≥ 2.5, SLS-Community ≥ 35, P1 ≥ 5). The largest labor markets sit in states that don\'t decide elections; the counties that do are smaller, with workforces dominated by community-facing sectors.</p>'
          + '<p>This is not a modeling failure — it is an empirical description of American political and economic geography, and it confirms McAlevey\'s sectoral argument independently: to organize where it matters electorally, organize hospitals and schools in Pennsylvania, Michigan, and Wisconsin — not ports and logistics hubs in California.</p></div>',
        "The scores are independent by design. The model does not combine them into a single ranking, because doing so would require imposing a weighting between structural leverage and political terrain — a decision that depends on the user's theory of change, not on the data. The model surfaces both dimensions and leaves that judgment where it belongs."
      ],
      limitations: [],
      seeAlso: [
        { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" },
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "Incumbent Alignment", href: "#factor-incumbent-alignment" },
        { label: "Tiers & the two pathways", href: "#output-tiers" }
      ]
    },

    /* ════════════════ OUTPUT — genuinely empty stubs ════════════════ */
    {
      id: "output-tiers",
      title: "Tiers & the two pathways",
      status: "stub",
      summary: "",
      flowchart: { inputs: [], outputs: [], dataSources: [] },
      details: [],
      rationale: [],
      limitations: [],
      seeAlso: [{ label: "The 2×2", href: "#output-2x2" }]
      /* TODO(dual-track narrative): Capital / Community tiers and how a county travels them. */
    },
    {
      id: "output-scatter",
      title: "Scatter",
      status: "stub",
      summary: "",
      flowchart: { inputs: [], outputs: [], dataSources: [] },
      details: [],
      rationale: [],
      limitations: [],
      seeAlso: [{ label: "The 2×2", href: "#output-2x2" }]
      /* TODO(scatter view): not built yet; flowchart quadrant clicks stay stubbed. */
    }
  ];

  /* ──────────────────────────────────────────────────────────────────────────
     SPEC RESOLUTION (Architecture C) — every constant resolves from model_spec.json
     ────────────────────────────────────────────────────────────────────────── */
  var MISSING = '<span class="spec-missing">[value missing from spec]</span>';

  function specDisplay(spec, key) {
    if (spec && spec.constants && spec.constants[key]) {
      var e = spec.constants[key];
      return e.display != null ? String(e.display) : String(e.value);
    }
    return null;
  }

  // Replace {{specKey}} tokens in a string with the spec's display value.
  function subst(str, spec) {
    if (str == null) return "";
    return String(str).replace(/\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g, function (_, key) {
      var d = specDisplay(spec, key);
      return d == null ? MISSING : d;
    });
  }

  /* ──────────────────────────────────────────────────────────────────────────
     RENDER — ONE function turns a section object into the locked-template body.
     ────────────────────────────────────────────────────────────────────────── */
  function linkOrLabel(item) {
    if (item == null) return "";
    if (typeof item === "string") return '<span class="method-chip">' + item + "</span>";
    if (item.href) return '<a class="method-chip method-chip--link" href="' + item.href + '">' + item.label + "</a>";
    return '<span class="method-chip">' + item.label + "</span>";
  }

  // INPUT / OUTPUT cards — large rectangular cards; live link when href present.
  function flowCard(item, cls) {
    if (item == null) return "";
    var label = (typeof item === "string") ? item : item.label;
    var href = (item && typeof item === "object") ? item.href : null;
    if (href) {
      return '<a class="mf2-card ' + cls + ' mf2-card--link" href="' + href + '">' + label + "</a>";
    }
    return '<div class="mf2-card ' + cls + '">' + label + "</div>";
  }

  // SOURCES row — pill-shaped mono chips; preserve the live href wiring.
  function sourceChip(item) {
    if (item == null) return "";
    var label = (typeof item === "string") ? item : item.label;
    var href = (item && typeof item === "object") ? item.href : null;
    if (href) {
      return '<a class="mf2-chip mf2-chip--link" href="' + href + '">' + label + "</a>";
    }
    return '<span class="mf2-chip">' + label + "</span>";
  }

  function renderFlow(sec) {
    var f = sec.flowchart || {};
    var inputs = f.inputs || [];
    var outputs = f.outputs || [];
    var sources = f.dataSources || [];
    if (!inputs.length && !outputs.length && !sources.length) {
      return '<div class="method-flow method-flow--empty"><span class="method-todo-tag">TODO — mini-flowchart</span></div>';
    }
    var inCards = inputs.length
      ? inputs.map(function (i) { return flowCard(i, "mf2-card--in"); }).join("")
      : '<div class="mf2-card mf2-card--in mf2-card--muted">—</div>';
    var outCards = outputs.length
      ? outputs.map(function (i) { return flowCard(i, "mf2-card--out"); }).join("")
      : '<div class="mf2-card mf2-card--out mf2-card--muted">—</div>';

    var html = '<div class="method-flow2" data-flow>'
      + '<div class="mf2-inner">'
      + '<div class="method-flow2-grid">'
      + '<svg class="mf2-connectors" aria-hidden="true" preserveAspectRatio="none"></svg>'
      + '<div class="mf2-col mf2-col--in"><span class="mf2-cap">Inputs</span><div class="mf2-cards">' + inCards + '</div></div>'
      + '<div class="mf2-col mf2-col--var"><span class="mf2-cap mf2-cap--var">This variable</span><div class="mf2-varwrap"><div class="mf2-box">' + sec.title + '</div></div></div>'
      + '<div class="mf2-col mf2-col--out"><span class="mf2-cap">Outputs</span><div class="mf2-cards">' + outCards + '</div></div>'
      + '</div>';
    if (sources.length) {
      html += '<div class="mf2-sources"><span class="mf2-cap mf2-cap--sources">Sources</span><div class="mf2-chips">'
        + sources.map(sourceChip).join("") + '</div></div>';
    }
    html += '</div></div>';
    return html;
  }

  /* ──────────────────────────────────────────────────────────────────────────
     ADAPTIVE ELBOW CONNECTORS — drawn dynamically from the rendered box
     positions, so the bracket/manifold look holds for ANY number of inputs and
     outputs. Recomputed on resize and after fonts load (positions shift).
     ────────────────────────────────────────────────────────────────────────── */

  // A two-corner elbow: horizontal from (x1,y1) to a vertical bus at busX, then
  // up/down to y2, then horizontal to (x2,y2). Corners rounded by radius r.
  function bracketPath(x1, y1, x2, y2, busX, r) {
    if (Math.abs(y2 - y1) < 0.75) {
      return "M" + x1 + " " + y1 + " H" + x2;
    }
    var dy = (y2 > y1) ? 1 : -1;
    var rr = Math.min(r, Math.abs(y2 - y1) / 2, Math.abs(busX - x1), Math.abs(x2 - busX));
    if (rr < 0.5) {
      return "M" + x1 + " " + y1 + " H" + busX + " V" + y2 + " H" + x2;
    }
    return "M" + x1 + " " + y1
      + " H" + (busX - rr)
      + " Q" + busX + " " + y1 + " " + busX + " " + (y1 + dy * rr)
      + " V" + (y2 - dy * rr)
      + " Q" + busX + " " + y2 + " " + (busX + rr) + " " + y2
      + " H" + x2;
  }

  function drawConnectors(flow) {
    var grid = flow.querySelector(".method-flow2-grid");
    var svg = flow.querySelector(".mf2-connectors");
    var box = flow.querySelector(".mf2-box");
    if (!grid || !svg || !box) return;
    // If the columns have collapsed to a single stack (narrow viewport), the SVG
    // is hidden by CSS; skip the draw entirely so nothing renders mis-routed.
    if (getComputedStyle(svg).display === "none") return;

    var ins = grid.querySelectorAll(".mf2-card--in");
    var outs = grid.querySelectorAll(".mf2-card--out");
    var gb = grid.getBoundingClientRect();
    if (!gb.width || !gb.height) return;

    function rel(el) {
      var r = el.getBoundingClientRect();
      return {
        l: r.left - gb.left, r: r.right - gb.left,
        cy: (r.top + r.bottom) / 2 - gb.top
      };
    }

    var W = gb.width, H = gb.height;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);

    var b = rel(box);
    var radius = 12;
    var paths = [];

    // INPUTS gather → a single bus, then one line into the box's left-center.
    var maxInR = 0;
    ins.forEach(function (el) { var x = rel(el).r; if (x > maxInR) maxInR = x; });
    if (ins.length) {
      var inBus = maxInR + (b.l - maxInR) * 0.45;
      ins.forEach(function (el) {
        var c = rel(el);
        paths.push(bracketPath(c.r, c.cy, b.l, b.cy, inBus, radius));
      });
    }

    // OUTPUTS fan ← from the box's right-center, one line out to each card.
    var minOutL = W;
    outs.forEach(function (el) { var x = rel(el).l; if (x < minOutL) minOutL = x; });
    if (outs.length) {
      var outBus = b.r + (minOutL - b.r) * 0.55;
      outs.forEach(function (el) {
        var c = rel(el);
        paths.push(bracketPath(b.r, b.cy, c.l, c.cy, outBus, radius));
      });
    }

    var defs = '<defs><marker id="mf2-arrow" markerWidth="7" markerHeight="7" '
      + 'refX="5.6" refY="3" orient="auto" markerUnits="userSpaceOnUse">'
      + '<path d="M0,0 L6,3 L0,6 Z" fill="#26251f"></path></marker></defs>';
    svg.innerHTML = defs + paths.map(function (d) {
      return '<path d="' + d + '" marker-end="url(#mf2-arrow)"></path>';
    }).join("");
  }

  var _drawScheduled = false;
  function drawAllConnectors() {
    var flows = document.querySelectorAll(".method-flow2");
    for (var i = 0; i < flows.length; i++) drawConnectors(flows[i]);
  }
  function scheduleConnectorDraw() {
    if (_drawScheduled) return;
    _drawScheduled = true;
    requestAnimationFrame(function () {
      _drawScheduled = false;
      drawAllConnectors();
    });
  }

  function renderConstants(constants, spec) {
    if (!constants || !constants.length) return "";
    var items = constants.map(function (c) {
      var d = specDisplay(spec, c.specKey);
      var val = d == null ? MISSING : '<span class="spec-val">' + d + "</span>";
      var meta = (spec && spec.constants && spec.constants[c.specKey]) ? spec.constants[c.specKey] : null;
      var title = meta ? (meta.short_label + " — " + meta.source_file + (meta.source_line ? ":" + meta.source_line : (meta.config_key ? " · " + meta.config_key : ""))) : "";
      // If the label already ends in a comparison operator, don't add "=".
      var joiner = /[≥≤<>]\s*$/.test(c.label) ? " " : " = ";
      return '<span class="spec-item" title="' + (title || "").replace(/"/g, "&quot;") + '">' + c.label + joiner + val + "</span>";
    }).join('<span class="spec-sep">·</span>');
    return '<div class="method-constants"><span class="method-constants-cap">Constants — live from spec</span>' + items + "</div>";
  }

  function renderDetailVariant(d, spec) {
    var body = "";
    if (d.inputs) body += '<p><strong>Inputs.</strong> ' + subst(d.inputs, spec) + "</p>";
    if (d.cleaning) body += '<p><strong>Cleaning.</strong> ' + subst(d.cleaning, spec) + "</p>";
    if (d.formula) body += '<div class="formula-card-expr">' + subst(d.formula, spec) + "</div>";
    body += renderConstants(d.constants, spec);
    if (d.outputField) body += '<p><strong>Output field.</strong> <code>' + d.outputField + "</code></p>";
    if (d.notes) body += "<p>" + subst(d.notes, spec) + "</p>";
    if (d.html) body += subst(d.html, spec);
    var gloss = d.gloss ? '<span class="formula-card-gloss">' + d.gloss + "</span>" : "";
    return '<details class="formula-card">'
      + '<summary><span class="formula-card-name">' + d.variant + "</span>" + gloss + "</summary>"
      + '<div class="formula-card-detail">' + body + "</div></details>";
  }

  function renderDetails(sec, spec) {
    if (!sec.details || !sec.details.length) {
      if (sec.status === "stub") {
        return '<div class="method-todo"><span class="method-todo-tag">TODO — details</span><p>Formula / cleaning / constants to be written in the narrative pass.</p></div>';
      }
      return "";
    }
    return '<div class="method-details">' + sec.details.map(function (d) { return renderDetailVariant(d, spec); }).join("") + "</div>";
  }

  function renderRatLim(sec, spec) {
    var hasR = sec.rationale && sec.rationale.length;
    var hasL = sec.limitations && sec.limitations.length;
    if (!hasR && !hasL) {
      if (sec.status === "stub") {
        return '<div class="method-todo"><span class="method-todo-tag">TODO — rationale & limitations</span><p>To be written in the narrative pass.</p></div>';
      }
      return "";
    }
    var inner = "";
    if (hasR) inner += sec.rationale.map(function (p) { return '<div class="method-rationale-p">' + subst(p, spec) + "</div>"; }).join("");
    if (hasL) {
      inner += '<p class="method-prose-h">Limitations</p><ul class="method-limitations">'
        + sec.limitations.map(function (b) { return "<li>" + subst(b, spec) + "</li>"; }).join("") + "</ul>";
    }
    return '<details class="formula-card method-ratlim"><summary><span class="formula-card-name">Rationale &amp; Limitations</span></summary>'
      + '<div class="formula-card-detail">' + inner + "</div></details>";
  }

  function renderSeeAlso(sec) {
    if (!sec.seeAlso || !sec.seeAlso.length) return "";
    var links = sec.seeAlso.map(function (s) { return '<a href="' + s.href + '">' + s.label + "</a>"; }).join('<span class="method-seealso-sep">·</span>');
    return '<div class="method-seealso"><span class="method-seealso-cap">See also</span>' + links + "</div>";
  }

  function statusBanner(sec) {
    if (sec.status === "migrated") {
      return '<div class="method-status method-status--migrated">Migrated — existing content re-homed into the data structure, <strong>not yet rewritten</strong> to the locked template/voice.</div>';
    }
    if (sec.status === "stub") {
      return '<div class="method-status method-status--stub">Stub — structure only. Prose to be written in the narrative pass.</div>';
    }
    return "";
  }

  // THE one render function.
  function renderMethodologySection(sec, spec) {
    var parts = [];
    parts.push(statusBanner(sec));
    if (sec.summary) parts.push('<p class="method-summary">' + sec.summary + "</p>");
    else if (sec.status === "stub") parts.push('<div class="method-todo"><span class="method-todo-tag">TODO — summary</span><p>One-sentence question this variable answers.</p></div>');
    parts.push(renderFlow(sec));
    parts.push(renderDetails(sec, spec));
    parts.push(renderRatLim(sec, spec));
    parts.push(renderSeeAlso(sec));
    return parts.join("\n");
  }

  /* ──────────────────────────────────────────────────────────────────────────
     STYLES — injected once (keeps the whole system in this one editable file).
     ────────────────────────────────────────────────────────────────────────── */
  function injectStyles() {
    if (document.getElementById("method-content-styles")) return;
    var css = ''
      + '.method-render { margin-top: var(--space-3, 12px); }'
      + '.method-status { font-family: var(--font-mono, monospace); font-size: 12px; line-height: 1.5; padding: 8px 12px; border-radius: 6px; margin: 0 0 16px; }'
      + '.method-status--migrated { background: rgba(189,0,38,0.06); border: 1px solid rgba(189,0,38,0.25); color: var(--color-text-secondary, #555); }'
      + '.method-status--stub { background: rgba(0,0,0,0.03); border: 1px dashed rgba(0,0,0,0.2); color: var(--color-text-muted, #777); }'
      + '.method-summary { font-family: var(--font-serif, Georgia, serif); font-size: 1.15rem; line-height: 1.5; color: var(--color-text, #1a1a1a); margin: 0 0 18px; }'
      /* ── empty-state placeholder (stub sections) ── */
      + '.method-flow--empty { border: 1px dashed var(--color-border, #C8C3B8); border-radius: 12px; padding: 14px 16px; margin: 0 0 20px; background: var(--color-bg-card, #EFEFEA); }'
      /* ── mini-flowchart: redesigned manifold (one template → every section) ── */
      + '.method-flow2 { margin: 0 0 22px; background: var(--color-bg, #F7F5F0); border: 1px solid var(--color-rule, #C8C3B8); border-radius: 16px; padding: 9px; }'
      + '.mf2-inner { position: relative; background: var(--color-bg-subtle, #EDEAE3); border: 1px solid var(--color-rule, #C8C3B8); border-radius: 12px; padding: 24px 30px; }'
      + '.method-flow2-grid { position: relative; display: grid; grid-template-columns: 1fr auto 1fr; gap: 40px; align-items: stretch; }'
      + '.mf2-connectors { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; z-index: 2; }'
      + '.mf2-connectors path { fill: none; stroke: #26251f; stroke-width: 1.4; stroke-linejoin: round; stroke-linecap: round; }'
      + '.mf2-col { display: flex; flex-direction: column; min-width: 0; }'
      + '.mf2-cap { display: block; text-align: center; font-family: var(--font-mono, monospace); font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--color-text-muted, #5C6B7A); padding-bottom: 9px; margin-bottom: 20px; border-bottom: 1px solid var(--color-rule, #C8C3B8); }'
      + '.mf2-cap--var { color: var(--color-accent, #BD0026); }'
      + '.mf2-cards { flex: 1 1 auto; display: flex; flex-direction: column; justify-content: center; gap: 18px; }'
      + '.mf2-card { position: relative; z-index: 1; display: block; background: #FBFAF6; border: 1px solid var(--color-rule, #C8C3B8); border-radius: 11px; padding: 15px 20px; font-family: var(--font-serif, Georgia, serif); font-size: 15px; line-height: 1.3; color: var(--color-text, #1A1A18); }'
      + '.mf2-card--link { text-decoration: none; transition: border-color .15s ease, box-shadow .15s ease; }'
      + '.mf2-card--link:hover { border-color: var(--color-accent, #BD0026); box-shadow: 0 1px 0 rgba(189,0,38,0.12); }'
      + '.mf2-card--link:focus-visible { outline: 2px solid var(--color-accent, #BD0026); outline-offset: 2px; }'
      + '.mf2-card--muted { color: var(--color-text-muted, #5C6B7A); font-style: italic; }'
      + '.mf2-varwrap { flex: 1 1 auto; display: flex; align-items: center; justify-content: center; }'
      + '.mf2-box { position: relative; z-index: 1; background: var(--color-ink, #1A1A18); color: #fff; font-family: var(--font-display, Georgia, serif); font-size: 21px; line-height: 1.15; letter-spacing: 0.01em; padding: 24px 32px; border-radius: 13px; text-align: center; white-space: nowrap; }'
      + '.mf2-sources { display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px 14px; margin: 20px -30px 0; padding: 17px 30px 0; border-top: 1px dashed var(--color-rule, #C8C3B8); }'
      + '.mf2-cap--sources { text-align: left; border: none; padding: 0; margin: 0; flex: 0 0 auto; }'
      + '.mf2-chips { display: flex; flex-wrap: wrap; gap: 8px; }'
      + '.mf2-chip { display: inline-block; font-family: var(--font-mono, monospace); font-size: 11.5px; line-height: 1.4; padding: 5px 13px; border-radius: 999px; border: 1px solid var(--color-rule, #C8C3B8); background: var(--color-bg, #F7F5F0); color: var(--color-text-secondary, #3D3D3A); text-decoration: none; }'
      + '.mf2-chip--link { transition: border-color .15s ease, color .15s ease; }'
      + '.mf2-chip--link:hover { border-color: var(--color-accent, #BD0026); color: var(--color-accent, #BD0026); }'
      + '.mf2-chip--link:focus-visible { outline: 2px solid var(--color-accent, #BD0026); outline-offset: 2px; }'
      + '@media (max-width: 680px) {'
      +   '.method-flow2-grid { grid-template-columns: 1fr; gap: 12px; }'
      +   '.mf2-connectors { display: none; }'
      +   '.mf2-cap { text-align: left; margin-bottom: 12px; }'
      +   '.mf2-varwrap { justify-content: stretch; }'
      +   '.mf2-box { white-space: normal; width: 100%; padding: 18px 22px; font-size: 19px; }'
      +   '.mf2-col + .mf2-col::before { content: "\\2193"; display: block; text-align: center; color: var(--color-text-muted, #5C6B7A); font-family: var(--font-mono, monospace); font-size: 16px; margin: 0 0 8px; }'
      + '}'
      + '.method-constants-cap, .method-seealso-cap { display: block; font-family: var(--font-mono, monospace); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--color-text-muted, #888); margin-bottom: 6px; }'
      + '.method-constants { font-family: var(--font-mono, monospace); font-size: 12px; line-height: 1.7; margin: 10px 0 4px; padding: 8px 10px; background: rgba(0,0,0,0.02); border-left: 2px solid var(--color-accent, #BD0026); overflow-wrap: anywhere; }'
      + '.method-constants-cap { margin-bottom: 4px; }'
      + '.spec-val { font-weight: 700; color: var(--color-accent, #BD0026); white-space: nowrap; }'
      + '.spec-item { }'
      + '.spec-sep, .method-seealso-sep { color: var(--color-text-muted, #bbb); margin: 0 7px; }'
      + '.spec-missing { color: #fff; background: #BD0026; padding: 1px 5px; border-radius: 3px; font-weight: 700; }'
      + '.method-details { margin-bottom: 12px; }'
      + '.method-rationale-p { margin: 0 0 12px; line-height: 1.6; }'
      + '.method-rationale-p:last-child { margin-bottom: 0; }'
      + '.method-limitations { margin: 6px 0 0; padding-left: 20px; line-height: 1.6; }'
      + '.method-limitations li { margin-bottom: 8px; }'
      + '.method-seealso { margin-top: 8px; font-size: 13px; }'
      + '.method-seealso a { color: var(--color-accent, #BD0026); text-decoration: none; }'
      + '.method-seealso a:hover { text-decoration: underline; }';
    var style = document.createElement("style");
    style.id = "method-content-styles";
    style.textContent = css;
    document.head.appendChild(style);
  }

  /* ──────────────────────────────────────────────────────────────────────────
     INIT — fetch the spec, render every section into its placeholder.
     Placeholders are <div class="method-render" data-section="ID"> inside each
     static .method-sub shell (which keeps its id, anchors, number and heading so
     scroll-spy + flowchart box-links keep resolving regardless of render timing).
     ────────────────────────────────────────────────────────────────────────── */
  // Try a few paths so it works whether the doc root is the repo root or output/.
  var SPEC_PATHS = ["../model_spec.json", "model_spec.json", "/model_spec.json"];

  function fetchSpec() {
    var i = 0;
    function tryNext() {
      if (i >= SPEC_PATHS.length) return Promise.resolve(null);
      var p = SPEC_PATHS[i++];
      return fetch(p).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).catch(function () { return tryNext(); });
    }
    return tryNext();
  }

  function renderAll(spec) {
    injectStyles();
    if (!spec) {
      console.warn("[methodology] model_spec.json not loaded — constants will show as missing.");
    }
    METHODOLOGY_SECTIONS.forEach(function (sec) {
      var host = document.querySelector('.method-render[data-section="' + sec.id + '"]');
      if (!host) {
        console.warn("[methodology] no placeholder for section:", sec.id);
        return;
      }
      host.innerHTML = renderMethodologySection(sec, spec);
    });
    // Draw the adaptive elbow connectors now that the boxes are laid out, and
    // redraw on resize / once webfonts settle (both shift box positions).
    scheduleConnectorDraw();
    window.addEventListener("resize", scheduleConnectorDraw);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(scheduleConnectorDraw);
    }
    // Nudge the scroll-spy to recompute offsets now that bodies are in place.
    window.dispatchEvent(new Event("resize"));
  }

  function boot() {
    fetchSpec().then(renderAll);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  // Expose for debugging / future inline use.
  window.TerrainMethodology = {
    sections: METHODOLOGY_SECTIONS,
    render: renderMethodologySection
  };
})();
