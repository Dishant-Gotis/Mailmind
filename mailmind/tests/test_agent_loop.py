"""
Phase 6 routing and loop integration tests with mocked dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
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

        assert route_by_completeness({"pending_responses": [], "outbound_draft": None, "thread_id": "t"}) == "overlap_node"
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
