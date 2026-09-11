"""SMTP email delivery for password reset (optional).

When SMTP is not configured, the API falls back to returning the reset token
in the response ONLY when DEBUG mode is enabled (see app/api/auth.py).
In production the token is never exposed.
"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from app.config import get_settings


def send_reset_email(to_email: str, reset_link: str) -> bool:
    settings = get_settings()
    if not settings.SMTP_HOST:
        return False
    message = MIMEText(
        f"Hello,\n\nYou requested a password reset for your AI Project Builder Agent account.\n\n"
        f"Click the link below to set a new password (valid for 1 hour):\n{reset_link}\n\n"
        f"If you did not request this, you can safely ignore this email.",
        "plain",
    )
    message["Subject"] = "Reset your password - AI Project Builder Agent"
    message["From"] = settings.SMTP_FROM
    message["To"] = to_email
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, [to_email], message.as_string())
        return True
    except Exception:
        return False
