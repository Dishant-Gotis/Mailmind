"""
Graph constants and routing map for the MailMind state machine.
"""

# Sentinel value for loop termination.
END = "__END__"

TRIAGE_NODE = "triage_node"
COORDINATION_NODE = "coordination_node"
AMBIGUITY_NODE = "ambiguity_node"
OVERLAP_NODE = "overlap_node"
RANK_SLOTS_NODE = "rank_slots_node"
CALENDAR_NODE = "calendar_node"
THREAD_INTELLIGENCE_NODE = "thread_intelligence_node"
REWRITE_NODE = "rewrite_node"
APPROVAL_NODE = "approval_node"
SEND_NODE = "send_node"
ERROR_NODE = "error_node"

from agent.router import (
    route_by_approval,
    route_by_completeness,
    route_by_intent,
    route_by_threshold,
)


GRAPH: dict[str, object] = {
    TRIAGE_NODE: route_by_intent,
    COORDINATION_NODE: route_by_completeness,
    AMBIGUITY_NODE: lambda state: SEND_NODE,
    OVERLAP_NODE: lambda state: RANK_SLOTS_NODE,
    RANK_SLOTS_NODE: route_by_threshold,
    CALENDAR_NODE: lambda state: REWRITE_NODE,
    THREAD_INTELLIGENCE_NODE: lambda state: REWRITE_NODE,
    REWRITE_NODE: lambda state: APPROVAL_NODE,
    APPROVAL_NODE: route_by_approval,
    SEND_NODE: lambda state: END,
    ERROR_NODE: lambda state: END,
}
