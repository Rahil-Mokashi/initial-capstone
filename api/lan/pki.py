"""The Main PC's own certificate authority, server certificate and per-device client certificates.

Layout under lan_dir()/pki:
  master.bin     random passphrase, protected by the Protector (Windows DPAPI on a real Main PC)
  ca.key         CA private key, PEM encrypted with that passphrase
  ca.crt         CA certificate (public; clients pin it)
  server.key/.crt  the listener's identity (names = the chosen address and any extra host names)
  crl.pem        revoked device certificates
Client private keys are produced here, sent once inside TLS during enrolment and never stored.
"""

import datetime as dt
import hashlib
import ipaddress
import secrets
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Protocol

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from api.lan import dpapi
from api.lan.config import LanConfig

CA_YEARS = 20
SERVER_DAYS = 825
CLIENT_DAYS = 365 * 5
RENEW_BEFORE_DAYS = 30


class Protector(Protocol):
    secure: bool

    def protect(self, data: bytes) -> bytes: ...

    def unprotect(self, blob: bytes) -> bytes: ...


class DpapiProtector:
    secure = True

    def protect(self, data: bytes) -> bytes:
        return dpapi.protect(data)

    def unprotect(self, blob: bytes) -> bytes:
        return dpapi.unprotect(blob)


class InsecureTestProtector:
    """Reversible but NOT protective. Tests only; a Main PC refuses it (see server.run_main)."""

    secure = False

    def protect(self, data: bytes) -> bytes:
        return b"TEST" + data[::-1]

    def unprotect(self, blob: bytes) -> bytes:
        return blob[4:][::-1]


def fingerprint_of(cert_pem: bytes) -> str:
    cert = x509.load_pem_x509_certificate(cert_pem)
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@dataclass
class ClientIdentity:
    cert_pem: bytes
    key_pem: bytes
    serial: str  # hex
    fingerprint: str


class Pki:
    def __init__(self, folder: Path, protector: Protector):
        self.dir = Path(folder)
        self.protector = protector

    # ---- paths
    @property
    def ca_crt(self) -> Path:
        return self.dir / "ca.crt"

    @property
    def crl_pem(self) -> Path:
        return self.dir / "crl.pem"

    # ---- passphrase
    def _passphrase(self) -> bytes:
        path = self.dir / "master.bin"
        if not path.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.protector.protect(secrets.token_bytes(32).hex().encode()))
        return self.protector.unprotect(path.read_bytes())

    def _write_key(self, name: str, key: ec.EllipticCurvePrivateKey) -> None:
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(self._passphrase()),
        )
        (self.dir / name).write_bytes(pem)

    def _read_key(self, name: str) -> ec.EllipticCurvePrivateKey:
        key = serialization.load_pem_private_key((self.dir / name).read_bytes(), password=self._passphrase())
        assert isinstance(key, ec.EllipticCurvePrivateKey)
        return key

    # ---- CA
    def has_ca(self) -> bool:
        return self.ca_crt.exists() and (self.dir / "ca.key").exists()

    def create_ca(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Petrol Pump ERP"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"Petrol Pump ERP Main PC CA {secrets.token_hex(4)}"),
        ])
        now = _now()
        cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=365 * CA_YEARS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256())
        )
        self._write_key("ca.key", key)
        self.ca_crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    def ca_cert(self) -> x509.Certificate:
        return x509.load_pem_x509_certificate(self.ca_crt.read_bytes())

    def ca_pem(self) -> bytes:
        return self.ca_crt.read_bytes()

    def ca_fingerprint(self) -> str:
        return fingerprint_of(self.ca_pem())

    def _sign(self, subject: x509.Name, public_key, days: int, usage: ExtendedKeyUsageOID, san: Optional[list] = None):
        ca_key, ca = self._read_key("ca.key"), self.ca_cert()
        now = _now()
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject).issuer_name(ca.subject).public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(min(now + dt.timedelta(days=days), ca.not_valid_after_utc))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False, data_encipherment=False,
                                         key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False,
                                         decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        )
        if san:
            builder = builder.add_extension(x509.SubjectAlternativeName(san), critical=False)
        return builder.sign(ca_key, hashes.SHA256())

    # ---- server certificate
    @staticmethod
    def _san(config: LanConfig) -> list:
        names: list = [x509.IPAddress(ipaddress.ip_address(config.bind_address))]
        for n in config.server_names:
            names.append(x509.DNSName(n))
        return names

    def ensure_server_cert(self, config: LanConfig) -> None:
        crt, wanted = self.dir / "server.crt", self._san(config)
        if crt.exists() and (self.dir / "server.key").exists():
            cur = x509.load_pem_x509_certificate(crt.read_bytes())
            have = cur.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            fresh = cur.not_valid_after_utc - _now() > dt.timedelta(days=RENEW_BEFORE_DAYS)
            if fresh and {str(x) for x in have} == {str(x) for x in wanted}:
                return
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Petrol Pump ERP Main PC")])
        cert = self._sign(subject, key.public_key(), SERVER_DAYS, ExtendedKeyUsageOID.SERVER_AUTH, wanted)
        self._write_key("server.key", key)
        crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    # ---- client certificates
    def issue_client(self, device_name: str, device_id: str) -> ClientIdentity:
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Petrol Pump ERP device"),
            x509.NameAttribute(NameOID.COMMON_NAME, device_id),
        ])
        cert = self._sign(subject, key.public_key(), CLIENT_DAYS, ExtendedKeyUsageOID.CLIENT_AUTH)
        pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        return ClientIdentity(pem, key_pem, format(cert.serial_number, "x"), fingerprint_of(pem))

    # ---- revocation list
    def write_crl(self, revoked: Iterable[tuple[str, dt.datetime]]) -> None:
        ca_key, ca = self._read_key("ca.key"), self.ca_cert()
        now = _now()
        builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(ca.subject).last_update(now - dt.timedelta(minutes=5)).next_update(now + dt.timedelta(days=365 * 5))
        )
        for serial_hex, when in revoked:
            builder = builder.add_revoked_certificate(
                x509.RevokedCertificateBuilder().serial_number(int(serial_hex, 16)).revocation_date(when).build()
            )
        crl = builder.sign(ca_key, hashes.SHA256())
        self.crl_pem.write_bytes(crl.public_bytes(serialization.Encoding.PEM))

    # ---- TLS contexts
    def _server_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(self.dir / "server.crt", self.dir / "server.key", password=lambda: self._passphrase())
        return ctx

    def mutual_tls_context(self) -> ssl.SSLContext:
        """The main listener: a client certificate signed by our CA (and not revoked) or no handshake."""
        ctx = self._server_context()
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
        bundle = self.dir / "trust.pem"
        bundle.write_bytes(self.ca_pem() + b"\n" + self.crl_pem.read_bytes())
        ctx.load_verify_locations(cafile=str(bundle))
        return ctx

    def server_only_context(self) -> ssl.SSLContext:
        """The enrolment listener: no client certificate exists yet."""
        return self._server_context()

    # ---- the whole preparation
    def ensure(self, config: LanConfig) -> None:
        if not self.has_ca():
            self.create_ca()
        self.ensure_server_cert(config)
        if not self.crl_pem.exists():
            self.write_crl([])
