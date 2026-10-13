"""Main PC mode: refuses unsafe configuration, demands a certificate AND a device token, enrols with a short-lived single-use code."""

import ipaddress
import socket
import ssl

import httpx
import pytest

from api.lan.config import LanConfigError
from api.lan.devices import CODE_MINUTES, MAX_WRONG_TRIES, PairingManager, pairing_key, proof
from api.lan.pki import InsecureTestProtector, Pki, fingerprint_of
from lan_helpers import ADDRESS, MainPc, client_context, make_config
from api_helpers import audit_chain_ok, audit_events

TLS_FAILURES = (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError)


# ---- configuration is refused rather than guessed -------------------------------------------------------------
@pytest.mark.parametrize("over,words", [
    ({"bind_address": "0.0.0.0"}, "every network card"),
    ({"bind_address": ""}, "own network address"),
    ({"bind_address": "8.8.8.8"}, "private"),
    ({"bind_address": "pump-pc"}, "own network address"),
    ({"allowed_subnets": []}, "at least one"),
    ({"allowed_subnets": ["0.0.0.0/0"]}, "too wide"),
    ({"allowed_subnets": ["10.0.0.0/8"]}, "too wide"),
    ({"allowed_subnets": ["8.8.8.0/24"]}, "too wide"),
])
def test_unsafe_configuration_is_refused(over, words):
    with pytest.raises(LanConfigError, match=words):
        make_config(**over).validate_for_main()


def test_same_port_for_both_listeners_is_refused():
    with pytest.raises(LanConfigError, match="differ"):
        make_config(pairing_port=8443, port=8443).validate_for_main()


def test_single_pc_is_the_default_and_a_broken_file_is_not_silently_single(tmp_path):
    from api.lan import config

    assert config.load(tmp_path / "none.json").mode == "single"
    (tmp_path / "lan.json").write_text("{not json")
    with pytest.raises(LanConfigError):
        config.load(tmp_path / "lan.json")


def test_keys_that_cannot_be_protected_stop_the_main_pc(tmp_path):
    from api.lan import server

    with pytest.raises(LanConfigError, match="DPAPI"):
        server.prepare(make_config(), InsecureTestProtector(), tmp_path)


# ---- the certificate is the first gate --------------------------------------------------------------------------
def test_no_client_certificate_means_no_conversation(main_pc, device):
    with pytest.raises(TLS_FAILURES):
        httpx.get(f"{main_pc.base}/api/health", verify=str(main_pc.folder / "pki" / "ca.crt"))


def test_a_certificate_from_another_authority_is_refused(main_pc, device, tmp_path):
    other = Pki(tmp_path / "other", InsecureTestProtector())
    other.ensure(make_config())
    ident = other.issue_client("evil", "evil-id")
    (tmp_path / "c.pem").write_bytes(ident.cert_pem)
    (tmp_path / "k.pem").write_bytes(ident.key_pem)
    with pytest.raises(TLS_FAILURES):
        with httpx.Client(verify=client_context(main_pc.folder / "pki" / "ca.crt", tmp_path / "c.pem", tmp_path / "k.pem")) as c:
            c.get(f"{main_pc.base}/api/health", headers={"X-Device-Token": device["token"]})


def test_a_client_that_does_not_trust_our_authority_will_not_connect(main_pc, device, tmp_path):
    other = Pki(tmp_path / "other", InsecureTestProtector())
    other.ensure(make_config())
    (tmp_path / "wrong-ca.pem").write_bytes(other.ca_pem())
    with pytest.raises(httpx.ConnectError):
        with httpx.Client(base_url=main_pc.base, verify=str(tmp_path / "wrong-ca.pem")) as c:
            c.get("/api/health")


def test_old_tls_versions_are_not_spoken(main_pc):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
        ctx.maximum_version = ssl.TLSVersion.TLSv1_1
    except ValueError:
        pytest.skip("this OpenSSL cannot even offer TLS 1.1")
    with pytest.raises(ssl.SSLError):
        with socket.create_connection((ADDRESS, main_pc.config.port), 5) as s:
            ctx.wrap_socket(s)


def test_plain_http_gets_nothing(main_pc):
    with pytest.raises(httpx.HTTPError):
        httpx.get(f"http://{ADDRESS}:{main_pc.config.port}/api/health", timeout=3)


# ---- the device token is the second gate ----------------------------------------------------------------------------
def test_certificate_without_the_device_token_gets_nothing(main_pc, device):
    with main_pc.client(device, with_token=False) as c:
        r = c.get("/api/health")
    assert r.status_code == 401 and r.json()["error"]["code"] == "device_not_recognised"


def test_a_guessed_token_is_refused(main_pc, device):
    with main_pc.client(device) as c:
        r = c.get("/api/health", headers={"X-Device-Token": "0" * 64})
    assert r.status_code == 401


def test_certificate_and_token_reach_the_api_and_the_old_launch_secret_is_not_needed(main_pc, device):
    with main_pc.client(device) as c:
        assert c.get("/api/health").json() == {"status": "ok"}
        assert c.get("/api/system/device").json()["device"] == "Counter PC (127.0.0.1)"


def test_docs_and_openapi_do_not_exist_and_nobody_can_shut_the_main_pc_down(main_pc, device):
    with main_pc.client(device) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path).status_code == 404, path
        assert c.post("/api/system/shutdown").status_code == 404
        assert c.get("/api/health").status_code == 200  # still alive


# ---- the network and request rules --------------------------------------------------------------------------------
def test_allow_list_blocks_a_valid_device_from_the_wrong_network(main_pc, device):
    main_pc.app.nets[:] = [ipaddress.ip_network("10.9.0.0/16")]  # the owner narrowed the list to a network this PC is not in
    with main_pc.client(device) as c:
        r = c.get("/api/health")
    assert r.status_code == 403 and r.json()["error"]["code"] == "network_not_allowed"
    assert main_pc.blocks and main_pc.blocks[0][0] == "network"


def test_an_unexpected_host_header_is_refused(main_pc, device):
    with main_pc.client(device) as c:
        r = c.get("/api/health", headers={"Host": "evil.example"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_host"


def test_big_requests_are_refused_and_so_are_undeclared_sizes(main_pc, device):
    with main_pc.client(device) as c:
        r = c.post("/api/auth/login", content=b"x" * (main_pc.config.max_body_bytes + 10), headers={"content-type": "application/json"})
        assert r.status_code == 413
        r = c.post("/api/auth/login", content=iter([b"{}"]), headers={"content-type": "application/json"})
        assert r.status_code == 411


def test_one_device_cannot_flood_the_main_pc(session_factory, users, tmp_path, owner_id):
    with MainPc(tmp_path / "lan", session_factory, make_config(requests_per_minute=10), InsecureTestProtector()) as pc:
        code, _ = pc.lan.start_pairing(owner_id)
        dev = pc.enrol("Busy PC", code)
        with pc.client(dev) as c:
            codes = [c.get("/api/health").status_code for _ in range(14)]
    assert codes[:10] == [200] * 10 and set(codes[10:]) == {429}


# ---- enrolment -------------------------------------------------------------------------------------------------------
def test_enrolment_port_is_closed_until_the_owner_asks_for_a_code(main_pc, owner_id):
    def reachable() -> bool:
        try:
            httpx.get(f"https://{ADDRESS}:{main_pc.config.pairing_port}/pair/ca", verify=False, timeout=2)
            return True
        except httpx.HTTPError:
            return False

    assert not reachable()
    main_pc.lan.start_pairing(owner_id)
    assert reachable()
    main_pc.lan.cancel_pairing()
    assert not reachable()


def test_a_code_works_once_and_then_the_door_closes(main_pc, owner_id):
    code, minutes = main_pc.lan.start_pairing(owner_id)
    assert minutes == CODE_MINUTES and len(code.replace("-", "")) == 10
    first = main_pc.enrol("Counter PC", code)
    assert first["status"] == 200
    # the server proves it knew the code as well
    assert first["server_proof"] == proof(first["key"], "ok", first["nonce"], first["fingerprint"], first["token"])
    assert fingerprint_of(first["ca_pem"].encode()) == first["fingerprint"]
    assert not main_pc.lan.devices.pairing.active()


def test_the_same_code_cannot_enrol_a_second_device(main_pc, owner_id):
    code, _ = main_pc.lan.start_pairing(owner_id)
    assert main_pc.enrol("First PC", code)["status"] == 200
    try:
        second = main_pc.enrol("Second PC", code)["status"]
    except httpx.HTTPError:
        second = 403  # the enrolment port may already be closed: even better
    assert second == 403


def test_wrong_codes_burn_the_code(main_pc, owner_id):
    code, _ = main_pc.lan.start_pairing(owner_id)
    for _ in range(MAX_WRONG_TRIES):
        assert main_pc.enrol("Thief", "AAAAA-BBBBB")["status"] == 403
    assert not main_pc.lan.devices.pairing.active()


def test_an_expired_code_is_dead():
    clock = [0.0]
    pm = PairingManager(clock=lambda: clock[0])
    code, _ = pm.create("u1")
    p = proof(pairing_key(code), "enrol", "pc", "n" * 16, "f" * 64)
    clock[0] = CODE_MINUTES * 60 + 1
    assert pm.consume("pc", "n" * 16, "f" * 64, p) is None


def test_a_machine_in_the_middle_with_its_own_authority_is_noticed(main_pc, owner_id):
    code, _ = main_pc.lan.start_pairing(owner_id)
    # the client computed its proof over a fingerprint the real Main PC does not have
    assert main_pc.enrol("Counter PC", code, tamper_fingerprint=True)["status"] == 403


def test_every_enrolment_and_refusal_is_audited_with_the_device_and_address(main_pc, owner_id, session_factory):
    code, _ = main_pc.lan.start_pairing(owner_id)
    main_pc.enrol("Thief", "AAAAA-BBBBB")
    main_pc.enrol("Counter PC", code)
    ok, bad = audit_events(session_factory, "device_enrolled"), audit_events(session_factory, "device_enrol_refused")
    assert len(ok) == 1 and "Counter PC" in ok[0].description and "127.0.0.1" in ok[0].device_info and ok[0].actor_id == owner_id
    assert len(bad) == 1 and "Thief" in bad[0].description
    assert audit_chain_ok(session_factory)


def test_the_client_private_key_is_not_kept_on_the_main_pc(main_pc, device):
    blob = b"".join(p.read_bytes() for p in main_pc.folder.rglob("*") if p.is_file() and not p.name.startswith(("dev-", "seen-")))
    assert device["key_pem"].encode().strip() not in blob


# ---- removing a device -------------------------------------------------------------------------------------------------
def test_removing_a_device_stops_it_at_once_and_is_recorded(main_pc, device, owner_id, session_factory):
    with main_pc.client(device) as c:
        assert c.get("/api/health").status_code == 200
        main_pc.lan.devices.revoke(device["device_id"], owner_id, "PC was stolen")
        r = c.get("/api/health")
    assert r.status_code == 401
    ev = audit_events(session_factory, "device_revoked")
    assert len(ev) == 1 and "stolen" in ev[0].description
    assert audit_chain_ok(session_factory)


def test_a_removed_device_certificate_is_also_on_the_revocation_list(main_pc, device, owner_id):
    from cryptography import x509

    main_pc.lan.devices.revoke(device["device_id"], owner_id, "lost")
    crl = x509.load_pem_x509_crl((main_pc.folder / "pki" / "crl.pem").read_bytes())
    cert = x509.load_pem_x509_certificate(device["cert_pem"].encode())
    assert crl.get_revoked_certificate_by_serial_number(cert.serial_number) is not None


def test_removing_without_a_reason_records_that_none_was_given(main_pc, device, owner_id):
    assert main_pc.lan.devices.revoke(device["device_id"], owner_id, "  ").revoke_reason == "No reason given"
