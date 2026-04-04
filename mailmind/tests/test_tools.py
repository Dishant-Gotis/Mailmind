"""Phase 5 tool module tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from exceptions import ToolNotFoundError


class TestEmailCoordinator:
    def test_classify_valid_intent(self):
        from tools.email_coordinator import classify

        result = classify(
            body="Let us meet tomorrow",
            subject="Meeting",
            intent="scheduling",
            confidence=0.91,
        )
        assert result["intent"] == "scheduling"
        assert result["confidence"] == 0.91

    def test_classify_invalid_intent_falls_back(self):
        from tools.email_coordinator import classify

        result = classify(
            body="text",
            subject="text",
            intent="unsupported",
            confidence=0.99,
        )
        assert result == {"intent": "noise", "confidence": 0.0}

    def test_detect_ambiguity_flags_vague_text(self):
        from tools.email_coordinator import detect_ambiguity

        result = detect_ambiguity("I am flexible sometime next week")
        assert result["is_ambiguous"] is True
        assert "specific" in result["question"].lower()

    def test_parse_availability_returns_slot_shape(self):
        from tools.email_coordinator import parse_availability

        result = parse_availability("I am free on 2026-12-01 10:00 UTC", "UTC")
        assert "slots" in result
        assert "count" in result
        if result["count"] > 0:
            slot = result["slots"][0]
            assert "start_utc" in slot
            assert "end_utc" in slot
            assert "timezone" in slot

    @patch("tools.email_coordinator.smtp_send_reply")
    def test_send_reply_delegates_to_smtp_sender(self, mock_send):
        from tools.email_coordinator import send_reply

        result = send_reply(
            to="alice@example.com",
            subject="Re: Sync",
            body="Thanks",
            thread_id="thread-1",
        )

        assert result["sent"] is True
        mock_send.assert_called_once()


class TestThreadIntelligence:
    @patch("tools.thread_intelligence.call_for_text")
    @patch("tools.thread_intelligence.load_state")
    def test_summarise_thread_uses_llm(self, mock_load_state, mock_call_for_text):
        from tools.thread_intelligence import summarise_thread

        mock_load_state.return_value = {
            "history": [
                {"role": "user", "content": "Can we meet Monday?"},
                {"role": "assistant", "content": "Please share times."},
            ]
        }
        mock_call_for_text.return_value = "Summary text"

        result = summarise_thread("thread-1")
        assert result["summary"] == "Summary text"

    @patch("tools.thread_intelligence.load_state")
    def test_get_scheduling_status_defaults_for_missing_state(self, mock_load_state):
        from tools.thread_intelligence import get_scheduling_status

        mock_load_state.return_value = None
        result = get_scheduling_status("thread-2")

        assert result["thread_id"] == "thread-2"
        assert result["has_ranked_slot"] is False

    def test_detect_cancellation(self):
        from tools.thread_intelligence import detect_cancellation

        assert detect_cancellation("Please cancel this meeting")["is_cancellation"] is True
        assert detect_cancellation("I can do Tuesday afternoon")["is_cancellation"] is False

    @patch("tools.thread_intelligence.get_historical_slots")
    def test_suggest_optimal_time(self, mock_hist):
        from tools.thread_intelligence import suggest_optimal_time

        mock_hist.return_value = [
            {"start_utc": "2026-04-10T10:00:00+00:00"},
            {"start_utc": "2026-04-11T10:30:00+00:00"},
            {"start_utc": "2026-04-12T14:00:00+00:00"},
        ]

        result = suggest_optimal_time("alice@example.com")
        assert result["sample_size"] == 3
        assert 10 in result["preferred_hour_buckets"]


class TestCoordinationMemory:
    @patch("tools.coordination_memory.save_state")
    @patch("tools.coordination_memory.load_state")
    def test_track_participant_slots_updates_state(self, mock_load_state, mock_save_state):
        from tools.coordination_memory import track_participant_slots

        mock_load_state.return_value = {
            "slots_per_participant": {},
            "pending_responses": ["alice@example.com"],
        }

        slot = {
            "start_utc": "2026-04-10T10:00:00+00:00",
            "end_utc": "2026-04-10T11:00:00+00:00",
            "participant": "",
            "raw_text": "10 to 11",
            "timezone": "UTC",
        }

        result = track_participant_slots("thread-1", "alice@example.com", [slot])
        assert result["tracked"] is True
        assert result["slot_count"] == 1
        mock_save_state.assert_called_once()

    @patch("tools.coordination_memory.load_state")
    def test_find_overlap_returns_candidates(self, mock_load_state):
        from tools.coordination_memory import find_overlap

        a_slot = {
            "start_utc": "2026-04-10T10:00:00+00:00",
            "end_utc": "2026-04-10T11:00:00+00:00",
            "participant": "a@example.com",
            "raw_text": "slot a",
            "timezone": "UTC",
        }
        b_slot = {
            "start_utc": "2026-04-10T10:30:00+00:00",
            "end_utc": "2026-04-10T11:30:00+00:00",
            "participant": "b@example.com",
            "raw_text": "slot b",
            "timezone": "UTC",
        }

        mock_load_state.return_value = {
            "slots_per_participant": {
                "a@example.com": [a_slot],
                "b@example.com": [b_slot],
            },
            "non_responsive": [],
        }

        result = find_overlap("thread-1")
        assert result["participant_count"] == 2
        assert result["count"] >= 1

    @patch("tools.coordination_memory.check_vip_status", return_value=False)
    def test_rank_slots_prefers_preferred_hour(self, _mock_vip):
        from tools.coordination_memory import rank_slots

        good = {
            "start_utc": "2026-04-10T10:00:00+00:00",
            "end_utc": "2026-04-10T11:00:00+00:00",
            "participant": "",
            "raw_text": "good",
            "timezone": "UTC",
        }
        bad = {
            "start_utc": "2026-04-10T03:00:00+00:00",
            "end_utc": "2026-04-10T04:00:00+00:00",
            "participant": "",
            "raw_text": "bad",
            "timezone": "UTC",
        }
        prefs = {
            "alice@example.com": {
                "preferred_hours_start": 9,
                "preferred_hours_end": 17,
                "blocked_days": [],
                "vip": False,
                "slots": [good, bad],
            }
        }

        result = rank_slots([good, bad], prefs)
        assert result["ranked_slot"]["start_utc"] == good["start_utc"]
        assert isinstance(result["score"], float)


class TestCalendarManager:
    def _mock_service(self):
        service = MagicMock()
        return service

    @patch("tools.calendar_manager._get_service")
    def test_check_duplicate_detects_existing_event(self, mock_get_service):
        from tools.calendar_manager import check_duplicate

        service = self._mock_service()
        mock_get_service.return_value = service
        service.events.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "evt-1",
                    "summary": "Team Sync",
                    "attendees": [{"email": "alice@example.com"}],
                }
            ]
        }

        result = check_duplicate(
            title="sync",
            start_utc="2026-04-10T10:00:00+00:00",
            participants=["alice@example.com"],
        )
        assert result["duplicate"] is True
        assert result["event_id"] == "evt-1"

    @patch("tools.calendar_manager._get_service")
    def test_create_event_returns_metadata(self, mock_get_service):
        from tools.calendar_manager import create_event

        service = self._mock_service()
        mock_get_service.return_value = service
        service.events.return_value.insert.return_value.execute.return_value = {
            "id": "evt-2",
            "htmlLink": "https://calendar.google.com/event?eid=evt-2",
        }

        result = create_event(
            title="Project Sync",
            start_utc="2026-04-10T10:00:00+00:00",
            end_utc="2026-04-10T11:00:00+00:00",
            participants=["alice@example.com"],
            description="Agenda",
        )
        assert result["event_id"] == "evt-2"

    @patch("tools.calendar_manager._get_service")
    def test_send_invite_returns_invited_list(self, mock_get_service):
        from tools.calendar_manager import send_invite

        service = self._mock_service()
        mock_get_service.return_value = service
        service.events.return_value.patch.return_value.execute.return_value = {}

        participants = ["a@example.com", "b@example.com"]
        result = send_invite("evt-3", participants)

        assert result["event_id"] == "evt-3"
        assert result["invited"] == participants


class TestToolRegistry:
    def test_get_schema_returns_named_schema(self):
        from tool_registry import get_schema

        schema = get_schema("classify")
        assert schema["function"]["name"] == "classify"

    def test_call_tool_unknown_raises(self):
        from tool_registry import call_tool

        with pytest.raises(ToolNotFoundError):
            call_tool("nonexistent", {})

    @patch("tool_registry._get_registry")
    def test_call_tool_dispatches(self, mock_registry):
        from tool_registry import call_tool

        mock_registry.return_value = {
            "demo_tool": lambda value: {"ok": True, "value": value}
        }
        result = call_tool("demo_tool", {"value": 5})
        assert result == {"ok": True, "value": 5}
