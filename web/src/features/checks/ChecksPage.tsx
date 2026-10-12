import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { SelectField, TextAreaField, TextField } from '@/components/ui/Field';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { formatDateTime, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';
import { formatCheckValue, statusWords } from './checkText';

type S = components['schemas'];
type Check = S['CheckOut'];

const TONE: Record<string, Tone> = { pass: 'ok', warn: 'warn', fail: 'danger' };
const AREAS = ['Daily report', 'Cash', 'Stock', 'Credit', 'Bank', 'Payroll'];

function CheckRow({ check, onExplain }: { check: Check; onExplain: (c: Check) => void }) {
  const { can } = useAuth();
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <StatusBadge tone={TONE[check.status] ?? 'neutral'}>
            {statusWords(check.status)}
          </StatusBadge>
          <p className="font-semibold">{check.sentence}</p>
        </div>
        <span className="text-xs font-semibold tracking-wide text-muted uppercase">
          {check.area}
        </span>
      </div>
      <dl className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-muted">Should be</dt>
          <dd className="num font-semibold">{formatCheckValue(check.unit, check.expected)}</dd>
        </div>
        <div>
          <dt className="text-muted">Found</dt>
          <dd className="num font-semibold">{formatCheckValue(check.unit, check.actual)}</dd>
        </div>
        <div>
          <dt className="text-muted">Difference</dt>
          <dd className="num font-semibold">{formatCheckValue(check.unit, check.difference)}</dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-center gap-3">
        {check.links.map((l) => (
          <Link
            key={`${l.route}-${l.label}`}
            to={String(l.route)}
            className="inline-flex min-h-[44px] items-center rounded-md border border-line-strong px-3 text-sm font-semibold hover:bg-surface-2"
          >
            {String(l.label)} &rarr;
          </Link>
        ))}
        {check.status !== 'pass' && can(P.CHECK_EXPLAIN) && (
          <Button onClick={() => onExplain(check)}>Add an explanation</Button>
        )}
      </div>
      {check.explanations.length > 0 && (
        <ul
          aria-label="Explanations"
          className="flex flex-col gap-1 border-t border-line pt-2 text-sm"
        >
          {check.explanations.map((e, i) => (
            <li key={i}>
              <span className="font-semibold">{e.by}</span>{' '}
              <span className="text-muted">({formatDateTime(e.at)})</span>: {e.text}
            </li>
          ))}
          <li className="text-xs text-muted">
            An explanation never changes the result above. It stays{' '}
            {statusWords(check.status).toLowerCase()} until the figures themselves agree.
          </li>
        </ul>
      )}
    </li>
  );
}

export function ChecksPage() {
  const [day, setDay] = useState(todayIso());
  const [area, setArea] = useState('');
  const [history, setHistory] = useState(false);
  const [explaining, setExplaining] = useState<Check | null>(null);
  const [text, setText] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const query = `/checks?day=${day}${area ? `&area=${encodeURIComponent(area)}` : ''}`;
  const current = useGet<S['DayChecksOut']>(['checks', 'day', day, area], query);
  const hist = useGet<Check[]>(['checks', 'history', day], `/checks/history?day=${day}`, history);
  const run = useWrite(() => api.post('/checks/run', { day }), ['checks']);
  const explain = useWrite(
    (v: { id: string; text: string }) => api.post(`/checks/${v.id}/explanations`, { text: v.text }),
    ['checks'],
  );

  const summary = current.data?.summary;
  const submit = async () => {
    if (!explaining) return;
    setProblem(null);
    try {
      await explain.mutateAsync({ id: explaining.id, text });
      setExplaining(null);
      setText('');
    } catch (error) {
      setProblem(friendlyMessage(error));
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Checks"
        subtitle="Every check the software makes, with the two figures it compared. Failures come first."
      >
        <Button loading={run.isPending} onClick={() => run.mutate(undefined)}>
          Check again now
        </Button>
      </PageHeader>
      <div className="flex flex-wrap items-end gap-3">
        <TextField label="Day" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        <SelectField label="Area" value={area} onChange={(e) => setArea(e.target.value)}>
          <option value="">All areas</option>
          {AREAS.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </SelectField>
        <Button aria-pressed={history} onClick={() => setHistory((h) => !h)}>
          {history ? 'Hide history' : 'Show history for this day'}
        </Button>
      </div>
      {current.isLoading ? (
        <LoadingBlock label="Loading checks" rows={3} />
      ) : current.isError ? (
        <ErrorState error={current.error} onRetry={() => void current.refetch()} />
      ) : summary && summary.total === 0 ? (
        <EmptyState title="No checks for this day yet">
          Checks appear as soon as shifts, sales or tank readings are saved for the day.
        </EmptyState>
      ) : (
        <>
          <p role="status" className="text-lg font-bold">
            {summary?.passed} of {summary?.total} checks passed
            {summary && summary.failed > 0 ? `, ${summary.failed} failed` : ''}
            {summary && summary.warned > 0 ? `, ${summary.warned} to look at` : ''}
          </p>
          <ul aria-label="Check results" className="flex flex-col gap-3">
            {(current.data?.results ?? []).map((c) => (
              <CheckRow key={c.id} check={c} onExplain={setExplaining} />
            ))}
          </ul>
        </>
      )}
      {history && (
        <section aria-labelledby="history-title" className="flex flex-col gap-2">
          <h2 id="history-title" className="text-base font-bold">
            Everything recorded on this day
          </h2>
          <p className="text-sm text-muted">
            Results are never overwritten. When a figure changes, a new result is added and the
            older one stays here.
          </p>
          {hist.isLoading ? (
            <LoadingBlock rows={2} />
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {(hist.data ?? []).map((c) => (
                <li key={c.id}>
                  <span className="text-muted">{formatDateTime(c.run_at)}</span> —{' '}
                  {statusWords(c.status)} — {c.sentence}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      <Dialog
        open={explaining !== null}
        onOpenChange={(open) => !open && setExplaining(null)}
        title="Add an explanation"
        description={explaining?.sentence}
      >
        <div className="flex flex-col gap-4">
          <TextAreaField
            label="What explains this?"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <p className="text-xs text-muted">
            Your name and the time are saved with it. The result itself will not change.
          </p>
          {problem && (
            <p role="alert" className="text-sm font-medium text-danger-fg">
              {problem}
            </p>
          )}
          <div className="flex justify-end gap-3">
            <Button onClick={() => setExplaining(null)}>Cancel</Button>
            <Button variant="primary" loading={explain.isPending} onClick={() => void submit()}>
              Save explanation
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
