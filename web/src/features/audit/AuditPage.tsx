import { useState, type FormEvent } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { SelectField, TextField } from '@/components/ui/Field';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { addDaysIso, todayIso } from '@/lib/format';

type S = components['schemas'];
type Entry = S['AuditEntryOut'];

interface Filters {
  event: string;
  actor: string;
  from: string;
  to: string;
}

// Seconds matter in an audit trail, unlike on the other screens.
function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function query(f: Filters): string {
  const q = new URLSearchParams();
  if (f.event.trim()) q.set('event_type', f.event.trim());
  if (f.actor) q.set('actor_id', f.actor);
  if (f.from) q.set('date_from', f.from);
  if (f.to) q.set('date_to', f.to);
  return q.toString();
}

export function AuditPage() {
  // Same defaults as the Qt screen: the last 7 days. Filters apply when the person presses Filter.
  const initial: Filters = { event: '', actor: '', from: addDaysIso(-7), to: todayIso() };
  const [draft, setDraft] = useState<Filters>(initial);
  const [applied, setApplied] = useState<Filters>(initial);
  const actors = useGet<S['ActorOut'][]>(['audit', 'actors'], '/audit/actors');
  const entries = useGet<Entry[]>(['audit', 'list', applied], `/audit?${query(applied)}`);
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<S['VerifyOut'] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const verify = async () => {
    setVerifying(true);
    setProblem(null);
    try {
      setResult(await api.post<S['VerifyOut']>('/audit/verify'));
    } catch (error) {
      setProblem(friendlyMessage(error));
    } finally {
      setVerifying(false);
    }
  };
  const apply = (e: FormEvent) => {
    e.preventDefault();
    setApplied(draft);
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Audit Log"
        subtitle="Every change made in the application, who made it and when. Entries can never be edited or removed."
      >
        <Button loading={verifying} onClick={() => void verify()}>
          Verify Trail
        </Button>
      </PageHeader>
      <form onSubmit={apply} className="flex flex-wrap items-end gap-3">
        <TextField
          label="Event contains"
          placeholder="Event contains..."
          value={draft.event}
          onChange={(e) => setDraft({ ...draft, event: e.target.value })}
        />
        <SelectField
          label="User"
          value={draft.actor}
          onChange={(e) => setDraft({ ...draft, actor: e.target.value })}
        >
          <option value="">All users</option>
          {(actors.data ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.username}
            </option>
          ))}
        </SelectField>
        <TextField
          label="From"
          type="date"
          value={draft.from}
          onChange={(e) => setDraft({ ...draft, from: e.target.value })}
        />
        <TextField
          label="To"
          type="date"
          value={draft.to}
          onChange={(e) => setDraft({ ...draft, to: e.target.value })}
        />
        <Button type="submit" variant="primary">
          Filter
        </Button>
      </form>
      {problem && (
        <p role="alert" className="text-sm font-medium text-danger-fg">
          {problem}
        </p>
      )}
      {entries.isLoading ? (
        <LoadingBlock label="Loading the audit log" rows={5} />
      ) : entries.isError ? (
        <ErrorState error={entries.error} onRetry={() => void entries.refetch()} />
      ) : (
        <DataTable<Entry>
          caption="Audit log"
          getRowId={(e) => e.id}
          data={entries.data ?? []}
          empty={<p className="text-sm text-muted">No entries match these filters.</p>}
          columns={[
            {
              accessorKey: 'created_at',
              header: 'When',
              cell: ({ getValue }) => when(getValue<string>()),
            },
            { accessorKey: 'event_type', header: 'Event' },
            {
              accessorKey: 'actor',
              header: 'Actor',
              cell: ({ getValue }) => getValue<string | null>() ?? '',
            },
            {
              accessorKey: 'device',
              header: 'From PC',
              cell: ({ getValue }) => getValue<string | null>() ?? '',
            },
            { accessorKey: 'entity', header: 'Entity' },
            { accessorKey: 'description', header: 'Description' },
          ]}
        />
      )}
      {result && (
        <Dialog
          open
          onOpenChange={(open) => !open && setResult(null)}
          title={result.intact ? 'Audit trail verified' : 'Audit trail has been altered'}
          description={
            result.intact
              ? 'The audit trail is intact. Every entry matches its recorded hash and follows its predecessor.'
              : 'The audit trail does not verify. This means the database was modified outside the application.'
          }
        >
          {!result.intact && (
            <ul className="mb-4 list-disc pl-5 text-sm">
              {result.problems.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
          <div className="flex justify-end">
            <Button variant="primary" onClick={() => setResult(null)}>
              OK
            </Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
