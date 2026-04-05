"""
Session coordination memory tools: slot tracking, overlap detection, and ranking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from checkpointer import load_state, save_state
from config import config
from logger import get_logger
from preference_store import check_vip_status

if TYPE_CHECKING:
    from models import PreferenceProfile

logger = get_logger(__name__)

# Hybrid Phase 5A constants (final tuning can be done in Phase 5B).
WEIGHT_ATTENDANCE = 0.50
WEIGHT_PREFERENCE = 0.25
WEIGHT_VIP = 0.15
WEIGHT_CHRONOLOGY = 0.10
PREFERENCE_VIOLATION_PENALTY = 0.10
SLOT_SCORE_THRESHOLD = 0.50


def track_participant_slots(thread_id: str, email: str, slots: list[dict]) -> dict[str, Any]:
    """
    Persist parsed UTC slots for one participant into session state.
    """
    state = load_state(thread_id)
    if state is None:
        return {"tracked": False, "email": email, "slot_count": 0}

    norm_email = email.lower().strip()
    existing = list(state.get("slots_per_participant", {}).get(norm_email, []))
    existing.extend(slots)
    state["slots_per_participant"][norm_email] = existing

    pending = state.get("pending_responses", [])
    if norm_email in pending:
        pending.remove(norm_email)

    save_state(thread_id, state)
    return {"tracked": True, "email": norm_email, "slot_count": len(existing)}


def find_overlap(thread_id: str) -> dict[str, Any]:
    """
    Find candidate slots that meet configured attendance threshold across participants.
    """
    state = load_state(thread_id)
    if state is None:
        return {"candidates": [], "count": 0, "participant_count": 0}

    slots_map: dict[str, list[dict]] = state.get("slots_per_participant", {})
    non_responsive = set(state.get("non_responsive", []))
    active_participants = [email for email in slots_map.keys() if email not in non_responsive]

    if not active_participants:
        return {"candidates": [], "count": 0, "participant_count": 0}

    if len(active_participants) == 1:
        only_participant = active_participants[0]
        solo_candidates = sorted(
            slots_map.get(only_participant, []),
            key=lambda slot: _parse_dt(slot.get("start_utc")),
        )
        return {
            "candidates": solo_candidates,
            "count": len(solo_candidates),
            "participant_count": 1,
        }

    threshold = config.attendance_threshold
    seen: set[tuple[str, str]] = set()
    candidates: list[dict] = []

    # Evaluate each known slot as an anchor candidate.
    for participant in active_participants:
        for slot in slots_map.get(participant, []):
            slot_key = (str(slot.get("start_utc")), str(slot.get("end_utc")))
            if slot_key in seen:
                continue
            seen.add(slot_key)

            overlap_count = 0
            for other in active_participants:
                if _has_overlap(slot, slots_map.get(other, [])):
                    overlap_count += 1

            attendance_fraction = overlap_count / len(active_participants)
            if attendance_fraction >= threshold:
                candidates.append(slot)

    candidates.sort(key=lambda slot: _parse_dt(slot.get("start_utc")))
    return {
        "candidates": candidates,
        "count": len(candidates),
        "participant_count": len(active_participants),
    }


def rank_slots(
    candidate_slots: list[dict],
    preferences: dict[str, "PreferenceProfile"],
) -> dict[str, Any]:
    """
    Rank candidate slots using weighted deterministic scoring.
    """
    if not candidate_slots:
        logger.warning("rank_slots called with empty candidate_slots.")
        return {
            "ranked_slot": None,
            "score": 0.0,
            "reason": "No candidate slots available. Request more availability windows.",
            "below_threshold": True,
        }

    participants = list(preferences.keys())
    total_participants = max(len(participants), 1)

    vip_participants = [
        email
        for email in participants
        if preferences.get(email, {}).get("vip", False) or check_vip_status(email)
    ]

    starts = [_parse_dt(slot.get("start_utc")) for slot in candidate_slots]
    earliest = min(starts)
    latest = max(starts)
    time_span_seconds = max((latest - earliest).total_seconds(), 1.0)

    scored: list[tuple[float, dict, str, float]] = []
    for slot in candidate_slots:
        slot_start = _parse_dt(slot.get("start_utc"))
        slot_hour = slot_start.hour
        slot_day = slot_start.strftime("%A")

        available_count = 0
        for email in participants:
            participant_slots = preferences.get(email, {}).get("slots", [])
            if _has_overlap(slot, participant_slots):
                available_count += 1
        attendance_score = available_count / total_participants

        preference_score = 0.0
        total_penalty = 0.0
        for email in participants:
            pref = preferences.get(email, {})
            pref_start = int(pref.get("preferred_hours_start", 9))
            pref_end = int(pref.get("preferred_hours_end", 17))
            blocked_days = pref.get("blocked_days", [])

            within_hours = pref_start <= slot_hour < pref_end
            not_blocked = slot_day not in blocked_days

            if within_hours and not_blocked:
                preference_score += 1.0 / total_participants
            else:
                total_penalty += PREFERENCE_VIOLATION_PENALTY / total_participants

        if vip_participants:
            vip_available = 0
            for email in vip_participants:
                participant_slots = preferences.get(email, {}).get("slots", [])
                if _has_overlap(slot, participant_slots):
                    vip_available += 1
            vip_score = vip_available / len(vip_participants)
        else:
            vip_score = 1.0

        elapsed = (slot_start - earliest).total_seconds()
        chronology_score = 1.0 - (elapsed / time_span_seconds)

        final_score = (
            WEIGHT_ATTENDANCE * attendance_score
            + WEIGHT_PREFERENCE * preference_score
            + WEIGHT_VIP * vip_score
            + WEIGHT_CHRONOLOGY * chronology_score
            - total_penalty
        )
        final_score = max(0.0, min(1.0, final_score))

        reason_parts = [f"{int(attendance_score * 100)}% attendance"]
        if vip_score == 1.0 and vip_participants:
            reason_parts.append("all VIPs available")
        elif vip_score < 1.0 and vip_participants:
            reason_parts.append(f"{int(vip_score * 100)}% VIP coverage")
        if preference_score >= 0.75:
            reason_parts.append("within most participants' preferred hours")
        elif preference_score < 0.25:
            reason_parts.append("outside many participants' preferred hours")
        if total_penalty > 0:
            reason_parts.append(f"soft penalty {total_penalty:.2f} applied")

        scored.append((final_score, slot, "; ".join(reason_parts), attendance_score))

    scored.sort(key=lambda row: row[0], reverse=True)
    best_score, best_slot, best_reason, best_attendance = scored[0]

    # Even if other factors inflate score, low attendance must fail threshold.
    below_threshold = (
        best_score < SLOT_SCORE_THRESHOLD
        or best_attendance < config.attendance_threshold
    )
    if below_threshold:
        logger.warning(
            "Best slot rejected (score=%.4f, attendance=%.2f, attendance_threshold=%.2f, score_threshold=%.2f).",
            best_score,
            best_attendance,
            config.attendance_threshold,
            SLOT_SCORE_THRESHOLD,
        )

    return {
        "ranked_slot": best_slot,
        "score": round(best_score, 4),
        "reason": best_reason,
        "below_threshold": below_threshold,
    }


def _parse_dt(value: Any) -> datetime:
    """
    Parse datetime-like input and normalize to UTC aware datetime.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    else:
        raise ValueError(f"Unsupported datetime value: {value!r}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _has_overlap(slot: dict, participant_slots: list[dict]) -> bool:
    """
    Return True if the slot overlaps any slot in participant_slots.
    """
    start = _parse_dt(slot.get("start_utc"))
    end = _parse_dt(slot.get("end_utc"))

    for candidate in participant_slots:
        c_start = _parse_dt(candidate.get("start_utc"))
        c_end = _parse_dt(candidate.get("end_utc"))
        if start < c_end and c_start < end:
            return True
    return False
