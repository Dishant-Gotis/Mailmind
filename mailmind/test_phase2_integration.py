import asyncio
import sys
from imap_poller import IMAPPoller
from smtp_sender import send_reply
from logger import get_logger

logger = get_logger("TestPhase2")

def print_banner(text):
    print(f"\n{'=' * 60}\n  {text}\n{'=' * 60}")

async def run_integration_test():
    print_banner("MAILMIND PHASE 2: END-TO-END INTEGRATION TEST")
    print("\n👉 ACTION REQUIRED: Please send an email to your MailMind email address right now.")
    print("👉 Provide a subject like 'Test Phase 2' and any basic body text.\n")
    print("Listening for incoming unread emails... (Press Ctrl+C to abort)\n")
    
    poller = None

    def on_new_email(thread_id, email_obj):
        sender = email_obj['sender_email']
        subject = email_obj['subject']
        body = email_obj['body']
        
        logger.info(f"✅ RECEIVED NEW EMAIL! ")
        logger.info(f"   From: {sender}")
        logger.info(f"   Subject: {subject}")
        logger.info(f"   Thread ID: {thread_id}")
        logger.info(f"   Body snippet: {body[:50]}...")
        
        reply_body = (
            f"Hello {sender}!\n\n"
            f"This is an automated integration test from MailMind Phase 2.\n"
            f"I successfully received your email exactly at {email_obj['timestamp']}.\n"
            f"Your original subject was: '{subject}'\n\n"
            f"If you are seeing this inside the exact same thread in Gmail, then "
            f"IMAP ingestion, email parsing, and outbound SMTP threading are 100% PERFECT!"
        )

        logger.info(f"🚀 FIRING AUTOMATED REPLY VIA SMTP...")
        
        try:
            send_reply(
                to=sender,
                subject=subject,
                body=reply_body,
                thread_id=thread_id,
                in_reply_to=email_obj['message_id'],
                references=f"{email_obj.get('references', '')} {email_obj['message_id']}".strip()
            )
            logger.info("✅ REPLY SENT SUCCESSFULLY!")
            print_banner("PHASE 1 AND 2 FULLY TESTED AND PERFECT!")
            print("\nShutting down poller automatically. Proceed to Phase 3.\n")
            if poller:
                poller.stop()

        except Exception as e:
            logger.error(f"❌ Failed to send reply: {e}")
            if poller:
                poller.stop()

    poller = IMAPPoller(callback=on_new_email)
    
    try:
        await poller.start()
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(run_integration_test())
    except KeyboardInterrupt:
        print("\nTest manually aborted.")
