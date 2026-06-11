"""
Regression tests for Terrain v1 scoring functions.
These tests capture current behavior as a safety net during v2.0 migration.
They do NOT assert the behavior is theoretically correct —
they assert it hasn't accidentally changed.

Generated: 2026-06-11
Migration gate: 2 of 7
"""

import pytest
import sys
from pathlib import Path

# Add scripts/ to path so task9_fast (and its notion_client dependency) can be imported.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from task9_fast import (
    score_sectoral_value,
    score_organizing_potential,
    score_presidential,
    score_statewide,
    score_congressional,
    score_organized_scale,
    score_union_culture,
    score_organizing_opportunity,
    classify_intervention,
    priority_tier,
)


# ── score_sectoral_value ──────────────────────────────────────────────────────

class TestScoreSectoralValue:
    def test_empty_employment_dict_returns_zero(self):
        assert score_sectoral_value({}, {}) == 0.0

    def test_empty_employment_nonempty_svs_returns_zero(self):
        assert score_sectoral_value({}, {"s1": 80.0}) == 0.0

    def test_single_sector_middle_value(self):
        # 50000 workers * SVS=80 = 4,000,000 → /100,000 = 40.0
        result = score_sectoral_value({"s1": 50000}, {"s1": 80.0})
        assert result == 40.0

    def test_single_sector_caps_at_100(self):
        # 1,000,000 * 100 / 100,000 = 1,000 → capped at 100
        result = score_sectoral_value({"s1": 1_000_000}, {"s1": 100.0})
        assert result == 100.0

    def test_sector_missing_from_svs_contributes_zero(self):
        # s1 not in svs dict → svs defaults to 0.0 → total = 0
        result = score_sectoral_value({"s1": 50_000}, {})
        assert result == 0.0

    def test_multiple_sectors_summed_correctly(self):
        # s1: 20000 * 60 = 1,200,000  s2: 30000 * 40 = 1,200,000  total = 2,400,000
        # 2,400,000 / 100,000 = 24.0
        result = score_sectoral_value(
            {"s1": 20_000, "s2": 30_000},
            {"s1": 60.0, "s2": 40.0},
        )
        assert result == 24.0

    def test_multiple_sectors_capped_at_100(self):
        result = score_sectoral_value(
            {"s1": 500_000, "s2": 500_000},
            {"s1": 100.0, "s2": 100.0},
        )
        assert result == 100.0


# ── score_organizing_potential ────────────────────────────────────────────────

class TestScoreOrganizingPotential:
    def test_rtw_small_workforce_no_sectors(self):
        # a=5 (<10k), b=0, c=5 (RTW) → 10
        assert score_organizing_potential(5_000, {}, True) == 10

    def test_non_rtw_large_workforce_healthcare_heavy(self):
        # a=40 (>=100k), Healthcare=100k/100k → b=min(30,15)=15, c=30 → 85
        result = score_organizing_potential(200_000, {"Healthcare": 100_000}, False)
        assert result == 85

    def test_zero_unorganized_workers_rtw(self):
        # a=5 (0 < 10k), b=0, c=5 → 10
        assert score_organizing_potential(0, {}, True) == 10

    def test_zero_unorganized_non_rtw(self):
        # a=5, b=0, c=30 → 35
        assert score_organizing_potential(0, {}, False) == 35

    def test_missing_sector_mix_empty_dict(self):
        # Empty sector_mix: healthcare=education=logistics=0, total=1 (or 0→1)
        # a=10 (10k≥10k), b=0, c=30 → 40
        assert score_organizing_potential(10_000, {}, False) == 40

    def test_50k_tier(self):
        # a=30 (50k≤x<100k)
        assert score_organizing_potential(50_000, {}, True) == 35  # 30+0+5

    def test_25k_tier(self):
        # a=20
        assert score_organizing_potential(25_000, {}, True) == 25  # 20+0+5

    def test_sector_mix_education_and_logistics(self):
        # unorganized=100k (a=40), Education=50, Logistics=50, total=100
        # b = min(30, round(0 + 50/100*10 + 50/100*10)) = min(30, round(10)) = 10
        # RTW=False → c=30 → 40+10+30=80
        result = score_organizing_potential(
            100_000, {"Education": 50, "Logistics": 50}, False
        )
        assert result == 80

    def test_cap_at_100(self):
        # Large workforce, all healthcare, non-RTW
        # a=40, b=15, c=30 → 85 (already tested, not >100 in this config)
        # To force cap: set a=40, b=30 (unreachable), c=30
        # Can't exceed 40+15+30=85 with real inputs given b formula max ~15
        # Confirm min(100,...) is working — use artificially large components
        # Actually with the formula as-written, max possible is 40+15+30=85. Cap doesn't fire.
        # Test passes as long as function doesn't return >100.
        result = score_organizing_potential(200_000, {"Healthcare": 100_000}, False)
        assert result <= 100


# ── score_presidential ────────────────────────────────────────────────────────

class TestScorePresidential:
    def test_swing_state_close_margin_returns_100(self):
        # PA (swing), margin=2.0: a=50 (swing), b=50 (abs≤5) → 100
        assert score_presidential(2.0, "PA") == 100

    def test_non_swing_safe_state_large_margin_returns_10(self):
        # CA (non-swing), margin=-30.0: a=5 (abs>15), b=5 (abs>20) → 10
        assert score_presidential(-30.0, "CA") == 10

    def test_swing_state_large_margin_swing_bonus_applied(self):
        # NC (swing), margin=20.0: a=50 (swing), b=10 (abs≤20) → 60
        assert score_presidential(20.0, "NC") == 60

    def test_none_margin_returns_default_20(self):
        assert score_presidential(None, "PA") == 20

    def test_non_swing_close_margin(self):
        # TX (non-swing), margin=4.0: a=35 (abs≤5), b=50 (abs≤5) → 85
        assert score_presidential(4.0, "TX") == 85

    def test_non_swing_medium_margin(self):
        # CA, margin=12.0: a=15 (abs≤15), b=20 (abs≤15) → 35
        assert score_presidential(12.0, "CA") == 35

    def test_swing_state_medium_margin(self):
        # AZ (swing), margin=8.0: a=50 (swing), b=35 (abs≤10) → 85
        assert score_presidential(8.0, "AZ") == 85


# ── score_statewide ───────────────────────────────────────────────────────────

class TestScoreStatewide:
    def test_tight_state_margin_returns_100(self):
        # margin=2.0: abs≤3 → 100; 2<15 → no bonus → 100
        assert score_statewide(2.0, None) == 100

    def test_safe_dem_state_gets_bonus(self):
        # margin=18.0: abs≤20 → 20; 18≥15 → +20 = 40
        assert score_statewide(18.0, None) == 40

    def test_none_state_margin_falls_back_to_county(self):
        # state=None, county=5.0: margin=5.0, abs≤6 → 80; 5<15 → no bonus → 80
        assert score_statewide(None, 5.0) == 80

    def test_both_none_returns_default_20(self):
        assert score_statewide(None, None) == 20

    def test_margin_at_boundary_10(self):
        # margin=10.0: abs≤10 → 60; 10<15 → no bonus → 60
        assert score_statewide(10.0, None) == 60

    def test_margin_at_boundary_15_triggers_bonus(self):
        # margin=15.0: abs≤15 → 40; 15≥15 → +20 = 60
        assert score_statewide(15.0, None) == 60

    def test_state_margin_takes_precedence_over_county(self):
        # state=2.0 → 100; county=18.0 is ignored
        assert score_statewide(2.0, 18.0) == 100

    def test_margin_over_20(self):
        # margin=25.0: abs>20 → 10; 25≥15 → +20 = 30
        assert score_statewide(25.0, None) == 30


# ── score_congressional ───────────────────────────────────────────────────────

class TestScoreCongressional:
    def test_tight_margin_divided_trifecta_capped_at_100(self):
        # margin=2.0, Divided: abs≤3 → 100, +15=115 → capped at 100
        assert score_congressional(2.0, "Divided") == 100

    def test_large_margin_republican_trifecta_returns_10(self):
        # margin=40.0, Rep: abs>25 → 10; not Divided → 10
        assert score_congressional(40.0, "Republican") == 10

    def test_none_margin_returns_default_20(self):
        assert score_congressional(None, "Divided") == 20

    def test_medium_margin_no_trifecta_bonus(self):
        # margin=5.0, None: abs≤7 → 80; not Divided → 80
        assert score_congressional(5.0, None) == 80

    def test_divided_trifecta_adds_15(self):
        # margin=5.0, Divided: 80+15=95
        assert score_congressional(5.0, "Divided") == 95

    def test_margin_at_boundary_12(self):
        # margin=12.0: abs≤12 → 60
        assert score_congressional(12.0, None) == 60

    def test_margin_at_boundary_18(self):
        # margin=18.0: abs≤18 → 40
        assert score_congressional(18.0, None) == 40


# ── score_organized_scale ─────────────────────────────────────────────────────

class TestScoreOrganizedScale:
    def test_zero_members_zero_locals(self):
        assert score_organized_scale(0, 0) == 0

    def test_sub_1000_members_uses_union_count_formula(self):
        # 500 < 1000 → else: min(100, max(0, 10*3)) = 30
        assert score_organized_scale(500, 10) == 30

    def test_1000_members_returns_10(self):
        assert score_organized_scale(1_000, 5) == 10

    def test_5000_members_returns_20(self):
        assert score_organized_scale(5_000, 0) == 20

    def test_10000_members_returns_40(self):
        assert score_organized_scale(10_000, 0) == 40

    def test_25000_members_returns_60(self):
        assert score_organized_scale(25_000, 0) == 60

    def test_50000_members_returns_80(self):
        assert score_organized_scale(50_000, 0) == 80

    def test_100000_plus_members_returns_100(self):
        assert score_organized_scale(100_000, 0) == 100
        assert score_organized_scale(500_000, 0) == 100

    def test_union_count_formula_capped_at_100(self):
        # sub-1000 members, 40 locals: min(100, max(0, 40*3)) = min(100, 120) = 100
        assert score_organized_scale(999, 40) == 100

    def test_union_count_formula_zero_locals(self):
        # <1000 members, 0 locals → 0
        assert score_organized_scale(0, 0) == 0


# ── score_union_culture ───────────────────────────────────────────────────────

class TestScoreUnionCulture:
    def test_zero_members_returns_floor_5(self):
        assert score_union_culture(0, 100_000) == 5

    def test_zero_workforce_returns_floor_5_no_divide_by_zero(self):
        # density = 0 / 0 → guarded → 0.0 < 0.03 → 5
        assert score_union_culture(0, 0) == 5
        assert score_union_culture(1_000, 0) == 5

    def test_density_0_25_returns_80(self):
        # 25000/100000 = 0.25 ≥ 0.20 → 80
        assert score_union_culture(25_000, 100_000) == 80

    def test_density_at_0_30_returns_100(self):
        assert score_union_culture(30_000, 100_000) == 100

    def test_density_at_0_20_boundary(self):
        assert score_union_culture(20_000, 100_000) == 80

    def test_density_at_0_12_boundary(self):
        assert score_union_culture(12_000, 100_000) == 60

    def test_density_at_0_07_boundary(self):
        assert score_union_culture(7_000, 100_000) == 40

    def test_density_at_0_03_boundary(self):
        assert score_union_culture(3_000, 100_000) == 20

    def test_density_below_0_03(self):
        assert score_union_culture(1_000, 100_000) == 5


# ── score_organizing_opportunity ─────────────────────────────────────────────

class TestScoreOrganizingOpportunity:
    def test_both_max_returns_100(self):
        assert score_organizing_opportunity(100.0, 100) == 100.0

    def test_both_50_returns_50(self):
        # 50*0.55 + 50*0.45 = 27.5 + 22.5 = 50.0
        assert score_organizing_opportunity(50.0, 50) == 50.0

    def test_both_zero_returns_zero(self):
        assert score_organizing_opportunity(0.0, 0) == 0.0

    def test_weights_applied_correctly(self):
        # sectoral=80, org=60 → 80*0.55 + 60*0.45 = 44.0 + 27.0 = 71.0
        assert score_organizing_opportunity(80.0, 60) == 71.0

    def test_sectoral_only(self):
        # sectoral=100, org=0 → 55.0
        assert score_organizing_opportunity(100.0, 0) == 55.0

    def test_org_only(self):
        # sectoral=0, org=100 → 45.0
        assert score_organizing_opportunity(0.0, 100) == 45.0


# ── classify_intervention ─────────────────────────────────────────────────────

class TestClassifyIntervention:
    def test_low_infra_returns_type_a(self):
        # infra=10 < 30 → Type A
        assert classify_intervention(10.0, 80.0, 80) == "Type A: Organize Unorganized"

    def test_infra_29_is_still_type_a(self):
        assert classify_intervention(29.9, 80.0, 80) == "Type A: Organize Unorganized"

    def test_high_infra_high_electoral_high_statewide_returns_type_c(self):
        # infra=50≥30, electoral=60≥50, statewide=60≥50 → Type C
        assert classify_intervention(50.0, 60.0, 60) == "Type C: Partnership"

    def test_high_infra_high_electoral_low_statewide_returns_type_b(self):
        # infra=50, electoral=60, statewide=40<50 → Type B
        assert classify_intervention(50.0, 60.0, 40) == "Type B: Political Activation"

    def test_high_infra_low_electoral_returns_type_b(self):
        # infra=50≥30, electoral=40<50 → else branch → Type B
        assert classify_intervention(50.0, 40.0, 80) == "Type B: Political Activation"

    def test_statewide_exactly_50_is_type_c(self):
        # statewide=50≥50 → Type C
        assert classify_intervention(50.0, 60.0, 50) == "Type C: Partnership"

    def test_electoral_exactly_50_is_type_c(self):
        # electoral=50≥50 → goes to statewide check
        assert classify_intervention(50.0, 50.0, 60) == "Type C: Partnership"

    def test_infra_exactly_30_is_not_type_a(self):
        # infra=30 is NOT < 30, so goes to elif
        assert classify_intervention(30.0, 60.0, 60) == "Type C: Partnership"


# ── priority_tier ─────────────────────────────────────────────────────────────

class TestPriorityTier:
    def test_high_score_returns_tier_a(self):
        assert priority_tier(40.0) == "A: High Priority"

    def test_medium_score_returns_tier_b(self):
        assert priority_tier(25.0) == "B: Medium Priority"

    def test_low_score_returns_tier_c(self):
        assert priority_tier(10.0) == "C: Lower Priority"

    def test_tier_a_boundary_exactly_37(self):
        # ≥37.0 → A
        assert priority_tier(37.0) == "A: High Priority"

    def test_just_below_tier_a_boundary(self):
        # 36.9 < 37 → B (if ≥19)
        assert priority_tier(36.9) == "B: Medium Priority"

    def test_tier_b_boundary_exactly_19(self):
        # ≥19.0 → B
        assert priority_tier(19.0) == "B: Medium Priority"

    def test_just_below_tier_b_boundary(self):
        # 18.9 < 19 → C
        assert priority_tier(18.9) == "C: Lower Priority"

    def test_zero_score_is_tier_c(self):
        assert priority_tier(0.0) == "C: Lower Priority"
