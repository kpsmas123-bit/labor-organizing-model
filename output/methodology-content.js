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
      status: "populated",
      summary: "What raw materials does Sectoral Leverage run on — who works where, and how strategically important is each industry?",
      flowchart: {
        inputs: [
          { label: "County employment" },
          { label: "Sector strategic score" }
        ],
        outputs: [
          { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" }
        ],
        dataSources: [
          { label: "Census County Business Patterns (CBP, 2023)", href: "#m-data" },
          { label: "BLS QCEW (public-sector supplement)", href: "#m-data" },
          { label: "Sector SVS rubric (repo; NAICS-coded)", href: "#m-data" }
        ]
      },
      details: [
        {
          variant: "County employment",
          gloss: "How many people work in each industry in this county?",
          inputs: "Per-county → per-sector employment, ~3,143 counties.",
          cleaning: "Used as raw counts at score time; sectors not present in the SVS rubric are skipped; counties with zero total employment are guarded to 0 in the community calculation.",
          outputField: "not emitted directly; feeds SLS-Capital and SLS-Community",
          notes: "Source: Census County Business Patterns (private sector); BLS QCEW supplements public-sector employment that CBP under-counts. Employment is the rawest available proxy for where workers — and therefore potential organized power — actually are."
        },
        {
          variant: "Sector strategic score (the composite SVS rubric)",
          gloss: "How strategically important is each industry — its composite Sector Strategic Value (SVS)?",
          inputs: "Each sector carries four expert-assigned ratings: a capital-reach and a community-reach ordinal (none / local / state / national), a community-facing ordinal (none / local / state / national), and a non-offshorability level (none / partial / full).",
          formula: "composite_svs = capital_reach + community_reach + community_facing + non_offshorability\n              + dual_crisis_bonus + whole_worker_bonus\nThe FULL composite SVS (range ~10–60) is the per-sector weight in Sectoral Leverage.",
          outputField: "sector-level composite SVS; feeds BOTH SLS dimensions and the “top strategic sectors” tooltip",
          notes: "Not all employment is equal leverage: a sector whose disruption ripples nationally, that faces the community directly, and that can't be offshored carries more strategic weight than one whose effects stay local. The composite SVS captures all of that, and now feeds the live model in full as the per-sector weight in Sectoral Leverage — not just the two reach ordinals."
        }
      ],
      rationale: [
        "<strong>Employment as the base layer.</strong> Everything in Sectoral Leverage is built on who works where; employment is the rawest available proxy for where organized power could form. The composite SVS then weights that raw employment by how strategically important the sector is — how far its disruption travels, whether it faces the community, and how hard it is to offshore — turning a headcount into a measure of leverage."
      ],
      limitations: [
        "<strong>CBP under-counts some employment</strong> (notably public sector), which is why QCEW supplements it; coverage is good but not complete.",
        "<strong>Vintage.</strong> Employment is a recent annual snapshot, not real-time; sectors shift between releases.",
        "<strong>Counts, not readiness.</strong> Employment size is not the same as organizing readiness — it measures presence, not density or willingness.",
        "<strong>The rubric is expert judgment, not measurement.</strong> Every SVS component — the reach ordinals, the community-facing ordinal, the non-offshorability level, and the two bonuses — is assigned from case-study review and labor literature, not derived from observed disruption data; the ordinal scales are coarse by design."
      ],
      seeAlso: [
        { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" },
        { label: "The 2×2", href: "#output-2x2" }
      ]
    },
    {
      id: "input-electoral",
      title: "Inputs: Electoral",
      status: "populated",
      summary: "What raw materials does Electoral Leverage run on — how close was the county's last election, and how much does its state matter to the national outcome?",
      flowchart: {
        inputs: [
          { label: "Vote margin" },
          { label: "State decisiveness" }
        ],
        outputs: [
          { label: "Electoral Leverage", href: "#factor-electoral-leverage" }
        ],
        dataSources: [
          { label: "MIT Election Data & Science Lab (2024 presidential)", href: "#m-data" },
          { label: "538 tipping-point weights (2024 cycle)", href: "#m-data" }
        ]
      },
      details: [
        {
          variant: "Vote margin",
          gloss: "How close was this county's last presidential election?",
          inputs: "County 2024 presidential two-party margin, in percentage points. Positive = Democratic win, negative = Republican.",
          cleaning: "A missing margin is treated as non-competitive (defaults to 15.0 points) in the national Electoral Leverage calculation; the absolute margin is floored at {{min_margin}} points so a near-zero margin can't blow up 1/|margin|.",
          constants: [{ specKey: "min_margin", label: "|margin| floor (pp)" }],
          outputField: "margin_2024",
          notes: "Closeness is the starting point for electoral leverage — a place decided by a hair is where organized turnout can matter most."
        },
        {
          variant: "State decisiveness",
          gloss: "How much does this county's STATE matter to the national outcome?",
          inputs: "Per-state presidential tipping weight — the swing battlegrounds high, safe states near a floor. Ranges from a high of ~0.28 (the most pivotal state) down to a default floor of {{default_tip}} for safely-decided states.",
          constants: [{ specKey: "default_tip", label: "Safe-state tipping floor" }],
          outputField: "state_tipping_weight",
          notes: "A close race in a state that won't decide the national outcome is less strategically valuable than a close race in one that will; decisiveness is how the model expresses that. This weight also serves as the swing/lean gate in the Community Tier-1 pathway (see Federal lens)."
        }
      ],
      rationale: [
        "<strong>Closeness × decisiveness.</strong> The two electoral inputs answer different questions — how contested is this county, and how much does its state matter — and Electoral Leverage compounds them. Either alone is misleading: a nail-biter in a locked state, or a pivotal state that isn't actually close."
      ],
      limitations: [
        "<strong>Single cycle (2024).</strong> Both inputs are a 2024 presidential snapshot, not a trend; the presidential margin stands in for general competitiveness, and down-ballot or midterm dynamics can differ.",
        "<strong>Presidential tipping weights reflect the presidential map</strong>, not Senate / governor / House-specific competitiveness; a cycle-specific (e.g. 2026) electoral input would be a future enhancement.",
        "<strong>The national normalization constant (NORM) is hardcoded</strong>, derived from the most-pivotal state's 2024 tipping weight; if that reference shifts it would need recomputing — it does not auto-update. (Emitting it to the spec is the first step toward fixing this.)"
      ],
      seeAlso: [
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "Federal lens", href: "#lens-federal" }
      ]
    },
    {
      id: "input-alignment",
      title: "Inputs: Alignment",
      status: "populated",
      summary: "What raw materials does Incumbent Alignment run on — how legislators actually voted, where they sit ideologically, and (at the state level) the partisan makeup of the seats?",
      flowchart: {
        inputs: [
          { label: "Key votes" },
          { label: "Ideology score" },
          { label: "Party ID" }
        ],
        outputs: [
          { label: "Incumbent Alignment", href: "#factor-incumbent-alignment" }
        ],
        dataSources: [
          { label: "Congress.gov / House Clerk + Senate.gov XML", href: "#m-data" },
          { label: "GovTrack ideology (119th Congress)", href: "#m-data" },
          { label: "DIME CFscores", href: "#m-data" },
          { label: "Open States (state-leg rosters)", href: "#m-data" }
        ]
      },
      details: [
        {
          variant: "Key votes (federal)",
          gloss: "How did this county's federal legislators vote on the labor bills that matter?",
          inputs: "A defined set of federal labor votes (e.g. the PRO Act, the federal minimum-wage increase).",
          formula: "key_vote_score = per-legislator pro-labor share over the defined votes, ∈ [0,1]\nEnters federal P2 weighted 0.60.",
          outputField: "indirect, via p2_national",
          notes: "How a legislator actually voted on labor's priorities is the most direct evidence of where they stand — more direct than party or general ideology."
        },
        {
          variant: "Ideology score (federal)",
          gloss: "Where do this county's federal legislators sit on a general pro/anti-labor axis?",
          inputs: "Legislator ideology from sponsorship patterns (GovTrack, 119th Congress) and campaign-finance-derived ideal points (DIME CFscores).",
          formula: "inverse_ideology = 1 − ideology   (higher = more pro-labor)\nEnters federal P2 weighted 0.40.",
          outputField: "indirect, via p2_national",
          notes: "Where key votes are thin, a broader ideology measure fills in a legislator's general posture."
        },
        {
          variant: "Party ID (state)",
          gloss: "What is the partisan makeup of this county's state-legislative seats?",
          inputs: "Per-county list of state-leg seats with current party (D/R/I) and share (Open States rosters).",
          formula: "p2_state = Σ share[Democratic] / Σ share[D, R, I]\nIndependents count in the denominator but not the Democratic numerator.\nFallbacks: state-uniform Democratic share, then 0.5.",
          outputField: "p2_state (0–1), with a coverage flag (party_proxy / state_uniform / unavailable)",
          notes: "At the state level, seat-by-seat labor voting records aren't uniformly available, so party composition serves as the available proxy for alignment. This is the SOLE input to state Incumbent Alignment."
        }
      ],
      rationale: [
        "<strong>Record first, posture second.</strong> Federal alignment leads with how legislators actually voted (key votes, 60%) and fills the gaps with general ideology (40%) — behavior over label. The state level has no comparable national vote record, so it falls back to party composition as the best available signal."
      ],
      limitations: [
        "<strong>About half the federal roster has no non-zero key-vote score.</strong> For those legislators alignment falls back entirely to ideology — the key-votes signal is silently absent for roughly half of members. A handful of bills is also a thin, time-bound sample of a legislator's labor posture.",
        "<strong>The 0.40 weight is on inverse-IDEOLOGY, not on “inverse business funding”</strong> as an earlier design intended. The OpenSecrets / FollowTheMoney contribution-ratio sources from that earlier design are unused and have been removed; ideology is a general posture, not a labor-specific record.",
        "<strong>State alignment is PURE party ID</strong> — no key votes, no finance. It is a party proxy, not a record-based alignment, despite the shared “alignment” name; party label is a coarse instrument for predicting how a legislator acts on labor specifically."
      ],
      seeAlso: [
        { label: "Incumbent Alignment", href: "#factor-incumbent-alignment" },
        { label: "Federal lens", href: "#lens-federal" },
        { label: "State lens", href: "#lens-state" }
      ]
    },

    /* ═══════════════ SECTORAL LEVERAGE — POPULATED (Draft 2) ═══════════════ */
    {
      id: "factor-sectoral-leverage",
      title: "Sectoral Leverage",
      status: "populated",
      summary: "How much structural power do this county's workers have — both the raw weight of its strategic industries and how concentrated those industries are in the local economy?",
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
          { label: "Census County Business Patterns (CBP)", href: "#m-data" },
          { label: "BLS QCEW (public sector)", href: "#m-data" },
          { label: "Sector SVS rubric (repo)", href: "#m-data" }
        ]
      },
      details: [
        {
          variant: "SLS-Capital — magnitude",
          gloss: "The sheer weight of strategically important employment in the county.",
          inputs: "Per-sector county employment counts; each sector's composite Sector Strategic Value (SVS) weight (~10–60, from the rubric below).",
          cleaning: "Sectors absent from the rubric are skipped; no per-county normalization beyond the divisor.",
          formula: "raw         = Σ_sector ( composite_svs × sector_employment )\nSLS-Capital = min(100, raw / {{capital_divisor}})",
          constants: [
            { specKey: "capital_divisor", label: "Capital normalization divisor" },
            { specKey: "sls_capital_high_boundary", label: "Capital “high” boundary ≥" }
          ],
          outputField: "sls_capital",
          notes: "Each sector is weighted by its FULL composite SVS — not just capital reach — so a non-offshorable, community-facing sector carries its full strategic weight into the magnitude score too. The divisor is calibrated so the largest-employment county (Los Angeles) lands near the top of the 0–100 scale; observed range is roughly 0–84. Counties with major port, logistics, or energy workforces score highest.",
          html: '<div class="citation">Silver, B. (2003). Forces of Labor. Cambridge University Press — workplace bargaining power and spatial fixes.</div>'
        },
        {
          variant: "SLS-Community — concentration",
          gloss: "How much of the local economy those strategic sectors make up.",
          inputs: "Per-sector employment as a SHARE of the county's total employment; the SAME composite SVS weight as Capital; a confidence ramp on small counties.",
          cleaning: "Counties with zero total employment → 0. The confidence ramp suppresses noise in tiny labor markets (below).",
          formula: "weighted      = Σ_sector ( composite_svs × (sector_employment / total_employment) )\nshare_score   = min(100, weighted × {{community_share_mult}})\nSLS-Community = min(100, share_score × confidence_ramp)\n\nconfidence_ramp = 1.0   if total_employment ≥ {{ramp_full_at}}\n                = 0.0   if total_employment ≤ {{ramp_zero_at}}\n                = (emp − {{ramp_zero_at}}) / ({{ramp_full_at}} − {{ramp_zero_at}})   in between",
          constants: [
            { specKey: "community_share_mult", label: "Share → 0–100 multiplier (×)" },
            { specKey: "ramp_full_at", label: "Ramp full weight at ≥" },
            { specKey: "ramp_zero_at", label: "Ramp zero weight at ≤" },
            { specKey: "sls_community_high_boundary", label: "Community “high” boundary ≥" }
          ],
          outputField: "sls_community",
          notes: "The per-sector weight is the SAME composite SVS as Capital — only gross-vs-share differs. Observed range is roughly 0–57. A hospital employing 40% of a rural county's workforce is structurally central in a way the same hospital cannot be at 2% of a large metro — concentration, not size, drives this score. Counties with concentrated healthcare, education, or public transit workforces score highest.",
          html: '<div class="citation">McAlevey, J. (2016). No Shortcuts. Oxford University Press — whole-worker organizing.</div>'
        },
        {
          variant: "The composite SVS — shared per-sector weight",
          gloss: "One strategic-value score per sector, used as the weight in BOTH SLS dimensions.",
          html: '<p>Both SLS dimensions weight each sector by its <strong>composite Sector Strategic Value (SVS)</strong> — a single per-sector score (range ~10–60) the model feeds in <strong>full</strong>. The Capital/Community split comes entirely from how that weight is applied (gross employment vs employment share), <strong>not</strong> from giving the two dimensions different per-sector weights.</p>'
              + '<div class="formula-card-expr">composite_svs = capital_reach + community_reach + community_facing + non_offshorability\n              + dual_crisis_bonus + whole_worker_bonus</div>'
              + '<div class="method-table-wrap"><table class="method-table">'
              + '<thead><tr><th>Component</th><th>Levels → points</th></tr></thead>'
              + '<tbody>'
              + '<tr><td>Capital reach</td><td>none 0 · local 10 · state 15 · national 25</td></tr>'
              + '<tr><td>Community reach</td><td>none 0 · local 10 · state 15 · national 25</td></tr>'
              + '<tr><td>Community-facing reach</td><td>none 0 · local 5 · state 10 · national 15</td></tr>'
              + '<tr><td>Non-offshorability</td><td>none 0 · partial 3 · full 5</td></tr>'
              + '<tr><td>Dual-crisis bonus</td><td>+5 if both capital- and community-reach are non-zero</td></tr>'
              + '<tr><td>Whole-worker bonus</td><td>+5 if community-reach and community-facing are both non-zero</td></tr>'
              + '</tbody></table></div>'
        }
      ],
      rationale: [
        "<strong>Why two scores, not one.</strong> Worker power has two faces. A sector can matter because it is huge — disrupting it disrupts a lot (capital leverage) — or because it dominates a particular place, anchoring the local economy and the community around it (community leverage). A national logistics hub and a single-industry rural county express power differently; collapsing them into one number would hide the difference that matters for strategy. Capital rewards size; Community rewards concentration.",
        "<strong>Why the composite SVS is the weight (not bare reach).</strong> Both scores weight each sector by its <em>full</em> composite Sector Strategic Value — capital and community reach, plus community-facing reach, non-offshorability, and the dual-crisis and whole-worker bonuses — rather than by a single reach ordinal. So a sector that is hard to offshore or sits at the worker–community boundary carries that strategic weight into <em>both</em> dimensions. The magnitude-vs-concentration distinction is then carried entirely by gross employment vs employment share — not by tilting the per-sector weight differently for Capital and Community.",
        "<strong>Why the different scales.</strong> Because the two measure different things, their “high” thresholds are not comparable. A capital score clears “high” at a low absolute number ({{sls_capital_high_boundary}}) because it is a raw employment-weighted magnitude that only the largest labor markets push high; a community score needs much more ({{sls_community_high_boundary}}) because it is a 0–100 share index where many counties post moderate concentration. Reading them on one scale would make a high-magnitude metro look incomparably more “leveraged” than a county its strategic sector utterly dominates — which is exactly the false equivalence the two scores exist to avoid.",
        "<strong>Why the confidence ramp (Community only).</strong> Employment SHARE is volatile in small counties — a handful of workers can swing the percentage wildly. The ramp discounts community scores in very small labor markets so that concentration signals come from places where the share is meaningful: a county fades in fully above ~{{ramp_full_at}} covered workers and to zero below ~{{ramp_zero_at}}. Capital, being an absolute count, has no such noise problem and gets no ramp."
      ],
      limitations: [
        "<strong>SVS is a composite of expert-assigned ratings, not measured disruption.</strong> The per-sector weight sums ordinal ratings — capital and community reach, community-facing reach, non-offshorability — plus two fixed bonuses, all assigned from case-study review and labor literature rather than derived from observed disruption data. The four-level reach scale is coarse by design.",
        "<strong>Capital and Community are not directly comparable.</strong> Despite the shared “leverage” name, one is an absolute employment-weighted magnitude and the other a 0–100 share index; a county's two SLS numbers should be read as two different questions, not two points on one scale (their “high” gates, {{sls_capital_high_boundary}} vs {{sls_community_high_boundary}}, are not comparable).",
        "<strong>Community share is volatile in small labor markets.</strong> Employment share swings wildly where a county has few covered workers, so SLS-Community is gated by the confidence ramp — a noise discount, not a correction; concentration just below the full-weight threshold is still softened."
      ],
      seeAlso: [
        { label: "County employment", href: "#input-sectoral" },
        { label: "Sector strategic score", href: "#input-sectoral" },
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "Incumbent Alignment", href: "#factor-incumbent-alignment" },
        { label: "The 2×2", href: "#output-2x2" }
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
          { label: "GovTrack (federal ideology)", href: "#m-data" },
          { label: "DIME CFscores (federal ideology)", href: "#m-data" },
          { label: "Open States (state-leg party rosters)", href: "#m-data" }
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
              + '<p>Coverage: Federal P2 — 533 legislators scored, 3,142 counties with alignment data. State P2 is a different measure entirely — the partisan composition of each county\'s state-legislative seats (Σ Democratic seat-share / Σ all-party share, from Open States rosters), because seat-level labor voting records aren\'t uniformly available at the state level; it uses no key votes and no CFscores. Low P2 + high SLS + high P1 identifies the highest-value organizing targets: leverage, decisive geography, and a hostile incumbent.</p>'
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
      status: "populated",
      summary: "At the NATIONAL scale, what kind of strategic terrain is this county — and through which pathway?",
      flowchart: {
        inputs: [
          { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" },
          { label: "Electoral Leverage", href: "#factor-electoral-leverage" }
        ],
        outputs: [
          { label: "6 Tier Distribution", href: "#output-tiers" }
        ],
        dataSources: []
      },
      details: [
        {
          variant: "Two Tier-1 pathways",
          gloss: "A county can reach top priority through capital OR through community — incumbent alignment is NOT used here.",
          formula: "Capital pathway   → tier1_capital:\n   sls_capital ≥ {{sls_capital_high_boundary}}  AND  p1_national ≥ {{p1_high}}\n\nCommunity pathway → tier1_community:\n   sls_community ≥ {{sls_community_high_boundary}}  AND  state_tipping_weight ≥ {{state_tipping_swing_floor}}\n\nBoth clear → tier1_capital_community",
          constants: [
            { specKey: "sls_capital_high_boundary", label: "Capital “high” ≥" },
            { specKey: "p1_high", label: "Electoral-decisive (national) ≥" },
            { specKey: "sls_community_high_boundary", label: "Community “high” ≥" },
            { specKey: "state_tipping_swing_floor", label: "Swing-state floor ≥" }
          ],
          notes: "The capital pathway pairs strategic magnitude with a decisive presidential environment; the community pathway pairs concentrated worker power with a swing STATE. Neither reads incumbent alignment (P2)."
        },
        {
          variant: "The cascade (below Tier 1)",
          gloss: "What happens to counties that clear high leverage but not a Tier-1 gate.",
          formula: "capital_high but not electoral-decisive          → tier2_build_capital\ncommunity_high AND lean state\n   ({{state_tipping_lean_floor}} ≤ tipping < {{state_tipping_swing_floor}})  → tier2_build_community\nelse: tier3_electoral if electoral-decisive, otherwise tier4",
          constants: [
            { specKey: "state_tipping_lean_floor", label: "Lean-state floor ≥" },
            { specKey: "state_tipping_swing_floor", label: "Swing-state floor <" }
          ],
          notes: "P2-driven sublabels (activate / unknown) never appear on the national lens by construction — national strategy does not read incumbent posture."
        }
      ],
      rationale: [
        "<strong>Why two pathways.</strong> Labor's national leverage comes in two forms. Capital-leverage counties matter because disrupting their large strategic employment has national reach — they qualify when that magnitude meets a decisive electoral environment. Community-leverage counties matter because organized worker concentration in a swing state can move the state that moves the country. The two pathways honor that these are different theories of change, not a single ladder.",
        "<strong>Why no incumbent alignment nationally.</strong> National concessions tend to run through worker crises more than through individual members, and House control turns over too fast for a county alignment read to gate national priority. (See Incumbent Alignment for the fuller argument.)",
        "<strong>Why the Community pathway uses STATE swing status, not the county's own margin.</strong> Community Tier-1 turns on whether the county sits in a swing STATE — because a concentrated worker base influences the state-level outcome regardless of the county's own presidential margin. A safe-margin county in a swing state can still be Tier-1 community."
      ],
      limitations: [
        "<strong>No activate / transform sublabels nationally.</strong> Those depend on incumbent alignment, which is dropped here by design; they appear only on the state lens.",
        "<strong>The Community pathway ignores the county's own presidential margin entirely</strong> — its electoral value is purely the state's decisiveness."
      ],
      seeAlso: [
        { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" },
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "State lens", href: "#lens-state" },
        { label: "Tiers & the two pathways", href: "#output-tiers" },
        { label: "The 2×2", href: "#output-2x2" }
      ]
    },
    {
      id: "lens-state",
      title: "State lens",
      status: "populated",
      summary: "At the STATE-LEGISLATIVE scale, what kind of terrain is this county — and is its incumbent friendly or hostile?",
      flowchart: {
        inputs: [
          { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" },
          { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
          { label: "Incumbent Alignment", href: "#factor-incumbent-alignment" }
        ],
        outputs: [
          { label: "6 Tier Distribution", href: "#output-tiers" }
        ],
        dataSources: []
      },
      details: [
        {
          variant: "Tier-1 — competitive, high-leverage, hostile",
          gloss: "Unlike the federal lens, the state lens DOES use incumbent alignment.",
          formula: "Tier-1 (both pathways) requires:\n   sls_high  AND  p1_state ≥ {{p1_high_state}}  AND  p2_state < {{p2_hostile_ceiling}}\n   → tier1_{capital|community}  (or tier1_capital_community if both SLS dims high)",
          constants: [
            { specKey: "p1_high_state", label: "Competitive seat (state) ≥" },
            { specKey: "p2_hostile_ceiling", label: "Hostile incumbent: P2 <" }
          ],
          notes: "The competitive gate differs from the national gate and sits on a DIFFERENT scale — p1_high_state is the state-lens selectivity knob, not comparable to the national p1 gate."
        },
        {
          variant: "The cascade — transform vs activate-and-defend",
          gloss: "Hostile competitive seats are transform targets; aligned competitive seats are to protect.",
          formula: "not sls_high                         → tier3_electoral if p1_high(state) else tier4\nsls_high AND not competitive         → tier2_build_{dim}\nsls_high AND competitive:\n   hostile  (p2 < {{p2_hostile_ceiling}})  → tier1 (transform)\n   aligned  (p2 ≥ {{p2_aligned_floor}})    → tier2_activate_{dim} (activate-and-defend)\n   in between                              → tier2_unknown_{dim}",
          constants: [
            { specKey: "p2_hostile_ceiling", label: "Hostile: P2 <" },
            { specKey: "p2_aligned_floor", label: "Aligned: P2 ≥" }
          ],
          notes: "A hostile incumbent in a competitive high-leverage seat is a transform target; an aligned incumbent in an equally competitive seat is one to activate and defend — a vulnerable pro-labor seat is as worth protecting as a hostile one is worth flipping."
        }
      ],
      rationale: [
        "<strong>Why state uses alignment and federal doesn't.</strong> State-legislative outcomes turn on specific, flippable seats where the incumbent's posture is directly actionable — so transform / activate-and-defend is the right axis. National strategy runs on different logic (see Federal lens).",
        "<strong>Transform AND defend.</strong> The lens treats flipping a hostile seat and protecting a vulnerable aligned one as two halves of the same competitive terrain — both are where organized worker power changes the outcome."
      ],
      limitations: [
        "<strong>Interim status.</strong> The state lens is computed and shipped on every county (quadrant_state, p1_state, p2_state) but is not yet surfaced in the public map, which currently shows the national lens only; it goes live after a dedicated state-layer audit and un-gating pass.",
        "<strong>Defensive value may be underweighted.</strong> The classifier ranks transform (Tier 1) above activate-and-defend (Tier 2); the defensive value of a vulnerable aligned seat is arguably higher than that ordering implies — a known limitation bookmarked for a future model refinement.",
        "<strong>State competitiveness data carries mixed vintages</strong> (mostly 2022 districts, some 2021 gubernatorial and 2024 presidential backfill), flagged but not discounted."
      ],
      seeAlso: [
        { label: "Federal lens", href: "#lens-federal" },
        { label: "Incumbent Alignment", href: "#factor-incumbent-alignment" },
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "Tiers & the two pathways", href: "#output-tiers" }
      ]
    },

    /* ═══════════════ THE 2×2 — POPULATED (Draft 2) ═══════════════ */
    {
      id: "output-2x2",
      title: "The 2×2",
      status: "populated",
      summary: "How do the model's two big dimensions — how much electoral leverage a place has and how much labor leverage — combine into a simple strategic picture?",
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
          variant: "The four quadrants",
          gloss: "Place every county on two axes; four strategic quadrants fall out.",
          html: '<p>The 2×2 is the simplest way to read the model: place every county on two axes — <strong>electoral leverage</strong> (X: how consequential its elections are) and <strong>labor leverage</strong> (Y: how much worker power it holds) — and four quadrants fall out. It is a teaching picture, not the live engine (see limitations).</p>'
              + '<div class="method-table-wrap"><table class="method-table">'
              + '<thead><tr><th>Quadrant</th><th>Reading</th><th>Strategic posture</th></tr></thead>'
              + '<tbody>'
              + '<tr><td>High electoral · High labor</td><td>“tier one”</td><td>Highest priority — leverage over outcomes and over the economy at once.</td></tr>'
              + '<tr><td>Low electoral · High labor</td><td>“base building”</td><td>Build worker power where the electoral payoff isn\'t there yet (the build region).</td></tr>'
              + '<tr><td>High electoral · Low labor</td><td>“electoral”</td><td>Decisive geography without an organizing base at scale (the electoral region).</td></tr>'
              + '<tr><td>Low electoral · Low labor</td><td>“lower priority”</td><td>Not a current priority under finite resources.</td></tr>'
              + '</tbody></table></div>'
              + '<p>Thresholds are shown illustratively; the live classifier uses the full tier rules (see the Federal lens), not a simple quadrant split.</p>'
        }
      ],
      rationale: [
        "<strong>Why a 2×2 at all.</strong> The full model has six tiers, two leverage sub-dimensions, and an alignment axis — powerful but not glanceable. The 2×2 compresses it to the one comparison that carries the most strategic intuition: leverage over outcomes (electoral) against leverage over the economy (labor). It is the on-ramp to the fuller model, not a replacement for it."
      ],
      limitations: [
        "<strong>The 2×2 is illustrative, not the live classifier.</strong> The actual tiering splits labor leverage into capital and community, adds the swing-state and incumbent-alignment gates, and produces six tiers — none of which the four-quadrant picture captures. Read the 2×2 as a mental model; read the Tier definitions for what the model actually computes.",
        "<strong>The Y axis collapses two different leverages.</strong> “Labor leverage” on the 2×2 stands in for both SLS-Capital (magnitude) and SLS-Community (concentration), which — as the Sectoral Leverage section explains — are not the same thing and clear “high” at non-comparable boundaries (capital ≥ {{sls_capital_high_boundary}}, community ≥ {{sls_community_high_boundary}}). The simplification is deliberate but lossy."
      ],
      seeAlso: [
        { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" },
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "Tiers & the two pathways", href: "#output-tiers" },
        { label: "Scatter", href: "#output-scatter" },
        { label: "Federal lens", href: "#lens-federal" }
      ]
    },

    /* ════════════════ OUTPUT — genuinely empty stubs ════════════════ */
    {
      id: "output-tiers",
      title: "Tiers & the two pathways",
      status: "populated",
      summary: "What does each tier actually mean, and how many counties fall into each?",
      flowchart: {
        inputs: [
          { label: "Federal lens", href: "#lens-federal" }
        ],
        outputs: [
          { label: "Map", href: "#output-map" },
          { label: "Scatter", href: "#output-scatter" }
        ],
        dataSources: []
      },
      details: [
        {
          variant: "The six tier families (national lens)",
          gloss: "The strategic category each county lands in, with current counts.",
          html: '<p>The tiers are the model\'s output vocabulary — the strategic category each county lands in, produced by the pathway logic in the lenses. There are six families; the counts below are the live national-lens distribution across all 3,143 counties.</p>'
              + '<div class="method-table-wrap"><table class="method-table">'
              + '<thead><tr><th>Tier</th><th>Meaning</th><th>Counties</th></tr></thead>'
              + '<tbody>'
              + '<tr><td>tier1_capital</td><td>Capital pathway — top priority</td><td>15</td></tr>'
              + '<tr><td>tier1_community</td><td>Community pathway — top priority</td><td>54</td></tr>'
              + '<tr><td>tier1_capital_community</td><td>Both pathways</td><td>4</td></tr>'
              + '<tr><td>tier2_build_capital</td><td>High capital leverage, not yet decisive — build</td><td>280</td></tr>'
              + '<tr><td>tier2_build_community</td><td>High community leverage in a lean state — build</td><td>43</td></tr>'
              + '<tr><td>tier3_electoral</td><td>Decisive geography without a base at scale</td><td>74</td></tr>'
              + '<tr><td>tier4</td><td>Lower priority under finite resources</td><td>2,673</td></tr>'
              + '</tbody></table></div>'
              + '<p>Counts are the live <code>quadrant_national</code> distribution; they sum to 3,143.</p>'
        }
      ],
      rationale: [
        "<strong>Why named tiers.</strong> A small number of named tiers makes a 3,143-county model legible and actionable — the names encode the strategic posture, not just a rank."
      ],
      limitations: [
        "<strong>Heavily weighted to tier4 by construction</strong> — most counties are not high-leverage, which is the expected shape of a targeting model.",
        "<strong>tier1_capital_community is only a handful of counties</strong> (currently 4); the hybrid case is rare. The largest labor markets sit in states that don't decide national elections, and the counties that do are smaller and community-facing — so almost no county clears both pathways at once."
      ],
      seeAlso: [
        { label: "Federal lens", href: "#lens-federal" },
        { label: "State lens", href: "#lens-state" },
        { label: "The 2×2", href: "#output-2x2" },
        { label: "Map", href: "#output-map" },
        { label: "Scatter", href: "#output-scatter" }
      ]
    },

    /* ═══════════════════ MAP — POPULATED (Draft 2) ═══════════════════ */
    {
      id: "output-map",
      title: "Map",
      status: "populated",
      summary: "Where do the tiers fall geographically — and what does the map actually show, and not show?",
      flowchart: {
        inputs: [
          { label: "6 Tier Distribution", href: "#output-tiers" }
        ],
        outputs: [
          { label: "The interactive map" }
        ],
        dataSources: []
      },
      details: [
        {
          variant: "Per-county choropleth, colored by national-lens tier",
          gloss: "Every county filled by its own tier, using the shared palette so map, scatter, and county card all agree.",
          html: '<p>The map colors every county by its own national-lens tier value (<code>quadrant_national</code>), drawing each county as its own shape — metros are <strong>not</strong> merged in the base view. The fill uses the <strong>shared tier palette</strong>, so a county reads the same color on the map, in the scatter, and on its detail card.</p>'
              + '<div class="method-table-wrap"><table class="method-table">'
              + '<thead><tr><th>Swatch</th><th>Tier</th><th>Reading</th></tr></thead>'
              + '<tbody>'
              + '<tr><td><span class="map-swatch" style="background:#BD0026"></span></td><td>Tier 1 — Capital</td><td>Capital pathway, top priority</td></tr>'
              + '<tr><td><span class="map-swatch" style="background:#1a3a6b"></span></td><td>Tier 1 — Community</td><td>Community pathway, top priority</td></tr>'
              + '<tr><td><span class="map-swatch" style="background:#E8736B"></span></td><td>Tier 2 — Capital</td><td>High capital leverage, not yet decisive — build</td></tr>'
              + '<tr><td><span class="map-swatch" style="background:#4A7FB5"></span></td><td>Tier 2 — Community</td><td>High community leverage in a lean state — build</td></tr>'
              + '<tr><td><span class="map-swatch" style="background:#7B6B9E"></span></td><td>Tier 3 — Electoral</td><td>Decisive geography without a base at scale</td></tr>'
              + '<tr><td><span class="map-swatch" style="background:#E0DBD3"></span></td><td>Tier 4 — Lower priority</td><td>Not a current priority under finite resources</td></tr>'
              + '</tbody></table></div>'
              + '<p>The one county that clears both Tier-1 pathways (<code>tier1_capital_community</code>) takes the Tier-1 capital color. Counties with no tier value render in a neutral no-data gray.</p>'
        }
      ],
      rationale: [
        "<strong>Geography is how organizers navigate.</strong> The tiers answer “what kind of terrain”; the map answers “where.” Seeing the categories laid down on actual counties turns the model from a table into something you can plan a deployment around — which states, which metros, which rural counties light up.",
        "<strong>One palette, three views.</strong> The map, the scatter, and the county card all read from the same tier colors, so a county that is Tier-1 community blue on the map is the same blue everywhere else. The color is the model's output vocabulary made visual."
      ],
      limitations: [
        "<strong>National lens only (for now).</strong> The base map shows the national-lens tier; the state lens (<code>quadrant_state</code>) is computed and shipped on every county but not yet surfaced here — it goes live after a dedicated state-layer audit and un-gating pass.",
        "<strong>A few counties aren't drawable.</strong> Counties with no matching geometry — notably the Connecticut planning-region FIPS, which replaced its counties — can't be rendered and simply don't appear, though they still exist in the data.",
        "<strong>Metros are un-merged by design.</strong> Each county is its own shape; a metro that spans several counties shows as several shapes, not one. An optional MSA-merge overlay (grouping a metro into a single region) is bookmarked as a future view, not the default."
      ],
      seeAlso: [
        { label: "Tiers & the two pathways", href: "#output-tiers" },
        { label: "Scatter", href: "#output-scatter" },
        { label: "Federal lens", href: "#lens-federal" },
        { label: "The 2×2", href: "#output-2x2" }
      ]
    },
    {
      id: "output-scatter",
      title: "Scatter",
      status: "populated",
      summary: "How do all 3,143 counties distribute across electoral and labor leverage at once?",
      flowchart: {
        inputs: [
          { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
          { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" }
        ],
        outputs: [
          { label: "Scatter Plot Distribution" }
        ],
        dataSources: []
      },
      details: [
        {
          variant: "Two percentile axes, colored by tier",
          gloss: "Electoral leverage (X) against labor leverage (Y), every county a dot.",
          formula: "X = electoral-leverage percentile (p1_national), 0–100\nY = labor-leverage percentile = max(capital percentile, community percentile), 0–100\ncolor = tier (shared palette)",
          notes: "The map answers “where”; the scatter answers “how are counties distributed” — it shows the clusters and the empty regions the map can't."
        }
      ],
      rationale: [
        "<strong>Distribution, not geography.</strong> Plotting every county on the two leverage axes at once exposes the shape of the terrain — where counties cluster, and the high-high corner that turns out to be nearly empty (see Tier definitions)."
      ],
      limitations: [
        "<strong>The Y axis blends two different leverages.</strong> Y = max(capital percentile, community percentile) collapses the magnitude-vs-concentration distinction into one number; a high-Y county could be high on either, and the axis doesn't say which. A refined encoding (e.g. twin plots) is bookmarked.",
        "<strong>X uses presidential leverage (p1_national), but Community Tier-1 is gated on state swing status</strong>, not the county's own p1 — so a Tier-1-community dot can sit at low X yet be colored Tier 1. An axis/color mismatch by construction, worth noting."
      ],
      seeAlso: [
        { label: "Tiers & the two pathways", href: "#output-tiers" },
        { label: "Map", href: "#output-map" },
        { label: "The 2×2", href: "#output-2x2" },
        { label: "Electoral Leverage", href: "#factor-electoral-leverage" },
        { label: "Sectoral Leverage", href: "#factor-sectoral-leverage" }
      ]
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

  // Wrap the mini-flowchart in the SAME collapsible toggle as Details and
  // Rationale & Limitations — but OPEN by default. The adaptive elbow connectors
  // need measurable box geometry, which hidden (display:none) <details> bodies
  // don't have; a `toggle` listener (see renderAll) recomputes them on re-expand.
  function wrapFlow(inner) {
    return '<details class="formula-card method-flowtoggle" open>'
      + '<summary><span class="formula-card-name">Flowchart</span>'
      + '<span class="formula-card-gloss">Inputs, this variable, outputs, and data sources.</span></summary>'
      + '<div class="formula-card-detail">' + inner + "</div></details>";
  }

  function renderFlow(sec) {
    var f = sec.flowchart || {};
    var inputs = f.inputs || [];
    var outputs = f.outputs || [];
    var sources = f.dataSources || [];
    if (!inputs.length && !outputs.length && !sources.length) {
      return wrapFlow('<div class="method-flow method-flow--empty"><span class="method-todo-tag">TODO — mini-flowchart</span></div>');
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
    return wrapFlow(html);
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
      /* flowchart lives in the shared toggle (open by default); sit flush in the
         body — the toggle card is the frame now, so drop the flow2 outer border/
         background/padding to avoid a redundant nested tan box */
      + '.method-flowtoggle .formula-card-detail { overflow: visible; }'
      + '.method-flowtoggle .method-flow2 { margin: 0; border: none; background: none; padding: 0; }'
      + '.method-flowtoggle .method-flow--empty { margin: 0; }'
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
      + '.method-seealso a:hover { text-decoration: underline; }'
      + '.map-swatch { display: inline-block; width: 18px; height: 18px; border-radius: 4px; border: 1px solid rgba(0,0,0,0.18); vertical-align: middle; }';
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
    // The flowchart toggle starts open, so geometry is measurable at first draw.
    // When collapsed then re-expanded, recompute — a hidden <details> body has no
    // measurable box positions, so the initial draw inside it would be void.
    document.querySelectorAll("details.method-flowtoggle").forEach(function (d) {
      d.addEventListener("toggle", function () {
        if (d.open) scheduleConnectorDraw();
      });
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
