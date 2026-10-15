"""An attacker's checklist against the Main PC (LAN build, Phase 8): each test is something a hostile person on the network, or a stolen
device, would try. A failure here is a security bug, not a test to loosen."""

import socket
import ssl
import threading
import time

import httpx
import pytest

from api.lan import live
from api.lan.pki import InsecureTestProtector
from lan_helpers import ADDRESS, MainPc, make_config


@pytest.fixture()
def web_main_pc(session_factory, users, tmp_path):
    """A Main PC that also serves a (fake) web UI folder, with a secret file next to it that must never be reachable."""
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>app</html>")
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    from api.lan import server

    class WithWeb(MainPc):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.app = server.build_main_asgi(self.config, self.lan, session_factory, web_dir=web)
            import uvicorn

            self.server = uvicorn.Server(server.main_uvicorn_config(self.app, self.config, self.pki))
            self.thread = threading.Thread(target=self.server.run, daemon=True)

    with WithWeb(tmp_path / "lan", session_factory, make_config(), InsecureTestProtector()) as pc:
        yield pc


def enrolled(pc, owner_id, name="Counter PC"):
    code, _ = pc.lan.start_pairing(owner_id)
    return pc.client(pc.enrol(name, code))


# ---- reaching files and routes it should not ----------------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/%2e%2e%2fsecret.txt", "/static/../../secret.txt", "//secret.txt"])
def test_the_web_folder_cannot_be_escaped(web_main_pc, owner_id, path):
    with enrolled(web_main_pc, owner_id) as c:
        r = c.get(path)
    assert "TOP SECRET" not in r.text


def test_the_web_ui_itself_needs_an_enrolled_device(web_main_pc, owner_id):
    code, _ = web_main_pc.lan.start_pairing(owner_id)
    device = web_main_pc.enrol("Counter PC", code)
    with web_main_pc.client(device) as c:
        assert c.get("/").text == "<html>app</html>"
    with web_main_pc.client(device, with_token=False) as c:
        assert c.get("/").status_code == 401


# ---- hostile requests ---------------------------------------------------------------------------------------------------------
def test_an_enormous_header_is_refused_without_hurting_the_server(main_pc, device):
    with main_pc.client(device) as c:
        try:
            r = c.get("/api/health", headers={"X-Junk": "a" * 70_000})
            assert r.status_code in (400, 431)
        except httpx.HTTPError:
            pass  # the connection was simply dropped: also fine
    with main_pc.client(device) as c:
        assert c.get("/api/health").status_code == 200  # still alive


def test_garbage_on_the_secure_port_is_dropped_and_the_server_keeps_serving(main_pc, device):
    for junk in (b"GET / HTTP/1.1\r\n\r\n", b"\x16\x03\x01\x00\xff" + b"A" * 200, b"\x00" * 500, b"POST /api/auth/login HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"):
        with socket.create_connection((ADDRESS, main_pc.config.port), 5) as s:
            s.sendall(junk)
            s.settimeout(2)
            try:
                s.recv(100)
            except (socket.timeout, ConnectionError, OSError):
                pass
    with main_pc.client(device) as c:
        assert c.get("/api/health").status_code == 200


def test_a_connection_that_never_finishes_its_handshake_does_not_block_others(main_pc, device):
    idle = [socket.create_connection((ADDRESS, main_pc.config.port), 5) for _ in range(20)]  # TCP connects, TLS never starts
    try:
        began = time.time()
        with main_pc.client(device) as c:
            assert c.get("/api/health").status_code == 200
        assert time.time() - began < 5
    finally:
        [s.close() for s in idle]


def test_old_tls_and_weak_ciphers_are_not_offered(main_pc):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    ctx.minimum_version = ctx.maximum_version = ssl.TLSVersion.TLSv1_2  # TLS 1.3 has its own fixed, strong suites
    try:
        ctx.set_ciphers("RC4:3DES:DES:NULL:EXPORT:MD5")
    except ssl.SSLError:
        return  # this OpenSSL cannot even offer them: nothing to refuse
    with pytest.raises(ssl.SSLError):
        with socket.create_connection((ADDRESS, main_pc.config.port), 5) as s:
            ctx.wrap_socket(s)


# ---- stolen things -------------------------------------------------------------------------------------------------------------
def test_a_stolen_certificate_alone_and_a_stolen_token_alone_are_both_useless(main_pc, device, owner_id):
    with main_pc.client(device, with_token=False) as c:
        assert c.get("/api/tanks").status_code == 401
    # a token from one device sent with a different (but valid) device's certificate: still a valid pair of enrolled things, so it must
    # be recorded against the TOKEN's device, never silently trusted as the certificate's device
    code, _ = main_pc.lan.start_pairing(owner_id)
    other = main_pc.enrol("Thief's PC", code)
    with main_pc.client({**other, "token": device["token"]}) as c:
        assert c.get("/api/system/device").json()["device"] == "Counter PC (127.0.0.1)"


def test_a_removed_device_loses_the_event_stream_too(main_pc, device, owner_id):
    from api_helpers import PASSWORD

    with main_pc.client(device) as c:
        token = c.post("/api/auth/login", json={"username": "owner1", "password": PASSWORD}).json()["token"]
        main_pc.lan.devices.revoke(device["device_id"], owner_id, "stolen")
        assert c.get("/api/events", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_a_session_token_from_one_sign_in_cannot_be_used_after_logout(main_pc, device):
    from api_helpers import PASSWORD

    with main_pc.client(device) as c:
        token = c.post("/api/auth/login", json={"username": "manager1", "password": PASSWORD}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        assert c.get("/api/tanks", headers=h).status_code == 200
        c.post("/api/auth/logout", headers=h)
        assert c.get("/api/tanks", headers=h).status_code == 401


# ---- flooding ------------------------------------------------------------------------------------------------------------------
def test_too_many_open_event_streams_are_refused_not_allowed_to_eat_the_server(main_pc, device, monkeypatch):
    from api_helpers import PASSWORD

    monkeypatch.setattr(live, "MAX_SUBSCRIBERS", 2)
    with main_pc.client(device) as c:
        h = {"Authorization": f"Bearer {c.post('/api/auth/login', json={'username': 'owner1', 'password': PASSWORD}).json()['token']}"}
        opened = []
        try:
            for _ in range(2):
                cm = c.stream("GET", "/api/events", headers=h)
                opened.append(cm)
                assert cm.__enter__().status_code == 200
            with main_pc.client(device) as c2:
                assert c2.get("/api/events", headers=h).status_code == 503
        finally:
            for cm in opened:
                cm.__exit__(None, None, None)


# ---- what must never be written down ------------------------------------------------------------------------------------------------
def test_tokens_passwords_and_keys_never_reach_the_logs(main_pc, device, caplog):
    from api_helpers import PASSWORD

    with caplog.at_level("DEBUG"):
        with main_pc.client(device) as c:
            c.post("/api/auth/login", json={"username": "manager1", "password": "WrongPassword!1"})
            token = c.post("/api/auth/login", json={"username": "manager1", "password": PASSWORD}).json()["token"]
            c.get("/api/tanks", headers={"Authorization": f"Bearer {token}"})
    text = caplog.text
    for secret in (device["token"], token, PASSWORD, "WrongPassword!1", device["key_pem"].splitlines()[1]):
        assert secret not in text


def test_an_unexpected_failure_says_nothing_about_the_inside(main_pc, device, monkeypatch):
    from api.routers import tanks

    def boom(*a, **k):
        raise RuntimeError("secret internal detail C:\\Users\\Asus\\secrets.db")

    monkeypatch.setattr(tanks, "list_tanks", boom, raising=False)
    from api_helpers import PASSWORD

    with main_pc.client(device) as c:
        token = c.post("/api/auth/login", json={"username": "manager1", "password": PASSWORD}).json()["token"]
        import app.services.tank_service as ts

        monkeypatch.setattr(ts.TankService, "list_tanks", boom, raising=False)
        r = c.get("/api/tanks", headers={"Authorization": f"Bearer {token}"})
    assert "secret internal detail" not in r.text and "Traceback" not in r.text and "C:\\" not in r.text
