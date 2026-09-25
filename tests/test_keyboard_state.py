"""app/core/keyboard_state.py: Caps Lock state read via the Win32 API,
since Qt has no portable way to query a toggle key's current state.
"""


def test_caps_lock_is_false_off_windows(monkeypatch):
    import app.core.keyboard_state as keyboard_state

    monkeypatch.setattr(keyboard_state.sys, "platform", "linux")

    assert keyboard_state.is_caps_lock_on() is False


def test_caps_lock_on_windows_reads_the_toggle_bit(monkeypatch):
    import ctypes
    import types

    import app.core.keyboard_state as keyboard_state

    monkeypatch.setattr(keyboard_state.sys, "platform", "win32")

    fake_user32 = types.SimpleNamespace(GetKeyState=lambda vk: 0x0001)
    fake_windll = types.SimpleNamespace(user32=fake_user32)
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)

    assert keyboard_state.is_caps_lock_on() is True


def test_caps_lock_off_when_toggle_bit_is_clear(monkeypatch):
    import ctypes
    import types

    import app.core.keyboard_state as keyboard_state

    monkeypatch.setattr(keyboard_state.sys, "platform", "win32")

    fake_user32 = types.SimpleNamespace(GetKeyState=lambda vk: 0x0000)
    fake_windll = types.SimpleNamespace(user32=fake_user32)
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)

    assert keyboard_state.is_caps_lock_on() is False
