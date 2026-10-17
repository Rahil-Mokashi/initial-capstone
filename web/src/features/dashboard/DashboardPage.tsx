import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { Button } from '@/components/ui/Button';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { AlertCard, useAlerts } from '@/features/alerts/alerts';
import { GaugeBar, LevelBadge, StatusPill, StockFigures } from '@/features/tanks/TankGauge';
import { useTanks } from '@/features/tanks/queries';
import { cn } from '@/lib/cn';
import { formatMoney } from '@/lib/format';
import { P } from '@/lib/permissions';
import {
  ChecksCard,
  ChecksToLookAt,
  CreditCard,
  DayStatusCard,
  DigestCard,
  OpenLink,
  PayrollCard,
  ReviewLine,
  TodayFocus,
} from '@/features/today/TodayFocus';
import { todayPlan } from '@/features/today/plan';
import { ChaseList } from '@/features/credit/ChaseList';

type S = components['schemas'];

const ALERTS_SHOWN = 3;
const ROSTER_SHOWN = 6;

export function greetingFor(hour: number): string {
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
}

// ------------------------------------------------------------------ stat tiles
function StatTile({ value, label, tone }: { value: string; label: string; tone?: 'warning' }) {
  return (
    <li
      className={cn(
        'flex min-w-0 flex-col gap-1 rounded-lg border bg-surface p-5 shadow-card',
        tone === 'warning' ? 'border-warn' : 'border-line',
      )}
    >
      <p className="num text-2xl font-bold [overflow-wrap:anywhere] sm:text-3xl">{value}</p>
      <p className="text-sm text-muted">{label}</p>
    </li>
  );
}

/** Today's sales, in numbers and rupees, and how many tanks are running low. */
function SalesTiles({ s }: { s: S['SummaryOut'] }) {
  const tiles: Array<{ value: string; label: string; tone?: 'warning' }> = [];
  if (s.sales_today_count != null) {
    tiles.push({ value: String(s.sales_today_count), label: 'Sales today' });
    tiles.push({ value: formatMoney(s.sales_today_amount ?? '0.00'), label: 'Revenue today' });
  }
  if (s.low_stock_tanks_count != null)
    tiles.push({
      value: String(s.low_stock_tanks_count),
      label: 'Tanks running low',
      tone: s.low_stock_tanks_count > 0 ? 'warning' : undefined,
    });
  if (tiles.length === 0) return null;
  return (
    <ul aria-label="Today at a glance" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {tiles.map((t) => (
        <StatTile key={t.label} {...t} />
      ))}
    </ul>
  );
}

/** Behind "More": purchase orders waiting, and the open-shift count. */
export function MoreTiles({ s }: { s: S['SummaryOut'] }) {
  const tiles: Array<{ value: string; label: string }> = [];
  if (s.open_shifts_count != null) tiles.push({ value: String(s.open_shifts_count), label: 'Shifts open now' });
  if (s.pending_purchase_orders_count != null)
    tiles.push({ value: String(s.pending_purchase_orders_count), label: 'Purchase orders pending' });
  if (tiles.length === 0) return null;
  return (
    <ul aria-label="More figures" className="grid gap-4 sm:grid-cols-2">
      {tiles.map((t) => (
        <StatTile key={t.label} {...t} />
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- sales trend
export function SalesTrend() {
  const [days, setDays] = useState<7 | 30>(7);
  const trend = useGet<S['TrendPoint'][]>(
    ['dashboard', 'trend', days],
    `/dashboard/sales-trend?days=${days}`,
  );
  const [hover, setHover] = useState<number | null>(null);
  const pts = trend.data ?? [];
  const W = 600;
  const H = 180;
  const PAD = 12;
  // Plotting only: the numbers printed in the tooltip and the hidden table are the server's exact strings.
  const values = pts.map((p) => Number(p.amount));
  const max = Math.max(...values, 1);
  const xy = values.map((v, i) => [
    pts.length < 2 ? W / 2 : PAD + (i * (W - 2 * PAD)) / (pts.length - 1),
    H - PAD - (v / max) * (H - 2 * PAD),
  ]);
  const line = xy.map(([x, y]) => `${x},${y}`).join(' ');
  const shown = hover != null ? pts[hover] : null;
  return (
    <section
      aria-labelledby="trend-title"
      className="min-w-0 rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 id="trend-title" className="text-base font-bold">
          Sales Trend
        </h2>
        <div role="group" aria-label="Range" className="flex gap-2">
          {([7, 30] as const).map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={days === d}
              onClick={() => setDays(d)}
              className={cn(
                'min-h-[36px] rounded-full border px-4 text-sm font-semibold',
                days === d
                  ? 'border-primary bg-primary text-primary-fg'
                  : 'border-line-strong bg-surface hover:bg-surface-2',
              )}
            >
              {d} Days
            </button>
          ))}
        </div>
      </div>
      {trend.isLoading ? (
        <LoadingBlock label="Loading sales trend" rows={2} />
      ) : trend.isError ? (
        <ErrorState error={trend.error} onRetry={() => void trend.refetch()} />
      ) : (
        <>
          <p className="num mb-1 min-h-6 text-sm text-muted" aria-live="polite">
            {shown
              ? `${shown.day}: ${formatMoney(shown.amount)}`
              : 'Hover a point for that day’s revenue.'}
          </p>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label={`Daily sales revenue for the last ${days} days`}
            className="h-44 w-full"
            onMouseLeave={() => setHover(null)}
          >
            <polyline
              points={line}
              fill="none"
              stroke="var(--primary)"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            {xy.map(([x, y], i) => (
              <circle
                key={pts[i]!.day}
                cx={x}
                cy={y}
                r={hover === i ? 6 : 3.5}
                fill="var(--primary)"
                onMouseEnter={() => setHover(i)}
              />
            ))}
          </svg>
          <table className="sr-only">
            <caption>Daily sales revenue</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {pts.map((p) => (
                <tr key={p.day}>
                  <td>{p.day}</td>
                  <td>{formatMoney(p.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ tank gauges
function TankGauges() {
  const tanks = useTanks();
  if (tanks.isLoading || tanks.isError || !tanks.data?.length) return null;
  return (
    <section aria-labelledby="tanks-title" className="flex flex-col gap-3">
      <h2 id="tanks-title" className="text-xs font-bold tracking-widest text-muted uppercase">
        Live tank levels
      </h2>
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {tanks.data.map((t) => (
          <li
            key={t.id}
            className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-surface p-5 shadow-card"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-bold">
                  <Link to={`/tanks/${t.id}`} className="underline-offset-4 hover:underline">
                    {t.code}
                  </Link>
                </h3>
                <p className="text-sm text-muted">{t.fuel_type}</p>
              </div>
              <StatusPill status={t.status} />
            </div>
            <StockFigures tank={t} />
            <GaugeBar percent={t.fill_percent} low={t.is_low} />
            <div className="flex justify-end">
              <LevelBadge tank={t} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ----------------------------------------------------------------------- roster
export function Roster() {
  const roster = useGet<S['RosterRow'][]>(['dashboard', 'roster'], '/dashboard/roster');
  if (roster.isError) return null; // no shift.view: the card simply does not exist
  const rows = roster.data ?? [];
  return (
    <section
      aria-labelledby="roster-title"
      className="min-w-0 rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <h2 id="roster-title" className="mb-3 text-base font-bold">
        {rows.length ? `On Shift Now (${rows.length})` : 'On Shift Now'}
      </h2>
      {roster.isLoading ? (
        <LoadingBlock label="Loading the roster" rows={2} />
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">No attendant is currently assigned to a nozzle.</p>
      ) : (
        <>
          <ul className="flex flex-col gap-3">
            {rows.slice(0, ROSTER_SHOWN).map((r, i) => (
              <li key={`${r.name}-${i}`}>
                <p className="font-semibold">{r.name}</p>
                <p className="text-sm text-muted">{r.detail}</p>
              </li>
            ))}
          </ul>
          {rows.length > ROSTER_SHOWN && (
            <p className="mt-3 text-sm text-muted">+{rows.length - ROSTER_SHOWN} more on shift</p>
          )}
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ attention
function Attention() {
  const alerts = useAlerts();
  const s = alerts.data;
  if (alerts.isError || !s) return null;
  const shown = s.notifications.filter((n) => !n.is_summary).slice(0, ALERTS_SHOWN);
  return (
    <section aria-labelledby="attention-title" className="flex flex-col gap-3">
      <h2 id="attention-title" className="text-xs font-bold tracking-widest text-muted uppercase">
        Needs action
      </h2>
      <ReviewLine />
      <ChecksToLookAt />
      {s.total === 0 ? (
        <p className="text-sm text-muted">All clear — nothing needs attention right now.</p>
      ) : (
        <>
          <ul className="flex flex-col gap-3">
            {shown.map((n) => (
              <AlertCard key={n.key} alert={n} />
            ))}
          </ul>
          <div>
            <Link
              to="/alerts"
              className="inline-flex min-h-[44px] items-center rounded-md border border-line-strong px-4 text-sm font-semibold hover:bg-surface-2"
            >
              View all {s.total} alerts &rarr;
            </Link>
          </div>
        </>
      )}
    </section>
  );
}

function CreditToChase() {
  const { can } = useAuth();
  if (!can(P.CREDIT_VIEW)) return null;
  return (
    <section aria-labelledby="chase-title" className="flex flex-col gap-3">
      <h2 id="chase-title" className="text-xs font-bold tracking-widest text-muted uppercase">
        Credit to chase
      </h2>
      <div className="min-w-0 rounded-lg border border-line bg-surface p-5 shadow-card">
        <ChaseList limit={4} />
        <div className="mt-3">
          <OpenLink to="/credit/ageing">Open ageing</OpenLink>
        </div>
      </div>
    </section>
  );
}

function ShiftsNow({ summary }: { summary: S['SummaryOut'] | undefined }) {
  const { can } = useAuth();
  if (!can(P.SHIFT_VIEW)) return null;
  const labels = summary?.open_shift_labels ?? [];
  return (
    <section aria-labelledby="shifts-title" className="flex flex-col gap-3">
      <h2 id="shifts-title" className="text-xs font-bold tracking-widest text-muted uppercase">
        Shifts open and who is on them
      </h2>
      <p className="text-lg font-bold">
        {labels.length > 0 ? `${labels.join(', ')} open` : 'No shift is open right now'}
      </p>
      <Roster />
    </section>
  );
}

/** Today: what needs doing first, then the day in five short sections. The rest is one tap away under "More". */
export function DashboardPage() {
  const { user, can } = useAuth();
  const summary = useGet<S['SummaryOut']>(
    ['dashboard', 'summary'],
    '/dashboard/summary',
    true,
    60_000,
  );
  const today = new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  }).format(new Date());
  const name = user?.first_name || user?.username;
  const plan = todayPlan(user?.role);
  const showDay = plan.overview;
  return (
    <div className="mx-auto flex max-w-7xl min-w-0 flex-col gap-8">
      <header>
        <h1 className="text-3xl font-bold">
          {greetingFor(new Date().getHours())}, {name}
        </h1>
        <p className="text-sm text-muted">{today}</p>
      </header>
      <TodayFocus />
      {(showDay || plan.focus.length > 0) && <Attention />}
      {showDay && (
        <section aria-labelledby="sales-title" className="flex flex-col gap-3">
          <h2 id="sales-title" className="text-xs font-bold tracking-widest text-muted uppercase">
            Today&apos;s sales
          </h2>
          {summary.isLoading ? (
            <LoadingBlock label="Loading today" rows={2} />
          ) : summary.isError ? (
            // The KPI strip is an aid, never a gate: say so and carry on with the rest.
            <div className="flex items-center gap-3 text-sm text-muted">
              <span>Today&apos;s figures could not be loaded.</span>
              <Button onClick={() => void summary.refetch()}>Try again</Button>
            </div>
          ) : summary.data ? (
            <SalesTiles s={summary.data} />
          ) : null}
        </section>
      )}
      {showDay && <ShiftsNow summary={summary.data} />}
      {showDay && can(P.INVENTORY_VIEW) && <TankGauges />}
      {showDay && <CreditToChase />}
      {showDay && (
        <div>
          <Link
            to="/more"
            className="inline-flex min-h-[44px] items-center rounded-md border border-line-strong px-4 text-sm font-semibold hover:bg-surface-2"
          >
            More: trends, the month, purchase orders, revenue detail &rarr;
          </Link>
        </div>
      )}
    </div>
  );
}

/** Everything that used to crowd Today, kept in one place. */
export function MorePage() {
  const { can } = useAuth();
  const summary = useGet<S['SummaryOut']>(['dashboard', 'summary'], '/dashboard/summary', true, 60_000);
  return (
    <div className="mx-auto flex max-w-7xl min-w-0 flex-col gap-8">
      <header>
        <h1 className="text-3xl font-bold">More</h1>
        <p className="text-sm text-muted">The rest of the day&apos;s figures. The Today page keeps only what needs you.</p>
      </header>
      {can(P.DIGEST_VIEW) && <DigestCard />}
      {summary.data && <MoreTiles s={summary.data} />}
      {can(P.SALE_VIEW) && <SalesTrend />}
      <div className="grid gap-4 lg:grid-cols-2">
        <CreditCard />
        <PayrollCard />
        <DayStatusCard />
        <ChecksCard />
      </div>
    </div>
  );
}
