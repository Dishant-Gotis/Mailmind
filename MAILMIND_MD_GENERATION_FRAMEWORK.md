# MAILMIND_MD_GENERATION_FRAMEWORK.md
## A Self-Contained Generation Framework for All 11 Phase MD Files
**Feed this file + MAILMIND_IDEA.md + MAILMIND_IMPLEMENTATION_PLAN.md to any LLM to generate any phase MD file with full depth**

---

## HOW TO USE THIS FRAMEWORK

You are an expert Python backend engineer and AI systems architect.
You have been given three files:
1. `MAILMIND_IDEA.md` — the complete project idea, architecture, all component specs, schemas, algorithms, and design decisions
2. `MAILMIND_IMPLEMENTATION_PLAN.md` — the phased implementation plan listing what to build in each phase and which MD file to generate
3. This framework file — which tells you exactly HOW to generate each phase MD file

Your job is to generate ONE phase MD file at a time when asked.
The user will say: **"Generate [PHASE_X_FILENAME.md]"**
You will follow the universal generation protocol below, then apply the phase-specific depth rules for that file.

---

## PART 1 — UNIVERSAL GENERATION PROTOCOL

Every MD file you generate must follow these non-negotiable rules regardless of which phase it is for.

### Rule 1 — Source of Truth Hierarchy
When generating any MD file, pull information in this priority order:
1. `MAILMIND_IDEA.md` — canonical source for all schemas, algorithms, component specs, rationale
2. `MAILMIND_IMPLEMENTATION_PLAN.md` — canonical source for what belongs in this phase and what the MD file must cover
3. Your own knowledge of Python, FastAPI, SQLite, imaplib, smtplib, Gemini API, Google Calendar API — fill in implementation detail that the idea doc implies but does not spell out explicitly

Never contradict either source file. Never invent components that are not in the idea doc. Never add features that are not in the implementation plan.

### Rule 2 — Depth Standard
Every MD file must be implementation-ready. A developer must be able to open this MD file and write the actual code without asking any clarifying questions. This means:
- Every function must have its full signature — name, all parameters with types, return type
- Every data structure must have its full schema — all fields, all types, all default values
- Every algorithm must have its full logic — not "compute overlap" but the exact steps to compute overlap
- Every API call must have its exact request shape and expected response shape
- Every file must list all imports it will need
- Every decision must have its rationale stated

### Rule 3 — Structure Standard
Every MD file must have these sections in this order:
1. **Header** — phase number, file name, what this file covers, which files in the codebase it documents
2. **Purpose** — one paragraph explaining what this phase accomplishes and why it matters for the overall system
3. **Dependencies** — what must exist before this phase can be implemented (previous phases, external credentials, installed packages)
4. **Component Sections** — one section per file or module being documented (see Phase-Specific Rules below)
5. **Data Flow** — how data enters, transforms, and exits this component in the context of the full system
6. **Error Handling** — every failure mode specific to this phase and exactly what to do when it occurs
7. **Test Cases** — minimum 3 concrete test scenarios with inputs and expected outputs specific to this phase
8. **Integration Checklist** — a checklist of exactly what must be true before this phase is considered complete and ready for the next phase

### Rule 4 — Code Snippet Standard
Every MD file must include Python code snippets for:
- Every class or TypedDict definition — complete, copy-pasteable
- Every function — complete signature with docstring, parameter descriptions, return description
- Every non-trivial algorithm — full pseudocode or actual Python implementation
- Every external API call — exact call with real parameter names, not placeholders

Snippets must use proper Python type hints throughout. No `Any` unless genuinely unavoidable.

### Rule 5 — Naming Consistency
All file names, function names, variable names, class names, and field names used in a generated MD file must exactly match what is specified in `MAILMIND_IDEA.md`. If the idea doc says `track_participant_slots`, never write `trackParticipantSlots` or `store_slots`. Consistency is mandatory because multiple agents may generate different phase files and they must all integrate cleanly.

### Rule 6 — Cross-Phase References
When a component in this phase depends on something from a previous phase, explicitly state:
- Which file from the previous phase it imports from
- Which specific class, function, or constant it uses
- What it expects that import to provide

This ensures no integration gaps between phases.

---

## PART 2 — PHASE-SPECIFIC DEPTH RULES

These rules tell you exactly what depth and content each specific MD file must contain.
Apply the Universal Protocol from Part 1 PLUS the rules below for the requested phase.

---

### PHASE1_PROJECT_STRUCTURE.md

**What to generate:**
- Full directory tree of the entire MailMind project — every folder, every file, annotated with one-line purpose
- Exact `requirements.txt` content — every package with pinned version and reason for inclusion
- Complete `.env.example` — every variable name, a description comment above each one, an example value
- Complete `config.py` implementation — the Config class using pydantic-settings or python-dotenv, every field typed, validation logic, startup error messages
- Complete `exceptions.py` — every custom exception class the system will use across all phases, with docstring
- Complete `logger.py` — logging setup, format string, how thread_id gets tagged into every log line
- Complete `.gitignore` content

**Depth markers — must be present:**
- The directory tree must go three levels deep minimum
- `config.py` must show the actual validation logic that raises a human-readable error — not just `os.getenv`
- Every package in `requirements.txt` must have an inline comment explaining why it is needed
- Every exception class must include what scenario triggers it and what the catcher should do

---

### PHASE1_CONFIG_AND_ENV.md

**What to generate:**
- Table of every `.env` variable: variable name | type | required/optional | what it controls | how to obtain it | example value
- Step-by-step instructions for obtaining each credential: Gmail App Password setup, Gemini API key, Google Calendar OAuth credentials.json
- Complete `setup.py` implementation — every API connection test, what a passing result looks like, what a failing result looks like, exit codes
- Startup validation flow diagram in text — what happens in what order when `python main.py` is run before any email is processed

**Depth markers — must be present:**
- Gmail App Password setup must include the exact Google Account settings path to enable it
- Google Calendar OAuth must include the exact scopes string to request
- `setup.py` must test each connection independently and report each one — one failure must not block the others from being tested

---

### PHASE2_IMAP_SMTP.md

**What to generate:**
- Complete `imap_poller.py` implementation — class or function structure, IMAP4_SSL connection, SEARCH UNSEEN logic, fetch loop, SEEN marking, 30-second poll interval with asyncio.sleep, reconnect-on-disconnect logic
- Complete `email_parser.py` implementation — MIME parsing, plain text extraction from multipart, thread ID extraction from References header fallback to Message-ID, timezone-aware datetime parsing from Date header
- Complete `EmailObject` TypedDict — every field, type, description
- Complete `smtp_sender.py` implementation — SMTP_SSL connection, MIMEMultipart construction, In-Reply-To and References headers for threading, disclaimer append logic, connection reuse vs reconnect decision
- Complete `disclaimer.py` — the exact disclaimer text and the function that appends it
- Exact header names used for Gmail thread continuity — References, In-Reply-To, Message-ID — and how each is read and written
- Unit test cases for email_parser covering: plain text email, multipart email, reply in a thread, email with no References header

**Depth markers — must be present:**
- IMAP SEARCH command exact syntax
- How to handle the case where References header is absent — fallback strategy
- How to extract plain text from a multipart/alternative email that has both text/plain and text/html parts
- The exact SMTP connection sequence — connect, login, sendmail, quit

---

### PHASE3_SESSION_MEMORY.md

**What to generate:**
- Complete SQL DDL for both tables — `sessions` and `participant_preferences` — with all columns, types, constraints, indexes
- Complete `db.py` — connection factory, table creation on first run, connection context manager
- Complete `checkpointer.py` — `save_state`, `load_state`, `clear_state` with full JSON serialisation/deserialisation logic including datetime handling
- Complete `AgentState` TypedDict — every field, type, description, which node sets it, which node reads it
- Complete `TimeSlot` TypedDict — every field, type, description
- Complete `preference_store.py` — all four functions with full SQLite query logic
- How thread_id is derived from email headers — the exact logic
- Unit test cases for checkpointer: save then load returns identical state, update overwrites correctly, clear removes state, load on nonexistent thread returns None

**Depth markers — must be present:**
- How Python datetime objects are serialised to SQLite TEXT and deserialised back — exact format string
- How the `historical_slots` JSON list in participant_preferences is read, appended to, and written back atomically
- What happens if `save_state` is called concurrently for the same thread_id — how to handle this

---

### PHASE4_GEMINI_INTEGRATION.md

**What to generate:**
- Complete `gemini_client.py` — client initialization using OpenAI-compatible endpoint, model string, retry logic with exponential backoff, timeout handling
- Complete `tool_caller.py` — how tool schemas are formatted for Gemini, how the response is parsed to extract tool name and arguments, how the tool is dispatched via tool_registry, how the result is returned
- Complete `prompt_builder.py` — the system prompt template, how session context is injected, one complete prompt example per node type: triage, coordination, ambiguity, rewrite, summarise
- Confidence threshold implementation — how Gemini's response is checked for confidence, what threshold value is used, what happens below threshold
- Exact Gemini API endpoint URL and authentication header format
- How to handle Gemini returning text instead of a tool call — fallback parsing logic

**Depth markers — must be present:**
- The exact JSON schema format for a tool definition sent to Gemini
- The exact structure of a Gemini tool call response — how to extract function name and arguments
- Complete system prompt for the triage node — full text, not a summary
- Retry strategy — exactly how many retries, what delays, which errors are retryable

---

### PHASE5_TOOL_REGISTRY.md

**What to generate:**
- Complete function signatures for every function across all four tool modules — `email_coordinator`, `calendar_manager`, `coordination_memory`, `thread_intelligence`
- For each function: full signature, complete docstring, parameter descriptions, return type, what it reads from SQLite, what it writes to SQLite, what external API it calls if any
- Complete `tool_registry.py` — the TOOL_REGISTRY dict, the `get_schema(tool_name)` function, the `call_tool(name, args)` dispatcher
- How the @tool decorator pattern works — or how function signatures + docstrings are converted to JSON schema without a decorator
- How `send_reply` enforces the disclaimer — the exact append logic so it cannot be bypassed even if the caller does not include it

**Depth markers — must be present:**
- The exact JSON schema generated for at least two tools — one simple, one complex — showing how Python types map to JSON schema types
- The complete implementation of `parse_availability` including how dateparser is called and how results are normalised to UTC via pytz
- The complete implementation of `find_overlap` — the exact algorithm for computing time slot intersection across multiple participants

---

### PHASE5_RANK_SLOTS.md

**What to generate:**
- Complete `rank_slots()` function implementation — full Python code, not pseudocode
- The scoring algorithm in full detail — how each of the four criteria is computed, what the weight values are as constants, how the weighted sum is calculated
- Soft conflict penalty implementation — how preference violations reduce score without eliminating the slot, the exact penalty value
- Attendance threshold check — the exact comparison, what happens when no slot meets the threshold, the exact email sent to participants requesting more windows
- How the human-readable reason string is constructed — what it contains and how it is generated
- The `TimeSlot` and `PreferenceProfile` schemas used as inputs to rank_slots
- Three worked examples — inputs with specific slots and preferences, step-by-step scoring, expected output

**Depth markers — must be present:**
- The actual numeric weight values for all four criteria — not relative descriptions but actual floats that sum to 1.0
- The exact formula: `score = (attendance_weight * attendance_score) + (preference_weight * preference_score) + (vip_weight * vip_score) + (chrono_weight * chrono_score) - penalty`
- What "chronological priority" means as a computable value — the exact calculation
- Edge case: only one participant — how rank_slots behaves

---

### PHASE6_AGENT_STATE_MACHINE.md

**What to generate:**
- Complete implementation of every node function in `agent/nodes.py` — full Python, not pseudocode — every state read, every tool call, every state write
- Complete `agent/router.py` — every routing function with its exact conditional logic spelled out
- Complete `agent/graph.py` — the GRAPH dict, the END sentinel, the node name constants
- Complete `agent/loop.py` — the `run()` function with the while loop, checkpoint-after-every-node logic, exception handling
- State transition diagram in ASCII — showing every node and every possible edge between nodes
- What happens in `coordination_node` when only some participants have responded — how the agent waits and what triggers re-entry
- What the `error_node` logs and what it writes to session state

**Depth markers — must be present:**
- The exact state fields read and written by each node — in a table: node | reads from state | writes to state
- The complete routing logic for `route_by_completeness` — what it checks in state to know if all participants responded
- How the loop handles an exception thrown inside a node — does it retry, skip, or terminate
- The exact condition that causes `rank_slots_node` to restart the coordination round vs proceed to calendar

---

### PHASE7_MAIN_AND_ORCHESTRATION.md

**What to generate:**
- Complete `main.py` implementation — asyncio event loop setup, IMAP poller task, agent loop task spawning, graceful shutdown handler
- How the IMAP poller hands off an EmailObject to the agent loop — the exact function call and async task creation
- How concurrent emails on different threads are handled — one asyncio task per thread_id, what happens if two emails from the same thread arrive before the first is processed
- Complete `setup.py` implementation — the full connection test sequence with pass/fail output
- Smoke test procedure — exact steps, what emails to send, what to look for in logs to confirm each stage completed
- Graceful shutdown sequence — what is flushed, what is closed, in what order

**Depth markers — must be present:**
- The exact asyncio pattern used — `asyncio.create_task`, `asyncio.gather`, or `asyncio.run` — and why
- How to prevent two agent loop instances from running simultaneously on the same thread_id
- The exact log lines that confirm each stage of the smoke test succeeded

---

### PHASE8_TIMEZONE.md

**What to generate:**
- Complete `timezone_utils.py` implementation — `detect_timezone`, `to_utc`, `to_local`
- How `detect_timezone` works — checking email headers first (X-Mailer-Timezone if present), then scanning body text for timezone abbreviations and IANA names using regex, fallback to UTC
- How detected timezone is stored in `participant_preferences` and when it is updated
- How outbound emails display times — each participant sees times in their own local timezone, not UTC
- The pytz call sequence for converting a naive datetime + timezone string to UTC-aware datetime
- Edge cases: participant in IST, another in EST, a third with no detectable timezone — how overlap computation handles this

**Depth markers — must be present:**
- The regex pattern used to detect timezone mentions in email body text
- The exact pytz calls: `pytz.timezone(tz_string)`, `tz.localize(naive_dt)`, `.astimezone(pytz.utc)`
- How `to_local` formats the datetime for display in outbound email — the exact strftime format string

---

### PHASE9_PREFERENCE_LEARNING.md

**What to generate:**
- Complete updated `store_preferences()` — how it extracts hour and day from an accepted TimeSlot and appends to `historical_slots`
- Complete `suggest_optimal_time()` — how it reads `historical_slots`, computes hour frequency distribution, computes day frequency distribution, returns a PreferenceProfile
- Complete `PreferenceProfile` TypedDict — every field
- How PreferenceProfile integrates into `rank_slots()` — the exact additional scoring weight, how it combines with the existing four criteria
- Cold start behavior — first coordination with no history, how rank_slots falls back cleanly
- How many historical slots are needed before the preference signal becomes meaningful — the minimum threshold and what happens below it

**Depth markers — must be present:**
- The exact frequency computation — if participant has accepted 5 slots and 3 were between 10am-12pm, how does that translate to a preference score
- The exact field names and types in PreferenceProfile
- How `store_preferences` handles the JSON read-modify-write of `historical_slots` atomically in SQLite

---

### PHASE10_VIP_SCHEDULING.md

**What to generate:**
- Complete VIP initialization logic — how the VIP email list from `.env` is loaded and written to `participant_preferences` at startup
- Complete `check_vip_status()` implementation
- How VIP weight integrates into `rank_slots()` — the exact scoring logic when a VIP is available vs unavailable
- What happens when a VIP is not available in any candidate slot — does rank_slots still proceed or request more windows
- How VIP status can be changed at runtime — the exact SQLite update

**Depth markers — must be present:**
- The exact `.env` variable name and format for the VIP list
- The exact SQL query in `check_vip_status`
- The exact scoring difference between a slot where all VIPs are available vs a slot where no VIPs are available

---

### PHASE11_AMBIGUITY_DETECTION.md

**What to generate:**
- Complete ambiguity patterns library — a Python dict mapping vague expression patterns to the specific clarifying question to generate
- Complete updated `detect_ambiguity()` — how it uses the patterns library, how it falls back to Gemini for patterns not in the library
- Per-participant ambiguity round tracking — the exact AgentState field used, how it is incremented, how the escalation question differs from the first question
- Maximum rounds logic — the exact condition, how a participant is marked non-responsive in session state
- How non-responsive participants are excluded from `find_overlap` and `rank_slots`
- The exact clarifying question format — what information it asks for, how it is phrased to get a parseable response

**Depth markers — must be present:**
- At least 8 entries in the ambiguity patterns library with real expressions and real questions
- The exact AgentState field name that tracks ambiguity rounds per participant
- The exact condition in `coordination_node` that checks for non-responsive participants before calling `find_overlap`

---

## PART 3 — GENERATION INVOCATION INSTRUCTIONS

When the user says **"Generate PHASE_X_FILENAME.md"**, follow this exact sequence:

### Step 1 — Locate the Phase
Find the phase in `MAILMIND_IMPLEMENTATION_PLAN.md`. Read every bullet point under that phase. These are the mandatory items. Nothing listed there can be absent from the generated MD file.

### Step 2 — Pull from Idea Doc
Open `MAILMIND_IDEA.md`. Find every section relevant to this phase. Extract all schemas, algorithms, component specs, rationale, and technology choices that apply.

### Step 3 — Apply Universal Protocol
Apply all six rules from Part 1. Every rule applies to every MD file without exception.

### Step 4 — Apply Phase-Specific Rules
Apply the depth rules from Part 2 for the specific phase being generated. Every depth marker listed must be present in the output.

### Step 5 — Generate
Write the complete MD file. Do not summarize. Do not say "implement X here". Write the actual implementation spec with actual code, actual schemas, actual algorithms. The output must be implementation-ready.

### Step 6 — Self-Check Before Finalizing
Before outputting, verify:
- [ ] Every bullet from the implementation plan for this phase is covered
- [ ] Every depth marker for this phase is present
- [ ] Every function has a complete signature with types
- [ ] Every data structure has a complete schema
- [ ] Every algorithm has full logic, not a summary
- [ ] Every cross-phase dependency is explicitly called out with import paths
- [ ] The integration checklist section is present and complete
- [ ] The test cases section has at least 3 concrete scenarios with inputs and expected outputs
- [ ] No component contradicts MAILMIND_IDEA.md
- [ ] All naming matches MAILMIND_IDEA.md exactly

If any check fails, fix it before outputting.

---

## PART 4 — GENERATION ORDER ENFORCEMENT

The 11 MD files must be generated in this exact order. Each file depends on the ones before it.

```
1.  PHASE1_PROJECT_STRUCTURE.md
2.  PHASE1_CONFIG_AND_ENV.md
3.  PHASE2_IMAP_SMTP.md
4.  PHASE3_SESSION_MEMORY.md
5.  PHASE4_GEMINI_INTEGRATION.md
6.  PHASE5_TOOL_REGISTRY.md
7.  PHASE5_RANK_SLOTS.md
8.  PHASE6_AGENT_STATE_MACHINE.md
9.  PHASE7_MAIN_AND_ORCHESTRATION.md
10. PHASE8_TIMEZONE.md
11. PHASE9_PREFERENCE_LEARNING.md
12. PHASE10_VIP_SCHEDULING.md
13. PHASE11_AMBIGUITY_DETECTION.md
```

Do not generate a later-phase file before an earlier-phase file. Each later file may reference types, functions, and schemas defined in earlier files — those must already be specified before they can be referenced.

If the user asks for a file out of order, generate all skipped files first, then the requested one.

---

## PART 5 — QUALITY BENCHMARK

A correctly generated phase MD file passes this benchmark:

**Benchmark Test:** Take the generated MD file and give it to a mid-level Python developer who has never seen the MailMind project. They should be able to implement every file documented in that MD file without asking a single question. They should produce code that integrates correctly with every other phase without modification.

If that developer would need to ask any question — about a type, a function signature, an algorithm step, an API call format, a variable name, a schema field — the MD file has failed the depth standard and must be regenerated with more detail.

This benchmark applies to every single phase MD file.

---

*MAILMIND_MD_GENERATION_FRAMEWORK.md | Team TRIOLOGY | PCCOE Pune*
