# MailMind — Complete Idea & Implementation Document
**Team TRIOLOGY | PCCOE Pune | Problem Statement 03 — AI Email Coordination Assistant**

---

## 1. What MailMind Is

MailMind is a fully autonomous AI agent that operates through a dedicated Gmail address and acts as a digital executive assistant for scheduling, coordination, and thread intelligence. You CC it on any email thread and it takes over completely — reading every email in natural language, coordinating across all participants, finding the best meeting time, creating the Google Calendar event, sending invites, and confirming — all without any human action after the initial CC.

The key distinction from all existing tools is that MailMind lives inside email itself. Participants do not need any account, link, or form. They just reply to emails the way they always have and the agent handles everything invisibly in the background.

---

## 2. Problem It Solves

- 43% of workers spend more than 3 hours every week just on scheduling and organizing meetings
- US businesses lose $37 billion annually to unproductive meeting coordination alone
- Existing tools fail — Calendly requires accounts and links, ChatGPT/Copilot still need a human to send, scheduling bots break on complex multi-day threads
- MailMind is the only solution that handles the full coordination loop end-to-end with persistent memory, requiring zero tool adoption from participants

---

## 3. Architecture Overview

MailMind is a standalone Python backend service with the following core components:

```
IMAP Poller (imaplib)
    ↓
Email Parser + Normaliser
    ↓
Agent State Machine (custom directed state graph — no LangGraph)
    ↓  ←→  SQLite Session Memory (checkpointing per thread ID)
Tool Registry (4 modules)
    ↓
Telegram Approval Gate
    ↓
SMTP Send (smtplib) + Google Calendar API
    ↓
Admin Dashboard (FastAPI + React)
```

### Core Components

| Component | Role |
|---|---|
| IMAP Poller | Polls Gmail inbox every 30 seconds via imaplib — no webhook, no cloud setup |
| Email Parser | Normalises raw MIME email into typed Python object |
| Agent State Machine | Custom directed state graph — perceive → think → act → observe loop |
| SQLite Checkpointer | Persists full agent state per Gmail thread ID across days |
| Tool Registry | Four skill modules exposed as callable functions to the LLM |
| Conflict Resolution Engine | rank_slots() — weighted scoring to pick the optimal meeting time |
| Telegram Approval Gate | Operator notified before every outbound email fires |
| Admin Dashboard | FastAPI REST + WebSocket + React frontend at localhost:8000/admin |

---

## 4. Email Ingestion — IMAP Polling (No Pub/Sub)

### Why IMAP over Gmail Pub/Sub
- Zero Google Cloud project required
- No Pub/Sub topic or subscription setup
- No webhook server exposure
- No ngrok or Tailscale tunneling needed
- Runs entirely on local machine with just a Gmail address + App Password in `.env`
- Uses Python stdlib only — `imaplib` and `email` — zero extra dependencies for ingestion

### How It Works
```
Every 30 seconds:
    imaplib.IMAP4_SSL → imap.gmail.com
    Search UNSEEN emails in inbox
    For each unseen email:
        Fetch full MIME content
        Parse with email stdlib module
        Extract: sender, subject, body, thread ID (References header), timestamp
        Mark as SEEN
        Pass normalised EmailObject to agent state machine
```

### EmailObject (typed dict)
```python
{
  "message_id": str,        # unique Gmail message ID
  "thread_id": str,         # Gmail thread ID — used as session key
  "sender_email": str,
  "sender_name": str,
  "subject": str,
  "body": str,
  "timestamp": datetime,    # UTC normalised
  "in_reply_to": str,       # parent message ID
  "recipients": list[str]   # all CC and TO addresses
}
```

### SMTP for Sending
- `smtplib.SMTP_SSL` → smtp.gmail.com:465
- Gmail App Password stored in `.env`
- AI disclaimer appended at send level — cannot be bypassed
- Both ingestion (IMAP) and sending (SMTP) use stdlib only

---

## 5. Agent State Machine — Custom Directed State Graph

This replaces LangGraph entirely. The core logic of LangGraph is a directed state graph with conditional routing — implemented here in pure Python.

### AgentState (typed dict)
```python
{
  "thread_id": str,
  "intent": str,                    # scheduling | update_request | reschedule | cancellation | noise
  "participants": list[str],
  "slots_per_participant": dict,    # { email: [TimeSlot, ...] }
  "pending_responses": list[str],
  "ranked_slot": TimeSlot | None,
  "outbound_draft": str | None,
  "approval_status": str,           # pending | approved | rejected | timeout
  "preferences": dict,              # { email: { preferred_hours, blocked_days, vip } }
  "history": list[dict],            # full LLM conversation history
  "current_node": str,
  "error": str | None
}
```

### Graph Nodes

| Node | What It Does |
|---|---|
| `triage_node` | Classifies email intent using Gemini — scheduling / update_request / reschedule / cancellation / noise |
| `coordination_node` | Extracts availability from free-form text using dateparser + pytz, stores slots in session memory |
| `ambiguity_node` | Detects vague time expressions, generates one specific clarifying question, sends it, waits |
| `overlap_node` | Computes intersection of all participant time slots from SQLite session |
| `rank_slots_node` | Scores all valid windows using rank_slots() and picks the optimal slot |
| `calendar_node` | Checks for duplicate events, creates Calendar event, dispatches invites |
| `thread_intelligence_node` | Reads full email history, generates contextual summary for update requests |
| `rewrite_node` | Polishes outbound email tone, appends mandatory AI disclaimer |
| `approval_node` | Sends draft to Telegram, waits up to 5 minutes, auto-sends on timeout |
| `send_node` | Fires email via smtplib |
| `error_node` | Flags low-confidence classifications to operator via Telegram instead of acting |

### Routing Logic
```python
GRAPH = {
    "triage_node": route_by_intent,
    "coordination_node": route_by_completeness,
    "ambiguity_node": "send_node",          # send clarifying question then wait
    "overlap_node": "rank_slots_node",
    "rank_slots_node": route_by_threshold,  # threshold met → calendar_node | else → coordination_node
    "calendar_node": "rewrite_node",
    "thread_intelligence_node": "rewrite_node",
    "rewrite_node": "approval_node",
    "approval_node": route_by_approval,     # approved/timeout → send_node | rejected → rewrite_node
    "send_node": END,
    "error_node": END
}
```

### AgentLoop
```python
def run(thread_id, email_object):
    state = load_state(thread_id) or init_state(thread_id, email_object)
    state["current_node"] = "triage_node"
    while state["current_node"] != END:
        node_fn = NODE_REGISTRY[state["current_node"]]
        state = node_fn(state)
        save_state(thread_id, state)          # checkpoint after every node
        state["current_node"] = GRAPH[state["current_node"]](state)
```

---

## 6. SQLite Session Memory + Checkpointing

### Why SQLite
- Zero infrastructure — runs alongside the agent on same machine
- LangGraph's checkpointer concept implemented natively
- Thread ID is the session key — every Gmail thread maps to one persistent session
- Survives process restarts — agent picks up exactly where it left off

### Schema
```sql
CREATE TABLE sessions (
    thread_id TEXT PRIMARY KEY,
    state_json TEXT,              -- full AgentState serialised as JSON
    updated_at DATETIME
);

CREATE TABLE participant_preferences (
    email TEXT PRIMARY KEY,
    preferred_hours_start INTEGER,   -- 0-23 UTC
    preferred_hours_end INTEGER,
    blocked_days TEXT,               -- JSON list e.g. ["Friday"]
    vip BOOLEAN DEFAULT FALSE,
    historical_slots TEXT            -- JSON list of accepted UTC slots for learning
);
```

### Checkpointer Functions
```python
save_state(thread_id, state)    # serialise state dict → JSON → upsert sessions table
load_state(thread_id)           # load JSON → deserialise → return AgentState | None
clear_state(thread_id)          # called after meeting confirmed and thread closed
```

---

## 7. Tool Registry — Four Skill Modules

All agent capabilities are plain Python functions. Gemini receives their signatures and docstrings as JSON schema and decides autonomously which to call and with what arguments.

### email_coordinator
- `classify(body, subject)` — returns intent string using Gemini
- `parse_availability(text, sender_tz)` — extracts time slots using dateparser + pytz, returns list of UTC TimeSlot objects
- `detect_ambiguity(text)` — returns True + clarifying question string if availability is too vague
- `get_thread_history(thread_id)` — reads all stored emails for this thread from SQLite
- `send_reply(to, subject, body, thread_id)` — sends via smtplib, appends AI disclaimer

### calendar_manager
- `check_duplicate(title, start_utc, participants)` — queries Calendar API events.list before any insert
- `create_event(title, start_utc, end_utc, participants, description)` — Calendar API v3 events.insert
- `send_invite(event_id, participants)` — dispatches Google Calendar invitations

### coordination_memory
- `track_participant_slots(thread_id, email, slots)` — stores parsed UTC slots in SQLite session
- `find_overlap(thread_id)` — computes intersection of all participant slot lists
- `rank_slots(candidate_slots, preferences)` — weighted scoring, returns ranked TimeSlot with reason
- `store_preferences(email, accepted_slot)` — auto-updates historical_slots after confirmed meeting
- `check_vip_status(email)` — returns VIP boolean from participant_preferences

### thread_intelligence
- `summarise_thread(thread_id)` — reads full thread history, generates contextual summary via Gemini
- `get_scheduling_status(thread_id)` — returns current session state summary
- `detect_cancellation(body)` — identifies cancellation intent
- `suggest_optimal_time(email)` — reads historical_slots to bias next scheduling round

---

## 8. Conflict Resolution Engine — rank_slots()

Deterministic Python function. No LLM involved.

### Scoring Criteria

| Criterion | Weight | What It Measures |
|---|---|---|
| Attendance maximisation | Highest | How many participants are available in this slot |
| Preference alignment | Second | Whether slot falls in each participant's stored preferred hours |
| VIP availability | Third | Whether designated VIP participants are available |
| Chronological priority | Lowest | How early in the week — tiebreaker only |

### Soft Conflict Handling
- Preference violations (e.g. "never Fridays", "not before 10am IST") receive a penalty score but are NOT eliminated
- They remain as fallback options if no clean slot exists

### Failure Threshold
- If no slot scores above 50% attendance threshold → agent emails all participants asking for additional availability windows → restarts coordination round

### Learning Mechanism
- After every confirmed meeting, `store_preferences()` records the accepted slot's hour and day in `historical_slots`
- From the second coordination onwards, `suggest_optimal_time()` reads this history and biases `rank_slots()` scoring toward observed preferred patterns automatically
- First interaction = no history, falls back to pure weighted scoring
- This satisfies the bonus feature: "Maintain memory of preferred working hours"

---

## 9. Telegram Approval Gate

### Flow
```
rewrite_node produces outbound_draft
    ↓
Telegram Bot sends draft to operator with Approve / Reject buttons
    ↓
asyncio.Event pauses execution — 5 minute window
    ↓
Approve → send_node fires immediately
Reject + reason → reason fed back into rewrite_node → revised draft → resubmit
No response in 5 min → auto-send (system stays fully autonomous)
```

### Why Telegram
- Bot API is free
- Instant mobile notifications
- Inline reply buttons for approve/reject
- Persistent audit log of every operator decision
- Works when operator is offline — auto-send fallback means system never stalls

---

## 10. Preferred Working Hours — Learning Mechanism

This satisfies the bonus feature explicitly:

- `participant_preferences` table stores `historical_slots` as a JSON list of UTC datetimes from all past accepted meetings per participant
- `store_preferences(email, accepted_slot)` is called automatically after every confirmed meeting — no manual input needed
- `suggest_optimal_time(email)` aggregates historical slots → extracts most common hour buckets and day patterns → returns a PreferenceProfile
- PreferenceProfile is passed into `rank_slots()` as additional scoring weight alongside explicit stored preferences
- Result: the system learns each participant's actual availability patterns from real coordination history and improves slot selection over time automatically

---

## 11. Security and Configuration

### Credential Management
- All credentials in `.env` — never hardcoded
- `.env` listed in `.gitignore`
- `config.py` validates all required variables at startup — fails loudly with a clear error if anything is missing
- Gmail App Password scoped to IMAP read + SMTP send only
- Google Calendar OAuth 2.0 scoped to calendar events only — token stored in `token.json` locally
- No Google Cloud project required for email ingestion

### .env Variables Required
```
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
GEMINI_API_KEY=
GOOGLE_CALENDAR_CREDENTIALS_PATH=
TELEGRAM_BOT_TOKEN=
TELEGRAM_OPERATOR_CHAT_ID=
IMAP_POLL_INTERVAL_SECONDS=30
APPROVAL_TIMEOUT_SECONDS=300
ATTENDANCE_THRESHOLD=0.5
```

### Operator Setup — Four Steps
1. Clone the repository
2. Fill in `.env` with the above values
3. Run `python setup.py` — validates all credentials, tests every API connection, prints success/failure per check
4. Run `python main.py` — agent starts polling, admin dashboard available at `localhost:8000/admin`

### Data Privacy
- Raw email body is processed in memory only — not persisted after processing
- SQLite stores only structured coordination data: participant emails, parsed UTC slots, preferences, session state
- No email content stored after processing is complete

---

## 12. Admin Dashboard

React frontend served by FastAPI at `localhost:8000/admin`. No separate deployment needed.

| Panel | What It Shows |
|---|---|
| Live Activity Feed | Every email received, classified, and acted on in real time via WebSocket |
| Thread Management | All active sessions — click any to see full timeline and agent decisions |
| Participant Memory | Stored preferences per participant — toggle VIP, edit blocked days |
| Approval Queue | Outbound emails pending Telegram approval — approve/reject/edit from dashboard |
| Configuration Panel | Edit VIP list, meeting duration, approval timeout, attendance threshold live |
| Analytics | Meetings coordinated, average coordination time, ambiguity detection rate |

---

## 13. Complete Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Language | Python | All backend components |
| Email ingestion | imaplib (stdlib) | Zero dependencies, no cloud setup, just App Password |
| Email sending | smtplib (stdlib) | Already in standard library |
| Email parsing | email (stdlib) | MIME parsing built in |
| Web framework | FastAPI | Admin dashboard API + WebSocket |
| LLM | Gemini 2.0 Flash | Free tier, OpenAI-compatible API, fast inference |
| Agent state machine | Custom Python | Pure directed state graph — no LangGraph |
| Session memory | SQLite | Zero infrastructure, stdlib via sqlite3 |
| Calendar | Google Calendar API v3 | Event creation + invite dispatch |
| Approval gate | Telegram Bot API | Free, instant, mobile, inline buttons |
| Time parsing | dateparser + pytz | Natural language time expressions + UTC normalisation |
| Config | python-dotenv | Credential loading from .env |
| Frontend | React | Admin dashboard |
| Tunneling | None required | IMAP polling eliminates inbound webhook |

---

## 14. Evaluation Criteria Coverage

### All 8 Required Deliverables

| Requirement | Implementation |
|---|---|
| Dedicated assistant email identity | Dedicated Gmail address — MailMind operates exclusively through it |
| Autonomous meeting coordination | Full loop from first email to confirmed invite — zero human involvement |
| Availability extraction and overlap detection | dateparser + pytz + overlap_node + rank_slots() |
| Google Calendar event creation and invite dispatch | calendar_manager module via Calendar API v3 |
| Thread-aware contextual summaries | thread_intelligence module reads full stored thread history |
| Mandatory AI disclaimer on all outbound emails | Appended at send level in send_reply — cannot be bypassed |
| Secure credential management | .env + config.py + OAuth 2.0 scoped tokens + setup.py validation |
| Duplicate meeting prevention | check_duplicate queries Calendar before every event creation |

### All 5 Bonus Features

| Bonus Feature | Implementation |
|---|---|
| Multi-timezone optimisation | Full UTC normalisation via pytz before any overlap computation |
| Suggest optimal times from history | suggest_optimal_time reads historical_slots, biases rank_slots() scoring |
| VIP priority scheduling | VIP weight in rank_slots() + vip flag in participant_preferences |
| Detect ambiguous availability | ambiguity_node — sends one specific clarifying question and waits |
| Human override capability | Telegram approval gate with 5 minute window + auto-send fallback |

---

## 15. Key Challenges and How They Are Addressed

| Challenge | Solution |
|---|---|
| Vague time expressions like "sometime next week" | dateparser + pytz normalises everything to UTC before any computation |
| Multiple valid time slots exist | rank_slots() scores across 4 weighted criteria — picks optimal not just first overlap |
| Coordination spans days with many emails | SQLite session memory tied to thread ID — agent never loses context |
| Agent sends a wrong email | Telegram approval gate with 5 minute correction window before any email fires |
| Ambiguous availability from a participant | ambiguity_node sends one specific clarifying question and waits for reply |
| Same meeting created twice | Calendar queried before every event creation — if match exists, skip and send status reply |
| Operator has no visibility | Live admin dashboard shows every action and decision in real time |
| Gemini misclassifies or low confidence | Agent flags email to operator via Telegram instead of acting — human confirms |
| Complex infra setup | IMAP polling replaces Pub/Sub entirely — just Gmail App Password in .env |

---

## 16. What Makes MailMind Different

- **Email-native** — participants never leave their inbox, no accounts, no links, no forms
- **Persistent memory** — the only coordination tool that maintains full context across multi-day threads
- **Learns over time** — preferred working hours update automatically from observed coordination patterns
- **$0 running cost** — Gemini free tier + all stdlib email tools + SQLite
- **Soft conflict penalties** — never blindly picks the first overlap, always picks the optimal slot
- **Fully autonomous AND operator-controlled** — these are not contradictions — autonomous by default, deferring to operator when available
- **Zero infrastructure** — runs on any local machine or basic VM, no cloud services beyond the APIs

---

*MailMind | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
