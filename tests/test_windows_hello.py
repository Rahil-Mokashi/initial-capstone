"""app/core/windows_hello.py: best-effort Windows Hello detection for
the Lock Screen. The `winsdk` optional dependency isn't installed in
this environment (or CI), so these tests exercise the "unavailable"
degrade path directly rather than the real WinRT call - the real path
can only be verified on a Windows machine with Windows Hello enrolled
and winsdk installed, which is exactly why it's designed to degrade
this safely rather than assumed to work.
"""

import app.core.windows_hello as windows_hello


def test_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(windows_hello.sys, "platform", "linux")
    assert windows_hello.is_available() is False


def test_unavailable_when_winsdk_is_not_installed(monkeypatch):
    monkeypatch.setattr(windows_hello, "_WINSDK_AVAILABLE", False)
    monkeypatch.setattr(windows_hello.sys, "platform", "win32")
    assert windows_hello.is_available() is False


def test_verify_returns_false_when_unavailable(monkeypatch):
    monkeypatch.setattr(windows_hello, "is_available", lambda: False)
    assert windows_hello.verify() is False
