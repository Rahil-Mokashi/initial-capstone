"""Vehicle numbers are stored one way so the same truck always matches itself: upper case, no spaces ("mh 12 ab 1234" -> "MH12AB1234")."""

from typing import Optional


def normalise_vehicle(value: Optional[str]) -> Optional[str]:
    cleaned = "".join((value or "").split()).upper()
    return cleaned or None
