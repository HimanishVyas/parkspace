"""Email delivery abstraction.

V1 ships a console backend (prints to the log) and an SMTP backend. Adding a
transactional provider (SES, Postmark, ...) means implementing `EmailBackend`
and selecting it in `get_email_backend`.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailBackend(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailBackend:
    async def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info("EMAIL to=%s subject=%s\n%s", to, subject, body)


class SMTPEmailBackend:
    async def send(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = settings.email_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        await asyncio.to_thread(self._send_sync, message)

    @staticmethod
    def _send_sync(message: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)


def get_email_backend() -> EmailBackend:
    return SMTPEmailBackend() if settings.email_backend == "smtp" else ConsoleEmailBackend()


async def send_email(to: str, subject: str, body: str) -> None:
    """Never let a mail failure break the request that triggered it."""
    try:
        await get_email_backend().send(to=to, subject=subject, body=body)
    except Exception:
        logger.exception("Failed to send email to %s", to)
