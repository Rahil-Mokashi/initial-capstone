import { useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { Button } from '@/components/ui/Button';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { formatDate, formatMoney } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Row = S['BankStatementRowOut'];
type Expected = S['BankExpectedOut'];

const TONE: Record<string, Tone> = {
  matched: 'ok',
  suggested: 'warn',
  awaiting: 'info',
  unmatched: 'danger',
};
const WORDS: Record<string, string> = {
  matched: 'Matched',
  suggested: 'Please confirm',
  awaiting: 'On its way',
  unmatched: 'Not received',
};
const cell = 'border border-line px-3 py-2';
const BANK = ['bank'];

export function useRange(from: string, to: string) {
  return `date_from=${from}&date_to=${to}`;
}

/** Day by day: for each payment mode, what the books expect against what reached the bank. */
export function DaysTable({ from, to }: { from: string; to: string }) {
  const q = useRange(from, to);
  const days = useGet<S['BankDayModeOut'][]>(['bank', 'days', from, to], `/bank/days?${q}`);
  if (days.isLoading) return <LoadingBlock rows={3} label="Loading the days" />;
  if (days.isError) return <ErrorState error={days.error} onRetry={() => void days.refetch()} />;
  const rows = days.data ?? [];
  if (rows.length === 0)
    return (
      <p className="text-sm text-muted">
        Nothing is expected at the bank for these days yet. Payment-mode totals, cash deposits and
        credit payments appear here once they are typed in.
      </p>
    );
  return (
    <div className="overflow-x-auto">
      <table
        className="w-full border-collapse text-sm"
        aria-label="Expected against received, by day"
      >
        <thead>
          <tr className="bg-surface-2 text-left">
            <th className={cell}>Day</th>
            <th className={cell}>Payment mode</th>
            <th className={`${cell} text-right`}>Expected</th>
            <th className={`${cell} text-right`}>Received</th>
            <th className={`${cell} text-right`}>Bank charges</th>
            <th className={`${cell} text-right`}>Not matched</th>
            <th className={cell}>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.day}-${r.mode}`}>
              <td className={cell}>{formatDate(r.day)}</td>
              <th scope="row" className={`${cell} text-left`}>
                {r.label}
              </th>
              <td className={`${cell} num text-right`}>{formatMoney(r.expected)}</td>
              <td className={`${cell} num text-right`}>{formatMoney(r.received)}</td>
              <td className={`${cell} num text-right`}>{formatMoney(r.charges)}</td>
              <td className={`${cell} num text-right`}>
                {formatMoney((Number(r.unmatched) + Number(r.suggested)).toFixed(2))}
              </td>
              <td className={cell}>
                <StatusBadge tone={TONE[r.status] ?? 'neutral'}>
                  {WORDS[r.status] ?? r.status}
                </StatusBadge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Suggestions() {
  const toast = useToast();
  const list = useGet<S['BankSuggestionOut'][]>(['bank', 'suggestions'], '/bank/suggestions');
  const [rejecting, setRejecting] = useState<string | null>(null);
  const confirm = useWrite(
    (id: string) => api.post(`/bank/matches/${id}/confirm`),
    [...BANK, 'checks'],
  );
  const reject = useWrite(
    (v: { id: string; reason: string }) =>
      api.post(`/bank/matches/${v.id}/reject`, { reason: v.reason }),
    [...BANK, 'checks'],
  );
  const items = list.data ?? [];
  return (
    <section aria-labelledby="sug" className="flex flex-col gap-3">
      <h2 id="sug" className="text-base font-bold">
        Suggested matches: please check and confirm
      </h2>
      {items.length === 0 ? (
        <p className="text-sm text-muted">Nothing is waiting to be confirmed.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((s) => (
            <li
              key={s.match_id}
              className="rounded-lg border border-line bg-surface p-4 shadow-card"
            >
              <p className="mb-1 text-sm text-muted">{s.note}</p>
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <p className="text-xs font-bold tracking-wide text-muted uppercase">
                    The books say
                  </p>
                  <ul className="text-sm">
                    {s.expected.map((e) => (
                      <li key={e.id}>
                        {e.description}: <strong className="num">{formatMoney(e.amount)}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-bold tracking-wide text-muted uppercase">
                    The bank shows
                  </p>
                  <ul className="text-sm">
                    {s.rows.map((r) => (
                      <li key={r.id}>
                        {formatDate(r.txn_date)} {r.description}:{' '}
                        <strong className="num">
                          {formatMoney(Number(r.credit) > 0 ? r.credit : r.debit)}
                        </strong>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              {Number(s.charges) > 0 && (
                <p className="mt-2 text-sm">
                  <StatusBadge tone="warn">{`Bank charges of ${formatMoney(s.charges)} would be recorded`}</StatusBadge>
                </p>
              )}
              <div className="mt-3 flex gap-2">
                <Button
                  variant="primary"
                  onClick={() =>
                    confirm.mutateAsync(s.match_id).then(() => toast.success('Match confirmed.'))
                  }
                >
                  Confirm this match
                </Button>
                <Button onClick={() => setRejecting(s.match_id)}>Not a match</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {rejecting && (
        <ReasonDialog
          title="Not a match"
          description="The suggestion is dropped; both sides stay open."
          submitLabel="Drop the suggestion"
          onConfirm={(reason) => reject.mutateAsync({ id: rejecting, reason })}
          onClose={() => setRejecting(null)}
        />
      )}
    </section>
  );
}

function ManualDialog({
  credit,
  expected,
  onClose,
}: {
  credit: Row;
  expected: Expected[];
  onClose: () => void;
}) {
  const toast = useToast();
  const [picked, setPicked] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['BankManualIn']) => api.post('/bank/matches/manual', b),
    [...BANK, 'checks'],
  );
  return (
    <FormDialog
      title="Match by hand"
      description={`${formatDate(credit.txn_date)} ${credit.description}: ${formatMoney(credit.credit)}`}
      submitLabel="Match"
      busy={save.isPending}
      error={error}
      onClose={onClose}
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await save.mutateAsync({ expected_ids: picked, row_ids: [credit.id], reason });
          toast.success('Matched.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-semibold">
          Which payments reached the bank in this credit?
        </legend>
        {expected.length === 0 && (
          <p className="text-sm text-muted">Nothing unmatched is expected in these days.</p>
        )}
        {expected.map((e) => (
          <label key={e.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={picked.includes(e.id)}
              onChange={(ev) =>
                setPicked(ev.target.checked ? [...picked, e.id] : picked.filter((x) => x !== e.id))
              }
            />
            {e.description} - {formatMoney(e.amount)}
          </label>
        ))}
      </fieldset>
      <label className="flex flex-col gap-1 text-sm font-semibold">
        Why are you matching these?
        <input
          className="min-h-[44px] rounded-md border border-line-strong px-3 font-normal"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
    </FormDialog>
  );
}

/** Bank credits nobody has accounted for, expected payments that never arrived, and statements with missing rows. */
export function Attention({ from, to }: { from: string; to: string }) {
  const { can } = useAuth();
  const toast = useToast();
  const q = useRange(from, to);
  const ex = useGet<S['BankExceptionsOut']>(
    ['bank', 'exceptions', from, to],
    `/bank/exceptions?${q}`,
  );
  const [manual, setManual] = useState<Row | null>(null);
  const [notOurs, setNotOurs] = useState<Row | null>(null);
  const markNotOurs = useWrite(
    (v: { id: string; reason: string }) =>
      api.post(`/bank/rows/${v.id}/not-ours`, { reason: v.reason }),
    [...BANK, 'checks'],
  );
  if (ex.isLoading) return <LoadingBlock rows={2} />;
  if (ex.isError) return <ErrorState error={ex.error} onRetry={() => void ex.refetch()} />;
  const d = ex.data!;
  const manage = can(P.BANK_RECON_MANAGE);
  return (
    <section aria-labelledby="att" className="flex flex-col gap-4">
      <h2 id="att" className="text-base font-bold">
        Needs your attention
      </h2>
      <p className="text-sm">
        Bank charges deducted so far:{' '}
        <strong className="num">{formatMoney(d.total_charges)}</strong>
        {d.suggestions > 0 && ` · ${d.suggestions} suggestion(s) waiting for you`}
      </p>
      {d.broken_imports.map((i) => (
        <p
          key={i.id}
          role="alert"
          className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
        >
          {i.filename}: {i.continuity_notes}
        </p>
      ))}
      <div>
        <h3 className="mb-1 text-sm font-bold">Bank credits not matched to anything</h3>
        {d.unmatched_credits.length === 0 ? (
          <p className="text-sm text-muted">
            Every bank credit is matched or marked as not the pump&apos;s.
          </p>
        ) : (
          <ul className="flex flex-col gap-2" aria-label="Unmatched bank credits">
            {d.unmatched_credits.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line p-3 text-sm"
              >
                <span>
                  {formatDate(r.txn_date)} {r.description}:{' '}
                  <strong className="num">{formatMoney(r.credit)}</strong>
                </span>
                {manage && (
                  <span className="flex gap-2">
                    <Button onClick={() => setManual(r)}>Match by hand</Button>
                    <Button onClick={() => setNotOurs(r)}>Not the pump&apos;s</Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="mb-1 text-sm font-bold">Expected at the bank but not seen</h3>
        {d.aged_expected.length === 0 ? (
          <p className="text-sm text-muted">Everything expected has been matched.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm" aria-label="Expected but not received">
            {d.aged_expected.map((a) => (
              <li key={a.expected.id}>
                {a.expected.description}:{' '}
                <strong className="num">{formatMoney(a.expected.amount)}</strong>, {a.age_days}{' '}
                day(s) ago
              </li>
            ))}
          </ul>
        )}
      </div>
      {manual && (
        <ManualDialog
          credit={manual}
          expected={d.aged_expected.map((a) => a.expected)}
          onClose={() => setManual(null)}
        />
      )}
      {notOurs && (
        <ReasonDialog
          title="Not the pump's"
          description={`${notOurs.description}: ${formatMoney(notOurs.credit)}. It will not be matched to anything.`}
          submitLabel="Mark as not the pump's"
          onConfirm={async (reason) => {
            await markNotOurs.mutateAsync({ id: notOurs.id, reason });
            toast.success("Marked as not the pump's.");
          }}
          onClose={() => setNotOurs(null)}
        />
      )}
    </section>
  );
}

/** Every statement line with where it stands, and Unmatch / Lock for confirmed matches. */
export function StatementLines({ from, to }: { from: string; to: string }) {
  const { can } = useAuth();
  const q = useRange(from, to);
  const rows = useGet<Row[]>(['bank', 'rows', from, to], `/bank/rows?${q}`);
  const [undoing, setUndoing] = useState<Row | null>(null);
  const unmatch = useWrite(
    (v: { id: string; reason: string }) =>
      api.post(`/bank/matches/${v.id}/unmatch`, { reason: v.reason }),
    [...BANK, 'checks'],
  );
  const lock = useWrite(
    (v: { id: string; locked: boolean }) =>
      api.post(`/bank/matches/${v.id}/lock`, { locked: v.locked }),
    BANK,
  );
  if (rows.isLoading) return <LoadingBlock rows={2} />;
  const list = rows.data ?? [];
  const state = (r: Row) =>
    r.match_kind === 'not_ours'
      ? "Not the pump's"
      : r.match_kind === 'reversal'
        ? 'Reversal'
        : r.match_status === 'confirmed'
          ? 'Matched'
          : r.match_status === 'suggested'
            ? 'Suggested'
            : 'Open';
  return (
    <section aria-labelledby="lines" className="flex flex-col gap-2">
      <h2 id="lines" className="text-base font-bold">
        Bank statement lines
      </h2>
      {list.length === 0 ? (
        <p className="text-sm text-muted">
          No statement lines in these days. Import a statement first.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm" aria-label="Bank statement lines">
            <thead>
              <tr className="bg-surface-2 text-left">
                <th className={cell}>Date</th>
                <th className={cell}>Details</th>
                <th className={`${cell} text-right`}>Money in</th>
                <th className={`${cell} text-right`}>Money out</th>
                <th className={cell}>Where it stands</th>
                <th className={cell} />
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.id}>
                  <td className={cell}>{formatDate(r.txn_date)}</td>
                  <td className={cell}>{r.description}</td>
                  <td className={`${cell} num text-right`}>
                    {Number(r.credit) > 0 ? formatMoney(r.credit) : ''}
                  </td>
                  <td className={`${cell} num text-right`}>
                    {Number(r.debit) > 0 ? formatMoney(r.debit) : ''}
                  </td>
                  <td className={cell}>
                    {state(r)}
                    {r.locked ? ' (locked by an owner)' : ''}
                  </td>
                  <td className={cell}>
                    {r.match_status === 'confirmed' &&
                      r.match_id &&
                      can(P.BANK_RECON_MANAGE) &&
                      !r.locked && <Button onClick={() => setUndoing(r)}>Undo match</Button>}{' '}
                    {r.match_status === 'confirmed' && r.match_id && can(P.BANK_RECON_LOCK) && (
                      <Button onClick={() => lock.mutate({ id: r.match_id!, locked: !r.locked })}>
                        {r.locked ? 'Unlock' : 'Lock'}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {undoing && (
        <ReasonDialog
          title="Undo this match"
          description={`${undoing.description}. Both sides become open again; the undone match stays in the audit log.`}
          submitLabel="Undo match"
          tone="danger"
          onConfirm={(reason) => unmatch.mutateAsync({ id: undoing.match_id!, reason })}
          onClose={() => setUndoing(null)}
        />
      )}
    </section>
  );
}
