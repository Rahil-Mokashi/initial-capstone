"""The optional owner summary email: off by default, outbound only, figures only, a password that is never stored in the clear,
and a sender that can never hold anything else up."""

import base64
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from api.lan.mail_scheduler import MailScheduler
from api.lan.pki import InsecureTestProtector
from api.lan.secrets_store import SecretStore
from api.services import Services
from api_helpers import audit_chain_ok, audit_events
from pump_day import TODAY
from test_api_close_desk import _body, _modes, _setup

REPO = Path(__file__).resolve().parents[2]


class FakeSmtp:
    """Just enough SMTP for smtplib: EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT. Records what it was given."""

    def __init__(self):
        self.messages, self.logins, self.fail_auth = [], [], False
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._talk, args=(conn,), daemon=True).start()

    def _talk(self, conn):
        f = conn.makefile("rwb")

        def say(text):
            f.write((text + "\r\n").encode())
            f.flush()

        say("220 fake ESMTP")
        data_mode, buf = False, []
        while True:
            line = f.readline()
            if not line:
                return
            text = line.decode().rstrip("\r\n")
            if data_mode:
                if text == ".":
                    self.messages.append("\n".join(buf))
                    data_mode, buf = False, []
                    say("250 queued")
                else:
                    buf.append(text[1:] if text.startswith("..") else text)
                continue
            cmd = text.upper()
            if cmd.startswith("EHLO"):
                f.write(b"250-fake\r\n250 AUTH PLAIN\r\n")
                f.flush()
            elif cmd.startswith("AUTH PLAIN"):
                parts = base64.b64decode(text.split()[2]).split(b"\0")
                self.logins.append((parts[1].decode(), parts[2].decode()))
                say("535 nope" if self.fail_auth else "235 ok")
            elif cmd.startswith(("MAIL", "RCPT")):
                say("250 ok")
            elif cmd == "DATA":
                data_mode = True
                say("354 go")
            elif cmd == "QUIT":
                say("221 bye")
                return
            else:
                say("250 ok")

    def close(self):
        self.sock.close()


@pytest.fixture()
def smtp():
    server = FakeSmtp()
    yield server
    server.close()


@pytest.fixture()
def store(tmp_path, client):
    s = SecretStore(tmp_path / "secrets", InsecureTestProtector(), allow_insecure=True)
    client.app.state.secrets = s
    return s


def configure(client, owner, port, **over):
    values = {"mail_enabled": "on", "mail_host": "127.0.0.1", "mail_port": str(port), "mail_security": "none", "mail_user": "pump",
              "mail_from": "pump@example.com", "mail_to": "owner@example.com, partner@example.com", "mail_send_hour": "0", **over}
    for key, value in values.items():
        r = client.put(f"/api/pump-settings/{key}", headers=owner, json={"value": value})
        assert r.status_code == 200, (key, r.text)


def scheduler(session_factory, store, when=None):
    def make():
        db = session_factory()
        return Services(db, 8, secrets=store), db.close

    return MailScheduler(make, now=lambda: when or datetime(2026, 10, 13, 21, 5))


def test_mail_is_off_by_default_and_nothing_is_queued_or_sent(client, owner, store, session_factory, smtp, manager, data_entry):
    status = client.get("/api/mail", headers=owner).json()
    assert status["enabled"] is False and status["pending"] == 0
    nozzle, shift, _ = _setup(client, manager)
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, _modes(client, data_entry, shift["id"])))
    scheduler(session_factory, store).tick()
    assert client.get("/api/mail", headers=owner).json()["outbox"] == [] and smtp.messages == []


def test_only_owners_may_see_or_change_the_email_settings(client, accountant, manager, data_entry, attendant):
    for who in (accountant, manager, data_entry, attendant):
        assert client.get("/api/mail", headers=who).status_code == 403
        assert client.post("/api/mail/test", headers=who).status_code == 403
        assert client.put("/api/mail/password", headers=who, json={"password": "x"}).status_code == 403
        assert client.put("/api/pump-settings/mail_enabled", headers=who, json={"value": "on"}).status_code == 403


def test_what_is_missing_is_said_in_words_and_a_wide_open_server_is_refused(client, owner, store):
    client.put("/api/pump-settings/mail_enabled", headers=owner, json={"value": "on"})
    problems = client.get("/api/mail", headers=owner).json()["problems"]
    assert "Fill in the mail server." in problems and "Fill in who it goes to." in problems
    configure(client, owner, 25, mail_host="mail.example.com", mail_security="none")
    assert any("only allowed to this PC itself" in p for p in client.get("/api/mail", headers=owner).json()["problems"])


def test_the_password_is_stored_protected_and_is_never_shown_saved_or_logged(client, owner, store, smtp, tmp_path, session_factory, caplog):
    configure(client, owner, smtp.port)
    assert client.put("/api/mail/password", headers=owner, json={"password": "s3cret-mail-pw"}).status_code == 204
    assert client.get("/api/mail", headers=owner).json()["password_set"] is True
    everything = client.get("/api/mail", headers=owner).text + client.get("/api/pump-settings", headers=owner).text
    assert "s3cret-mail-pw" not in everything
    blob = b"".join(p.read_bytes() for p in (tmp_path / "secrets").iterdir())
    assert b"s3cret-mail-pw" not in blob  # the file holds the protected blob, not the password
    db_bytes = Path(session_factory.kw["bind"].url.database).read_bytes()
    assert b"s3cret-mail-pw" not in db_bytes
    client.post("/api/mail/test", headers=owner)
    assert "s3cret-mail-pw" not in caplog.text
    assert audit_events(session_factory, "mail_password_set") and all("s3cret-mail-pw" not in (e.description or "") for e in audit_events(session_factory, "mail_password_set"))


def test_a_test_message_goes_out_with_the_saved_password_and_says_what_went_wrong_when_it_cannot(client, owner, store, smtp):
    configure(client, owner, smtp.port)
    client.put("/api/mail/password", headers=owner, json={"password": "pw1"})
    ok = client.post("/api/mail/test", headers=owner)
    assert ok.status_code == 200 and smtp.logins == [("pump", "pw1")]
    assert "Test message" in smtp.messages[0] and "No figures are in this message" in smtp.messages[0]
    smtp.fail_auth = True
    bad = client.post("/api/mail/test", headers=owner)
    assert bad.status_code == 422 and "did not accept" in bad.json()["error"]["message"]
    smtp.close()
    gone = client.post("/api/mail/test", headers=owner)
    assert gone.status_code == 422


def test_the_daily_summary_is_figures_only_once_a_day(client, owner, store, smtp, session_factory, manager, data_entry, db):
    from app.models.customer import Customer

    configure(client, owner, smtp.port)
    client.put("/api/mail/password", headers=owner, json={"password": "pw"})
    client.post("/api/customers", headers=manager, json={"name": "ACME Secret Traders"})
    nozzle, shift, _ = _setup(client, manager)
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, _modes(client, data_entry, shift["id"])))
    s = scheduler(session_factory, store, datetime.fromisoformat(f"{TODAY}T21:05:00"))
    s.tick()
    s.tick()  # the same day again: nothing new
    assert len(smtp.messages) == 1
    body = smtp.messages[0]
    assert "Total sale: 50000.00" in body and "Litres sold: 500.000" in body and "SHORT 1000.00" in body and "Morning" in body
    for name in ("ACME", "Secret", "Ravi", "Kumar", "dataentry1", "owner1", "manager1"):
        assert name not in body, name
    assert "To: owner@example.com, partner@example.com" in body.replace("\r", "")
    outbox = client.get("/api/mail", headers=owner).json()["outbox"]
    assert [(o["status"], o["attempts"]) for o in outbox] == [("sent", 1)]
    assert audit_events(session_factory, "mail_sent") and audit_chain_ok(session_factory)


def test_before_the_chosen_hour_nothing_is_sent(client, owner, store, smtp, session_factory, manager, data_entry):
    configure(client, owner, smtp.port, mail_send_hour="21")
    client.put("/api/mail/password", headers=owner, json={"password": "pw"})
    nozzle, shift, _ = _setup(client, manager)
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, _modes(client, data_entry, shift["id"])))
    scheduler(session_factory, store, datetime.fromisoformat(f"{TODAY}T09:00:00")).tick()
    assert smtp.messages == []


def test_a_dead_mail_server_is_retried_later_then_given_up_and_never_raises_or_waits_long(client, owner, store, session_factory, manager, data_entry):
    dead = socket.socket()
    dead.bind(("127.0.0.1", 0))
    port = dead.getsockname()[1]
    dead.close()  # nothing listens here
    configure(client, owner, port)
    client.put("/api/mail/password", headers=owner, json={"password": "pw"})
    nozzle, shift, _ = _setup(client, manager)
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, _modes(client, data_entry, shift["id"])))
    start = time.time()
    for n in range(7):
        scheduler(session_factory, store, datetime.fromisoformat(f"{TODAY}T21:{5 + n * 20 % 40:02d}:00")).tick()
        with session_factory() as db:  # a pretend later time: the retry is not due yet, so make it due
            from app.models.mail_outbox import MailOutbox

            for row in db.query(MailOutbox).all():
                row.next_try_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
            db.commit()
    assert time.time() - start < 20
    row = client.get("/api/mail", headers=owner).json()["outbox"][0]
    assert row["status"] == "gave_up" and row["attempts"] == 6 and row["last_error"]
    assert audit_events(session_factory, "mail_failed") and audit_chain_ok(session_factory)


def test_a_slow_mail_server_does_not_slow_a_request(client, owner, store, session_factory, manager, data_entry):
    """The sender is a separate thread: while it is stuck on a mail server that never answers, requests are answered at once."""
    stuck = socket.socket()
    stuck.bind(("127.0.0.1", 0))
    stuck.listen(5)  # accepts connections (the kernel does) but never speaks
    configure(client, owner, stuck.getsockname()[1])
    client.put("/api/mail/password", headers=owner, json={"password": "pw"})
    nozzle, shift, _ = _setup(client, manager)
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, _modes(client, data_entry, shift["id"])))
    s = scheduler(session_factory, store, datetime.fromisoformat(f"{TODAY}T21:05:00"))
    thread = threading.Thread(target=s.tick, daemon=True)
    thread.start()
    time.sleep(0.5)
    began = time.time()
    assert client.get("/api/tanks", headers=owner).status_code == 200
    assert client.get("/api/health").status_code == 200
    assert time.time() - began < 3
    stuck.close()


def test_the_mail_module_is_the_only_code_that_can_connect_out():
    offenders = []
    for folder in ("api", "app"):
        for path in (REPO / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(word in text for word in ("import smtplib", "from smtplib", "import requests", "urllib.request", "import socket")):
                offenders.append(str(path.relative_to(REPO)))
    allowed = {"app\\services\\mail_service.py", "app/services/mail_service.py", "api\\lan\\server.py", "api/lan/server.py",
               "api\\lan\\fs_security.py", "api/lan/fs_security.py"}
    assert [o for o in offenders if o not in allowed and not o.startswith(("app\\ui", "app/ui"))] == []
