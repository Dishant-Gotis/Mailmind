"""
Routing functions for the MailMind state machine.

Node name strings are defined here as local constants to avoid a circular
import with agent/graph.py (which itself imports these routing functions).
"""

from __future__ import annotations

from logger import get_logger

logger = get_logger(__name__)

# Local string constants — match the values in agent/graph.py exactly.
# Do NOT import from agent.graph here (creates circular import).
_END                    = "__END__"
_COORDINATION_NODE      = "coordination_node"
_AMBIGUITY_NODE         = "ambiguity_node"
_OVERLAP_NODE           = "overlap_node"
_CALENDAR_NODE          = "calendar_node"
_THREAD_INTELLIGENCE    = "thread_intelligence_node"
_SEND_NODE              = "send_node"
_ERROR_NODE             = "error_node"
_REWRITE_NODE           = "rewrite_node"


def route_by_intent(state: dict) -> str:
    """
    Route from triage_node based on classified intent.
    """
    intent = state.get("intent", "noise")
    thread_id = state.get("thread_id", "")

    routing = {
        "scheduling": _COORDINATION_NODE,
        "update_request": _THREAD_INTELLIGENCE,
        "reschedule": _COORDINATION_NODE,
        "cancellation": _SEND_NODE,
        "noise": _ERROR_NODE,
    }
    next_node = routing.get(intent, _ERROR_NODE)
    logger.debug(
        "route_by_intent: intent=%s -> %s",
        intent,
        next_node,
        extra={"thread_id": thread_id},
    )
    return next_node


def route_by_completeness(state: dict) -> str:
    """
    Route from coordination_node based on availability completeness.
    """
    thread_id = state.get("thread_id", "")
    pending = state.get("pending_responses", [])
    draft = state.get("outbound_draft")
    slots_per_participant = state.get("slots_per_participant", {})
    has_collected_slots = any(slots_per_participant.values())

    # If we have a clarification draft and no slots yet, we must send it even in
    # direct-email scenarios where pending can be empty (only sender + bot).
    if draft and (pending or not has_collected_slots):
        logger.debug(
            "route_by_completeness: clarification draft present -> %s",
            _AMBIGUITY_NODE,
            extra={"thread_id": thread_id},
        )
        return _AMBIGUITY_NODE

    if not pending:
        if not has_collected_slots:
            logger.debug(
                "route_by_completeness: no collected slots yet -> %s",
                _END,
                extra={"thread_id": thread_id},
            )
            return _END

        logger.debug(
            "route_by_completeness: all participants responded -> %s",
            _OVERLAP_NODE,
            extra={"thread_id": thread_id},
        )
        return _OVERLAP_NODE

    logger.debug(
        "route_by_completeness: waiting on %d participant(s) -> %s",
        len(pending),
        _END,
        extra={"thread_id": thread_id},
    )
    return _END


def route_by_threshold(state: dict) -> str:
    """
    Route from rank_slots_node based on ranked slot quality.
    """
    thread_id = state.get("thread_id", "")
    ranked_slot = state.get("ranked_slot")
    restart_count = state.get("coordination_restart_count", 0)
    below_threshold = state.get("rank_below_threshold", False)

    if ranked_slot and not below_threshold:
        logger.debug(
            "route_by_threshold: ranked slot accepted -> %s",
            _CALENDAR_NODE,
            extra={"thread_id": thread_id},
        )
        return _CALENDAR_NODE

    if restart_count >= 2:
        logger.warning(
            "route_by_threshold: restart cap reached (%d) -> %s",
            restart_count,
            _ERROR_NODE,
            extra={"thread_id": thread_id},
        )
        return _ERROR_NODE

    logger.debug(
        "route_by_threshold: below threshold (restart=%d) -> %s",
        restart_count,
        _COORDINATION_NODE,
        extra={"thread_id": thread_id},
    )
    return _COORDINATION_NODE


def route_by_approval(state: dict) -> str:
    """
    Route from approval_node based on approval status.
    """
    thread_id = state.get("thread_id", "")
    status = state.get("approval_status", "")

    routing = {
        "approved": _SEND_NODE,
        "timeout": _SEND_NODE,
        "rejected": _REWRITE_NODE,
    }
    next_node = routing.get(status, _ERROR_NODE)
    logger.debug(
        "route_by_approval: status=%s -> %s",
        status,
        next_node,
        extra={"thread_id": thread_id},
    )
    return next_node
