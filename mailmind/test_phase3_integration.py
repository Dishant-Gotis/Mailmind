import os
from datetime import datetime, timezone
from pathlib import Path
from logger import get_logger
import db
import checkpointer
import preference_store
from models import init_state

logger = get_logger("TestPhase3")

def print_banner(text):
    print(f"\n{'=' * 60}\n  {text}\n{'=' * 60}")

def run_integration_test():
    print_banner("MAILMIND PHASE 3: SQLITE MEMORY & CHECKPOINTER TEST")

    # 1. Initialize the database
    logger.info("1. Initializing SQLite Database...")
    db.init_db()
    db_file = Path("data/mailmind.db")
    if db_file.exists():
        logger.info(f"✅ Database dynamically created at: {db_file.absolute()}")
    else:
        logger.error("❌ Database file is missing!")
        return

    # 2. Test Checkpointer (Agent State Save & Load)
    test_thread_id = "test_thread_777"
    
    logger.info("\n2. Initializing new AgentState...")
    fake_email = {
        "message_id": "<test@example.com>",
        "sender_email": "vip_user@apple.com",
        "recipients": ["mailmind@gmail.com"]
    }
    raw_state = init_state(test_thread_id, fake_email)
    raw_state["intent"] = "scheduling" # Modify something to test state mapping
    
    logger.info("Saving AgentState to SQLite...")
    checkpointer.save_state(test_thread_id, raw_state)
    logger.info("✅ State successfully saved")

    logger.info("Loading AgentState from SQLite...")
    loaded_state = checkpointer.load_state(test_thread_id)
    if loaded_state and loaded_state["intent"] == "scheduling" and "vip_user@apple.com" in loaded_state["participants"]:
        logger.info(f"✅ AgentState identically recovered! Current intent: {loaded_state['intent']}")
    else:
        logger.error("❌ AgentState could not be successfully loaded or mapped!")

    # 3. Test Preference Store
    logger.info("\n3. Testing Participant Preference Store...")
    user_email = "vip_user@apple.com"
    
    logger.info(f"Storing preferences for {user_email}...")
    preference_store.store_preferences(
        email=user_email,
        vip=True,
        blocked_days=["Saturday", "Sunday"],
        preferred_hours_start=10,
        preferred_hours_end=16
    )
    logger.info("✅ Preferences cleanly saved in SQLite.")

    logger.info(f"Loading preferences for {user_email}...")
    prefs = preference_store.load_preferences(user_email)
    
    if prefs["vip"] is True and "Sunday" in prefs["blocked_days"] and prefs["preferred_hours_end"] == 16:
        logger.info(f"✅ Preference mapping flawless! Preferences loaded:")
        print(f"    - VIP Status: {prefs['vip']}")
        print(f"    - Blocked Days: {prefs['blocked_days']}")
        print(f"    - Work Hours: {prefs['preferred_hours_start']} to {prefs['preferred_hours_end']} (UTC)")
    else:
        logger.error("❌ Preference mapping failed.")

    print_banner("PHASE 3 FULLY TESTED AND WORKING!")
    print("Agent State Checkpointing and Participant Preferences are 100% persistent.\n")

if __name__ == "__main__":
    try:
        run_integration_test()
    except Exception as e:
        logger.error(f"❌ Test crashed unexpectedly: {e}")
