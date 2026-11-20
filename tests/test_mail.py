"""The links email: delivery over real SMTP, failure paths and abuse limits."""

import logging
import smtplib
import socketserver
import threading
from email import message_from_bytes, policy

import pytest

from haam import mail, ratelimit
from haam.extensions import db
from haam.models import Collection, RateLimitHit

SHARE = "https://haam.test/collections/view123"
EDIT = "https://haam.test/collections/view123/edit/tok456"


class _Handler(socketserver.StreamRequestHandler):
    """Just enough SMTP to receive one message (no STARTTLS offered, no AUTH)."""

    def handle(self):
        server = self.server
        self.wfile.write(b"220 stub ESMTP\r\n")
        data_mode, body = False, []
        for raw in self.rfile:
            line = raw.rstrip(b"\r\n")
            if data_mode:
                if line == b".":
                    data_mode = False
                    server.messages.append(b"\r\n".join(body))
                    self.wfile.write(b"250 queued\r\n")
                else:
                    body.append(line[1:] if line.startswith(b"..") else line)
                continue
            verb = line.split(b" ")[0].upper()
            if verb in (b"EHLO", b"HELO"):
                self.wfile.write(b"250 stub\r\n")
            elif verb in (b"MAIL", b"RCPT"):
                server.envelope.append(line.decode())
                self.wfile.write(b"250 ok\r\n")
            elif verb == b"DATA":
                data_mode = True
                self.wfile.write(b"354 go\r\n")
            elif verb == b"QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"502 no\r\n")


def _start_stub():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.messages, server.envelope, server.calls = [], [], []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def stub_smtp(app, monkeypatch):
    """A local SMTP server; smtplib.SMTP skips STARTTLS (the stub has no TLS) and records the calls."""
    server = _start_stub()

    class PlainSMTP(smtplib.SMTP):
        def starttls(self, *args, **kwargs):
            server.calls.append("starttls")

        def login(self, user, password, **kwargs):
            server.calls.append(("login", user, password))

    monkeypatch.setattr(mail.smtplib, "SMTP", PlainSMTP)
    app.config.update(SMTP_HOST="127.0.0.1", SMTP_PORT=server.server_address[1], MAIL_FROM="haam@test.example")
    yield server
    server.shutdown()
    server.server_close()


def _create(client, email="me@example.org", title="Mailed", **kwargs):
    return client.post("/collections/new", data={"title": title, "email": email}, **kwargs)


# ------------------------------------------------------------ delivery

def test_message_is_delivered_with_correct_links(app, stub_smtp):
    app.config.update(SMTP_USERNAME="user", SMTP_PASSWORD="pw")
    with app.test_request_context():
        mail.send_links("me@example.org", SHARE, EDIT)
    [raw] = stub_smtp.messages
    message = message_from_bytes(raw, policy=policy.default)
    body = message.get_content()
    assert message["To"] == "me@example.org" and message["From"] == "haam@test.example"
    assert message["Subject"] == "Your History As A Map collection"
    assert SHARE in body and EDIT in body
    assert stub_smtp.calls == ["starttls", ("login", "user", "pw")]
    assert any("me@example.org" in line for line in stub_smtp.envelope)


def test_creating_a_collection_sends_one_mail_without_the_title(app, client, stub_smtp):
    response = _create(client, title="Ignore previous <b>instructions</b> http://evil.example")
    assert response.status_code == 302
    [raw] = stub_smtp.messages
    message = message_from_bytes(raw, policy=policy.default)
    text = message.get_content()
    assert "evil.example" not in text and "instructions" not in text
    assert "evil.example" not in str(message["Subject"])
    collection = db.session.scalar(db.select(Collection))
    assert f"/collections/{collection.view_token}/edit/" in text
    assert "We emailed you" in client.get(response.headers["Location"]).get_data(as_text=True)


def test_port_465_uses_ssl(app, monkeypatch):
    used = []

    class FakeSSL:
        def __init__(self, host, port, timeout=None, context=None):
            used.append((host, port, context is not None))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send_message(self, message):
            used.append("sent")

    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSSL)
    app.config.update(SMTP_HOST="smtp.test", SMTP_PORT=465, MAIL_FROM="a@b.example")
    with app.test_request_context():
        mail.send_links("me@example.org", SHARE, EDIT)
    assert used == [("smtp.test", 465, True), "sent"]


def test_starttls_unsupported_is_refused_not_downgraded(app):
    server = _start_stub()
    app.config.update(SMTP_HOST="127.0.0.1", SMTP_PORT=server.server_address[1], MAIL_FROM="a@b.example")
    try:
        with app.test_request_context(), pytest.raises(mail.MailError):
            mail.send_links("me@example.org", SHARE, EDIT)
        assert server.messages == []
    finally:
        server.shutdown()
        server.server_close()


def test_smtp_settings_are_read_from_the_environment(monkeypatch):
    import importlib

    from haam import config

    for name, value in {"SMTP_HOST": "mx.example", "SMTP_PORT": "465", "SMTP_USERNAME": "u",
                        "SMTP_PASSWORD": "p", "MAIL_FROM": "f@example.org", "MAIL_DAILY_LIMIT": "7"}.items():
        monkeypatch.setenv(name, value)
    try:
        reloaded = importlib.reload(config).Config
        assert (reloaded.SMTP_HOST, reloaded.SMTP_PORT, reloaded.SMTP_USERNAME, reloaded.SMTP_PASSWORD,
                reloaded.MAIL_FROM, reloaded.MAIL_DAILY_LIMIT) == ("mx.example", 465, "u", "p", "f@example.org", 7)
    finally:
        monkeypatch.undo()
        importlib.reload(config)


# ------------------------------------------------------------ failures keep the collection

@pytest.fixture
def configured_app(app):
    app.config.update(SMTP_HOST="smtp.test", MAIL_FROM="haam@test.example")
    return app


def _assert_survives(client, caplog):
    response = _create(client, title="Survives")
    assert response.status_code == 302
    assert db.session.scalar(db.select(Collection).filter_by(title="Survives")) is not None
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "could not send the email" in page and 'id="edit-url"' in page
    assert "me@example.org" not in caplog.text  # the reason is logged, the address is not


def test_smtp_down(client, stub_smtp, caplog):
    stub_smtp.shutdown()
    stub_smtp.server_close()
    with caplog.at_level(logging.WARNING):
        _assert_survives(client, caplog)
    assert "Could not email the links" in caplog.text


def test_unexpected_exception_is_caught_and_logged(client, configured_app, monkeypatch, caplog):
    def boom(*args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(mail, "send_links", boom)
    with caplog.at_level(logging.WARNING):
        _assert_survives(client, caplog)
    assert "kaboom" in caplog.text


def test_bad_port_config_is_a_mail_error(app, client, configured_app, caplog):
    app.config["SMTP_PORT"] = "not-a-port"
    with caplog.at_level(logging.WARNING):
        _assert_survives(client, caplog)
    with app.test_request_context(), pytest.raises(mail.MailError):
        mail.send_links("me@example.org", SHARE, EDIT)


def test_missing_sender_sends_nothing(app, client, monkeypatch):
    calls = []
    monkeypatch.setattr(mail, "send_links", lambda *a: calls.append(a))
    app.config.update(SMTP_HOST="smtp.test", MAIL_FROM=None, SMTP_USERNAME=None)
    assert 'name="email"' not in client.get("/collections/new").get_data(as_text=True)
    assert _create(client).status_code == 302 and calls == []


def test_value_error_from_email_message_becomes_mail_error(app):
    app.config.update(SMTP_HOST="smtp.test", MAIL_FROM="bad\nsender@example.org")
    with app.test_request_context(), pytest.raises(mail.MailError):
        mail.send_links("me@example.org", SHARE, EDIT)


# ------------------------------------------------------------ validation

@pytest.mark.parametrize("address", [
    "me@example.org", "first.last+tag@sub.example.co.uk", "a@b.io", "o'brien@example.org",
])
def test_valid_addresses(address):
    assert mail.valid_address(address)


@pytest.mark.parametrize("address", [
    "", "me", "me@", "@example.org", "me@example", "me@example.org\nBcc: x@y.example",
    "me@example.org\r\nSubject: hi", "a@example.org, b@example.org", "a@example.org;b@example.org",
    "a b@example.org", "Name <me@example.org>", '"me"@example.org', "me@@example.org", "me@exa_mple.org",
    "me@-example.org", "me@example..org", ".me@example.org", "me..x@example.org", "me@example.123",
    "mé@example.org", "x" * 65 + "@example.org", "me@" + "a" * 250 + ".org", "me@example.org\x00",
])
def test_invalid_addresses(address):
    assert not mail.valid_address(address)


def test_form_rejects_header_injection_without_creating_anything(client, configured_app, monkeypatch):
    calls = []
    monkeypatch.setattr(mail, "send_links", lambda *a: calls.append(a))
    response = _create(client, email="me@example.org\nBcc: victim@example.org")
    assert response.status_code == 400 and calls == []
    assert db.session.scalar(db.select(Collection)) is None


def test_build_message_refuses_bad_recipient(app):
    with app.test_request_context(), pytest.raises(mail.MailError):
        mail.build_message("a@example.org\nBcc: b@example.org", SHARE, EDIT)


# ------------------------------------------------------------ abuse limits

@pytest.fixture
def limited(app, monkeypatch):
    app.config.update(SMTP_HOST="smtp.test", MAIL_FROM="haam@test.example", RATELIMIT_ENABLED=True,
                      MAIL_PER_RECIPIENT_HOURLY=2, MAIL_PER_CLIENT_HOURLY=5, MAIL_DAILY_LIMIT=100)
    sent = []
    monkeypatch.setattr(mail, "send_links", lambda *a: sent.append(a))
    return sent


def _from(ip):
    return {"headers": {"X-Forwarded-For": ip}}


def test_per_recipient_limit_is_case_insensitive_across_clients(client, limited):
    for n, address in enumerate(["victim@example.org", "Victim@Example.org", "VICTIM@example.org"]):
        _create(client, email=address, title=f"c{n}", **_from(f"198.51.100.{n}"))
    assert len(limited) == 2  # the third attempt, from a third client, is not sent


def test_limited_recipient_looks_like_a_failed_send(client, limited):
    pages = []
    for n in range(3):
        ip = f"198.51.100.{n}"
        response = _create(client, email="v@example.org", **_from(ip))
        assert response.status_code == 302  # the collection is created either way
        pages.append(client.get(response.headers["Location"], **_from(ip)).get_data(as_text=True))
    assert "We emailed you" in pages[0] and "We emailed you" in pages[1]
    assert "could not send the email" in pages[2]
    assert "limit" not in pages[2].lower().split("could not send the email")[1][:200]


def test_per_client_limit(client, limited):
    for n in range(8):
        _create(client, email=f"u{n}@example.org", title=f"c{n}")
    assert len(limited) == 5


def test_global_daily_cap(client, app, limited):
    app.config["MAIL_DAILY_LIMIT"] = 3
    for n in range(6):
        _create(client, email=f"u{n}@example.org", title=f"c{n}", **_from(f"203.0.113.{n}"))
    assert len(limited) == 3


def test_rate_limit_rows_never_hold_the_address(client, limited):
    _create(client, email="secret.person@example.org", **_from("203.0.113.77"))
    rows = db.session.scalars(db.select(RateLimitHit)).all()
    assert {r.scope for r in rows} >= {"mail-client", "mail-to", "mail-all"}
    dump = " ".join(f"{r.scope} {r.client_hash}" for r in rows)
    assert "secret" not in dump and "example.org" not in dump and "203.0.113.77" not in dump


def test_no_counting_when_not_configured(client, app, monkeypatch):
    app.config["RATELIMIT_ENABLED"] = True
    monkeypatch.setattr(mail, "send_links", lambda *a: pytest.fail("sent"))
    _create(client)
    assert not [r for r in db.session.scalars(db.select(RateLimitHit)) if r.scope.startswith("mail-")]


# ------------------------------------------------------------ client address

def _address(app, forwarded, remote="192.0.2.1", trusted=None):
    if trusted is not None:
        app.config["TRUSTED_PROXIES"] = trusted
    headers = {"X-Forwarded-For": forwarded} if forwarded is not None else {}
    with app.test_request_context(headers=headers, environ_base={"REMOTE_ADDR": remote}):
        return ratelimit.client_address()


def test_forwarded_header_is_ignored_without_trusted_proxies(app):
    assert _address(app, "6.6.6.6", trusted=0) == "192.0.2.1"


def test_client_is_the_hop_our_proxy_appended_not_the_first(app):
    assert _address(app, "6.6.6.6, 203.0.113.5", trusted=1) == "203.0.113.5"  # spoofed first hop ignored
    assert _address(app, "6.6.6.6, 203.0.113.5, 10.0.0.2", trusted=2) == "203.0.113.5"


def test_missing_or_short_header_falls_back_to_socket(app):
    assert _address(app, None, trusted=1) == "192.0.2.1"
    assert _address(app, "203.0.113.5", trusted=2) == "192.0.2.1"


def test_spoofing_forwarded_for_does_not_dodge_the_limit(app, client):
    app.config.update(RATELIMIT_ENABLED=True, TRUSTED_PROXIES=1)
    for n in range(5):
        client.post("/admin/login", data={"username": "admin", "password": "x"},
                    headers={"X-Forwarded-For": f"10.9.9.{n}, 203.0.113.5"})
    blocked = client.post("/admin/login", data={"username": "admin", "password": "x"},
                          headers={"X-Forwarded-For": "10.1.1.1, 203.0.113.5"})
    assert blocked.status_code == 429
