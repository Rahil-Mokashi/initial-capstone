"""Windows DPAPI through ctypes (no extra package). Machine scope: the Main PC's service can read what an installer wrote."""

import ctypes
import sys
from ctypes import wintypes

_MACHINE = 0x4  # CRYPTPROTECT_LOCAL_MACHINE
_NO_UI = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def available() -> bool:
    return sys.platform == "win32"


def _call(fn_name: str, data: bytes) -> bytes:
    if not available():
        raise OSError("DPAPI is only available on Windows")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    source = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    args = (ctypes.byref(source), None, None, None, None, _MACHINE | _NO_UI, ctypes.byref(out))
    if fn_name == "CryptUnprotectData":
        args = (ctypes.byref(source), None, None, None, None, _NO_UI, ctypes.byref(out))
    if not getattr(crypt32, fn_name)(*args):
        raise OSError(f"{fn_name} failed (error {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    return _call("CryptProtectData", data)


def unprotect(blob: bytes) -> bytes:
    return _call("CryptUnprotectData", blob)
