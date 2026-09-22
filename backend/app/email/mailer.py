"""Sending email. The API only enqueues; the worker talks to SMTP (guide 4)."""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

import structlog
from arq.connections import ArqRedis

from app.config import Settings
from app.email.messages import Email

log = structlog.get_logger(__name__)
SEND_EMAIL_JOB = "send_email"


class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


class QueueMailer:
    """Hands the message to the worker, so a slow mail server never slows a request."""

    def __init__(self, queue: ArqRedis) -> None:
        self._queue = queue

    async def send(self, email: Email) -> None:
        await self._queue.enqueue_job(SEND_EMAIL_JOB, email.to, email.subject, email.body)


class UnconfiguredMailer:
    """Used when SMTP_HOST is empty. Logs that a message was dropped, never its content:
    bodies carry one-time links."""

    async def send(self, email: Email) -> None:
        log.warning("email.not_configured", subject=email.subject)


def deliver(settings: Settings, email: Email) -> None:
    """Blocking SMTP delivery, run by the worker."""
    if settings.smtp_host is None:
        log.warning("email.not_configured", subject=email.subject)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.body)
    context = ssl.create_default_context()
    smtp: smtplib.SMTP
    if settings.smtp_tls == "ssl":
        smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=15)
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with smtp:
        if settings.smtp_tls == "starttls":
            smtp.starttls(context=context)
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
    log.info("email.sent", subject=email.subject)
