"""Per-terminal login preferences (app/ui/terminal_settings.py): recently-
used usernames and the login screen's own language choice. Isolated from
the real per-machine QSettings store the same way tests/test_theme.py
isolates app.ui.theme's - a test run must never read or clobber whatever
is actually saved on the machine it runs on.
"""

import pytest


@pytest.fixture
def isolated_settings(monkeypatch):
    import app.ui.terminal_settings as terminal_settings_module

    store: dict[str, object] = {}

    class FakeSettings:
        def value(self, key, default=None, type=None):  # noqa: A002 - matches QSettings' own signature
            value = store.get(key, default)
            return type(value) if type is not None else value

        def setValue(self, key, value):  # noqa: N802 - matches QSettings' own method name
            store[key] = value

    monkeypatch.setattr(terminal_settings_module, "QSettings", lambda *a, **k: FakeSettings())
    return store


def test_recent_usernames_defaults_to_empty(isolated_settings):
    from app.ui.terminal_settings import get_recent_usernames

    assert get_recent_usernames() == []


def test_recording_a_username_adds_it_to_the_front(isolated_settings):
    from app.ui.terminal_settings import get_recent_usernames, record_recent_username

    record_recent_username("alice")
    record_recent_username("bob")

    assert get_recent_usernames() == ["bob", "alice"]


def test_recording_an_existing_username_moves_it_to_front_without_duplicating(isolated_settings):
    from app.ui.terminal_settings import get_recent_usernames, record_recent_username

    record_recent_username("alice")
    record_recent_username("bob")
    record_recent_username("alice")

    assert get_recent_usernames() == ["alice", "bob"]


def test_recent_usernames_list_is_capped(isolated_settings):
    from app.ui.terminal_settings import MAX_RECENT_USERNAMES, get_recent_usernames, record_recent_username

    for name in ["a", "b", "c", "d", "e"]:
        record_recent_username(name)

    recent = get_recent_usernames()
    assert len(recent) == MAX_RECENT_USERNAMES
    assert recent == ["e", "d", "c"]


def test_recording_a_blank_username_is_a_no_op(isolated_settings):
    from app.ui.terminal_settings import get_recent_usernames, record_recent_username

    record_recent_username("")
    record_recent_username("   ")

    assert get_recent_usernames() == []


def test_login_locale_defaults_to_english(isolated_settings):
    from app.ui.terminal_settings import get_login_locale

    assert get_login_locale() == "en"


def test_login_locale_round_trips(isolated_settings):
    from app.ui.terminal_settings import get_login_locale, set_login_locale

    set_login_locale("hi")
    assert get_login_locale() == "hi"
