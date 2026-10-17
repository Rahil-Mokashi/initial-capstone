"""Entered -> Verified -> Approved -> Locked: who has looked at a shift's figures (LAN build, Phase 4).

  Entered   the shift's figures were typed (Close Shift). Anyone with shift access can still change them.
  Verified  the accountant compared them with the paper and the bank. Changing a figure afterwards sends the shift back to
            Entered by itself (recorded as "data changed"), so a Verified stamp always describes the figures as they are now.
  Approved  an owner accepted them.
  Locked    an owner closed the shift for good. Nothing under it can be saved, voided or edited (entry_lock_guard.py).

A correction to a locked shift is a REOPEN by an owner with a reason: it is recorded, audit-logged, and the chain starts again.
Owner Choice V-06 `owner_lock_rule`: one_owner (default) = the same owner may approve and lock; two_owners = the locking owner
must be a different person from the approving one.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.shift import Shift
from app.models.shift_entry import APPROVED, ENTERED, LOCKED, VERIFIED, ShiftEntry, ShiftEntryEvent


class LockBlockedByChecks(ConflictError):
    """A day with a failing check cannot be locked unless an owner says why it should be (Owner Choice V-07)."""

    def __init__(self, failing: List[str]):
        self.details = {"failing": failing}
        super().__init__(f"{len(failing)} check(s) are failing for this day: " + "; ".join(failing))


@dataclass
class EntryView:
    shift_id: str
    shift_date: date
    shift_label: str
    status: str
    events: List[ShiftEntryEvent]


class EntryWorkflowService:
    def __init__(self, session, audit_repo, auth_service, settings, fresh_checks=None):
        # fresh_checks(actor_id, day) -> the day's current check results after re-running them now (None = no guard, e.g. Qt)
        self._fresh_checks = fresh_checks
        self._session = session
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._settings = settings

    # ---- reads
    def entry_for(self, shift_id: str) -> Optional[ShiftEntry]:
        return self._session.query(ShiftEntry).filter_by(shift_id=shift_id).first()

    def status_of(self, shift_id: str) -> Optional[str]:
        entry = self.entry_for(shift_id)
        return entry.status if entry else None

    @require_permission(Permission.ENTRY_VIEW.value)
    def list_between(self, actor_user_id: str, date_from: date, date_to: date) -> List[EntryView]:
        rows = (
            self._session.query(ShiftEntry, Shift)
            .join(Shift, Shift.id == ShiftEntry.shift_id)
            .filter(Shift.shift_date >= date_from, Shift.shift_date <= date_to)
            .order_by(Shift.shift_date.desc(), Shift.shift_label)
            .all()
        )
        return [EntryView(s.id, s.shift_date, s.shift_label, e.status, list(e.events)) for e, s in rows]

    def counts_by_status(self, day: date) -> Dict[str, int]:
        """How many of the day's shift entries stand at each step (internal read for the checks)."""
        out: Dict[str, int] = {}
        rows = (
            self._session.query(ShiftEntry.status)
            .join(Shift, Shift.id == ShiftEntry.shift_id)
            .filter(Shift.shift_date == day)
            .all()
        )
        for (status,) in rows:
            out[status] = out.get(status, 0) + 1
        return out

    # ---- moves
    def mark_entered(self, actor_user_id: Optional[str], shift_id: str) -> ShiftEntry:
        """A shift's figures were typed. Creates the entry the first time; later saves are handled by the lock guard."""
        entry = self.entry_for(shift_id)
        if entry is None:
            if self._session.get(Shift, shift_id) is None:
                raise NotFoundError(f"Shift not found: {shift_id}")
            entry = ShiftEntry(shift_id=shift_id, status=ENTERED)
            self._session.add(entry)
            self._session.flush()
            self._event(entry, None, ENTERED, "entered", actor_user_id)
        return entry

    @require_permission(Permission.ENTRY_VERIFY.value)
    def verify(self, actor_user_id: str, shift_id: str) -> ShiftEntry:
        entry = self._require(shift_id, ENTERED, "verified")
        self._move(entry, VERIFIED, "verified", actor_user_id)
        return entry

    @require_permission(Permission.ENTRY_APPROVE.value)
    def approve(self, actor_user_id: str, shift_id: str) -> ShiftEntry:
        entry = self._require(shift_id, VERIFIED, "approved")
        self._move(entry, APPROVED, "approved", actor_user_id)
        return entry

    @require_permission(Permission.ENTRY_LOCK.value)
    def lock(self, actor_user_id: str, shift_id: str, override_reason: Optional[str] = None) -> ShiftEntry:
        entry = self._require(shift_id, APPROVED, "locked")
        override = (override_reason or "").strip()
        if self._fresh_checks is not None and self._settings.get("failed_check_blocks_lock") == "block":
            day = self._session.get(Shift, shift_id).shift_date
            failing = [r.sentence for r in self._fresh_checks(actor_user_id, day) if r.status == "fail"]
            if failing and not override:
                raise LockBlockedByChecks(failing)
            if failing:
                self._audit_repo.record(
                    event_type="shift_lock_check_override", actor_id=actor_user_id, entity_type="Shift", entity_id=shift_id,
                    description=f"Locked with {len(failing)} failing check(s): {'; '.join(failing)}. Reason: {override}",
                )
        if self._settings.get("owner_lock_rule") == "two_owners":
            approver = next((e.by_user_id for e in reversed(entry.events) if e.action == "approved"), None)
            if approver == actor_user_id:
                raise ConflictError("Owner Choice V-06: a different owner has to lock a shift than the one who approved it.")
        self._move(entry, LOCKED, "locked", actor_user_id)
        return entry

    @require_permission(Permission.ENTRY_REOPEN.value)
    def reopen(self, actor_user_id: str, shift_id: str, reason: str) -> ShiftEntry:
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("A correction needs a reason: say what was wrong.")
        entry = self.entry_for(shift_id)
        if entry is None or entry.status == ENTERED:
            raise ConflictError("This shift is already open for changes.")
        self._move(entry, ENTERED, "reopened", actor_user_id, reason)
        return entry

    # ---- internals
    def _require(self, shift_id: str, needed: str, verb: str) -> ShiftEntry:
        entry = self.entry_for(shift_id)
        if entry is None:
            raise ConflictError("Nothing has been entered for this shift yet.")
        if entry.status != needed:
            raise ConflictError(f"This shift is {entry.status}; it has to be {needed} before it can be {verb}.")
        return entry

    def _move(self, entry: ShiftEntry, to: str, action: str, actor_user_id: Optional[str], reason: Optional[str] = None) -> None:
        before = entry.status
        entry.status = to
        self._event(entry, before, to, action, actor_user_id, reason)
        shift = self._session.get(Shift, entry.shift_id)
        self._audit_repo.record(
            event_type=f"shift_entry_{action}", actor_id=actor_user_id, entity_type="Shift", entity_id=entry.shift_id,
            description=f"{shift.shift_date} {shift.shift_label}: {before} -> {to}" + (f" ({reason})" if reason else ""),
            old_value=before, new_value=to,
        )

    def _event(self, entry: ShiftEntry, before: Optional[str], to: str, action: str, actor_user_id: Optional[str], reason: Optional[str] = None) -> None:
        self._session.add(ShiftEntryEvent(shift_entry_id=entry.id, from_status=before, to_status=to, action=action, by_user_id=actor_user_id, reason=reason))
        self._session.flush()
