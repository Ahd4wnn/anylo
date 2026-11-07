"""Outgoing email. Without SMTP settings (local dev) the message is logged instead of sent."""

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger("anylo.email")
outbox: list[EmailMessage] = []  # last messages, for tests and local dev


def send(to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    outbox.append(msg)
    del outbox[:-20]
    if not s.smtp_host:
        log.warning("SMTP not configured; email to %s not sent: %s", to, subject)
        return
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
