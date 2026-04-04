"""
Tests for agent.nodes.rank_slots_node under Phase 6 behavior.
"""

from __future__ import annotations

from unittest.mock import patch


def _good_slot() -> dict:
    return {
        "start_utc": "2026-04-10T10:00:00+00:00",
        "end_utc": "2026-04-10T11:00:00+00:00",
        "participant": "alice@example.com",
        "raw_text": "10 to 11",
        "timezone": "UTC",
    }


def _make_state(restart_count: int = 0, participants: list[str] | None = None) -> dict:
    emails = participants or ["alice@example.com", "bob@example.com"]
    return {
        "thread_id": "thread-test",
        "intent": "scheduling",
        "participants": emails,
        "slots_per_participant": {e: [_good_slot()] for e in emails},
        "pending_responses": [],
        "ranked_slot": None,
        "outbound_draft": None,
        "approval_status": "none",
        "preferences": {},
        "history": [],
        "current_node": "rank_slots_node",
        "ambiguity_rounds": {},
        "non_responsive": [],
        "overlap_candidates": [_good_slot()],
        "rank_below_threshold": False,
        "calendar_event_id": None,
        "coordination_restart_count": restart_count,
        "error": None,
        "created_at": "2026-04-04T09:00:00+00:00",
        "updated_at": "2026-04-04T09:00:00+00:00",
    }


def _rank_result(below_threshold: bool) -> dict:
    if below_threshold:
        return {
            "ranked_slot": None,
            "score": 0.20,
            "reason": "Low attendance",
            "below_threshold": True,
        }
    return {
        "ranked_slot": _good_slot(),
        "score": 0.88,
        "reason": "100% attendance",
        "below_threshold": False,
    }


class TestRankSlotsNodePhase6:
    @patch("agent.nodes.load_preferences")
    @patch("agent.nodes.call_tool")
    def test_good_slot_sets_ranked_slot(self, mock_call_tool, mock_load_prefs):
        mock_load_prefs.return_value = {
            "preferred_hours_start": 9,
            "preferred_hours_end": 17,
            "blocked_days": [],
            "vip": False,
            "timezone": "UTC",
        }
        mock_call_tool.return_value = _rank_result(below_threshold=False)

        from agent.nodes import rank_slots_node

        state = _make_state(restart_count=0)
        result = rank_slots_node(state, {})

        assert result["ranked_slot"] is not None
        assert result["ranked_slot"]["start_utc"] == _good_slot()["start_utc"]
        assert result["rank_below_threshold"] is False
        assert result["coordination_restart_count"] == 0

    @patch("agent.nodes.load_preferences")
    @patch("agent.nodes.call_tool")
    def test_below_threshold_restarts_coordination_round(self, mock_call_tool, mock_load_prefs):
        mock_load_prefs.return_value = {
            "preferred_hours_start": 9,
            "preferred_hours_end": 17,
            "blocked_days": [],
            "vip": False,
            "timezone": "UTC",
        }
        mock_call_tool.return_value = _rank_result(below_threshold=True)

        from agent.nodes import rank_slots_node

        state = _make_state(restart_count=0, participants=["a@x.com", "b@x.com"])
        result = rank_slots_node(state, {})

        assert result["rank_below_threshold"] is True
        assert result["coordination_restart_count"] == 1
        assert result["outbound_draft"] is not None
        assert result["slots_per_participant"] == {}
        assert set(result["pending_responses"]) == {"a@x.com", "b@x.com"}

    @patch("agent.nodes.load_preferences")
    @patch("agent.nodes.call_tool")
    def test_above_restart_cap_routes_to_error(self, mock_call_tool, mock_load_prefs):
        mock_load_prefs.return_value = {
            "preferred_hours_start": 9,
            "preferred_hours_end": 17,
            "blocked_days": [],
            "vip": False,
            "timezone": "UTC",
        }
        mock_call_tool.return_value = _rank_result(below_threshold=True)

        from agent.nodes import rank_slots_node, MAX_COORDINATION_RESTARTS

        state = _make_state(restart_count=MAX_COORDINATION_RESTARTS)
        result = rank_slots_node(state, {})

        assert result["current_node"] == "error_node"
        assert result["error"] is not None
