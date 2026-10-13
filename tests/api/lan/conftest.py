import pytest

from api.lan.pki import InsecureTestProtector
from lan_helpers import MainPc, make_config


@pytest.fixture()
def main_pc(session_factory, users, tmp_path):
    with MainPc(tmp_path / "lan", session_factory, make_config(), InsecureTestProtector()) as pc:
        yield pc


@pytest.fixture()
def owner_id(db, users):
    from app.models.user import User

    return db.query(User).filter_by(username="owner1").one().id


@pytest.fixture()
def device(main_pc, owner_id):
    """An enrolled device with its certificate, key and token."""
    code, _ = main_pc.lan.start_pairing(owner_id)
    out = main_pc.enrol("Counter PC", code)
    assert out["status"] == 200, out
    return out
