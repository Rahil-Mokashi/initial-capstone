"""Best-effort Windows Hello support for the main window's Lock Screen
(app/ui/lock_screen_dialog.py).

Deliberately lightweight (2026-09-25 user decision, choosing this over a
full native integration): detects whether Windows Hello is set up on
this machine and, if so, offers the OS's own consent prompt
(fingerprint/face/PIN, whichever the user has enrolled) as a shortcut to
RESUME an already-open session. It never touches credential storage of
its own and is not involved in the initial sign-in at all - see
lock_screen_dialog.py's own docstring for why that distinction matters.

The `winsdk` package (Python bindings for the Windows Runtime) is an
optional dependency: everything here degrades to "unavailable" if it
isn't installed, on a platform other than Windows, or if Windows Hello
itself isn't enrolled - the button that would trigger this simply never
appears in that case, rather than the app depending on it.
"""

import asyncio
import sys

try:
    from winsdk.windows.security.credentials.ui import (
        UserConsentVerificationResult,
        UserConsentVerifier,
        UserConsentVerifierAvailability,
    )

    _WINSDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only where winsdk is installed
    _WINSDK_AVAILABLE = False


def is_available() -> bool:
    """True only when there is a real chance the consent prompt will
    work: Windows, the optional dependency installed, and Windows Hello
    actually set up on this machine. Never guesses - anything it can't
    positively confirm is treated as unavailable."""
    if sys.platform != "win32" or not _WINSDK_AVAILABLE:
        return False
    try:
        availability = asyncio.run(UserConsentVerifier.check_availability_async())
        return availability == UserConsentVerifierAvailability.AVAILABLE
    except Exception:  # noqa: BLE001 - any WinRT failure means "not available", not a crash
        return False


def verify(message: str = "Unlock Petrol Pump ERP") -> bool:
    """Shows the OS's own Windows Hello consent prompt and returns
    whether the person completed it. Any failure (dismissed, hardware
    error, WinRT exception) is treated as "not verified" - this is a
    convenience shortcut, never the only way to unlock, so it fails
    closed rather than raising."""
    if not is_available():
        return False
    try:
        result = asyncio.run(UserConsentVerifier.request_verification_async(message))
        return result == UserConsentVerificationResult.VERIFIED
    except Exception:  # noqa: BLE001
        return False
