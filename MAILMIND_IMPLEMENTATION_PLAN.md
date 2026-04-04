# MailMind — Implementation Plan
**Team TRIOLOGY | PCCOE Pune | Problem Statement 03**

---

## Phase 1 — Project Foundation & Configuration

- Initialize project directory structure
- Create `requirements.txt` with all dependencies
- Create `.env.example` with all required variable names and descriptions
- Create `config.py` — loads and validates all env variables at startup, raises human-readable errors on missing values
- Create `setup.py` — validates all credentials, tests every API connection (Gmail IMAP, Gmail SMTP, Gemini, Google Calendar), prints pass/fail per check
- Create `.gitignore` — excludes `.env`, `token.json`, `*.db`, `__pycache__`
- Create base exception classes in `exceptions.py`
- Create `logger.py` — structured logging with timestamps and thread ID tagging

### MD Files for Phase 1
- `PHASE1_PROJECT_STRUCTURE.md` — full directory tree with every file and its responsibility
- `PHASE1_CONFIG_AND_ENV.md` — all env variables, what each does, how to obtain each credential

---

## Phase 2 — Email Ingestion Layer (IMAP + SMTP)

- Implement `imap_poller.py` — connects to imap.gmail.com via imaplib.IMAP4_SSL, polls every 30 seconds, searches UNSEEN emails, marks as SEEN after fetch
- Implement `email_parser.py` — parses raw MIME content using email stdlib, extracts sender, subject, body (plain text), thread ID from References header, timestamp, recipients list
- Define `EmailObject` typed dict in `models.py`
- Implement `smtp_sender.py` — connects to smtp.gmail.com:465 via smtplib.SMTP_SSL, constructs MIME email, appends AI disclaimer at send level, sends reply maintaining thread headers (In-Reply-To, References)
- Implement `disclaimer.py` — single source of truth for the mandatory AI disclaimer text
- Write unit tests for email parser covering plain text, multipart, and reply-chain emails

### MD Files for Phase 2
- `PHASE2_IMAP_SMTP.md` — IMAP poller logic, SMTP sender logic, EmailObject schema, disclaimer spec, threading headers explanation

---

## Phase 3 — SQLite Session Memory & Checkpointer

- Define full SQLite schema — `sessions` table and `participant_preferences` table
- Implement `db.py` — initializes database, creates tables on first run
- Implement `checkpointer.py` — `save_state(thread_id, state)`, `load_state(thread_id)`, `clear_state(thread_id)`
- Implement `preference_store.py` — `store_preferences(email, accepted_slot)`, `load_preferences(email)`, `get_historical_slots(email)`
- Define `AgentState` typed dict in `models.py`
- Define `TimeSlot` typed dict in `models.py`
- Write unit tests for checkpointer — save, load, update, clear cycle

### MD Files for Phase 3
- `PHASE3_SESSION_MEMORY.md` — full SQLite schema, AgentState schema, TimeSlot schema, checkpointer function signatures, preference store function signatures

---

## Phase 4 — Gemini LLM Integration

- Implement `gemini_client.py` — initializes Gemini 2.0 Flash client using OpenAI-compatible API endpoint, handles retries and timeouts
- Implement `tool_caller.py` — sends tool schema to Gemini, parses structured tool call response, dispatches to tool registry, returns tool result
- Implement `prompt_builder.py` — constructs system prompt and user message for each node type, injects relevant session context
- Implement confidence threshold check — if Gemini classification confidence is below threshold, log and skip action rather than acting on bad data

### MD Files for Phase 4
- `PHASE4_GEMINI_INTEGRATION.md` — Gemini client setup, tool calling flow, prompt templates per node, confidence threshold logic

---

## Phase 5 — Core Tool Registry (Required Deliverables)

This phase implements all four tool modules covering everything the problem statement mandates.

- Implement `tools/email_coordinator.py`
  - `classify(body, subject)` — Gemini call, returns intent: scheduling | update_request | reschedule | cancellation | noise
  - `parse_availability(text, sender_tz)` — dateparser + pytz, returns list of UTC TimeSlot objects
  - `detect_ambiguity(text)` — returns bool + clarifying question string to ask the participant
  - `get_thread_history(thread_id)` — reads stored thread emails from SQLite
  - `send_reply(to, subject, body, thread_id)` — calls smtp_sender, disclaimer appended

- Implement `tools/calendar_manager.py`
  - `check_duplicate(title, start_utc, participants)` — Calendar API events.list query before any insert
  - `create_event(title, start_utc, end_utc, participants, description)` — Calendar API events.insert
  - `send_invite(event_id, participants)` — dispatches Google Calendar invitations to all participants

- Implement `tools/coordination_memory.py`
  - `track_participant_slots(thread_id, email, slots)` — writes parsed UTC slots into session state in SQLite
  - `find_overlap(thread_id)` — computes intersection of all participant slot lists from session
  - `rank_slots(candidate_slots, preferences)` — weighted scoring, returns best TimeSlot with human-readable reason string

- Implement `tools/thread_intelligence.py`
  - `summarise_thread(thread_id)` — reads full thread history, Gemini call, returns contextual summary
  - `get_scheduling_status(thread_id)` — returns current session state summary string
  - `detect_cancellation(body)` — Gemini call, returns bool

- Implement `tool_registry.py` — central dict mapping tool names to callable functions, generates JSON schema for each tool for Gemini

### MD Files for Phase 5
- `PHASE5_TOOL_REGISTRY.md` — all four modules, every function signature with inputs and outputs, Gemini JSON schema format
- `PHASE5_RANK_SLOTS.md` — rank_slots() scoring algorithm, weight table, soft conflict penalty logic, failure threshold behavior

---

## Phase 6 — Agent State Machine (Core Engine)

- Implement `agent/nodes.py` — all core node functions:
  - `triage_node` — classify intent via Gemini, set state intent field
  - `coordination_node` — parse availability from email body, track slots per participant, check if all participants have responded
  - `ambiguity_node` — detect ambiguity in a participant reply, draft clarifying question, set outbound_draft, send it back to that specific participant only
  - `overlap_node` — call find_overlap across all participant slots stored in session
  - `rank_slots_node` — call rank_slots, store ranked_slot in state, check attendance threshold — if below 50% email all participants asking for more availability windows and restart coordination round
  - `calendar_node` — call check_duplicate, create_event, send_invite
  - `thread_intelligence_node` — call summarise_thread, set outbound_draft with summary
  - `rewrite_node` — polish outbound_draft tone via Gemini, append disclaimer
  - `send_node` — call send_reply via smtp_sender
  - `error_node` — log the issue, skip action, mark session with error flag

- Implement `agent/router.py` — all routing functions:
  - `route_by_intent(state)` — maps intent to next node
  - `route_by_completeness(state)` — checks if all participants responded, routes to overlap_node or stays waiting for remaining replies
  - `route_by_threshold(state)` — checks attendance score, routes to calendar_node or restarts coordination round

- Implement `agent/graph.py` — GRAPH dict mapping node names to routing functions, END constant
- Implement `agent/loop.py` — `run(thread_id, email_object)` — loads state, executes node loop, checkpoints after every node, terminates on END
- Write integration tests — mock Gemini and API calls, verify state transitions through full scheduling flow

### MD Files for Phase 6
- `PHASE6_AGENT_STATE_MACHINE.md` — all node functions with input/output state changes, full GRAPH routing table, AgentLoop execution flow, state transition diagram

---

## Phase 7 — Main Entry Point & Poller Orchestration

- Implement `main.py` — entry point, starts IMAP poller loop, wires poller callback to agent loop
- Implement async architecture — IMAP poller runs in asyncio loop, each new email spawns an async task calling `agent/loop.py run()`
- Implement graceful shutdown — catches SIGINT, stops poller, closes DB connections cleanly
- End-to-end smoke test — send a real test email to the MailMind address, verify full flow runs: classify → coordinate → overlap → rank → calendar → confirm email sent

### MD Files for Phase 7
- `PHASE7_MAIN_AND_ORCHESTRATION.md` — main.py wiring diagram, async task model, poller-to-agent handoff, graceful shutdown sequence, smoke test steps

---

## Phase 8 — Bonus: Multi-Timezone Optimization

- Implement timezone detection from email headers and explicit timezone mentions in body text
- Store detected timezone per participant in `participant_preferences` table
- All overlap computation done in UTC internally, converted back to each participant's local timezone in outbound emails only
- Implement `timezone_utils.py` — `detect_timezone(text, headers)`, `to_utc(slot, tz)`, `to_local(slot, tz)`

### MD Files for Phase 8
- `PHASE8_TIMEZONE.md` — timezone detection logic, UTC normalisation flow, per-participant timezone storage, display conversion in outbound emails

---

## Phase 9 — Bonus: Preferred Working Hours Learning

- Implement auto-learning in `store_preferences(email, accepted_slot)` — called after every confirmed meeting, records accepted slot hour and day into `historical_slots` JSON list per participant in SQLite
- Implement `suggest_optimal_time(email)` in thread_intelligence — reads historical_slots, extracts most common hour buckets and day patterns, returns PreferenceProfile
- Wire PreferenceProfile into `rank_slots()` as additional scoring weight — first interaction falls back to default scoring, improves automatically from second coordination onwards
- Define `PreferenceProfile` typed dict in `models.py`

### MD Files for Phase 9
- `PHASE9_PREFERENCE_LEARNING.md` — historical_slots schema, suggest_optimal_time algorithm, PreferenceProfile structure, how it integrates into rank_slots() scoring

---

## Phase 10 — Bonus: VIP Priority Scheduling

- Add `vip` boolean field to `participant_preferences` table
- Implement `check_vip_status(email)` in coordination_memory — returns VIP boolean
- Wire VIP weight fully into rank_slots() — VIP participant availability is always scored before non-VIP slots
- VIP list configurable via `.env` as comma-separated email addresses loaded at startup into participant_preferences on first run

### MD Files for Phase 10
- `PHASE10_VIP_SCHEDULING.md` — VIP flag storage, VIP weight in rank_slots(), VIP list config in .env

---

## Phase 11 — Bonus: Ambiguity Detection Hardening

- Refine `detect_ambiguity` with a patterns library of common vague expressions and the specific clarifying question to generate for each
- Implement per-participant ambiguity round tracking in session state — if same participant replies ambiguously twice, escalate to a more explicit question with concrete time window examples
- Implement maximum clarification rounds limit — after 2 rounds of ambiguity from same participant, mark them as non-responsive, proceed with remaining participants' slots
- Wire non-responsive flag into rank_slots() — non-responsive participants excluded from attendance computation

### MD Files for Phase 11
- `PHASE11_AMBIGUITY_DETECTION.md` — ambiguity patterns library, clarification round tracking in session state, escalation behavior, non-responsive participant handling in rank_slots()

---

## Execution Sequence Summary

```
Phase 1   →   Foundation & Config
Phase 2   →   IMAP + SMTP (email in and out)
Phase 3   →   SQLite Memory (session persistence)
Phase 4   →   Gemini LLM Integration
Phase 5   →   Core Tool Registry (all required features)
Phase 6   →   Agent State Machine (core engine)
Phase 7   →   Main Entry + Orchestration (system runs end to end)
─────────────────────────────────────────────────────────────
Phase 8   →   Bonus: Multi-Timezone Optimization
Phase 9   →   Bonus: Preferred Working Hours Learning
Phase 10  →   Bonus: VIP Priority Scheduling
Phase 11  →   Bonus: Ambiguity Detection Hardening
```

Phases 1–7 deliver a fully working system covering every mandatory problem statement requirement.
Phases 8–11 layer all bonus features on top of a stable, tested core.

---

*MailMind | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
