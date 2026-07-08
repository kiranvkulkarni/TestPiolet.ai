"""Optional SMTP notifications. All functions are best-effort: failures are
logged and swallowed so email never blocks a mutation."""

import logging
import smtplib
from email.mime.text import MIMEText

from .config import settings

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, body: str) -> bool:
    if not settings.EMAIL_ENABLED or not settings.EMAIL_HOST:
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to
        with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10) as server:
            server.starttls()
            if settings.EMAIL_USER:
                server.login(settings.EMAIL_USER, settings.EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


def send_task_assigned_email(to: str, task_title: str) -> bool:
    return _send(
        to,
        f"[QA Tasks] New task assigned: {task_title}",
        f'You have been assigned a new task: "{task_title}".\n\n'
        "Log in to the QA Task Assigner to view details.",
    )
