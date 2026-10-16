"""Times the things a user waits for, on a database made by generate_year.py. Works on a COPY (the source file is never touched).

Usage:  python scripts/bench/measure.py path/to/y365.db [--label before] [--out result.json]
Measures: app start (migrations included), the first save after login, save latency p50/p95, how long the automatic checks take to finish
after a save (0 on code where they run inside the save), an explicit checks run, daily report (both styles), digest, bank match, ageing.
"""
import argparse, base64, json, os, shutil, statistics, sys, tempfile, time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests" / "api"))

ap = argparse.ArgumentParser()
ap.add_argument("db"); ap.add_argument("--label", default="run"); ap.add_argument("--out"); ap.add_argument("--saves", type=int, default=20)
args = ap.parse_args()

work = Path(tempfile.mkdtemp(prefix="pperp-bench-"))
copy = work / "pump.db"
shutil.copyfile(args.db, copy)
for ext in ("-wal", "-shm"):
    if Path(args.db + ext).exists():
        shutil.copyfile(args.db + ext, str(copy) + ext)
os.environ["PETROL_PUMP_DB_PATH"] = str(copy)
meta = json.loads(Path(args.db).with_suffix(".meta.json").read_text())
last_day = meta["last_day"]
month_ago = (date.fromisoformat(last_day) - timedelta(days=30)).isoformat()

t0 = time.perf_counter()
from fastapi.testclient import TestClient  # noqa: E402
from api.app import create_app  # noqa: E402
from app.database import connection  # noqa: E402
from api_helpers import SECRET, login  # noqa: E402

connection.init_db()
app = create_app(SECRET, session_factory=connection.SessionLocal, session_timeout_hours=8)
c = TestClient(app, base_url="http://127.0.0.1", headers={"X-Launch-Secret": SECRET})
start_secs = time.perf_counter() - t0


def timed(fn):
    t = time.perf_counter(); out = fn(); return time.perf_counter() - t, out


def checks_idle_secs() -> float:
    """Seconds until the background checks (if the code has them) have finished; 0 when they run inside the save."""
    try:
        from api import check_worker
    except ImportError:
        return 0.0
    t = time.perf_counter()
    check_worker.wait_idle(app, timeout=600)
    return time.perf_counter() - t


res = {"label": args.label, "days": meta["days"], "app_start_s": round(start_secs, 2)}
O = login(c, "owner1"); A = login(c, "accountant1")
first, r = timed(lambda: c.post("/api/customers", headers=O, json={"name": "Bench First"}))
assert r.status_code in (200, 201), r.text
res["first_save_s"] = round(first, 3)
res["first_checks_finish_s"] = round(checks_idle_secs(), 2)
saves, finish = [], []
for n in range(args.saves):
    dt, r = timed(lambda: c.post("/api/customers", headers=O, json={"name": f"Bench Customer {n}"}))
    assert r.status_code in (200, 201), r.text
    saves.append(dt)
    if n % 5 == 4:
        finish.append(checks_idle_secs())
saves.sort()
res["save_p50_s"] = round(statistics.median(saves), 3)
res["save_p95_s"] = round(saves[min(len(saves) - 1, int(len(saves) * 0.95))], 3)
res["checks_finish_after_save_s"] = round(max(finish) if finish else 0.0, 2)
T = {
    "checks_run_s": lambda: c.post("/api/checks/run", headers=O, json={"day": last_day}),
    "daily_report_classic_s": lambda: c.get(f"/api/daily-report?day={last_day}&style=classic", headers=O),
    "daily_report_plus_s": lambda: c.get(f"/api/daily-report?day={last_day}&style=plus", headers=O),
    "digest_s": lambda: c.get(f"/api/digest?day={last_day}", headers=O),
    "bank_match_30d_s": lambda: c.post("/api/bank/match/run", headers=A, json={"date_from": month_ago, "date_to": last_day}),
    "credit_ageing_s": lambda: c.get("/api/credit/ageing", headers=O),
}
for key, fn in T.items():
    dt, r = timed(fn)
    res[key] = round(dt, 3); res[key.replace("_s", "_status")] = r.status_code
text = json.dumps(res, indent=1)
print(text)
if args.out:
    Path(args.out).write_text(text)
shutil.rmtree(work, ignore_errors=True)
