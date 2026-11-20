"""Sending the one-time collection links by email (plain SMTP, stdlib only).

Nothing is stored: the address is used for this one message and then forgotten.
Because anyone can type any address into the form, sending is limited per recipient,
per client and per day (``may_send``), the message is the same for everybody and
repeats nothing the visitor wrote, and the address must be a single plain one.
Tests replace ``send_links`` so that nothing is sent.
"""

from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

from haam import ratelimit

MAX_ADDRESS = 254
_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_LABEL = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


class MailError(Exception):
    """The message could not be sent."""


def valid_address(address: str) -> bool:
    """One plain ``local@domain.tld`` address: no names, quotes, comments, spaces or line breaks."""
    if not address or len(address) > MAX_ADDRESS or not address.isascii():
        return False
    local, at, domain = address.partition("@")
    if not at or not local or len(local) > 64 or "@" in domain:
        return False
    labels = domain.split(".")
    return (bool(_LOCAL.fullmatch(local)) and len(labels) >= 2 and all(_LABEL.fullmatch(p) for p in labels)
            and not labels[-1].isdigit())


def configured() -> bool:
    """Is SMTP set up (host and sender address)?"""
    config = current_app.config
    return bool(config.get("SMTP_HOST") and (config.get("MAIL_FROM") or config.get("SMTP_USERNAME")))


def may_send(address: str) -> bool:
    """Count this attempt against the limits; False when any is used up.

    Per recipient (a hash of the lowercased address, never the address), per client and
    all together per day. The caller shows the same message as for a failed send, so
    a visitor cannot tell a used-up limit from a down mail server, or learn that an
    address was used before.
    """
    config = current_app.config
    return (ratelimit.allow("mail-client", int(config["MAIL_PER_CLIENT_HOURLY"]), 3600)
            and ratelimit.allow("mail-to", int(config["MAIL_PER_RECIPIENT_HOURLY"]), 3600,
                                key=ratelimit.hash_of(address.strip().lower()))
            and ratelimit.allow("mail-all", int(config["MAIL_DAILY_LIMIT"]), 24 * 3600,
                                key=ratelimit.hash_of("mail-all")))


def build_message(to: str, share_url: str, edit_url: str) -> EmailMessage:
    """The same text for every visitor; the collection's title is deliberately not in it."""
    if not valid_address(to):
        raise MailError("invalid recipient address")
    config = current_app.config
    message = EmailMessage()
    message["Subject"] = "Your History As A Map collection"
    message["From"] = config.get("MAIL_FROM") or config["SMTP_USERNAME"]
    message["To"] = to
    message.set_content(
        "Someone (hopefully you) made a collection on History As A Map and asked for its links "
        "to be sent to this address.\n\n"
        f"Share link (view only, safe to pass around):\n{share_url}\n\n"
        f"Edit link (keep it private: anyone with it can change or delete the collection):\n{edit_url}\n\n"
        "This is the only time we send these links, and we have not stored your email address. "
        "If this was not you, ignore this message.\n")
    return message


def send_links(to: str, share_url: str, edit_url: str) -> None:
    """Email the share and edit links; raises ``MailError`` on any failure."""
    config = current_app.config
    try:
        message = build_message(to, share_url, edit_url)
        host, port = config["SMTP_HOST"], int(config.get("SMTP_PORT") or 587)
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
    except MailError:
        raise
    except (OSError, ValueError, KeyError, smtplib.SMTPException) as error:
        raise MailError(f"{type(error).__name__}: {error}") from error
