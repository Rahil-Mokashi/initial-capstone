import { BellRing, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { Menu } from '@/components/ui/Menu';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { alertRoute } from '@/lib/alertRoutes';
import { SEVERITY_LABEL, collapsedSummaryText, sentence } from '@/lib/alertText';
import { cn } from '@/lib/cn';

export type Alerts = components['schemas']['AlertsOut'];
export type Alert = components['schemas']['AlertOut'];

/** The alert list is recomputed from live data on the server; the shell re-reads it every minute, as Qt does. */
export const useAlerts = (refetchMs?: number) =>
  useGet<Alerts>(['alerts'], '/alerts', true, refetchMs);

const TONE: Record<string, string> = {
  critical: 'border-l-danger',
  warning: 'border-l-warn',
  info: 'border-l-info',
};
const TAG: Record<string, string> = {
  critical: 'bg-danger-bg text-danger-fg',
  warning: 'bg-warn-bg text-warn-fg',
  info: 'bg-info-bg text-info-fg',
};

/** One alert: a coloured left edge, a title, the severity in WORDS (never colour alone), the detail. */
export function AlertCard({ alert }: { alert: Alert }) {
  return (
    <li
      className={cn(
        'flex flex-col gap-1.5 rounded-lg border border-line border-l-4 bg-surface p-4 shadow-card',
        TONE[alert.severity],
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="font-semibold">{alert.title}</p>
        <span
          className={cn(
            'shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-bold tracking-wide',
            TAG[alert.severity],
          )}
        >
          {SEVERITY_LABEL[alert.severity] ?? alert.severity.toUpperCase()}
        </span>
      </div>
      {alert.detail && <p className="text-sm text-muted">{alert.detail}</p>}
    </li>
  );
}

export function AlertsPage() {
  const alerts = useAlerts();
  const s = alerts.data;
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title="Alerts"
        subtitle="Computed from live data; an alert clears itself once what caused it is fixed."
      >
        <Button onClick={() => void alerts.refetch()} loading={alerts.isFetching}>
          <RefreshCw className="size-4" aria-hidden /> Refresh
        </Button>
      </PageHeader>
      {alerts.isLoading ? (
        <LoadingBlock label="Loading alerts" rows={3} />
      ) : alerts.isError || !s ? (
        // Say so rather than showing an empty list, which would read as "all clear".
        <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />
      ) : s.total === 0 ? (
        <div className="rounded-lg border border-dashed border-line-strong bg-surface p-8 text-center text-sm text-muted">
          <p className="font-semibold text-fg">Nothing needs your attention right now.</p>
          <p className="mt-2">
            Alerts appear here automatically when something changes - low stock, an unapproved
            expense, an overdue customer - and disappear again once it is dealt with.
          </p>
        </div>
      ) : (
        <>
          <p className="text-sm text-muted">
            {s.total} alert(s): {s.critical_count} needing attention, {s.warning_count} worth a
            look. An alert clears itself once the situation behind it is resolved.
          </p>
          <ul className="flex flex-col gap-3">
            {s.notifications.map((n, i) => (
              <AlertCard key={`${n.category}-${i}`} alert={n} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/** The top-bar Alerts button: a count coloured by the worst thing in the list, and a dropdown preview. */
export function AlertsMenu() {
  const alerts = useAlerts(60_000);
  const navigate = useNavigate();
  const s = alerts.data;
  const total = s?.total ?? 0;
  const tone = s?.critical_count
    ? 'border-danger bg-danger-bg text-danger-fg'
    : s?.warning_count
      ? 'border-warn bg-warn-bg text-warn-fg'
      : '';
  return (
    <Menu
      label={total ? `Alerts (${total})` : 'Alerts'}
      triggerClassName={tone}
      trigger={
        <>
          <BellRing className="size-4" aria-hidden /> {total ? `Alerts (${total})` : 'Alerts'}
        </>
      }
    >
      {(close) => (
        <div className="flex flex-col gap-3">
          {alerts.isError ? (
            <p className="text-sm text-danger-fg">The alert list could not be loaded.</p>
          ) : !s || s.total === 0 ? (
            <p className="text-sm text-muted">All clear — nothing needs attention right now.</p>
          ) : (
            <>
              <ul className="flex flex-col gap-2">
                {s.notifications
                  .filter((n) => !n.is_summary)
                  .slice(0, 3)
                  .map((n, i) => (
                    <AlertCard key={`${n.category}-${i}`} alert={n} />
                  ))}
              </ul>
              <Button
                onClick={() => {
                  close();
                  navigate('/alerts');
                }}
              >
                View all {s.total} alerts &rarr;
              </Button>
            </>
          )}
        </div>
      )}
    </Menu>
  );
}

/** Always visible above the content: a one-line summary, expandable into every alert, each one clickable. */
export function AlertStrip() {
  const alerts = useAlerts(60_000);
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const s = alerts.data;
  const shown = (s?.notifications ?? []).filter((n) => !n.is_summary);
  const tone = !s
    ? ''
    : s.critical_count
      ? 'border-danger bg-danger-bg'
      : s.warning_count
        ? 'border-warn bg-warn-bg'
        : '';
  return (
    <section
      aria-label="Alerts summary"
      className={cn('border-b border-line bg-surface-2 px-6 py-2.5 text-sm', tone)}
    >
      <div className="flex items-center gap-3">
        <p role="status" className="min-w-0 flex-1">
          {alerts.isError ? 'The alert list could not be loaded.' : collapsedSummaryText(s)}
        </p>
        {shown.length > 1 && (
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded((e) => !e)}
            className="inline-flex min-h-[36px] items-center gap-1 rounded-md px-2 font-semibold underline-offset-4 hover:underline"
          >
            {expanded ? (
              <>
                Hide <ChevronUp className="size-4" aria-hidden />
              </>
            ) : (
              <>
                Show all {shown.length} <ChevronDown className="size-4" aria-hidden />
              </>
            )}
          </button>
        )}
      </div>
      {expanded && shown.length > 1 && (
        <ul className="mt-2 flex max-h-64 flex-col gap-2 overflow-y-auto">
          {shown.map((n, i) => {
            const to = alertRoute(n.category, n.title);
            return (
              <li key={`${n.category}-${i}`}>
                <button
                  type="button"
                  disabled={!to}
                  onClick={() => {
                    setExpanded(false);
                    if (to) navigate(to);
                  }}
                  className="w-full rounded-md border border-line bg-surface px-3 py-2 text-left hover:bg-surface-2 disabled:cursor-default"
                >
                  {sentence(n)}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
