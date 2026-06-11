"""
Tests for Terrain v2.0 scoring functions in scoring/.
These test the new pure functions independently of Notion.

Generated: 2026-06-11
Migration gate: 3 of 7
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scoring.svs import score_svs
from scoring.sls import score_sls_capital, score_sls_community
from scoring.electoral import (
    score_presidential, score_statewide,
    score_congressional, score_p1_presidential
)
from scoring.infrastructure import (
    score_organized_scale, score_union_culture,
    infrastructure_composite, classify_intervention
)


class TestScoreSVS:
    def test_ports_equivalent(self):
        # cap=national(3), comm=state(2), facing=local(1), non_off=full(2)
        # 25+15+5+5 + dual_bonus(5) + whole_worker_bonus(5) = 60
        assert score_svs(3, 2, 1, 2) == 60.0

    def test_hospital_equivalent(self):
        # cap=none(0), comm=national(3), facing=state(2), non_off=full(2)
        # 0+25+10+5 + whole_worker_bonus(5) = 45
        assert score_svs(0, 3, 2, 2) == 45.0

    def test_zero_sector(self):
        assert score_svs(0, 0, 0, 0) == 0.0

    def test_dual_crisis_bonus_fires(self):
        # cap>0 AND comm>0 triggers +5 bonus
        without_bonus = score_svs(1, 0, 0, 0) + score_svs(0, 1, 0, 0)
        with_bonus = score_svs(1, 1, 0, 0)
        assert with_bonus == without_bonus + 5.0

    def test_dual_crisis_bonus_does_not_fire_one_zero(self):
        # Only cap, no comm — no dual crisis bonus
        result = score_svs(1, 0, 0, 0)
        assert result == 10.0

    def test_whole_worker_bonus_fires(self):
        # comm>0 AND facing>0 triggers +5 bonus
        result = score_svs(0, 1, 1, 0)
        # 0 + 10 + 5 + 0 + whole_worker(5) = 20
        assert result == 20.0

    def test_whole_worker_bonus_does_not_fire_no_comm(self):
        # facing>0 but comm=0 — no whole worker bonus
        result = score_svs(0, 0, 1, 0)
        assert result == 5.0

    def test_max_sector_all_national_full(self):
        # cap=national(3), comm=national(3), facing=national(3), non_off=full(2)
        # 25+25+15+5 + dual(5) + whole_worker(5) = 80
        assert score_svs(3, 3, 3, 2) == 80.0

    def test_returns_float(self):
        result = score_svs(1, 1, 1, 1)
        assert isinstance(result, float)


class TestScoreSLSCapital:
    def test_empty_employment(self):
        assert score_sls_capital({}, {}) == 0.0

    def test_single_sector_50k_workers(self):
        # cap_reach=25, 50000 workers, benchmark=100000
        # (25 * 50000) / 100000 = 12.5
        result = score_sls_capital({"s1": 50000}, {"s1": 25})
        assert result == 12.5

    def test_single_sector_no_reach(self):
        result = score_sls_capital({"s1": 50000}, {"s1": 0})
        assert result == 0.0

    def test_capped_at_100(self):
        # Very large employment would exceed 100 without cap
        result = score_sls_capital({"s1": 500000}, {"s1": 25})
        assert result == 100.0

    def test_multiple_sectors_sum(self):
        # (25*10000 + 10*20000) / 100000 = (250000+200000)/100000 = 4.5
        result = score_sls_capital({"s1": 10000, "s2": 20000}, {"s1": 25, "s2": 10})
        assert result == 4.5

    def test_missing_reach_treated_as_zero(self):
        # sector not in reach dict → 0
        result = score_sls_capital({"s1": 50000}, {})
        assert result == 0.0


class TestScoreSLSCommunity:
    def test_empty_employment(self):
        assert score_sls_community({}, {}, 100000) == 0

    def test_zero_total_employment(self):
        assert score_sls_community({"s1": 1000}, {"s1": 10}, 0) == 0.0

    def test_one_percent_share_comm10(self):
        # 10 * (1000/100000) * 100 = 10.0
        result = score_sls_community({"s1": 1000}, {"s1": 10}, 100000)
        assert result == 10.0

    def test_capped_at_100_with_large_share(self):
        # 25 * (50000/100000) * 100 = 1250 → 100.0
        result = score_sls_community({"s1": 50000}, {"s1": 25}, 100000)
        assert result == 100.0

    def test_multiple_sectors_sum(self):
        # sector1: 10 * (1000/100000) * 100 = 10
        # sector2: 10 * (1000/100000) * 100 = 10
        # total = 20.0
        result = score_sls_community(
            {"s1": 1000, "s2": 1000},
            {"s1": 10, "s2": 10},
            100000
        )
        assert result == 20.0

    def test_missing_reach_treated_as_zero(self):
        result = score_sls_community({"s1": 10000}, {}, 100000)
        assert result == 0.0


class TestScoreP1Presidential:
    def test_none_margin_returns_default(self):
        # null_margin_default = 20
        assert score_p1_presidential(None, 0.5) == 20.0

    def test_high_tipping_weight_tight_margin(self):
        # 0.8 * (1/2.0) * 100 = 40.0
        assert score_p1_presidential(2.0, 0.8) == 40.0

    def test_low_tipping_weight_wide_margin(self):
        # 0.1 * (1/30.0) * 100 = 0.33
        result = score_p1_presidential(30.0, 0.1)
        assert result == 0.33

    def test_very_tight_margin_capped_at_100(self):
        # 1.0 * (1/0.01) * 100 = 10000 → 100.0
        result = score_p1_presidential(0.005, 1.0)
        assert result == 100.0

    def test_negative_margin_same_as_positive(self):
        # Uses abs(margin) so D-favored and R-favored same score
        pos = score_p1_presidential(5.0, 0.5)
        neg = score_p1_presidential(-5.0, 0.5)
        assert pos == neg

    def test_returns_float(self):
        assert isinstance(score_p1_presidential(5.0, 0.3), float)


class TestScorePresidentialLegacy:
    def test_swing_state_tight_margin(self):
        # PA is swing: a=50, margin=3 -> b=50 -> 100
        assert score_presidential(3.0, "PA") == 100

    def test_swing_state_wide_margin(self):
        # PA is swing: a=50, margin=25 -> b=5 -> 55
        assert score_presidential(25.0, "PA") == 55

    def test_non_swing_tight_margin(self):
        # CA not swing: margin=3 -> a=35, b=50 -> 85
        assert score_presidential(3.0, "CA") == 85

    def test_non_swing_mid_margin(self):
        # CA: margin=8 -> a=25 (<=10), b=35 (<=10) -> 60
        assert score_presidential(8.0, "CA") == 60

    def test_none_margin_returns_default(self):
        assert score_presidential(None, "TX") == 20

    def test_negative_margin_handled(self):
        # R+8 in CA: abs=8 same as D+8
        result = score_presidential(-8.0, "CA")
        assert result == 60


class TestScoreStatewide:
    def test_very_tight_margin(self):
        # abs <= 3 -> 100
        assert score_statewide(2.0, None) == 100

    def test_tight_margin(self):
        # abs <= 6 -> 80
        assert score_statewide(5.0, None) == 80

    def test_none_state_falls_back_to_county(self):
        # state_margin=None, county=5.0 -> 80
        assert score_statewide(None, 5.0) == 80

    def test_safe_dem_bonus(self):
        # margin >= 15 -> base(40 for <=15) + 20 = 60
        result = score_statewide(15.0, None)
        assert result == 60

    def test_both_none(self):
        assert score_statewide(None, None) == 20


class TestScoreCongressional:
    def test_very_tight_margin(self):
        assert score_congressional(2.0, None) == 100

    def test_divided_trifecta_bonus(self):
        # margin=5 -> <=7 bracket -> 80, divided +15 -> 95
        result = score_congressional(5.0, "Divided")
        assert result == 95

    def test_no_trifecta_bonus(self):
        # margin=5 -> <=7 bracket -> 80, no bonus
        result = score_congressional(5.0, "Republican")
        assert result == 80

    def test_none_margin(self):
        assert score_congressional(None, None) == 20

    def test_capped_at_100(self):
        # very tight + divided: 100 + 15 -> capped at 100
        result = score_congressional(1.0, "Divided")
        assert result == 100


class TestInfrastructureComposite:
    def test_both_zero(self):
        assert infrastructure_composite(0, 0) == 0.0

    def test_both_100(self):
        # 100*0.6 + 100*0.4 = 100.0
        assert infrastructure_composite(100, 100) == 100.0

    def test_weights_applied(self):
        # 60*0.6 + 40*0.4 = 36+16 = 52.0
        assert infrastructure_composite(60, 40) == 52.0


class TestClassifyIntervention:
    def test_low_infra_type_a(self):
        assert classify_intervention(10, 60, 60) == "Type A: Organize Unorganized"

    def test_infra_29_still_type_a(self):
        assert classify_intervention(29, 70, 70) == "Type A: Organize Unorganized"

    def test_high_infra_high_both_type_c(self):
        assert classify_intervention(50, 60, 60) == "Type C: Partnership"

    def test_high_infra_high_electoral_low_statewide_type_b(self):
        assert classify_intervention(50, 60, 40) == "Type B: Political Activation"

    def test_high_infra_low_electoral_type_b(self):
        assert classify_intervention(50, 40, 60) == "Type B: Political Activation"

    def test_statewide_exactly_50_is_type_c(self):
        assert classify_intervention(50, 60, 50) == "Type C: Partnership"

    def test_electoral_exactly_50_is_type_c(self):
        assert classify_intervention(50, 50, 60) == "Type C: Partnership"

    def test_infra_exactly_30_is_not_type_a(self):
        # infra >= 30 → not Type A
        result = classify_intervention(30, 60, 60)
        assert result != "Type A: Organize Unorganized"
