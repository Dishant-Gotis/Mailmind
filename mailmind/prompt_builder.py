"""
Constructs system prompts and user messages for each agent node type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from models import AgentState, EmailObject


# ── System prompts (static per node type) ─────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
Your ONLY job right now is to classify the intent of an inbound email.
Classify into exactly one of these categories:
  - scheduling: The email is initiating, requesting, or accepting a meeting invitation.
  - update_request: The email is asking for a summary or status of an existing meeting/thread.
  - reschedule: The email is requesting to change the time of an already agreed meeting.
  - cancellation: The email is cancelling an existing meeting or coordination thread.
  - noise: The email is unrelated to scheduling (newsletters, spam, social messages, etc).
Return your classification using the "classify" tool.
Include a confidence score between 0.0 (wild guess) and 1.0 (certain).
Do not write any explanatory text outside the tool call."""

COORDINATION_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant. 
Your job is to extract availability information from the email body provided.
Use the "parse_availability" tool to extract all mentioned time slots.
Convert all times to UTC. If no specific times are mentioned, use "detect_ambiguity".
Do not infer or invent times. Only extract what is explicitly stated."""

AMBIGUITY_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
A participant replied with vague availability (e.g. "sometime next week", "mornings").
Use the "detect_ambiguity" tool to generate one specific clarifying question. 
The question must ask for SPECIFIC dates and times, preferably in a given format:
"Could you share 2-3 specific times (e.g. Monday 10 Apr 10am–12pm IST)?"
Do not ask multiple questions. One clear, specific question only."""

REWRITE_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
You have been given a draft email to review and polish.
Improve clarity and professionalism. Keep it concise (under 200 words).
Do not change any factual content: times, participant names, event title.
Do not add or remove the AI disclaimer — it is added separately.
Return ONLY the polished email body text. No markdown, no subject line."""

SUMMARISE_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
You have been given the full history of an email thread.
Provide a concise summary (3-5 bullet points) of: who is involved, what meeting is being coordinated,
what times have been proposed, and what the current status is.
Return plain text only. No markdown headers."""

THREAD_INTELLIGENCE_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
A participant has asked for a status update on this thread.
Using the thread history provided, summarise the current state of scheduling coordination.
Be factual and concise. Use the "summarise_thread" tool."""


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_triage_prompt(email_obj: EmailObject, state: AgentState) -> list[dict]:
    """
    Build the message list for triage_node.
    """
    messages = [{"role": "system", "content": TRIAGE_SYSTEM_PROMPT}]
    
    # Prepend history if exists
    if state.get("history"):
        messages.extend(state["history"])

    messages.append({
        "role": "user",
        "content": (
            f"From: {email_obj['sender_name']} <{email_obj['sender_email']}>\n"
            f"Subject: {email_obj['subject']}\n\n"
            f"{email_obj['body']}"
        ),
    })
    return messages


def build_coordination_prompt(email_obj: EmailObject, state: AgentState) -> list[dict]:
    """
    Build the message list for coordination_node.
    """
    participants_str = ", ".join(state.get("participants", []))
    pending_str = ", ".join(state.get("pending_responses", [])) or "none"

    messages = [{"role": "system", "content": COORDINATION_SYSTEM_PROMPT}]
    
    if state.get("history"):
        messages.extend(state["history"])

    messages.append({
        "role": "user",
        "content": (
            f"Participants: {participants_str}\n"
            f"Still waiting for: {pending_str}\n\n"
            f"Email from {email_obj['sender_email']}:\n"
            f"{email_obj['body']}"
        ),
    })
    return messages


def build_ambiguity_prompt(email_obj: EmailObject, state: AgentState) -> list[dict]:
    """
    Build the message list for ambiguity_node.
    """
    rounds = state.get("ambiguity_rounds", {}).get(email_obj["sender_email"], 0)
    escalation_note = ""
    if rounds >= 1:
        escalation_note = (
            "\nThis is the second clarification attempt. "
            "Be more explicit — ask for times in this exact format: "
            "Day DD Mon HH:MM–HH:MM Timezone (e.g. Monday 07 Apr 10:00–12:00 IST)."
        )

    messages = [{"role": "system", "content": AMBIGUITY_SYSTEM_PROMPT + escalation_note}]
    messages.append({
        "role": "user",
        "content": (
            f"Sender: {email_obj['sender_email']}\n"
            f"Their message:\n{email_obj['body']}"
        ),
    })
    return messages


def build_rewrite_prompt(draft: str) -> list[dict]:
    """
    Build the message list for rewrite_node.
    """
    return [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Draft email to polish:\n\n{draft}"},
    ]


def build_summarise_prompt(thread_history_text: str) -> list[dict]:
    """
    Build the message list for thread_intelligence_node summary calls.
    """
    return [
        {"role": "system", "content": SUMMARISE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Thread history:\n\n{thread_history_text}"},
    ]


def append_to_history(state: AgentState, role: str, content: str) -> None:
    """
    Append one message to AgentState history in place.
    """
    if "history" not in state or state["history"] is None:
        state["history"] = []
        
    state["history"].append({"role": role, "content": content})
