"""
Single source of truth for the mandatory AI disclaimer.
Every outbound email must include this text — it is appended at send level in smtp_sender.py.
No caller can bypass it because smtp_sender.py calls append_disclaimer() unconditionally.
"""

DISCLAIMER_TEXT = (
    "\n\n---\n"
    "This email was composed and sent by MailMind, an AI scheduling assistant. "
    "It acts autonomously on behalf of the meeting organiser. "
    "If you have concerns or wish to speak to a human, please reply and a human will follow up."
)


def append_disclaimer(body: str) -> str:
    """
    Append the mandatory AI disclaimer to an email body.

    Args:
        body: The email body text before disclaimer. May be empty string.

    Returns:
        str: body with DISCLAIMER_TEXT appended. The disclaimer is always the last content.

    Note:
        This function is called exclusively by smtp_sender.send_reply().
        Callers must never append the disclaimer themselves — always pass the raw body here.
    """
    return body.rstrip() + DISCLAIMER_TEXT
