"""Passphrase encryption for backup copies that leave the Main PC (a USB stick, a network folder).

A backup on the same disk is protected by the folder's access list and BitLocker; a copy on a stick is not, so it is encrypted:
scrypt turns the passphrase into a key, AES-256-GCM encrypts and authenticates the whole file. A wrong passphrase or any change to the
file makes decryption fail; nothing readable is ever written for a failed attempt.

File layout: b"PPERPBK1" | salt (16) | nonce (12) | ciphertext+tag.
"""

import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"PPERPBK1"
MIN_LENGTH = 10


class BackupCryptoError(Exception):
    pass


def _key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def check_passphrase(passphrase: str) -> None:
    if len(passphrase) < MIN_LENGTH:
        raise BackupCryptoError(f"Use a passphrase of at least {MIN_LENGTH} characters.")


def encrypt_file(source: str, destination: str, passphrase: str) -> None:
    check_passphrase(passphrase)
    salt, nonce = os.urandom(16), os.urandom(12)
    data = Path(source).read_bytes()
    blob = MAGIC + salt + nonce + AESGCM(_key(passphrase, salt)).encrypt(nonce, data, MAGIC)
    tmp = Path(destination).with_suffix(Path(destination).suffix + ".part")
    tmp.write_bytes(blob)
    os.replace(tmp, destination)


def decrypt_file(source: str, destination: str, passphrase: str) -> None:
    blob = Path(source).read_bytes()
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 28:
        raise BackupCryptoError("This is not an encrypted backup from this program.")
    salt, nonce, body = blob[8:24], blob[24:36], blob[36:]
    try:
        data = AESGCM(_key(passphrase, salt)).decrypt(nonce, body, MAGIC)
    except InvalidTag:
        raise BackupCryptoError("Wrong passphrase, or the file was changed or damaged.") from None
    Path(destination).write_bytes(data)
