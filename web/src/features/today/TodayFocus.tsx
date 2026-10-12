import { Link } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatCheckValue } from '@/features/checks/checkText';
import { sumMoney } from '@/lib/decimalMath';
import { formatMoney } from '@/lib/format';
import { P } from '@/lib/permissions';
import { SHIFT_ENTRY_STEPS, todayPlan, type FocusId } from './plan';

type S = components['schemas'];

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      aria-label={title}
      className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <h2 className="text-xs font-bold tracking-widest text-muted uppercase">{title}</h2>
      {children}
    </section>
  );
}

function OpenLink({ to, children }: { to: string; children: string }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-[44px] w-fit items-center rounded-md border border-line-strong px-4 text-sm font-semibold hover:bg-surface-2"
    >
      {children} &rarr;
    </Link>
  );
}

function ChecksCard() {
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

function DayStatusCard() {
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

function CreditCard() {
  const { can } = useAuth();
  const allowed = can(P.CREDIT_VIEW);
  const accounts = useGet<S['AccountOut'][]>(['credit', 'accounts'], '/credit/accounts', allowed);
  if (!allowed) return null;
  const rows = accounts.data ?? [];
  const overdue = rows.filter((a) => a.overdue).length;
  return (
    <Card title="Credit outstanding">
      <p className="num text-2xl font-bold">
        {accounts.data ? formatMoney(sumMoney(rows.map((a) => a.outstanding))) : '…'}
      </p>
      <p className="text-sm text-muted">
        {rows.length} credit customers{overdue > 0 ? `, ${overdue} overdue` : ''}
      </p>
      <OpenLink to="/credit">Open Credit</OpenLink>
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
      <p className="text-sm text-muted">Readings, then the cash book, then close the shift.</p>
      <div className="flex flex-wrap gap-3">
        <OpenLink to="/shifts">Shifts and readings</OpenLink>
        <OpenLink to="/reconciliation">Cash book and reconciliation</OpenLink>
      </div>
    </Card>
  );
}

function MyShiftCard() {
  return (
    <Card title="My shift">
      <OpenLink to="/my-shift">Open My Shift</OpenLink>
    </Card>
  );
}

const CARDS: Record<FocusId, () => React.ReactElement | null> = {
  checks: ChecksCard,
  day_status: DayStatusCard,
  credit_outstanding: CreditCard,
  shift_entry: ShiftEntryCard,
  manager_close: ManagerCard,
  my_shift: MyShiftCard,
};

/** The short list for this person's role, shown at the top of Today. */
export function TodayFocus() {
  const { user } = useAuth();
  const plan = todayPlan(user?.role);
  if (plan.focus.length === 0) return null;
  return (
    <div aria-label="Your list for today" className="grid gap-4 lg:grid-cols-2">
      {plan.focus.map((id) => {
        const Card = CARDS[id];
        return <Card key={id} />;
      })}
    </div>
  );
}
