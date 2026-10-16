from datetime import date
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.check_result import CheckExplanation, CheckResult
from app.repositories.base import safe_commit


class CheckResultRepository:
    """Insert and read only: there is deliberately no update or delete."""

    def __init__(self, session: Session):
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def add(self, result: CheckResult) -> CheckResult:
        self._session.add(result)
        safe_commit(self._session)
        self._session.refresh(result)
        return result

    def get_by_id(self, result_id: str) -> Optional[CheckResult]:
        return self._session.get(CheckResult, result_id)

    def latest(self, check_key: str, scope_type: str, scope_id: str) -> Optional[CheckResult]:
        return (
            self._session.query(CheckResult)
            .filter_by(check_key=check_key, scope_type=scope_type, scope_id=scope_id)
            .order_by(CheckResult.run_at.desc(), CheckResult.id.desc())
            .first()
        )

    def current_for_day(self, day: date, area: Optional[str] = None) -> List[CheckResult]:
        """Newest row per (check_key, scope) for one business date."""
        q = self._session.query(CheckResult).filter(CheckResult.business_date == day)
        if area:
            q = q.filter(CheckResult.area == area)
        rows = q.order_by(CheckResult.run_at.asc(), CheckResult.id.asc()).all()
        newest = {}
        for r in rows:  # ascending, so a later row replaces an earlier one in the dict only
            newest[(r.check_key, r.scope_type, r.scope_id)] = r
        return list(newest.values())

    def history_for_day(self, day: date) -> List[CheckResult]:
        return (
            self._session.query(CheckResult)
            .filter(CheckResult.business_date == day)
            .order_by(CheckResult.run_at.desc(), CheckResult.id.desc())
            .all()
        )

    def days_with_results(self, limit: int = 60) -> List[date]:
        rows = (
            self._session.query(CheckResult.business_date)
            .group_by(CheckResult.business_date)
            .order_by(CheckResult.business_date.desc())
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows]


class CheckExplanationRepository:
    def __init__(self, session: Session):
        self._session = session

    def add(self, explanation: CheckExplanation) -> CheckExplanation:
        self._session.add(explanation)
        safe_commit(self._session)
        self._session.refresh(explanation)
        return explanation
