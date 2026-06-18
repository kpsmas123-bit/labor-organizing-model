"""
emit_model_spec.py — EMIT model_spec.json, the single source of truth for every
numeric constant / threshold / formula-parameter the public methodology cites.

WHY THIS EXISTS
---------------
The methodology must read its numbers rather than hardcode them, so the prose can
never silently drift from the model (the bug class that produced the stale "35"
and a hardcoded NORM in the rendered page). This script consolidates every cited
constant into one flat, clearly-keyed catalog that the methodology page reads at
render time. Each entry records WHERE the value truly lives, so the provenance is
auditable.

SOURCES (values are pulled from where they actually live — never re-typed):
  * config/thresholds.json   — state_competitiveness.*, quadrant.*
  * config/weights.json      — svs_normalization.denominator, svs_formula.*
  * pipeline/build_v2_canonical.py — the P1 formula constants that are HARDCODED
        there as named module constants (_NORM, _MIN_MARGIN_PP, _PRES_DEFAULT_TIP).
        These are IMPORTED, not re-typed, so the spec cannot drift from the code.
  * B1 (2026-06-17): the SLS-Capital divisor AND the SLS-Community share
        multiplier now BOTH live in config (svs_normalization.denominator /
        svs_normalization.community_multiplier) — the old ×4 code literal was
        lifted to config, so neither is a code literal anymore.

GUARANTEE: this script only READS config + code and WRITES model_spec.json. It
does NOT touch any scoring input, config, or data file. county_scores.json and
the config files are byte-identical before and after running it.

TODO(pipeline): fold this emission into build_v2_canonical.py / rebuild_state_lens.py
so model_spec.json regenerates as part of the main build. For now it is a small
standalone step run after a build (or any time the cited constants change).

Run:
  python pipeline/emit_model_spec.py            # writes model_spec.json at repo root
  python pipeline/emit_model_spec.py --check     # print the catalog, write nothing
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Make `import build_v2_canonical` resolve (it lives in pipeline/, same as us).
sys.path.insert(0, str(Path(__file__).parent))

# Import the REAL hardcoded P1 constants straight from the build module. Importing
# build_v2_canonical only runs its module-level defs (main() is guarded by
# __name__ == "__main__"), so this has no side effects on any data file.
import build_v2_canonical as bvc  # noqa: E402

OUT_PATH = ROOT / "model_spec.json"


def load_json(rel):
    with open(ROOT / rel) as f:
        return json.load(f)


def fmt(value):
    """Human display string: ints show plain; floats trim trailing zeros, max 6dp."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        # up to 6 significant decimals, trailing zeros trimmed
        s = f"{value:.6f}".rstrip("0").rstrip(".")
        # NORM (357.142857…) should read as 357.14 in the prose
        if abs(value) >= 100:
            s = f"{value:.2f}".rstrip("0").rstrip(".")
        return s
    return str(value)


def entry(value, source_file, locator, short_label, display=None):
    """One catalog entry. `locator` is a source_line (code) or config_key (config)."""
    e = {
        "value": value,
        "display": display if display is not None else fmt(value),
        "source_file": source_file,
        "short_label": short_label,
    }
    # Record the locator under the right key name for honesty about its kind.
    if isinstance(locator, int):
        e["source_line"] = locator
    else:
        e["config_key"] = locator
    return e


def build_catalog():
    thresholds = load_json("config/thresholds.json")
    weights = load_json("config/weights.json")

    sc = thresholds["state_competitiveness"]
    quad = thresholds["quadrant"]
    svs_norm = weights["svs_normalization"]

    # --- Cross-checks: the imported code constants must match their documented
    #     values, and any value that ALSO appears in config must agree. If these
    #     ever diverge, the emit fails loudly rather than shipping a wrong number.
    assert bvc._MIN_MARGIN_PP == 0.5, bvc._MIN_MARGIN_PP
    assert bvc._PRES_DEFAULT_TIP == 0.005, bvc._PRES_DEFAULT_TIP
    assert abs(bvc._NORM - 100.0 / 0.28) < 1e-9, bvc._NORM

    catalog = {
        # ───────── Electoral Leverage — NATIONAL variant ─────────
        "NORM": entry(
            bvc._NORM, "pipeline/build_v2_canonical.py", 41,
            "P1 national normalization = 100 / 0.28 (calibrates PA's 0.28 "
            "competitive counties to ~100)",
            display="357.14",
        ),
        "min_margin": entry(
            bvc._MIN_MARGIN_PP, "pipeline/build_v2_canonical.py", 40,
            "Floor on |vote margin| (pp) so a near-zero margin can't blow up 1/|margin|",
        ),
        "default_tip": entry(
            bvc._PRES_DEFAULT_TIP, "pipeline/build_v2_canonical.py", 42,
            "Default presidential state-tipping weight when a state is absent "
            "(the locked 0.005 floor)",
        ),
        "p1_high": entry(
            quad["p1_high_boundary"], "config/thresholds.json",
            "quadrant.p1_high_boundary",
            "National Electoral-Leverage 'high' gate (Tier-1 capital pathway "
            "treats a county as decisive at p1_national ≥ this)",
        ),

        # ───────── Electoral Leverage — STATE variant ─────────
        "plateau_edge": entry(
            sc["plateau_edge"], "config/thresholds.json",
            "state_competitiveness.plateau_edge",
            "State competitiveness: full weight for |seat margin| ≤ this (toss-up "
            "plateau, pp)",
        ),
        "zero_edge": entry(
            sc["zero_edge"], "config/thresholds.json",
            "state_competitiveness.zero_edge",
            "State competitiveness: weight fades linearly to 0 at |seat margin| = "
            "this (lean edge, pp)",
        ),
        "p1_high_state": entry(
            sc["p1_high_state"], "config/thresholds.json",
            "state_competitiveness.p1_high_state",
            "State Electoral-Leverage 'high' gate (DIFFERENT scale than national; "
            "the state-lens selectivity knob)",
        ),

        # ───────── Room to grow — constants other sections will cite ─────────
        # Sectoral Leverage
        "capital_divisor": entry(
            svs_norm["denominator"], "config/weights.json",
            "svs_normalization.denominator",
            "SLS-Capital normalization divisor. B1: SLS now weights each sector by "
            "the full composite SVS; divisor recalibrated to 750000 so LA County's "
            "raw sum still anchors at ~84 on 0–100.",
        ),
        "community_share_mult": entry(
            svs_norm["community_multiplier"], "config/weights.json",
            "svs_normalization.community_multiplier",
            "SLS-Community share→0–100 multiplier. B1: LIFTED FROM HARDCODE (was the "
            "×4 literal) to config and recalibrated to 1.875 for the full-composite-SVS "
            "scale (post-ramp max ~57).",
        ),
        # Quadrant / classification boundaries
        "sls_capital_high_boundary": entry(
            quad["sls_capital_high_boundary"], "config/thresholds.json",
            "quadrant.sls_capital_high_boundary",
            "SLS-Capital 'high' boundary (top ~decile of counties)",
        ),
        "sls_community_high_boundary": entry(
            quad["sls_community_high_boundary"], "config/thresholds.json",
            "quadrant.sls_community_high_boundary",
            "SLS-Community 'high' boundary on the post-ramp (Option D) scale",
        ),
        "p2_hostile_ceiling": entry(
            quad["p2_hostile_ceiling"], "config/thresholds.json",
            "quadrant.p2_hostile_ceiling",
            "Incumbent Alignment: P2 < this = hostile incumbent (Transform)",
        ),
        "p2_aligned_floor": entry(
            quad["p2_aligned_floor"], "config/thresholds.json",
            "quadrant.p2_aligned_floor",
            "Incumbent Alignment: P2 ≥ this = aligned incumbent (Activate)",
        ),
        "state_tipping_swing_floor": entry(
            quad["state_tipping_swing_floor"], "config/thresholds.json",
            "quadrant.state_tipping_swing_floor",
            "Community Tier-1 national gate: state_tipping_weight ≥ this = swing state",
        ),
        "state_tipping_lean_floor": entry(
            quad["state_tipping_lean_floor"], "config/thresholds.json",
            "quadrant.state_tipping_lean_floor",
            "Community Tier-2 national band floor: lean state",
        ),
    }
    return catalog


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="print the catalog, write nothing")
    args = ap.parse_args()

    catalog = build_catalog()
    doc = {
        "_note": "SINGLE SOURCE OF TRUTH for every numeric constant the public "
                 "methodology cites. GENERATED by pipeline/emit_model_spec.py from "
                 "config + code — do NOT hand-edit. To change a number, change it "
                 "at its source_file/source_line (or config_key) and re-run the "
                 "emit step.",
        "_generated_by": "pipeline/emit_model_spec.py",
        "_schema": "each entry = { value, display, source_file, "
                   "(source_line | config_key), short_label }",
        "constants": catalog,
    }
    out = json.dumps(doc, indent=2)

    if args.check:
        print(out)
        print(f"\n[{len(catalog)} constants — not written (--check)]")
        return

    with open(OUT_PATH, "w") as f:
        f.write(out + "\n")
    print(f"Wrote {len(catalog)} constants -> {OUT_PATH}")


if __name__ == "__main__":
    main()
