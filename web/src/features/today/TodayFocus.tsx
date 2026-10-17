import { Link } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatCheckValue } from '@/features/checks/checkText';
import { sumMoney } from '@/lib/decimalMath';
import { formatMoney } from '@/lib/format';
import { ChaseList } from '@/features/credit/ChaseList';
import { DigestView } from '@/features/digest/DigestView';
import { P } from '@/lib/permissions';
import { SHIFT_ENTRY_STEPS, todayPlan, type FocusId } from './plan';

type S = components['schemas'];

export function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      aria-label={title}
      className="flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <h2 className="text-xs font-bold tracking-widest text-muted uppercase">{title}</h2>
      {children}
    </section>
  );
}

export function OpenLink({ to, children }: { to: string; children: string }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-[44px] w-fit items-center rounded-md border border-line-strong px-4 text-sm font-semibold hover:bg-surface-2"
    >
      {children} &rarr;
    </Link>
  );
}

/** The owner's home: how the latest day went. */
export function DigestCard() {
  const { can } = useAuth();
  if (!can(P.DIGEST_VIEW)) return null;
  return (
    <Card title="Daily digest">
      <DigestView />
      <OpenLink to="/digest">Open the digest</OpenLink>
    </Card>
  );
}

/** What is waiting for THIS person, in words: "3 entries need your check" (accountant), "approval" / "to lock" (owner). Nothing shown when nothing waits. */
export function ReviewLine() {
  const { can } = useAuth();
  const allowed = can(P.ENTRY_VIEW);
  const entries = useGet<S['EntryOut'][]>(['entries', 'today'], '/entries', allowed, 60_000);
  if (!allowed || !entries.data) return null;
  const rows = entries.data;
  const waiting = [
    can(P.ENTRY_VERIFY) ? { n: rows.filter((e) => e.status === 'entered').length, what: 'need your check' } : null,
    can(P.ENTRY_APPROVE) ? { n: rows.filter((e) => e.status === 'verified').length, what: 'need your approval' } : null,
    can(P.ENTRY_LOCK) ? { n: rows.filter((e) => e.status === 'approved').length, what: 'are ready for you to lock' } : null,
  ].filter((w): w is { n: number; what: string } => w !== null && w.n > 0);
  if (waiting.length === 0) return null;
  return (
    <ul aria-label="Waiting for you" className="flex flex-col gap-2">
      {waiting.map((w) => (
        <li key={w.what} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line border-l-4 border-l-info bg-surface p-4 shadow-card">
          <p className="min-w-0 font-semibold">
            <span className="num">{w.n}</span> {w.n === 1 ? 'entry' : 'entries'} {w.what}
          </p>
          <OpenLink to="/review">Review</OpenLink>
        </li>
      ))}
    </ul>
  );
}

/** Only the checks that failed or need a look, with the figure; nothing at all when every check passed. */
export function ChecksToLookAt() {
  const { can } = useAuth();
  const allowed = can(P.CHECK_VIEW);
  const checks = useGet<S['DayChecksOut']>(['checks', 'today'], '/checks', allowed, 60_000);
  const bad = (checks.data?.results ?? []).filter((r) => r.status !== 'pass').slice(0, 4);
  if (!allowed || bad.length === 0) return null;
  return (
    <ul aria-label="Checks to look at" className="flex flex-col gap-2">
      {bad.map((r) => (
        <li key={r.id} className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line border-l-4 bg-surface p-4 shadow-card ${r.status === 'fail' ? 'border-l-danger' : 'border-l-warn'}`}>
          <p className="min-w-0 [overflow-wrap:anywhere]">
            <StatusBadge tone={r.status === 'fail' ? 'danger' : 'warn'}>{r.status === 'fail' ? 'Failed' : 'Look'}</StatusBadge>{' '}
            {r.sentence} <span className="num text-muted">({formatCheckValue(r.unit, r.difference)})</span>
          </p>
          <OpenLink to="/checks">Open Checks</OpenLink>
        </li>
      ))}
    </ul>
  );
}

export function ChecksCard() {
  const { can } = useAuth();
  const allowed = can(P.CHECK_VIEW);
  const checks = useGet<S['DayChecksOut']>(['checks', 'today'], '/checks', allowed, 60_000);
  if (!allowed) return null;
  const s = checks.data?.summary;
  const bad = (checks.data?.results ?? []).filter((r) => r.status !== 'pass').slice(0, 3);
  return (
    <Card title="Checks today">
      {!s ? (
        <p className="text-sm text-muted">Loading the checks…</p>
      ) : s.total === 0 ? (
        <p className="text-sm text-muted">No checks yet today. They appear as data is saved.</p>
      ) : (
        <>
          <p className="num text-2xl font-bold">
            {s.passed} of {s.total} checks passed
          </p>
          {bad.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm">
              {bad.map((r) => (
                <li key={r.id} className="flex items-center gap-2">
                  <StatusBadge tone={r.status === 'fail' ? 'danger' : 'warn'}>
                    {r.status === 'fail' ? 'Failed' : 'Look'}
                  </StatusBadge>
                  {r.sentence} ({formatCheckValue(r.unit, r.difference)})
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <OpenLink to="/checks">Open Checks</OpenLink>
    </Card>
  );
}

export function DayStatusCard() {
  const { can } = useAuth();
  const allowed = can(P.SHIFT_VIEW);
  const summary = useGet<S['SummaryOut']>(
    ['dashboard', 'summary'],
    '/dashboard/summary',
    allowed,
    60_000,
  );
  if (!allowed) return null;
  const labels = summary.data?.open_shift_labels ?? [];
  return (
    <Card title="Day status">
      <p className="text-lg font-bold">
        {labels.length > 0 ? `${labels.join(', ')} shift open` : 'No shift is open right now'}
      </p>
      <OpenLink to="/shifts">Open Shifts</OpenLink>
    </Card>
  );
}

export function CreditCard() {
  const { can } = useAuth();
  const allowed = can(P.CREDIT_VIEW);
  const accounts = useGet<S['AccountOut'][]>(['credit', 'accounts'], '/credit/accounts', allowed);
  if (!allowed) return null;
  const rows = accounts.data ?? [];
  const overdue = rows.filter((a) => a.overdue).length;
  return (
    <Card title="Credit outstanding">
      <p className="num text-2xl font-bold [overflow-wrap:anywhere]">
        {accounts.data ? formatMoney(sumMoney(rows.map((a) => a.outstanding))) : '…'}
      </p>
      <p className="text-sm text-muted">
        {rows.length} credit customers{overdue > 0 ? `, ${overdue} overdue` : ''}
      </p>
      <OpenLink to="/credit">Open Credit</OpenLink>
    </Card>
  );
}

export function ChaseCard() {
  const { can } = useAuth();
  if (!can(P.CREDIT_VIEW)) return null;
  return (
    <Card title="Credit to chase">
      <ChaseList limit={4} />
      <OpenLink to="/credit/ageing">Open ageing</OpenLink>
    </Card>
  );
}

export function PayrollCard() {
  const { can } = useAuth();
  const runs = useGet<S['PayrollRunRowOut'][]>(
    ['payroll', 'runs'],
    '/payroll/runs',
    can(P.PAYROLL_VIEW),
  );
  if (!can(P.PAYROLL_VIEW)) return null;
  const latest = runs.data?.[0];
  const words = !latest
    ? 'No month has been prepared yet.'
    : latest.status === 'draft'
      ? `${latest.month}: prepared, waiting for an owner to approve`
      : latest.status === 'approved'
        ? `${latest.month}: approved, salaries still to be paid`
        : `${latest.month}: all paid`;
  return (
    <Card title="Payroll">
      <p className="text-lg font-bold">{words}</p>
      <OpenLink to="/payroll">Open Payroll</OpenLink>
    </Card>
  );
}

function ShiftEntryCard() {
  const { can } = useAuth();
  const steps = SHIFT_ENTRY_STEPS.filter((s) => can(s.permission));
  return (
    <Card title="Shift entry, in the order the bundle arrives">
      <ol className="flex flex-col gap-2">
        {steps.map((s, i) => (
          <li key={s.label}>
            <Link
              to={s.to}
              className="flex min-h-[56px] items-center gap-4 rounded-md border border-line-strong px-4 py-2 hover:bg-surface-2"
            >
              <span className="num flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-fg">
                {i + 1}
              </span>
              <span>
                <span className="block font-semibold">{s.label}</span>
                <span className="block text-sm text-muted">{s.hint}</span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function ManagerCard() {
  return (
    <Card title="Shift close">
      <p className="text-sm text-muted">Type the closing readings and how the money was collected; the tally and any shortage show beside them.</p>
      <div className="flex flex-wrap gap-3">
        <OpenLink to="/close-shift">Close Shift</OpenLink>
        <OpenLink to="/shifts">Shifts</OpenLink>
        <OpenLink to="/reconciliation">Cash book and reconciliation</OpenLink>
      </div>
    </Card>
  );
}

// Today shows only the lists of steps a role works through. The figures live in the sections of the Today page or behind "More".
const CARDS: Partial<Record<FocusId, () => React.ReactElement | null>> = {
  shift_entry: ShiftEntryCard,
  manager_close: ManagerCard,
};

/** The short list for this person's role, shown at the top of Today. */
export function TodayFocus() {
  const { user } = useAuth();
  const plan = todayPlan(user?.role);
  const lists = plan.focus.filter((id) => CARDS[id]);
  if (lists.length === 0) return null;
  return (
    <div aria-label="Your list for today" className="grid gap-4 lg:grid-cols-2">
      {lists.map((id) => {
        const Card = CARDS[id]!;
        return <Card key={id} />;
      })}
    </div>
  );
}
