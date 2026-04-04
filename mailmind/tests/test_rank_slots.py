"""Deterministic tests for rank_slots scoring behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tools.coordination_memory import (
    SLOT_SCORE_THRESHOLD,
    WEIGHT_ATTENDANCE,
    WEIGHT_CHRONOLOGY,
    WEIGHT_PREFERENCE,
    WEIGHT_VIP,
    rank_slots,
)


def _slot(hour_utc: int, day_offset: int = 0, email: str = "alice@example.com") -> dict:
    """Build a one-hour UTC slot for test inputs."""
    base = datetime(2026, 4, 6, hour_utc, 0, tzinfo=timezone.utc)  # Monday
    start = base + timedelta(days=day_offset)
    end = start + timedelta(hours=1)
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "participant": email,
        "raw_text": "test",
        "timezone": "UTC",
    }


def _prefs(
    email: str,
    pref_start: int = 9,
    pref_end: int = 17,
    blocked: list[str] | None = None,
    vip: bool = False,
    slots: list[dict] | None = None,
) -> dict:
    """Build a PreferenceProfile-like dict for tests."""
    return {
        "email": email,
        "preferred_hours_start": pref_start,
        "preferred_hours_end": pref_end,
        "blocked_days": blocked or [],
        "vip": vip,
        "timezone": "UTC",
        "slots": slots or [],
        "preferred_hour_buckets": [],
        "preferred_days": [],
    }


class TestEmptyInput:
    def test_empty_slots_returns_below_threshold(self):
        result = rank_slots([], {})
        assert result["ranked_slot"] is None
        assert result["below_threshold"] is True
        assert result["score"] == 0.0


class TestSingleSlotSingleParticipant:
    @patch("tools.coordination_memory.check_vip_status", return_value=False)
    def test_single_slot_always_returned(self, _mock_vip):
        slot = _slot(10)
        prefs = {"alice@example.com": _prefs("alice@example.com", slots=[slot])}

        result = rank_slots([slot], prefs)

        assert result["ranked_slot"] is not None
        assert result["below_threshold"] is False

    @patch("tools.coordination_memory.check_vip_status", return_value=False)
    def test_attendance_component_baseline(self, _mock_vip):
        slot = _slot(10)
        prefs = {"alice@example.com": _prefs("alice@example.com", slots=[slot])}

        result = rank_slots([slot], prefs)

        # Attendance alone contributes 0.50 in single-participant case.
        assert result["score"] >= WEIGHT_ATTENDANCE


class TestPreferenceScoring:
    @patch("tools.coordination_memory.check_vip_status", return_value=False)
    def test_slot_within_preferred_hours_scores_higher(self, _mock_vip):
        slot_good = _slot(10)
        slot_bad = _slot(3)
        prefs = {
            "alice@example.com": _prefs("alice@example.com", slots=[slot_good, slot_bad])
        }

        result = rank_slots([slot_good, slot_bad], prefs)

        assert result["ranked_slot"]["start_utc"] == slot_good["start_utc"]

    @patch("tools.coordination_memory.check_vip_status", return_value=False)
    def test_blocked_day_slot_penalized_not_eliminated(self, _mock_vip):
        slot = _slot(10, day_offset=4)  # Friday
        prefs = {
            "alice@example.com": _prefs(
                "alice@example.com",
                blocked=["Friday"],
                slots=[slot],
            )
        }

        result = rank_slots([slot], prefs)

        assert result["ranked_slot"] is not None
        assert "soft penalty" in result["reason"]


class TestVIPScoring:
    @patch("tools.coordination_memory.check_vip_status", side_effect=lambda e: e == "ceo@co.com")
    def test_all_vips_available_maximizes_vip_score(self, _mock_vip):
        slot = _slot(10)
        prefs = {
            "ceo@co.com": _prefs("ceo@co.com", vip=True, slots=[slot]),
            "bob@co.com": _prefs("bob@co.com", slots=[slot]),
        }

        result = rank_slots([slot], prefs)

        assert "all VIPs available" in result["reason"]

    @patch("tools.coordination_memory.check_vip_status", return_value=False)
    def test_no_vips_configured_gives_full_vip_score(self, _mock_vip):
        slot = _slot(10)
        prefs = {"alice@example.com": _prefs("alice@example.com", slots=[slot])}

        result = rank_slots([slot], prefs)

        assert result["score"] >= WEIGHT_ATTENDANCE + WEIGHT_VIP

    @patch("tools.coordination_memory.check_vip_status", side_effect=lambda e: e == "vip@co.com")
    def test_vip_unavailable_reduces_score(self, _mock_vip):
        slot = _slot(10)
        prefs = {
            "vip@co.com": _prefs("vip@co.com", vip=True, slots=[]),
            "bob@co.com": _prefs("bob@co.com", slots=[slot]),
        }

        result = rank_slots([slot], prefs)

        assert "0% VIP coverage" in result["reason"]
        assert result["score"] < 0.90


class TestChronologyTiebreaker:
    @patch("tools.coordination_memory.check_vip_status", return_value=False)
    def test_earlier_slot_wins_on_tie(self, _mock_vip):
        slot_early = _slot(10, day_offset=0)
        slot_late = _slot(10, day_offset=2)
        prefs = {
            "alice@example.com": _prefs("alice@example.com", slots=[slot_early, slot_late])
        }

        result = rank_slots([slot_early, slot_late], prefs)

        assert result["ranked_slot"]["start_utc"] == slot_early["start_utc"]


class TestBelowThreshold:
    @patch("tools.coordination_memory.check_vip_status", return_value=False)
    def test_score_below_threshold_flagged(self, _mock_vip):
        slot = _slot(3)
        prefs = {
            "a@x.com": _prefs("a@x.com", slots=[slot]),
            "b@x.com": _prefs("b@x.com", slots=[]),
            "c@x.com": _prefs("c@x.com", slots=[]),
            "d@x.com": _prefs("d@x.com", slots=[]),
        }

        result = rank_slots([slot], prefs)

        assert result["below_threshold"] is True
        assert result["score"] < SLOT_SCORE_THRESHOLD


class TestWeightConstants:
    def test_weights_sum_to_one(self):
        total = WEIGHT_ATTENDANCE + WEIGHT_PREFERENCE + WEIGHT_VIP + WEIGHT_CHRONOLOGY
        assert abs(total - 1.0) < 1e-9
