"""OS-level keyboard state that Qt itself doesn't expose.

Caps Lock is a toggle key: Qt's own event system reports individual key
presses, not "is this toggle currently on", so there is no portable
Qt/QML API to ask for its current state. On Windows this is available
through the Win32 API directly (GetKeyState), which is exactly what
every other Windows application (including the OS's own login screen)
uses to show its own Caps Lock warning.
"""

import sys

_VK_CAPITAL = 0x14
_TOGGLE_BIT = 0x0001


def is_caps_lock_on() -> bool:
    """True if Caps Lock is currently toggled on.

    Always False off Windows — this app is developed and packaged for
    Windows (see README's Technology stack), and there is no single
    portable equivalent across macOS/Linux worth adding for a warning
    label. A wrong answer here would be misleading, so "unknown"
    degrades to "don't show the warning" rather than a guess.
    """
    if sys.platform != "win32":
        return False
    import ctypes

    return bool(ctypes.windll.user32.GetKeyState(_VK_CAPITAL) & _TOGGLE_BIT)
