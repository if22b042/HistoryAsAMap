"""Sending the one-time collection links by email (plain SMTP, stdlib only).

Nothing is stored: the address is used for this one message and then forgotten.
Tests replace ``send_links`` so that nothing is sent.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


class MailError(Exception):
    """The message could not be sent."""


def configured() -> bool:
    """Is SMTP set up (host and sender address)?"""
    config = current_app.config
    return bool(config.get("SMTP_HOST") and (config.get("MAIL_FROM") or config.get("SMTP_USERNAME")))


def build_message(to: str, title: str, share_url: str, edit_url: str) -> EmailMessage:
    config = current_app.config
    message = EmailMessage()
    message["Subject"] = "Your History As A Map collection"
    message["From"] = config.get("MAIL_FROM") or config["SMTP_USERNAME"]
    message["To"] = to
    message.set_content(
        f"Your collection \"{title}\" is ready.\n\n"
        f"Share link (view only, safe to pass around):\n{share_url}\n\n"
        f"Edit link (keep it private: anyone with it can change or delete the collection):\n{edit_url}\n\n"
        "This is the only time we send these links, and we have not stored your email address. "
        "Keep this message.\n")
    return message


def send_links(to: str, title: str, share_url: str, edit_url: str) -> None:
    """Email the share and edit links; raises ``MailError`` on any failure."""
    config = current_app.config
    message = build_message(to, title, share_url, edit_url)
    host, port = config["SMTP_HOST"], int(config.get("SMTP_PORT") or 587)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=10)
        with server:
            if port != 465:
                server.starttls(context=ssl.create_default_context())
            if config.get("SMTP_USERNAME"):
                server.login(config["SMTP_USERNAME"], config.get("SMTP_PASSWORD") or "")
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise MailError(str(error)) from error
