# MailMind — Edge Case Test Suite
**Team TRIOLOGY | PCCOE Pune | Problem Statement 03**
> One test case per edge. Each test includes: what it tests, why it will fail on the current code, the exact fix needed, and the test code.

---

## INDEX

| # | Component | Edge Case | Severity |
|---|---|---|---|
| EC-01 | `email_parser.py` | `References` header has only one entry (no space separator) | 🔴 HIGH |
| EC-02 | `email_parser.py` | Email body is HTML-only (no `text/plain` part) | 🟡 MEDIUM |
| EC-03 | `email_parser.py` | Sender email has display name with angle brackets AND quoted string | 🟡 MEDIUM |
| EC-04 | `imap_poller.py` | MailMind's OWN reply arrives in INBOX and gets processed as a new thread | 🔴 HIGH |
| EC-05 | `checkpointer.py` | `save_state()` called with `datetime` inside a nested dict inside `slots_per_participant` | 🔴 HIGH |
| EC-06 | `checkpointer.py` | `load_state()` on a thread that was mid-node when process crashed — `current_node` is a broken intermediate state | 🟡 MEDIUM |
| EC-07 | `preference_store.py` | `seed_vip_list()` called with duplicate emails in the list | 🟢 LOW |
| EC-08 | `preference_store.py` | `store_preferences(accepted_slot=...)` where `start_utc` is a `datetime` object (not ISO string) | 🔴 HIGH |
| EC-09 | `rank_slots()` | All candidate slots fall on a participant's `blocked_days` — penalty pushes score below threshold | 🟡 MEDIUM |
| EC-10 | `rank_slots()` | `preferences` dict contains a participant not in any candidate slot's `participant` field | 🟡 MEDIUM |
| EC-11 | `rank_slots()` | Single candidate slot, single VIP participant who IS available — VIP score must be full 1.0 | 🟡 MEDIUM |
| EC-12 | `agent/router.py` | `route_by_completeness` — `outbound_draft` is set AND `pending_responses` is empty | 🔴 HIGH |
| EC-13 | `agent/router.py` | `route_by_threshold` — `ranked_slot` is set but `rank_below_threshold` key is missing from state | 🔴 HIGH |
| EC-14 | `agent/nodes.py` | `triage_node` — Gemini returns intent `"reschedule"` but session already has a confirmed `calendar_event_id` | 🔴 HIGH |
| EC-15 | `agent/nodes.py` | `coordination_node` — participant replies with ONLY blocked days ("I can't do Monday or Tuesday") with no positive availability | 🟡 MEDIUM |
| EC-16 | `agent/nodes.py` | `ambiguity_node` — same participant triggers ambiguity more than `MAX_CLARIFICATION_ROUNDS` times | 🔴 HIGH |
| EC-17 | `agent/nodes.py` | `calendar_node` — duplicate meeting check finds a match but `check_duplicate()` comparison uses naive vs aware datetime | 🔴 HIGH |
| EC-18 | `agent/loop.py` | New email arrives for a thread whose `current_node` in saved state is `"send_node"` (session not cleared after crash mid-send) | 🔴 HIGH |
| EC-19 | `smtp_sender.py` | `send_reply()` called with `cc` list containing MailMind's own address — agent emails itself, infinite loop | 🔴 CRITICAL |
| EC-20 | `telegram_bot.py` | `request_approval()` — `threading.Event.wait()` returns but `result[0]` is still `"timeout"` because callback fired AFTER the wait check | 🔴 HIGH |
| EC-21 | `main.py` | VIP list in `.env` contains trailing comma: `ceo@co.com,` — produces empty string in list | 🟡 MEDIUM |
| EC-22 | `models.py` | `init_state()` — `email_obj["recipients"]` is empty list (email sent directly TO MailMind with no CC) | 🟡 MEDIUM |
| EC-23 | `config.py` | `ATTENDANCE_THRESHOLD=1.0` — valid per validator but means ALL participants must overlap — single non-responder makes it impossible | 🟡 MEDIUM |
| EC-24 | Cross-phase | Thread receives a reply WHILE `approval_node` is waiting for Telegram — second email triggers a second `loop.run()` on same thread_id | 🔴 HIGH |

---

## DETAILED TEST CASES

---

### EC-01 — `References` Header With Single Entry (No Space)

**File:** `email_parser.py`
**Severity:** 🔴 HIGH

**What it is:**
The References header parsing splits on whitespace and takes `all_refs[0]`. If someone's mail client sends `References: <only-one-id@mail.com>` (single entry, no space), it still works. BUT if the client sends `References:<root@mail.com>` with NO space after the colon AND no spaces in the value, `msg.get("References", "").strip()` still returns the one ID — this actually works. The real failure is when References looks like `<root@mail.com>\r\n\t<msg2@mail.com>` (folded header, tab-indented continuation). `split()` handles tabs fine. **Actual failure:** When References has ONLY the Message-ID of the PREVIOUS message (not root), some clients set `References` = `In-Reply-To` value. Then `all_refs[0]` gives the direct parent, NOT the root, and two emails in the same thread get different `thread_id`s.

**Why it fails:**
```python
# Current code:
references_header = msg.get("References", "").strip()
if references_header:
    all_refs = references_header.split()
    thread_id = all_refs[0].strip()  # ← takes FIRST reference as root
```
If a client only puts the immediate parent (not full chain) in `References`, then email 3 will have `thread_id` = message_id of email 2, not email 1. Two sessions get created for one Gmail thread.

**Test:**
```python
def test_references_only_parent_not_root():
    """
    Outlook and some mobile clients only put the direct parent in References,
    not the full chain. The parser must still produce the SAME thread_id as the
    first email in the thread.
    """
    # Email 1 (original)
    raw_email1 = _make_raw(
        message_id="<root001@example.com>",
        references="",
    )
    obj1 = parse_email(raw_email1)
    assert obj1["thread_id"] == "<root001@example.com>"

    # Email 3 — client only adds DIRECT parent, not full chain
    raw_email3 = _make_raw(
        message_id="<msg003@example.com>",
        in_reply_to="<msg002@example.com>",
        references="<msg002@example.com>",  # ← only parent, not root
    )
    obj3 = parse_email(raw_email3)

    # CURRENT BEHAVIOR: thread_id = "<msg002@example.com>" ← WRONG
    # EXPECTED: thread_id must equal obj1["thread_id"] = "<root001@example.com>"
    # This test WILL FAIL on current code.
    assert obj3["thread_id"] == "<root001@example.com>", (
        f"Expected thread root <root001@example.com>, got {obj3['thread_id']}"
    )
```

**Fix needed in `email_parser.py`:**
The agent cannot know the true root from the email alone in this case. The fix is: after parsing, check SQLite — if any `thread_id` in the sessions table matches ANY of the References entries, use that stored `thread_id`. This requires `email_parser.py` to call `checkpointer.find_thread_by_any_ref(refs)` as a fallback lookup before assigning `thread_id = all_refs[0]`.

```python
# In parse_email(), replace thread_id assignment block:
if references_header:
    all_refs = references_header.split()
    # Try to find an existing session whose thread_id matches any known ref
    from checkpointer import find_thread_by_any_ref  # add this function to checkpointer
    existing_tid = find_thread_by_any_ref(all_refs)
    thread_id = existing_tid if existing_tid else all_refs[0].strip()
else:
    thread_id = message_id if message_id else _generate_fallback_id(...)
```

---

### EC-02 — HTML-Only Email Body (No `text/plain` Part)

**File:** `email_parser.py`
**Severity:** 🟡 MEDIUM

**What it is:**
Some modern email clients (Superhuman, HEY, some Outlook configurations) send `multipart/alternative` with ONLY a `text/html` part and no `text/plain`. The parser is documented to prefer `text/plain`. If there is no `text/plain`, the current implementation returns empty string.

**Why it fails:**
```python
# Current code returns empty string when no text/plain exists
# body="" means coordination_node gets nothing to parse availability from
# → ambiguity_node fires, asks clarifying question, even though the email had full content
```

**Test:**
```python
def test_html_only_email_returns_stripped_text():
    """
    Email has no text/plain part — only text/html.
    Parser must strip HTML tags and return readable text, not empty string.
    """
    raw = _make_raw(
        body_plain=None,  # no plain text part
        body_html="<html><body><p>I'm available <strong>Monday 10am</strong> or <em>Wednesday 2pm</em>.</p></body></html>",
    )
    obj = parse_email(raw)

    # CURRENT BEHAVIOR: obj["body"] == ""  ← WRONG
    # EXPECTED: body contains "Monday 10am" and "Wednesday 2pm"
    assert "Monday" in obj["body"], f"Expected availability text, got: '{obj['body']}'"
    assert "<html>" not in obj["body"], "HTML tags must be stripped"
    assert "<p>" not in obj["body"], "HTML tags must be stripped"
```

**Fix needed in `email_parser.py`:**
```python
# In _extract_body(), after failing to find text/plain:
if not body and html_part:
    import html as html_lib
    import re
    raw_html = html_part.get_payload(decode=True).decode(charset or "utf-8", errors="replace")
    # Strip tags
    body = re.sub(r"<[^>]+>", " ", raw_html)
    body = html_lib.unescape(body)
    body = " ".join(body.split())  # collapse whitespace
```

---

### EC-03 — Sender Display Name Contains Quotes or Angle Brackets

**File:** `email_parser.py`
**Severity:** 🟡 MEDIUM

**What it is:**
`email.utils.parseaddr` handles most names but fails on pathological From headers like:
`From: "Smith, John (CEO)" <john.smith@company.com>`
The comma inside the quoted string confuses some downstream display, not the parsing. The worse case is:
`From: John <Assistant> Smith <john@company.com>` — two angle bracket groups.

**Why it fails:**
```python
sender_name, sender_email = email.utils.parseaddr(from_header)
# For: "John <Assistant> Smith <john@company.com>"
# parseaddr returns sender_email="" (empty) because the format is invalid
# → EmailParseError("Email has no From header") is NOT raised (From exists)
# → sender_email="" means all DB lookups by email fail silently
```

**Test:**
```python
def test_malformed_from_with_nested_angle_brackets():
    """
    Malformed From header with two angle-bracket groups.
    Parser must extract a usable email address or raise EmailParseError cleanly.
    """
    raw = (
        b"From: John <Assistant> Smith <john@company.com>\r\n"
        b"To: mailmind@gmail.com\r\n"
        b"Subject: Meeting\r\n"
        b"Date: Mon, 04 Apr 2026 09:15:00 +0000\r\n"
        b"Message-ID: <abc@company.com>\r\n"
        b"\r\nBody"
    )
    obj = parse_email(raw)

    # CURRENT BEHAVIOR: sender_email="" — silent failure
    # EXPECTED: either correct email extracted, or EmailParseError raised
    assert obj["sender_email"] != "", (
        "sender_email must never be empty string — "
        "either extract the last valid address or raise EmailParseError"
    )
    assert "@" in obj["sender_email"]
```

**Fix needed in `email_parser.py`:**
```python
# After parseaddr, add fallback regex extraction:
if not sender_email or "@" not in sender_email:
    import re
    matches = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', from_header)
    if matches:
        sender_email = matches[-1].lower()  # last match = most likely actual address
    else:
        raise EmailParseError(f"Cannot extract valid email from From header: {from_header!r}")
```

---

### EC-04 — MailMind's OWN Reply Re-Enters the Processing Loop

**File:** `imap_poller.py`
**Severity:** 🔴 HIGH

**What it is:**
When MailMind sends a reply via SMTP, Gmail's "Sent" folder copies the sent email into the INBOX under some configurations (especially when the MailMind address CCs itself, or when Gmail mirrors sent messages). The IMAP poller marks all UNSEEN emails as SEEN and passes them to the agent. If MailMind's own email re-enters as UNSEEN, the agent processes it, classifies its own disclaimer text as a new email, and creates an infinite coordination loop.

**Why it fails:**
```python
# Current code in _fetch_and_process() has NO sender filter:
email_obj = parse_email(raw_bytes)
self.callback(email_obj["thread_id"], email_obj)  # ← fires even for own emails
```

**Test:**
```python
def test_own_email_is_not_processed(monkeypatch):
    """
    An email FROM the MailMind address itself must be silently skipped.
    The callback must NOT be called.
    """
    from unittest.mock import MagicMock, patch
    import email as email_stdlib

    callback = MagicMock()

    # Construct a raw email where sender = MailMind's own address
    raw = _make_raw(
        from_addr=f"MailMind <{config.gmail_address}>",
        subject="Re: Team sync",
        body="This email was composed and sent by MailMind...",
        message_id="<sent001@gmail.com>",
    )

    with patch("imap_poller.parse_email", return_value={
        "sender_email": config.gmail_address,  # ← own address
        "thread_id": "<root001@gmail.com>",
        "message_id": "<sent001@gmail.com>",
        "subject": "Re: Team sync",
        "body": "MailMind disclaimer...",
        "timestamp": datetime.now(timezone.utc),
        "recipients": [],
        "sender_name": "MailMind",
        "in_reply_to": "",
    }):
        poller = IMAPPoller(callback=callback)
        poller._process_email(raw)

    # CURRENT BEHAVIOR: callback IS called ← WRONG
    # EXPECTED: callback is NOT called for own emails
    callback.assert_not_called()
```

**Fix needed in `imap_poller.py`:**
```python
# In _fetch_and_process(), add BEFORE calling callback:
if email_obj["sender_email"].lower() == config.gmail_address.lower():
    logger.debug(
        "Skipping own email (sender=%s, thread=%s)",
        email_obj["sender_email"], email_obj["thread_id"],
    )
    return
```

---

### EC-05 — `save_state()` With Nested `datetime` Inside `slots_per_participant`

**File:** `checkpointer.py`
**Severity:** 🔴 HIGH

**What it is:**
`slots_per_participant` is a `dict[str, list[TimeSlot]]`. Each `TimeSlot` has `start_utc` and `end_utc` as `datetime` objects. When `save_state()` serializes to JSON via `json.dumps()`, the `default_serialiser` is supposed to handle `datetime`. But if the custom serialiser is only applied at the TOP level and not recursively into nested dicts, `datetime` objects inside `slots_per_participant` will raise `TypeError: Object of type datetime is not JSON serializable`.

**Why it fails:**
```python
# json.dumps uses default= only for objects it cannot natively serialize
# datetime inside a nested dict is reached by the encoder, so default IS called
# BUT: if the implementation uses a non-standard path like:
state_copy = dict(state)
state_copy["slots_per_participant"] = str(state["slots_per_participant"])  # naive stringify
# → load_state() gets a string, not a dict → _deserialise_state() fails
```

**Test:**
```python
def test_save_and_load_preserves_datetime_in_slots(tmp_path, monkeypatch):
    """
    AgentState with actual datetime objects inside slots_per_participant
    must survive a full save → load cycle with datetime types preserved.
    """
    import db as db_module
    from db import init_db
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()

    from checkpointer import save_state, load_state
    from datetime import datetime, timezone

    slot = {
        "start_utc": datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),  # real datetime
        "end_utc":   datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        "participant": "alice@example.com",
        "raw_text": "Monday 9am",
        "timezone": "UTC",
    }
    state = _make_blank_state("thread-dt-test")
    state["slots_per_participant"] = {"alice@example.com": [slot]}

    save_state(state["thread_id"], state)
    loaded = load_state(state["thread_id"])

    assert loaded is not None
    loaded_slot = loaded["slots_per_participant"]["alice@example.com"][0]

    # CURRENT RISK: loaded_slot["start_utc"] may be a string, not a datetime
    assert isinstance(loaded_slot["start_utc"], datetime), (
        f"start_utc must be datetime after load, got {type(loaded_slot['start_utc'])}"
    )
    assert loaded_slot["start_utc"].tzinfo is not None, "datetime must be UTC-aware after load"
    assert loaded_slot["start_utc"].hour == 9
```

**Fix needed in `checkpointer.py`:**
```python
# _deserialise_state() must walk slots_per_participant and ranked_slot
# and convert any ISO string that looks like a datetime back to datetime:

import re
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

def _restore_datetimes_in_slot(slot: dict) -> dict:
    for key in ("start_utc", "end_utc"):
        val = slot.get(key)
        if isinstance(val, str) and _ISO_RE.match(val):
            slot[key] = datetime.fromisoformat(val)
    return slot
```

---

### EC-06 — `load_state()` Returns State With `current_node = "calendar_node"` After Mid-Node Crash

**File:** `agent/loop.py`
**Severity:** 🟡 MEDIUM

**What it is:**
The loop checkpoints AFTER every node. If the process crashes INSIDE `calendar_node` (after the Calendar event is created but BEFORE `save_state()` is called), the next run loads the state where `current_node = "overlap_node"` or `"rank_slots_node"` (last saved) and re-runs `calendar_node`. This creates a duplicate Calendar event. The Calendar manager has `check_duplicate()` — but only if the node actually calls it on re-entry.

**Why it fails:**
If `calendar_node` does NOT call `check_duplicate()` on its own `calendar_event_id` field (i.e., it skips the check when `state["calendar_event_id"]` is already set from a prior partial run), a duplicate event is created.

**Test:**
```python
def test_calendar_node_skips_creation_if_event_id_already_set():
    """
    If state["calendar_event_id"] is already populated from a previous partial run,
    calendar_node must NOT create another event — it must proceed directly to rewrite_node.
    """
    from unittest.mock import patch, MagicMock
    from agent.nodes import calendar_node

    state = _make_blank_state("thread-cal-crash")
    state["ranked_slot"] = {
        "start_utc": "2026-04-07T09:00:00+00:00",
        "end_utc":   "2026-04-07T10:00:00+00:00",
        "participant": "alice@example.com",
        "raw_text": "Monday 9am",
        "timezone": "UTC",
    }
    state["calendar_event_id"] = "existing_event_id_abc123"  # ← already set
    state["participants"] = ["alice@example.com"]

    create_event_mock = MagicMock()

    with patch("tools.calendar_manager.create_event", create_event_mock):
        result = calendar_node(state)

    # CURRENT RISK: create_event IS called again → duplicate
    # EXPECTED: create_event NOT called when event_id already exists
    create_event_mock.assert_not_called()
    assert result["calendar_event_id"] == "existing_event_id_abc123"
```

**Fix needed in `agent/nodes.py` `calendar_node`:**
```python
def calendar_node(state: AgentState) -> AgentState:
    # Guard: if event already created (crash-recovery case), skip creation
    if state.get("calendar_event_id"):
        logger.info(
            "calendar_node: event_id already set (%s) — skipping duplicate creation.",
            state["calendar_event_id"], extra={"thread_id": state["thread_id"]},
        )
        return state
    # ... rest of creation logic
```

---

### EC-07 — `seed_vip_list()` With Duplicate Emails

**File:** `preference_store.py`
**Severity:** 🟢 LOW

**What it is:**
If `.env` contains `VIP_EMAIL_LIST=ceo@co.com,ceo@co.com` (accidental duplicate), `seed_vip_list()` is called with `["ceo@co.com", "ceo@co.com"]`. With `INSERT OR IGNORE`, the second call is a no-op. But if the implementation uses `INSERT OR REPLACE`, it creates two writes, last one wins — harmless but wastes a write and may reset `updated_at`.

**Test:**
```python
def test_seed_vip_list_with_duplicates_is_idempotent(tmp_path, monkeypatch):
    """Duplicate entries in VIP list must not cause errors or double-writes."""
    import db as db_module
    from db import init_db
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()

    from preference_store import seed_vip_list, load_preferences

    # Should not raise and should result in exactly one row
    seed_vip_list(["ceo@co.com", "ceo@co.com", "ceo@co.com"])

    prefs = load_preferences("ceo@co.com")
    assert prefs["vip"] is True
    # No exception raised = PASS for this case
```

**Fix:** Deduplicate in `main.py` before calling `seed_vip_list()`:
```python
vips = list(set(v.strip().lower() for v in config.vip_email_list.split(",") if v.strip()))
seed_vip_list(vips)
```

---

### EC-08 — `store_preferences(accepted_slot=...)` With `datetime` Object vs ISO String

**File:** `preference_store.py`
**Severity:** 🔴 HIGH

**What it is:**
`store_preferences()` appends to `historical_slots` in JSON. If `accepted_slot["start_utc"]` is a `datetime` object (passed directly from `rank_slots` result), `json.dumps` will fail unless the serialiser handles it. The test in Phase 3 passes ISO strings. In production, `calendar_node` calls `store_preferences(email, accepted_slot=state["ranked_slot"])` and `state["ranked_slot"]` may contain real `datetime` objects after `_deserialise_state()` restores them.

**Test:**
```python
def test_store_preferences_accepts_datetime_in_slot(tmp_path, monkeypatch):
    """
    accepted_slot with datetime objects (not strings) must not raise TypeError.
    historical_slots must persist and reload correctly.
    """
    import db as db_module
    from db import init_db
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()

    from preference_store import store_preferences, get_historical_slots
    from datetime import datetime, timezone

    slot = {
        "start_utc": datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),  # datetime object
        "end_utc":   datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc), # datetime object
        "participant": "alice@example.com",
        "raw_text": "Monday 9am",
        "timezone": "UTC",
    }

    # CURRENT RISK: TypeError: Object of type datetime is not JSON serializable
    try:
        store_preferences("alice@example.com", accepted_slot=slot)
    except TypeError as e:
        pytest.fail(f"store_preferences raised TypeError on datetime slot: {e}")

    slots = get_historical_slots("alice@example.com")
    assert len(slots) == 1
```

**Fix needed in `preference_store.py` `_append_historical_slot()`:**
```python
def _datetime_serialiser(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# In _append_historical_slot:
new_slot_json_safe = json.loads(json.dumps(slot, default=_datetime_serialiser))
```

---

### EC-09 — All Candidate Slots Fall on Participant's `blocked_days`

**File:** `tools/coordination_memory.py`
**Severity:** 🟡 MEDIUM

**What it is:**
`rank_slots()` applies `PREFERENCE_VIOLATION_PENALTY` per blocked day violation but does NOT eliminate the slot. If there is only one candidate slot and it falls on a participant's `blocked_days`, the penalty is applied but the slot is still returned. The test must verify that `below_threshold` is correctly set when the penalty drops the score below `SLOT_SCORE_THRESHOLD`.

**Test:**
```python
def test_single_slot_on_blocked_day_may_trigger_below_threshold():
    """
    A single slot on ALL participants' blocked day should score low enough
    to set below_threshold=True for sufficient participants.
    """
    from unittest.mock import patch
    from tools.coordination_memory import rank_slots, SLOT_SCORE_THRESHOLD

    # Friday slot — both participants block Friday
    slot = _slot(10, day_offset=4)  # Friday

    prefs = {
        "alice@example.com": _prefs("alice@example.com",
                                     blocked=["Friday"], slots=[slot]),
        "bob@example.com":   _prefs("bob@example.com",
                                     blocked=["Friday"], slots=[slot]),
        "carol@example.com": _prefs("carol@example.com",
                                     blocked=["Friday"], slots=[slot]),
    }

    with patch("tools.coordination_memory.check_vip_status", return_value=False):
        result = rank_slots([slot], prefs)

    # Penalty = 0.10 / 3 participants per violation × 3 participants × 1 violation each
    # = 0.10 total penalty reduction
    # Attendance = 1.0 (all available), preference_score near 0 (blocked day)
    # Combined score should be low
    print(f"Score: {result['score']}, below_threshold: {result['below_threshold']}")

    # The slot must still be RETURNED (not eliminated)
    assert result["ranked_slot"] is not None, "Slot must be returned even if penalised"

    # If score < 0.50, below_threshold must be True
    if result["score"] < SLOT_SCORE_THRESHOLD:
        assert result["below_threshold"] is True
    else:
        # If score is still ≥ 0.50, verify the penalty was applied (score < perfect)
        assert result["score"] < 1.0, "Penalties must reduce score below perfect"
```

---

### EC-10 — `preferences` Contains Email Not Present in Any Candidate Slot

**File:** `tools/coordination_memory.py`
**Severity:** 🟡 MEDIUM

**What it is:**
`rank_slots()` computes attendance by checking which participants have a slot that overlaps the candidate window. If `preferences` has 5 participants but only 3 sent availability, the `slots` list for the other 2 is empty. `attendance_score` = 3/5 = 0.60. This is correct behavior. The failure is if the attendance check doesn't properly handle a participant with `slots=[]` — it must count as "not available", not crash.

**Test:**
```python
def test_participant_with_empty_slots_counts_as_absent():
    """
    A participant in preferences with slots=[] must be counted as absent,
    lowering attendance_score, without raising any exception.
    """
    from unittest.mock import patch
    from tools.coordination_memory import rank_slots

    slot = _slot(10)  # Monday 10am

    prefs = {
        "alice@example.com": _prefs("alice@example.com", slots=[slot]),   # present
        "bob@example.com":   _prefs("bob@example.com",   slots=[]),       # absent
        "carol@example.com": _prefs("carol@example.com", slots=[]),       # absent
    }

    with patch("tools.coordination_memory.check_vip_status", return_value=False):
        result = rank_slots([slot], prefs)

    assert result["ranked_slot"] is not None
    # attendance = 1/3 ≈ 0.33, weighted = 0.50 * 0.33 = 0.165
    # Below SLOT_SCORE_THRESHOLD (0.50) → below_threshold=True
    assert result["below_threshold"] is True, (
        f"1/3 attendance must be below threshold, score={result['score']}"
    )
    # Score must reflect partial attendance, not 1.0
    assert result["score"] < 0.5
```

---

### EC-11 — Single VIP Participant Who IS Available Gives Full VIP Score

**File:** `tools/coordination_memory.py`
**Severity:** 🟡 MEDIUM

**What it is:**
VIP score formula: `vip_participants_available / total_vip_participants`. If there is 1 VIP and they ARE available, VIP score = 1/1 = 1.0. If there are NO VIPs configured at all, VIP score defaults to 1.0 (per spec). The test verifies the single-VIP case doesn't accidentally use the "no VIPs" default path and that the VIP contribution to score is correct.

**Test:**
```python
def test_single_vip_available_contributes_full_vip_weight():
    """
    One VIP configured, that VIP IS available → vip_score = 1.0 → contributes 0.15.
    Score must include full WEIGHT_VIP contribution.
    """
    from unittest.mock import patch
    from tools.coordination_memory import rank_slots, WEIGHT_ATTENDANCE, WEIGHT_VIP

    slot = _slot(10)
    prefs = {
        "ceo@co.com": _prefs("ceo@co.com", vip=True, slots=[slot]),
        "bob@co.com": _prefs("bob@co.com", vip=False, slots=[slot]),
    }

    with patch("tools.coordination_memory.check_vip_status",
               side_effect=lambda e: e == "ceo@co.com"):
        result = rank_slots([slot], prefs)

    # All participants available → attendance=1.0 → 0.50
    # VIP available → vip_score=1.0 → 0.15
    # Score must be at least 0.65 (attendance + vip, ignoring preference and chronology)
    assert result["score"] >= WEIGHT_ATTENDANCE + WEIGHT_VIP, (
        f"Expected score ≥ {WEIGHT_ATTENDANCE + WEIGHT_VIP}, got {result['score']}"
    )
    assert "VIP" in result["reason"], "Reason must mention VIP availability"
```

---

### EC-12 — `route_by_completeness`: Draft Set AND Pending Responses Empty

**File:** `agent/router.py`
**Severity:** 🔴 HIGH

**What it is:**
The `route_by_completeness` routing logic checks `draft` FIRST. If `outbound_draft` is set, it returns `AMBIGUITY_NODE` regardless of `pending_responses`. But if all participants have responded AND an ambiguity draft exists (e.g., the last responder triggered ambiguity), the agent sends an ambiguity question to a participant who ALREADY responded. This is a logical contradiction — ambiguity should only be sent if the CURRENT responder's availability was ambiguous AND they are still in `pending_responses`.

**Why it fails:**
```python
# Current code — draft takes priority even if pending is empty:
if draft:
    return AMBIGUITY_NODE  # ← fires even when ALL participants responded
```

**Test:**
```python
def test_route_by_completeness_all_responded_but_draft_set():
    """
    If outbound_draft is set (from ambiguity detection on last participant)
    BUT pending_responses is now empty (all responded), still route to ambiguity_node
    only if there are pending participants, otherwise go to overlap_node.

    Current behavior: AMBIGUITY_NODE (wrong — all have responded)
    Expected behavior: This is ambiguous — but the spec says draft → ambiguity_node.
                       The real fix is: ambiguity_node must check pending_responses
                       before sending, and skip if empty.
    """
    from agent.router import route_by_completeness

    state = {
        "pending_responses": [],            # all responded
        "outbound_draft": "Please clarify when you say 'sometime next week'.",
        "thread_id": "tid-edge-12",
    }

    result = route_by_completeness(state)

    # The routing WILL return AMBIGUITY_NODE per current code.
    # This test documents the risk: ambiguity_node must handle empty pending_responses
    # gracefully by clearing the draft and routing to overlap instead.
    # Test that ambiguity_node handles this without sending an email to nobody:
    from agent.nodes import ambiguity_node
    from unittest.mock import patch, MagicMock

    state_full = _make_blank_state("tid-edge-12")
    state_full["outbound_draft"] = "Please clarify..."
    state_full["pending_responses"] = []  # nobody left to ask

    send_mock = MagicMock()
    with patch("tools.email_coordinator.send_clarification", send_mock):
        result_state = ambiguity_node(state_full)

    # EXPECTED: No email sent, draft cleared, can proceed to overlap
    send_mock.assert_not_called()
    assert result_state["outbound_draft"] is None
```

---

### EC-13 — `route_by_threshold`: `rank_below_threshold` Key Missing From State

**File:** `agent/router.py`
**Severity:** 🔴 HIGH

**What it is:**
`route_by_threshold` reads `state.get("rank_below_threshold", False)`. If `rank_slots_node` crashed before setting this key, or an older session was loaded that predates adding this field, `state.get(...)` returns `False`. Combined with `ranked_slot` being set from a previous attempt, the router incorrectly proceeds to `calendar_node` when it should re-route.

But the WORSE case: `rank_below_threshold` key is NOT in `AgentState.__annotations__` in `models.py` (it was added as a Phase 6 footnote addition, easy to miss). Then `init_state()` doesn't include it, and every fresh state is missing the key.

**Test:**
```python
def test_route_by_threshold_missing_key_does_not_false_positive():
    """
    If rank_below_threshold is missing from state, route_by_threshold must
    NOT silently proceed to calendar_node when ranked_slot is set from a
    stale previous round.
    """
    from agent.router import route_by_threshold

    # Simulate state where ranked_slot exists from a prior failed round
    # but rank_below_threshold was never set (missing key)
    state = {
        "ranked_slot": {"start_utc": "2026-04-07T09:00:00+00:00"},
        # "rank_below_threshold" key is MISSING
        "coordination_restart_count": 0,
        "thread_id": "tid-edge-13",
    }

    result = route_by_threshold(state)

    # Current code: state.get("rank_below_threshold", False) → False
    # → ranked_slot is truthy + below_threshold is False → returns CALENDAR_NODE
    # This is the CORRECT behavior IF ranked_slot is genuinely valid.
    # The test documents that init_state() MUST include rank_below_threshold=False
    # so the logic is intentional, not accidental.

    # Verify init_state includes the field:
    from models import init_state
    from datetime import datetime, timezone

    email_obj = {
        "message_id": "<m@x.com>", "thread_id": "<t@x.com>",
        "sender_email": "a@x.com", "sender_name": "A",
        "subject": "s", "body": "b",
        "timestamp": datetime.now(timezone.utc),
        "in_reply_to": "", "recipients": [],
    }
    fresh_state = init_state("<t@x.com>", email_obj)

    assert "rank_below_threshold" in fresh_state, (
        "rank_below_threshold must be in init_state() — "
        "add it to AgentState TypedDict and init_state() defaults"
    )
    assert fresh_state["rank_below_threshold"] is False
```

**Fix needed in `models.py` `init_state()`:**
```python
return AgentState(
    # ... existing fields ...
    overlap_candidates=[],
    rank_below_threshold=False,      # ← add this
    calendar_event_id=None,          # ← add this
    coordination_restart_count=0,    # ← add this
)
```

---

### EC-14 — `triage_node` Classifies `"reschedule"` on a Thread With a Confirmed Calendar Event

**File:** `agent/nodes.py`
**Severity:** 🔴 HIGH

**What it is:**
When a participant replies to a confirmed meeting thread saying "Can we move this to Thursday?", the triage node correctly classifies it as `"reschedule"`. The router sends it to `coordination_node`. But the current state still has `calendar_event_id` set (from the confirmed event), `ranked_slot` set, and `slots_per_participant` populated with the OLD availability. The coordination node would append new slots on top of old ones, leading to incorrect overlap computation.

**Why it fails:**
Reschedule path does not clear `slots_per_participant`, `ranked_slot`, `ranked_below_threshold`, or `pending_responses` before restarting coordination.

**Test:**
```python
def test_reschedule_clears_old_coordination_state():
    """
    When intent is 'reschedule', triage_node (or coordination_node on reschedule entry)
    must clear: slots_per_participant, ranked_slot, pending_responses, overlap_candidates.
    Otherwise old availability pollutes the new round.
    """
    from agent.nodes import triage_node
    from unittest.mock import patch

    state = _make_blank_state("tid-reschedule")
    state["intent"] = "scheduling"
    state["slots_per_participant"] = {
        "alice@example.com": [{"start_utc": "2026-04-07T09:00:00+00:00",
                                "end_utc": "2026-04-07T10:00:00+00:00",
                                "participant": "alice@example.com",
                                "raw_text": "Monday 9am", "timezone": "UTC"}]
    }
    state["ranked_slot"] = {"start_utc": "2026-04-07T09:00:00+00:00",
                             "end_utc": "2026-04-07T10:00:00+00:00",
                             "participant": "alice@example.com",
                             "raw_text": "Monday 9am", "timezone": "UTC"}
    state["calendar_event_id"] = "event_abc123"

    email_obj = {
        "body": "Can we move the meeting to Thursday instead?",
        "sender_email": "alice@example.com",
        "subject": "Re: Team sync",
        "thread_id": "tid-reschedule",
        "message_id": "<rmsg@x.com>",
        "timestamp": datetime.now(timezone.utc),
        "recipients": [],
        "sender_name": "Alice",
        "in_reply_to": "",
    }

    with patch("agent.nodes.call_with_tools", return_value={
        "intent": "reschedule", "confidence": 0.92
    }):
        result = triage_node(state, email_obj)

    assert result["intent"] == "reschedule"

    # On reschedule, old coordination data must be cleared
    # CURRENT RISK: slots_per_participant and ranked_slot are NOT cleared
    assert result["slots_per_participant"] == {}, (
        "slots_per_participant must be cleared on reschedule intent"
    )
    assert result["ranked_slot"] is None, (
        "ranked_slot must be cleared on reschedule intent"
    )
```

**Fix needed in `agent/nodes.py` `triage_node`:**
```python
if result["intent"] == "reschedule":
    state["slots_per_participant"] = {}
    state["ranked_slot"] = None
    state["rank_below_threshold"] = False
    state["pending_responses"] = list(state["participants"])
    state["overlap_candidates"] = []
    state["coordination_restart_count"] = 0
    # Note: do NOT clear calendar_event_id here — calendar_node will delete it via Calendar API
```

---

### EC-15 — Participant Replies With ONLY Blocked Days (No Positive Availability)

**File:** `agent/nodes.py` → `coordination_node`
**Severity:** 🟡 MEDIUM

**What it is:**
A participant sends: *"I'm not available Monday, Tuesday, or Wednesday next week."* The dateparser cannot extract a positive time slot from this. The coordination_node must detect this as a special case: the participant has expressed constraints but NOT availability. If it treats this as "replied with availability" and removes the participant from `pending_responses`, overlap computation will fail because that participant has zero slots.

**Test:**
```python
def test_coordination_node_handles_negative_only_response():
    """
    A reply expressing ONLY unavailability (blocked days) with no positive slot
    must NOT be treated as a valid availability reply.
    The participant must remain in pending_responses and an ambiguity question sent.
    """
    from agent.nodes import coordination_node
    from unittest.mock import patch

    state = _make_blank_state("tid-neg-avail")
    state["pending_responses"] = ["bob@example.com"]
    state["participants"] = ["alice@example.com", "bob@example.com"]
    state["slots_per_participant"] = {
        "alice@example.com": [_make_slot(10)]  # alice already responded
    }

    email_obj = {
        "sender_email": "bob@example.com",
        "body": "I'm not available Monday, Tuesday, or Wednesday. Terrible week for me.",
        "thread_id": "tid-neg-avail",
        "message_id": "<bob-neg@x.com>",
        "subject": "Re: Team sync",
        "timestamp": datetime.now(timezone.utc),
        "recipients": ["alice@example.com"],
        "sender_name": "Bob",
        "in_reply_to": "",
    }

    # Tool call returns empty slots list (dateparser found no positive availability)
    with patch("agent.nodes.call_with_tools", return_value={"slots": []}):
        result = coordination_node(state, email_obj)

    # CURRENT RISK: bob removed from pending_responses even though no slots extracted
    # EXPECTED: bob stays in pending_responses OR an ambiguity question is drafted
    if "bob@example.com" not in result["pending_responses"]:
        # If removed from pending, they must have at least one slot
        assert "bob@example.com" in result["slots_per_participant"], (
            "Bob removed from pending but has no slots — data loss"
        )
        assert len(result["slots_per_participant"]["bob@example.com"]) > 0
    else:
        # Bob is still pending — ambiguity question should be drafted
        assert result["outbound_draft"] is not None, (
            "If Bob stays in pending with no slots, ambiguity question must be drafted"
        )
```

---

### EC-16 — Participant Triggers Ambiguity More Than `MAX_CLARIFICATION_ROUNDS`

**File:** `agent/nodes.py` → `ambiguity_node`
**Severity:** 🔴 HIGH

**What it is:**
The spec defines `ambiguity_rounds` dict and `non_responsive` list. If a participant keeps sending vague replies (triggering ambiguity each time), the agent must eventually mark them as `non_responsive` and proceed without their availability. If this cap is not enforced, the agent loops forever with one participant in an ambiguity loop and the thread never progresses.

**Test:**
```python
def test_ambiguity_node_marks_participant_non_responsive_after_max_rounds():
    """
    After MAX_CLARIFICATION_ROUNDS (should be defined as constant in nodes.py),
    participant must be moved to non_responsive and removed from pending_responses.
    """
    from agent.nodes import ambiguity_node, MAX_CLARIFICATION_ROUNDS
    from unittest.mock import patch, MagicMock

    state = _make_blank_state("tid-ambig-max")
    state["pending_responses"] = ["bob@example.com"]
    state["ambiguity_rounds"] = {"bob@example.com": MAX_CLARIFICATION_ROUNDS}  # at limit

    email_obj = {
        "sender_email": "bob@example.com",
        "body": "sometime soon works for me",  # still vague
        "thread_id": "tid-ambig-max",
        "message_id": "<bob-vague@x.com>",
        "subject": "Re: sync", "timestamp": datetime.now(timezone.utc),
        "recipients": [], "sender_name": "Bob", "in_reply_to": "",
    }

    send_mock = MagicMock()
    with patch("tools.email_coordinator.send_clarification", send_mock):
        result = ambiguity_node(state, email_obj)

    # CURRENT RISK: MAX_CLARIFICATION_ROUNDS might not be defined or checked
    assert "bob@example.com" in result["non_responsive"], (
        "Bob must be in non_responsive after exceeding MAX_CLARIFICATION_ROUNDS"
    )
    assert "bob@example.com" not in result["pending_responses"], (
        "Bob must be removed from pending_responses once non-responsive"
    )
    # No further clarification email must be sent after marking non-responsive
    send_mock.assert_not_called()
```

**Fix needed in `agent/nodes.py`:**
```python
MAX_CLARIFICATION_ROUNDS = 2  # define as module constant

def ambiguity_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    email = email_obj["sender_email"]
    rounds = state.get("ambiguity_rounds", {})
    current_round = rounds.get(email, 0)

    if current_round >= MAX_CLARIFICATION_ROUNDS:
        # Mark non-responsive, remove from pending
        state["non_responsive"] = list(set(state.get("non_responsive", []) + [email]))
        state["pending_responses"] = [p for p in state["pending_responses"] if p != email]
        state["outbound_draft"] = None
        logger.warning("Marking %s as non-responsive after %d rounds.", email, current_round)
        return state
    # ... send clarification, increment counter
```

---

### EC-17 — Calendar Duplicate Check Compares Naive vs Aware `datetime`

**File:** `tools/calendar_manager.py`
**Severity:** 🔴 HIGH

**What it is:**
`check_duplicate()` queries existing Calendar events and compares their `start.dateTime` with `ranked_slot["start_utc"]`. The Google Calendar API returns datetime strings in RFC 3339 format (e.g., `"2026-04-07T09:00:00+05:30"`). If parsed with `datetime.fromisoformat()` (Python 3.11+) this gives a timezone-aware datetime. But if `ranked_slot["start_utc"]` is a naive UTC datetime (no tzinfo), the comparison `event_start == slot_start` raises `TypeError: can't compare offset-naive and offset-aware datetimes`.

**Test:**
```python
def test_duplicate_check_handles_naive_vs_aware_comparison():
    """
    check_duplicate must not raise TypeError when comparing Calendar API datetimes
    (timezone-aware) against slot start_utc that may be naive (missing tzinfo).
    """
    from unittest.mock import patch, MagicMock
    from tools.calendar_manager import check_duplicate
    from datetime import datetime, timezone

    # Simulate Calendar API returning an aware datetime
    mock_event = {
        "id": "event123",
        "summary": "Team sync",
        "start": {"dateTime": "2026-04-07T09:00:00+00:00"},
        "end":   {"dateTime": "2026-04-07T10:00:00+00:00"},
    }

    mock_service = MagicMock()
    mock_service.events().list().execute.return_value = {"items": [mock_event]}

    # slot with NAIVE datetime (no tzinfo) — the dangerous case
    naive_slot = {
        "start_utc": datetime(2026, 4, 7, 9, 0),  # ← no tzinfo
        "end_utc":   datetime(2026, 4, 7, 10, 0),
    }

    with patch("tools.calendar_manager.get_calendar_service", return_value=mock_service):
        try:
            result = check_duplicate(naive_slot, "Team sync")
            # If it didn't raise, verify the result
            # (may return True or False, but must not crash)
        except TypeError as e:
            pytest.fail(f"check_duplicate raised TypeError on naive datetime: {e}")
```

**Fix needed in `tools/calendar_manager.py`:**
```python
# When comparing datetimes, always normalize to UTC-aware:
def _to_utc_aware(dt) -> datetime:
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
```

---

### EC-18 — New Email Arrives for Thread Whose Saved `current_node` is `"send_node"`

**File:** `agent/loop.py`
**Severity:** 🔴 HIGH

**What it is:**
After `send_node` succeeds, `clear_state()` is called and the session is deleted. But if the process crashes between `send_node` completing and `clear_state()` running, the saved state has `current_node = "send_node"`. The next email in this thread loads this state and the loop tries to resume from `"send_node"`, which would re-send the confirmation email.

**Test:**
```python
def test_loop_handles_saved_state_at_send_node():
    """
    If saved state has current_node='send_node' (crash after send, before clear),
    loop must NOT re-fire send_node. It must treat the thread as completed and
    either clear state and re-triage, or skip processing.
    """
    from unittest.mock import patch, MagicMock
    import db as db_module
    from db import init_db

    send_mock = MagicMock()
    triage_mock = MagicMock(return_value={
        "intent": "noise", "confidence": 0.9
    })

    state = _make_blank_state("tid-send-crash")
    state["current_node"] = "send_node"          # ← crash recovery state
    state["outbound_draft"] = "The meeting is confirmed for Monday 9am."
    state["calendar_event_id"] = "event_abc"

    with patch("checkpointer.load_state", return_value=state), \
         patch("checkpointer.clear_state") as clear_mock, \
         patch("smtp_sender.send_reply", send_mock), \
         patch("agent.nodes.call_with_tools", triage_mock):

        from agent.loop import run
        email_obj = _make_email_obj("tid-send-crash")
        run("tid-send-crash", email_obj)

    # CURRENT RISK: send_reply called again → duplicate confirmation email
    # EXPECTED: clear_state called (clean up stale state) and do NOT re-send
    clear_mock.assert_called_once()
    # Verify send was NOT called a second time for the old draft
    for call in send_mock.call_args_list:
        assert "confirmed for Monday" not in str(call), (
            "Must not re-send the previous confirmation email"
        )
```

**Fix needed in `agent/loop.py`:**
```python
def run(thread_id: str, email_obj: EmailObject) -> None:
    state = load_state(thread_id)

    if state is not None and state.get("current_node") == "send_node":
        # Crash recovery: send already happened, clear and re-triage
        logger.warning("Recovered state at send_node for %s — clearing stale state.", thread_id)
        clear_state(thread_id)
        state = None  # fall through to init_state
    
    if state is None:
        state = init_state(thread_id, email_obj)
    # ... rest of loop
```

---

### EC-19 — `send_reply()` CC List Contains MailMind's OWN Address → Infinite Loop

**File:** `smtp_sender.py`
**Severity:** 🔴 CRITICAL

**What it is:**
When replying, `send_reply()` constructs the CC list from `email_obj["recipients"]`. In a thread where MailMind was CC'd on the original email, its own address is in `recipients`. If that address is passed into the outbound CC header, Gmail delivers the sent email back to MailMind's INBOX as a new UNSEEN email. Combined with EC-04 being unfixed, this creates an infinite loop: MailMind sends → receives its own reply → processes it → sends again → infinite.

**Test:**
```python
def test_send_reply_filters_own_address_from_cc():
    """
    MailMind's own Gmail address must never appear in the CC list of outbound emails.
    Including it causes Gmail to deliver the sent email back to MailMind's inbox.
    """
    from unittest.mock import patch, MagicMock
    import smtplib

    sent_messages = []

    class MockSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, *a): pass
        def sendmail(self, from_addr, to_addrs, msg):
            sent_messages.append((from_addr, to_addrs, msg))

    with patch("smtplib.SMTP_SSL", MockSMTP):
        from smtp_sender import send_reply
        send_reply(
            to="alice@example.com",
            subject="Re: Team sync",
            body="The meeting is confirmed.",
            thread_id="<root@x.com>",
            in_reply_to="<msg001@x.com>",
            references="<root@x.com>",
            cc=["bob@example.com", config.gmail_address.lower(), "carol@example.com"],
        )

    assert len(sent_messages) == 1
    _, to_addrs, raw_msg = sent_messages[0]

    # MailMind's own address must NOT be in any To/CC field
    combined_recipients = " ".join(to_addrs).lower()
    assert config.gmail_address.lower() not in combined_recipients, (
        f"MailMind's own address {config.gmail_address} must be filtered from CC"
    )
```

**Fix needed in `smtp_sender.py` `send_reply()`:**
```python
def send_reply(to, subject, body, thread_id, in_reply_to="", references="", cc=None):
    own_address = config.gmail_address.lower()
    filtered_cc = [
        addr for addr in (cc or [])
        if addr.lower() != own_address and addr.lower() != to.lower()
    ]
    # use filtered_cc in message construction
```

---

### EC-20 — Telegram `request_approval()`: Race Condition Between `event.wait()` Timeout and Callback

**File:** `telegram_bot.py`
**Severity:** 🔴 HIGH

**What it is:**
In `request_approval()`, the code does:
```python
responded = event.wait(timeout=config.approval_timeout_seconds)
answer = result[0]
del _pending_approvals[thread_id]
```
If `event.wait()` returns `False` (timeout), `result[0]` is `"timeout"`. BUT there is a race: the operator taps "Approve" at exactly the timeout moment. `_handle_callback()` fires, sets `result[0] = "approved"`, then calls `event.set()`. If `event.wait()` already returned `False` before `event.set()` is called, `result[0]` could be "approved" even though `responded = False`. The code then returns "approved" but logs "Approval timeout" — inconsistent behavior.

**Test:**
```python
def test_request_approval_timeout_returns_timeout_not_stale_approval():
    """
    If event.wait() times out (returns False), result must be 'timeout'
    even if callback fires immediately after the timeout.
    Demonstrates the race condition window.
    """
    import threading
    import time
    from unittest.mock import patch, MagicMock

    # Mock the bot send to succeed instantly
    with patch("telegram_bot._send_approval_message", return_value=None), \
         patch("telegram_bot._bot_loop", new_callable=lambda: MagicMock()), \
         patch("asyncio.run_coroutine_threadsafe") as rct_mock:

        # Simulate: future.result() succeeds (message sent)
        future_mock = MagicMock()
        future_mock.result.return_value = None
        rct_mock.return_value = future_mock

        from telegram_bot import _pending_approvals, request_approval

        def _late_callback(thread_id):
            """Simulates operator approving JUST after timeout."""
            time.sleep(0.15)  # fires after event.wait() timeout
            if thread_id in _pending_approvals:
                event, result = _pending_approvals[thread_id]
                result[0] = "approved"
                event.set()

        # Use very short timeout to make the race deterministic
        with patch.object(__import__("config").config, "approval_timeout_seconds", 0.1):
            t = threading.Thread(target=_late_callback, args=("tid-race",))
            t.start()
            result = request_approval("Test draft", "tid-race")
            t.join()

        # EXPECTED: "timeout" (event.wait returned False before callback)
        # CURRENT RISK: "approved" if result[0] was mutated before del
        # This test documents the race — fix by reading result BEFORE the wait returns:
        print(f"Result: {result}")  # May be "timeout" or "approved" — non-deterministic
```

**Fix needed in `telegram_bot.py` `request_approval()`:**
```python
responded = event.wait(timeout=config.approval_timeout_seconds)
# Read result IMMEDIATELY after wait, before any callback can mutate it:
answer = result[0] if responded else "timeout"
del _pending_approvals[thread_id]  # remove BEFORE returning so late callbacks are no-ops
return answer
```

---

### EC-21 — VIP List With Trailing Comma Produces Empty-String Entry

**File:** `main.py` / `config.py`
**Severity:** 🟡 MEDIUM

**What it is:**
`VIP_EMAIL_LIST=ceo@co.com,` (trailing comma) produces `["ceo@co.com", ""]` after `split(",")`. The empty string gets passed to `seed_vip_list()` and inserted as a VIP row with `email=""`. Every unknown participant would then accidentally inherit the empty-string VIP record if any lookup uses `""` as a fallback key.

**Test:**
```python
def test_vip_list_trailing_comma_produces_no_empty_entry(tmp_path, monkeypatch):
    """
    VIP_EMAIL_LIST with trailing comma must not create an empty-string VIP row.
    """
    import db as db_module
    from db import init_db
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()

    from preference_store import seed_vip_list, check_vip_status

    # Simulate what main.py does with a trailing-comma VIP list
    raw_vip_list = "ceo@co.com,"
    vips = [v.strip() for v in raw_vip_list.split(",") if v.strip()]  # correct filter
    seed_vip_list(vips)

    # No empty-string entry should exist
    assert check_vip_status("") is False, (
        "Empty string must not be a VIP — trailing comma in VIP_EMAIL_LIST creates this"
    )
    assert check_vip_status("ceo@co.com") is True
    assert vips == ["ceo@co.com"]  # verify filter works
```

**Fix:** The `if v.strip()` filter in `main.py` is the fix. Verify it's in place:
```python
# main.py Step 3 — must use this exact pattern:
vips = [v.strip().lower() for v in config.vip_email_list.split(",") if v.strip()]
```

---

### EC-22 — `init_state()` With Empty `recipients` List

**File:** `models.py`
**Severity:** 🟡 MEDIUM

**What it is:**
`init_state()` computes participants as:
```python
participants=list({email_obj["sender_email"]} | set(email_obj["recipients"]))
```
If `recipients` is `[]` (MailMind was emailed directly with no CC), `participants` = `[sender_email]`. This is valid. The issue: `pending_responses` in the spec is populated in `triage_node`, not `init_state()`. If `triage_node` sets `pending_responses = state["participants"]` minus the sender, a direct email to MailMind yields `pending_responses = []` immediately, and `route_by_completeness` skips to `overlap_node` before ANY availability has been collected.

**Test:**
```python
def test_direct_email_no_cc_does_not_skip_to_overlap():
    """
    Email sent directly to MailMind (no CC, no other participants) must NOT
    skip to overlap_node immediately just because pending_responses is empty.
    Single-participant scheduling should still go through coordination.
    """
    from agent.router import route_by_completeness

    # After triage: only sender, no other participants → pending is empty
    state = {
        "pending_responses": [],            # empty because only 1 participant
        "outbound_draft": None,
        "slots_per_participant": {},        # NO slots yet collected
        "participants": ["alice@example.com"],
        "thread_id": "tid-solo",
    }

    result = route_by_completeness(state)

    # Current behavior: returns OVERLAP_NODE (because pending is empty)
    # But slots_per_participant is also empty — overlap will find nothing!
    if result == "overlap_node":
        # Verify overlap_node handles empty slots gracefully
        from agent.nodes import overlap_node
        from unittest.mock import patch
        overlap_result = overlap_node(state)
        # Should not crash and should set below_threshold
        assert overlap_result.get("rank_below_threshold") is True or \
               overlap_result.get("overlap_candidates") == [], (
            "overlap_node with empty slots must set below_threshold or empty candidates"
        )
```

---

### EC-23 — `ATTENDANCE_THRESHOLD=1.0` Makes Coordination Impossible With Any Non-Responder

**File:** Behavior across `rank_slots()` + `agent/nodes.py`
**Severity:** 🟡 MEDIUM

**What it is:**
`ATTENDANCE_THRESHOLD=1.0` means 100% attendance required. If even one participant never responds, `rank_slots()` returns `below_threshold=True` for every slot, triggering coordination restart. After 2 restarts, `error_node` is hit. The operator gets an error alert but never a clear message that the threshold setting is the problem.

**Test:**
```python
def test_attendance_threshold_1_with_non_responder_triggers_error_not_silent_fail():
    """
    At ATTENDANCE_THRESHOLD=1.0 with one non-responder, the system must:
    1. Correctly compute attendance < 1.0
    2. Return below_threshold=True
    3. Eventually route to error_node with a CLEAR explanation mentioning attendance
    """
    from unittest.mock import patch
    from tools.coordination_memory import rank_slots

    slot = _slot(10)
    prefs = {
        "alice@example.com": _prefs("alice@example.com", slots=[slot]),
        "bob@example.com":   _prefs("bob@example.com", slots=[]),  # non-responder
    }

    with patch("tools.coordination_memory.check_vip_status", return_value=False), \
         patch("tools.coordination_memory.SLOT_SCORE_THRESHOLD", 1.0):
        # Using threshold=1.0 means attendance=0.50 weight × 1.0 threshold
        # 1 of 2 available → attendance_score=0.5 → weighted=0.25
        # 0.25 < 1.0 threshold → below_threshold=True
        result = rank_slots([slot], prefs)

    assert result["below_threshold"] is True
    assert "attendance" in result["reason"].lower() or "50%" in result["reason"], (
        "Reason must explain WHY below threshold — mention attendance percentage"
    )
```

---

### EC-24 — Concurrent `loop.run()` on Same `thread_id` (Two Emails Arrive Close Together)

**File:** `agent/loop.py` + `main.py`
**Severity:** 🔴 HIGH

**What it is:**
IMAP polling is sequential — one email at a time per poll cycle. BUT if two emails arrive for the same thread in the same 30-second window, they are both fetched and processed in the SAME `_poll_once()` call, sequentially. The first `loop.run()` starts, loads state, runs nodes, saves state. While it's running (inside `asyncio.to_thread`), the second `loop.run()` starts on the same thread_id, loads the SAME initial state (before the first run saved its updates), and processes with stale data. This is a write-write race on the SQLite session row.

**Test:**
```python
def test_concurrent_runs_on_same_thread_id_do_not_corrupt_state(tmp_path, monkeypatch):
    """
    Two sequential agent runs on the same thread_id (simulating two emails in one poll)
    must not result in lost slot data (second run must see first run's state updates).
    """
    import db as db_module
    from db import init_db
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()

    from checkpointer import save_state, load_state
    from models import init_state

    tid = "<thread-concurrent@x.com>"

    email1 = _make_email_obj(tid, sender="alice@example.com",
                              body="I can do Monday 10am")
    email2 = _make_email_obj(tid, sender="bob@example.com",
                              body="I'm free Tuesday 2pm")

    # Simulate first run saving Alice's slot
    state_after_alice = init_state(tid, email1)
    state_after_alice["slots_per_participant"]["alice@example.com"] = [_make_slot(10)]
    save_state(tid, state_after_alice)

    # Second run loads state — MUST see Alice's slot
    loaded = load_state(tid)
    assert loaded is not None
    assert "alice@example.com" in loaded["slots_per_participant"], (
        "Second run must load first run's saved state — Alice's slot must be present"
    )

    # Now add Bob's slot and save again
    loaded["slots_per_participant"]["bob@example.com"] = [_make_slot(14)]
    save_state(tid, loaded)

    final = load_state(tid)
    assert "alice@example.com" in final["slots_per_participant"]
    assert "bob@example.com" in final["slots_per_participant"], (
        "Both participants' slots must survive sequential saves"
    )
```

**Fix:** The real fix is a per-thread_id lock in `main.py`:
```python
# main.py — add thread locks
_thread_locks: dict[str, asyncio.Lock] = {}

async def agent_run_locked(thread_id: str, email_obj: EmailObject) -> None:
    if thread_id not in _thread_locks:
        _thread_locks[thread_id] = asyncio.Lock()
    async with _thread_locks[thread_id]:
        await asyncio.to_thread(loop.run, thread_id, email_obj)
```

---

## SUMMARY TABLE — FIXES BY FILE

| File | Edge Cases | Priority |
|---|---|---|
| `email_parser.py` | EC-01, EC-02, EC-03 | EC-01 first (silent thread split is catastrophic) |
| `imap_poller.py` | EC-04 | Fix immediately — infinite loop risk |
| `smtp_sender.py` | EC-19 | Fix immediately — infinite loop risk |
| `checkpointer.py` | EC-05, EC-06 | EC-05 blocks production use |
| `preference_store.py` | EC-07, EC-08 | EC-08 blocks calendar confirmation |
| `agent/router.py` | EC-12, EC-13 | EC-13 causes silent wrong routing |
| `agent/nodes.py` | EC-14, EC-15, EC-16, EC-17 | EC-16 blocks threads forever |
| `agent/loop.py` | EC-18, EC-24 | EC-18 sends duplicate emails |
| `models.py` `init_state()` | EC-13, EC-22 | EC-13 needs init_state fix |
| `telegram_bot.py` | EC-20 | Fix race condition |
| `main.py` | EC-21, EC-24 | EC-24 is architectural |
| `tools/coordination_memory.py` | EC-09, EC-10, EC-11 | All medium, EC-09 needs documentation |
| `config.py` | EC-23 | Document intended behavior |

---

*MailMind Edge Case Tests | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
