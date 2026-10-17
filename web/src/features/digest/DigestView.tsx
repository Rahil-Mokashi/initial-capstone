import { CheckCircle2, OctagonAlert, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { Button } from '@/components/ui/Button';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { formatDate, formatDateTime, formatMoney, formatQuantity } from '@/lib/format';

type S = components['schemas'];

const VERDICT: Record<string, { tone: Tone; word: (amount: string) => string }> = {
  balanced: { tone: 'ok', word: () => 'Balanced' },
  short: { tone: 'danger', word: (a) => `Short ${formatMoney(a)}` },
  excess: { tone: 'warn', word: (a) => `Excess ${formatMoney(a.replace('-', ''))}` },
};
const ENTRY_WORD: Record<string, string> = { entered: 'Entered', verified: 'Verified', approved: 'Approved', locked: 'Locked' };

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface-2 p-3">
      <div className="text-xs font-semibold tracking-wide text-muted uppercase">{label}</div>
      <div className="num mt-1 text-lg font-bold [overflow-wrap:anywhere] sm:text-xl">{value}</div>
    </div>
  );
}

/** How the day went, in one place, with what needs a decision. Every figure comes from the service that owns it. */
export function DigestView({ day }: { day?: string }) {
  const toast = useToast();
  const query = day ? `?day=${day}` : '';
  const digest = useGet<S['DigestOut']>(['digest', day ?? 'latest'], `/digest${query}`);
  const review = useWrite((d: string) => api.post<S['DigestOut']>('/digest/review', { day: d }), ['digest']);

  if (digest.isLoading) return <LoadingBlock label="Loading the digest" rows={4} />;
  if (digest.isError) return <ErrorState error={digest.error} onRetry={() => void digest.refetch()} />;
  const d = digest.data!;
  const waiting = Object.entries(d.waiting).filter(([status]) => status !== 'locked');

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">{formatDate(d.day)}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Figure label="Total sale" value={formatMoney(d.total_sale)} />
        <Figure label="Litres sold" value={formatQuantity(d.litres_sold)} />
        <Figure label="Credit sales" value={formatMoney(d.credit_sales)} />
        <Figure label="Credit outstanding" value={formatMoney(d.credit_outstanding)} />
      </div>

      <section aria-label="Shifts" className="min-w-0 rounded-lg border border-line bg-surface p-4 shadow-card">
        <h3 className="mb-2 text-sm font-bold tracking-widest text-muted uppercase">Shifts</h3>
        {d.shifts.length === 0 ? (
          <p className="text-sm text-muted">No shift was closed on this day.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {d.shifts.map((s) => {
              const v = VERDICT[s.status]!;
              return (
                <li key={s.shift_id} className="flex flex-wrap items-center gap-3">
                  <span className="min-w-28 font-semibold">{s.label}</span>
                  <span className="num">{formatMoney(s.total_sale)} sold</span>
                  <span className="num text-muted">{formatMoney(s.collected)} collected</span>
                  <StatusBadge tone={v.tone}>{v.word(s.difference)}</StatusBadge>
                  {s.entry_status && <span className="text-sm text-muted">{ENTRY_WORD[s.entry_status]}</span>}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-label="Checks" className="rounded-lg border border-line bg-surface p-4 shadow-card">
          <h3 className="mb-2 text-sm font-bold tracking-widest text-muted uppercase">Checks</h3>
          <p className="num flex items-center gap-2 text-lg font-bold">
            {d.checks_to_look_at.some((c) => c.status === 'fail') ? <OctagonAlert className="size-5 text-danger-fg" aria-hidden /> : d.checks_to_look_at.length ? <TriangleAlert className="size-5 text-warn-fg" aria-hidden /> : <CheckCircle2 className="size-5 text-ok-fg" aria-hidden />}
            {d.checks_passed} of {d.checks_total} passed
          </p>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {d.checks_to_look_at.map((c) => (
              <li key={c.sentence}>
                <StatusBadge tone={c.status === 'fail' ? 'danger' : 'warn'}>{c.status === 'fail' ? 'Failed' : 'Look'}</StatusBadge> {c.sentence}
              </li>
            ))}
          </ul>
          <Link className="mt-3 inline-block text-sm underline" to="/checks">Open Checks</Link>
        </section>

        <section aria-label="Waiting" className="rounded-lg border border-line bg-surface p-4 shadow-card">
          <h3 className="mb-2 text-sm font-bold tracking-widest text-muted uppercase">Waiting for a decision</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {waiting.length === 0 && d.pending_expenses === 0 && <li>Nothing is waiting.</li>}
            {waiting.map(([status, n]) => (
              <li key={status}>
                {n} {n === 1 ? 'shift' : 'shifts'} {status === 'entered' ? 'not yet verified' : status === 'verified' ? 'verified, to approve' : 'approved, to lock'}
              </li>
            ))}
            {d.pending_expenses > 0 && <li>{d.pending_expenses} {d.pending_expenses === 1 ? 'expense' : 'expenses'} not yet approved</li>}
          </ul>
          <Link className="mt-3 inline-block text-sm underline" to="/review">Open Review</Link>
        </section>
      </div>

      <section aria-label="Reviewed" className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-4 shadow-card">
        {d.reviewed.length > 0 ? (
          <p className="text-sm">
            Reviewed by {d.reviewed.map((r) => `${r.by} at ${formatDateTime(r.at)}`).join(', ')}.
          </p>
        ) : (
          <p className="text-sm text-muted">No owner has marked this day as reviewed yet.</p>
        )}
        {!d.reviewed_by_me && (
          <Button
            variant="primary"
            loading={review.isPending}
            onClick={async () => {
              try {
                await review.mutateAsync(d.day);
                toast.success('Marked as reviewed.');
              } catch (error) {
                toast.error(friendlyMessage(error));
              }
            }}
          >
            Mark as reviewed
          </Button>
        )}
      </section>
    </div>
  );
}
