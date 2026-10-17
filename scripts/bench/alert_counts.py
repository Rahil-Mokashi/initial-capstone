"""Alert counts by type: what the old list showed (every notification) against what people see now (merged, minus acknowledged and booked).

Usage: python scripts/bench/alert_counts.py path/to.db     (works on a COPY; the file is never touched)
"""
import json, os, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
work = Path(tempfile.mkdtemp(prefix="pperp-alerts-"))
copy = work / "pump.db"
shutil.copyfile(sys.argv[1], copy)
os.environ["PETROL_PUMP_DB_PATH"] = str(copy)

from app.database import connection  # noqa: E402
from api.services import Services  # noqa: E402
from app.models.user import User  # noqa: E402

connection.init_db()
db = connection.SessionLocal()
owner = db.query(User).filter_by(username="owner1").first()
s = Services(db, 8)
print(json.dumps({"before": s.alerts.raw_counts_by_category(owner.id), "after": s.alerts.counts_by_category(owner.id)}, indent=1))
shutil.rmtree(work, ignore_errors=True)
