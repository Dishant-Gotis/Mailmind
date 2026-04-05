"""
Phase 6 routing and loop integration tests with mocked dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
from unittest.mock import patch

import pytest

import db as db_module
from db import init_db
from models import EmailObject


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()


def _email_obj(
    thread_id: str = "thread-001",
    sender: str = "alice@example.com",
    subject: str = "Team sync",
    body: str = "Can we meet next week?",
) -> EmailObject:
    return EmailObject(
        message_id="<msg001@example.com>",
        thread_id=thread_id,
        sender_email=sender,
        sender_name="Alice",
        subject=subject,
        body=body,
        timestamp=datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc),
        in_reply_to="",
        recipients=["mailmind@gmail.com"],
    )


class TestRouting:
    def test_route_by_intent(self):
        from agent.router import route_by_intent

        assert route_by_intent({"intent": "scheduling", "thread_id": "t"}) == "coordination_node"
        assert route_by_intent({"intent": "update_request", "thread_id": "t"}) == "thread_intelligence_node"
        assert route_by_intent({"intent": "noise", "thread_id": "t"}) == "error_node"

    def test_route_by_completeness(self):
        from agent.graph import END
        from agent.router import route_by_completeness

        assert route_by_completeness({"pending_responses": [], "outbound_draft": None, "slots_per_participant": {}, "thread_id": "t"}) == END
        assert route_by_completeness({"pending_responses": [], "outbound_draft": None, "slots_per_participant": {"alice@example.com": [{"start_utc": "2026-04-07T09:00:00+00:00"}]}, "thread_id": "t"}) == "overlap_node"
        assert route_by_completeness({"pending_responses": ["bob@example.com"], "outbound_draft": None, "thread_id": "t"}) == END
        assert route_by_completeness({"pending_responses": ["bob@example.com"], "outbound_draft": "Please clarify", "thread_id": "t"}) == "ambiguity_node"

    def test_route_by_threshold(self):
        from agent.router import route_by_threshold

        assert route_by_threshold(
            {
                "ranked_slot": {"start_utc": "2026-04-07T09:00:00+00:00"},
                "rank_below_threshold": False,
                "coordination_restart_count": 0,
                "thread_id": "t",
            }
        ) == "calendar_node"
        assert route_by_threshold(
            {
                "ranked_slot": None,
                "rank_below_threshold": True,
                "coordination_restart_count": 0,
                "thread_id": "t",
            }
        ) == "coordination_node"
        assert route_by_threshold(
            {
                "ranked_slot": None,
                "rank_below_threshold": True,
                "coordination_restart_count": 2,
                "thread_id": "t",
            }
        ) == "error_node"

    def test_route_by_approval(self):
        from agent.router import route_by_approval

        assert route_by_approval({"approval_status": "approved", "thread_id": "t"}) == "send_node"
        assert route_by_approval({"approval_status": "timeout", "thread_id": "t"}) == "send_node"
        assert route_by_approval({"approval_status": "rejected", "thread_id": "t"}) == "rewrite_node"


class TestLoop:
    @patch("agent.nodes.call_with_tools")
    def test_loop_checkpoints_state_for_noise_intent(self, mock_call_with_tools):
        mock_call_with_tools.return_value = {"intent": "noise", "confidence": 0.99}

        from agent.loop import run
        from checkpointer import load_state

        email = _email_obj(thread_id="thread-noise")
        run(email["thread_id"], email)

        saved = load_state(email["thread_id"])
        assert saved is not None
        assert saved["intent"] == "noise"

    def test_loop_routes_node_exceptions_to_error(self):
        def boom(_state, _email):
            raise RuntimeError("boom")

        from agent.loop import run
        from agent.nodes import NODE_REGISTRY
        from checkpointer import load_state

        email = _email_obj(thread_id="thread-error")

        with patch.dict(NODE_REGISTRY, {"triage_node": boom}, clear=False):
            run(email["thread_id"], email)

        saved = load_state(email["thread_id"])
        assert saved is not None
        assert "boom" in (saved.get("error") or "")

    @patch("agent.nodes.call_with_tools")
    def test_loop_clears_stale_send_node_state(self, mock_call_with_tools):
        mock_call_with_tools.return_value = {"intent": "noise", "confidence": 0.99}

        from agent.loop import run
        from checkpointer import load_state, save_state

        email = _email_obj(thread_id="thread-send-recovery")
        stale_state = {
            "thread_id": email["thread_id"],
            "intent": "scheduling",
            "participants": [email["sender_email"]],
            "slots_per_participant": {},
            "pending_responses": [],
            "ranked_slot": None,
            "outbound_draft": "The meeting is confirmed for Monday 9am.",
            "approval_status": "approved",
            "preferences": {},
            "history": [],
            "current_node": "send_node",
            "ambiguity_rounds": {},
            "non_responsive": [],
            "overlap_candidates": [],
            "rank_below_threshold": False,
            "calendar_event_id": "event_abc",
            "coordination_restart_count": 0,
            "error": None,
            "created_at": datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc).isoformat(),
            "updated_at": datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc).isoformat(),
        }

        save_state(email["thread_id"], stale_state)
        with patch("agent.loop.clear_state") as clear_mock:
            run(email["thread_id"], email)

        clear_mock.assert_called_once_with(email["thread_id"])
        saved = load_state(email["thread_id"])
        assert saved is not None
        assert saved["current_node"] == "triage_node"

    def test_loop_serializes_same_thread_id_runs(self):
        from agent.loop import run
        from agent.nodes import NODE_REGISTRY
        from checkpointer import load_state, save_state

        email = _email_obj(thread_id="thread-lock")
        state = {
            "thread_id": email["thread_id"],
            "intent": "unknown",
            "participants": [email["sender_email"]],
            "slots_per_participant": {},
            "pending_responses": [],
            "ranked_slot": None,
            "outbound_draft": None,
            "approval_status": "none",
            "preferences": {},
            "history": [],
            "current_node": "triage_node",
            "ambiguity_rounds": {},
            "non_responsive": [],
            "overlap_candidates": [],
            "rank_below_threshold": False,
            "calendar_event_id": None,
            "coordination_restart_count": 0,
            "error": None,
            "created_at": datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc).isoformat(),
            "updated_at": datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc).isoformat(),
        }

        save_state(email["thread_id"], state)

        first_entered = threading.Event()
        release_first = threading.Event()
        second_entered = threading.Event()
        call_count = {"value": 0}

        def blocking_triage(_state, _email_obj):
            call_count["value"] += 1
            if call_count["value"] == 1:
                first_entered.set()
                release_first.wait(timeout=2)
            else:
                second_entered.set()
            _state["intent"] = "noise"
            return _state

        with patch.dict(NODE_REGISTRY, {"triage_node": blocking_triage}, clear=False):
            first_thread = threading.Thread(target=run, args=(email["thread_id"], email))
            second_thread = threading.Thread(target=run, args=(email["thread_id"], email))

            first_thread.start()
            assert first_entered.wait(timeout=2), "first run never entered triage"

            second_thread.start()
            assert not second_entered.is_set(), "second run entered before the first released the lock"

            release_first.set()
            first_thread.join(timeout=2)
            second_thread.join(timeout=2)

        assert not first_thread.is_alive()
        assert not second_thread.is_alive()
        assert second_entered.is_set()
        saved = load_state(email["thread_id"])
        assert saved is not None