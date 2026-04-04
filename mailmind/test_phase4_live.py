"""
Live integration test for Phase 4: OpenRouter LLM Calling.
This makes a REAL call to OpenRouter.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from logger import get_logger
from config import config
import prompt_builder
import tool_caller
from models import init_state, EmailObject

# Ensure we have the logger
logger = get_logger("TestPhase4")

def print_banner(text):
    print(f"\n{'=' * 60}\n  {text}\n{'=' * 60}")

def run_live_test():
    print_banner("MAILMIND PHASE 4: LIVE OPENROUTER INTEGRATION TEST")

    # 1. Setup Mock Data
    sample_email: EmailObject = {
        "message_id": "<test-msg-123@gmail.com>",
        "thread_id": "thread-abc-456",
        "sender_email": "prithvirajsherikar3@gmail.com",
        "sender_name": "Prithviraj",
        "subject": "Lunch meeting tomorrow?",
        "body": "Hey, are you free for lunch tomorrow at 1 PM to discuss the new project?",
        "timestamp": datetime.now(timezone.utc),
        "in_reply_to": "",
        "recipients": ["mailmind.assistant@gmail.com"]
    }
    
    state = init_state(sample_email["thread_id"], sample_email)

    # 2. Test Triage (Classification)
    print("\n--- TEST 1: LIVE CLASSIFICATION (Triage) ---")
    logger.info("Building triage prompt...")
    messages = prompt_builder.build_triage_prompt(sample_email, state)
    
    # We define the tool schema for 'classify' here since tool_registry 
    # will be fully built in Phase 5.
    classify_schema = {
        "type": "function",
        "function": {
            "name": "classify",
            "description": "Classify the intent of an inbound email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string", 
                        "enum": ["scheduling", "update_request", "reschedule", "cancellation", "noise"]
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Probability score between 0.0 and 1.0"
                    }
                },
                "required": ["intent", "confidence"]
            }
        }
    }

    logger.info(f"Calling OpenRouter with model: {config.openrouter_model}...")
    try:
        # Note: tool_caller.call_with_tools will try to call tool_registry.call_tool
        # We created a dummy tool_registry.py earlier that returns {"status": "success"}
        result = tool_caller.call_with_tools(
            messages=messages,
            tool_schemas=[classify_schema],
            thread_id=state["thread_id"]
        )
        
        logger.info("✅ Live Response Received!")
        print(f"    - Classification: {result.get('intent', 'N/A')}")
        print(f"    - Confidence: {result.get('confidence', 'N/A')}")
        
        if result.get("intent") == "scheduling":
            logger.info("✅ SUCCESS: AI correctly identified the scheduling intent.")
        else:
            logger.warning(f"⚠️ UNEXPECTED INTENT: AI returned '{result.get('intent')}'")

    except Exception as e:
        logger.error(f"❌ Live Triage call failed: {e}")

    # 3. Test Creative Writing (Rewrite)
    print("\n--- TEST 2: LIVE TEXT GENERATION (Polishing) ---")
    raw_draft = "Hey, lets do lunch at 1pm tomorrow. I'm free. See ya."
    logger.info("Building rewrite prompt...")
    messages = prompt_builder.build_rewrite_prompt(raw_draft)
    
    try:
        logger.info("Calling OpenRouter for polishing...")
        polished = tool_caller.call_for_text(messages, thread_id=state["thread_id"])
        
        logger.info("✅ Live Polished Content Received:")
        print(f"    --- DRAFT ---")
        print(f"    {raw_draft}")
        print(f"    --- POLISHED ---")
        print(f"    {polished}")
        
        if len(polished) > 5:
            logger.info("✅ SUCCESS: AI successfully polished the email.")
    except Exception as e:
        logger.error(f"❌ Live Rewrite call failed: {e}")

    print_banner("PHASE 4 LIVE TESTING COMPLETE!")

if __name__ == "__main__":
    if not config.openrouter_api_key:
        print("❌ ERROR: OPENROUTER_API_KEY not found in .env")
    else:
        run_live_test()
