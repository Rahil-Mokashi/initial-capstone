"""Keys are never stored readable, DPAPI round-trips, and folders are limited to SYSTEM, Administrators and the running account."""

import subprocess
import sys

import pytest

from api.lan import dpapi, fs_security
from api.lan.config import LanConfigError
from api.lan.pki import InsecureTestProtector, Pki
from lan_helpers import make_config

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_private_keys_on_disk_are_encrypted(tmp_path):
    pki = Pki(tmp_path / "pki", InsecureTestProtector())
    pki.ensure(make_config())
    for name in ("ca.key", "server.key"):
        text = (tmp_path / "pki" / name).read_text()
        assert "BEGIN ENCRYPTED PRIVATE KEY" in text and "BEGIN PRIVATE KEY" not in text
    # the passphrase file is not the passphrase itself
    assert (tmp_path / "pki" / "master.bin").read_bytes().startswith(b"TEST")


@windows_only
def test_dpapi_protects_and_returns_the_same_bytes_and_the_blob_hides_them():
    secret = b"correct horse battery staple"
    blob = dpapi.protect(secret)
    assert secret not in blob and dpapi.unprotect(blob) == secret


@windows_only
def test_dpapi_refuses_a_tampered_blob():
    blob = bytearray(dpapi.protect(b"x" * 32))
    blob[-5] ^= 0xFF
    with pytest.raises(OSError):
        dpapi.unprotect(bytes(blob))


@windows_only
def test_a_real_pki_with_dpapi_can_be_reopened(tmp_path):
    from api.lan.pki import DpapiProtector

    config = make_config()
    first = Pki(tmp_path / "pki", DpapiProtector())
    first.ensure(config)
    again = Pki(tmp_path / "pki", DpapiProtector())
    again.ensure(config)  # reads the same keys back; does not create a second authority
    assert first.ca_fingerprint() == again.ca_fingerprint()
    again.mutual_tls_context()


@windows_only
def test_hardening_removes_everyone_and_users_and_is_detected_when_undone(tmp_path):
    folder = tmp_path / "secure"
    fs_security.harden(folder)
    assert fs_security.is_hardened(folder)
    listing = subprocess.run(["icacls", str(folder)], capture_output=True, text=True).stdout
    for broad in ("Everyone", "BUILTIN\\Users", "Authenticated Users"):
        assert broad not in listing
    subprocess.run(["icacls", str(folder), "/grant", "*S-1-1-0:(R)"], capture_output=True)  # Everyone: read
    assert not fs_security.is_hardened(folder)


def test_prepare_refuses_to_start_when_keys_cannot_be_protected_even_with_a_good_config(tmp_path):
    from api.lan import server

    with pytest.raises(LanConfigError):
        server.prepare(make_config(), InsecureTestProtector(), tmp_path)
    assert not (tmp_path / "pki").exists()  # nothing was created before the refusal
