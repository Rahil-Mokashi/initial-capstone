import { useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';
import { FormError } from '@/components/ui/FormDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { formatDateTime } from '@/lib/format';

type S = components['schemas'];

const LOOK: Record<string, { tone: Tone; word: string }> = {
  good: { tone: 'ok', word: 'Good' },
  look: { tone: 'warn', word: 'Look' },
  problem: { tone: 'danger', word: 'Problem' },
};

/** Is the Main PC safe? Backups, the database file, the audit log, the second copy, disk space and the PCs, each in one sentence. */
export function SystemHealthPage() {
  const toast = useToast();
  const health = useGet<S['HealthRowOut'][]>(['system-health'], '/system/health', true, 60_000);
  const run = useWrite(() => api.post<S['HealthRowOut'][]>('/system/health/run'), ['system-health', 'checks']);
  const phrase = useWrite((p: string) => api.put('/system/backup-passphrase', { passphrase: p }), ['system-health']);
  const [passphrase, setPassphrase] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (health.isLoading) return <LoadingBlock label="Checking the Main PC" rows={5} />;
  if (health.isError) return <ErrorState error={health.error} onRetry={() => void health.refetch()} />;
  const rows = health.data ?? [];
  const worst = rows.some((r) => r.state === 'problem') ? 'problem' : rows.some((r) => r.state === 'look') ? 'look' : 'good';

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader title="System health" subtitle="Whether the Main PC's data is safe. The Main PC takes backups and runs these checks by itself; you can run them now.">
        <Button
          variant="primary"
          loading={run.isPending}
          onClick={async () => {
            try {
              await run.mutateAsync(undefined);
              toast.success('Checks finished.');
            } catch (e) {
              toast.error(friendlyMessage(e));
            }
          }}
        >
          Run the checks now
        </Button>
      </PageHeader>
      <p role="status" className="text-lg font-semibold">
        {worst === 'good' ? 'Everything is in order.' : worst === 'look' ? 'Some things need a look.' : 'Something needs fixing.'}
      </p>
      <ul className="flex flex-col gap-2" aria-label="Checks">
        {rows.map((r) => (
          <li key={r.key} className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-3 shadow-card">
            <span className="min-w-40 font-semibold">{r.name}</span>
            <StatusBadge tone={LOOK[r.state]!.tone}>{LOOK[r.state]!.word}</StatusBadge>
            <span className="min-w-48 flex-1 text-sm">{r.detail}</span>
            {r.at && <span className="text-xs text-muted">{formatDateTime(r.at)}</span>}
          </li>
        ))}
      </ul>

      <section aria-label="Protecting copies" className="rounded-lg border border-line bg-surface p-4 shadow-card">
        <h2 className="mb-1 text-lg font-semibold">Protecting the data</h2>
        <ul className="mb-3 list-disc pl-5 text-sm text-muted">
          <li>The database lives only on the Main PC, in a folder only Windows administrators can open. Turn on BitLocker for that drive: it protects the data if the PC or its disk is stolen.</li>
          <li>Copies on a USB stick or network folder are encrypted with the passphrase below. Keep the passphrase somewhere safe: without it those copies cannot be opened, by anyone.</li>
        </ul>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await phrase.mutateAsync(passphrase);
              setPassphrase('');
              toast.success('The backup passphrase was saved.');
            } catch (err) {
              setError(friendlyMessage(err));
            }
          }}
        >
          <div className="min-w-64 flex-1">
            <TextField label="Backup passphrase (at least 10 characters)" type="password" autoComplete="new-password" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} />
          </div>
          <Button type="submit" variant="primary" disabled={passphrase.length === 0} loading={phrase.isPending}>
            Save passphrase
          </Button>
        </form>
        <FormError message={error} />
      </section>
    </div>
  );
}
