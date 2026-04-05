"""
Main agent execution loop.
"""

from __future__ import annotations

import threading

from checkpointer import clear_state, load_state, save_state
from exceptions import CheckpointError
from logger import get_logger
from models import EmailObject, init_state

from agent.graph import END, GRAPH
from agent.nodes import NODE_REGISTRY

logger = get_logger(__name__)

_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _get_thread_lock(thread_id: str) -> threading.Lock:
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(thread_id)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[thread_id] = lock
        return lock


def run(thread_id: str, email_obj: EmailObject) -> None:
    """
    Execute state-machine nodes for one inbound email.
    """
    lock = _get_thread_lock(thread_id)
    with lock:
        logger.info("Agent loop start for thread %s", thread_id, extra={"thread_id": thread_id})

        state = load_state(thread_id)
        if state is not None and state.get("current_node") == "send_node":
            logger.warning(
                "Recovered stale send_node state for thread %s; clearing completed session.",
                thread_id,
                extra={"thread_id": thread_id},
            )
            clear_state(thread_id)
            state = None

        if state is None:
            state = init_state(thread_id, email_obj)
            logger.info("Initialized new session state.", extra={"thread_id": thread_id})
        else:
            logger.info(
                "Resuming existing session at node=%s",
                state.get("current_node", "triage_node"),
                extra={"thread_id": thread_id},
            )

        from preference_store import load_preferences

        for participant in state.get("participants", []):
            if participant not in state.get("preferences", {}):
                state["preferences"][participant] = load_preferences(participant)

        # Every inbound email re-enters from triage.
        state["current_node"] = "triage_node"

        while state["current_node"] != END:
            current_node_name = state["current_node"]
            node_fn = NODE_REGISTRY.get(current_node_name)

            if node_fn is None:
                logger.error(
                    "Unknown node '%s' - routing to error_node.",
                    current_node_name,
                    extra={"thread_id": thread_id},
                )
                state["error"] = f"Unknown node: {current_node_name}"
                state["current_node"] = "error_node"
                continue

            try:
                state = node_fn(state, email_obj)
            except Exception as exc:
                logger.error(
                    "Unhandled exception in node '%s': %s",
                    current_node_name,
                    exc,
                    exc_info=True,
                    extra={"thread_id": thread_id},
                )
                state["error"] = f"Node {current_node_name} raised: {exc}"
                state["current_node"] = "error_node"

            try:
                save_state(thread_id, state)
            except CheckpointError as exc:
                logger.critical(
                    "CheckpointError after node '%s': %s. Halting loop.",
                    current_node_name,
                    exc,
                    extra={"thread_id": thread_id},
                )
                return

            if state.get("current_node") == "error_node" and current_node_name != "error_node":
                continue

            router_fn = GRAPH.get(current_node_name)
            if router_fn is None:
                logger.error(
                    "No router found for node '%s'. Terminating loop.",
                    current_node_name,
                    extra={"thread_id": thread_id},
                )
                break

            next_node = router_fn(state)
            state["current_node"] = next_node
            logger.debug(
                "%s -> %s",
                current_node_name,
                next_node,
                extra={"thread_id": thread_id},
            )

        logger.info("Agent loop complete for thread %s", thread_id, extra={"thread_id": thread_id})
