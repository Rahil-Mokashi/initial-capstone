import { useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { formatDate, formatDateTime } from '@/lib/format';

type S = components['schemas'];
type Entry = S['EntryOut'];

const STEPS = ['entered', 'verified', 'approved', 'locked'] as const;
const LOOK: Record<string, { tone: Tone; word: string; next: string }> = {
  entered: { tone: 'warn', word: 'Entered', next: 'Waiting for the accountant to verify' },
  verified: { tone: 'info', word: 'Verified', next: 'Waiting for an owner to approve' },
  approved: { tone: 'info', word: 'Approved', next: 'Waiting for an owner to lock' },
  locked: { tone: 'ok', word: 'Locked', next: 'Closed for good' },
};

function Steps({ status }: { status: string }) {
  const at = STEPS.indexOf(status as (typeof STEPS)[number]);
  return (
    <ol className="flex items-center gap-1 text-xs" aria-label={`Step ${at + 1} of 4`}>
      {STEPS.map((s, i) => (
        <li key={s} className={i <= at ? 'font-semibold text-ink' : 'text-muted'}>
          {i > 0 && <span aria-hidden> &rsaquo; </span>}
          {LOOK[s]!.word}
        </li>
      ))}
    </ol>
  );
}

/** Where each shift's figures stand: Entered, Verified, Approved, Locked. Only the next step the signed-in person may take is offered. */
export function ReviewPage() {
  const { can } = useAuth();
  const list = useGet<Entry[]>(['entries'], '/entries');
  const [reopening, setReopening] = useState<Entry | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const move = useWrite(({ id, step }: { id: string; step: 'verify' | 'approve' | 'lock' }) => api.post<Entry>(`/entries/${id}/${step}`), ['entries', 'checks', 'daily-report']);
  const reopen = useWrite(({ id, reason }: { id: string; reason: string }) => api.post<Entry>(`/entries/${id}/reopen`, { reason }), ['entries', 'checks', 'daily-report']);

  if (list.isLoading) return <LoadingBlock label="Loading shifts" rows={4} />;
  if (list.isError) return <ErrorState error={list.error} onRetry={() => void list.refetch()} />;
  const rows = list.data ?? [];

  const act = async (id: string, step: 'verify' | 'approve' | 'lock') => {
    setProblem(null);
    try {
      await move.mutateAsync({ id, step });
    } catch (error) {
      setProblem(friendlyMessage(error));
    }
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="Review"
        subtitle="Each shift's figures move from Entered to Verified (accountant), Approved and Locked (owner). Changing a figure after it was verified sends the shift back to Entered. A locked shift only changes if an owner reopens it, with a reason."
      />
      {problem && (
        <p role="alert" className="text-sm font-medium text-danger-fg">
          {problem}
        </p>
      )}
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No shifts have been entered in the last two weeks.</p>
      ) : (
        <ul className="flex flex-col gap-3" aria-label="Shifts">
          {rows.map((e) => {
            const look = LOOK[e.status]!;
            const last = e.events[e.events.length - 1];
            return (
              <li key={e.shift_id} className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-4 shadow-card">
                <div className="min-w-40">
                  <div className="font-semibold">
                    {formatDate(e.shift_date)} - {e.shift_label}
                  </div>
                  <Steps status={e.status} />
                </div>
                <StatusBadge tone={look.tone}>{look.word}</StatusBadge>
                <div className="min-w-48 flex-1 text-sm text-muted">
                  {look.next}
                  {last && (
                    <div>
                      Last: {last.action.replace('_', ' ')}
                      {last.by ? ` by ${last.by}` : ''} at {formatDateTime(last.at)}
                      {last.reason ? ` (${last.reason})` : ''}
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  {e.status === 'entered' && can('entry.verify') && (
                    <Button variant="primary" aria-label={`Verify ${formatDate(e.shift_date)} ${e.shift_label}`} onClick={() => void act(e.shift_id, 'verify')}>
                      Verify
                    </Button>
                  )}
                  {e.status === 'verified' && can('entry.approve') && (
                    <Button variant="primary" aria-label={`Approve ${formatDate(e.shift_date)} ${e.shift_label}`} onClick={() => void act(e.shift_id, 'approve')}>
                      Approve
                    </Button>
                  )}
                  {e.status === 'approved' && can('entry.lock') && (
                    <Button variant="primary" aria-label={`Lock ${formatDate(e.shift_date)} ${e.shift_label}`} onClick={() => void act(e.shift_id, 'lock')}>
                      Lock
                    </Button>
                  )}
                  {e.status !== 'entered' && can('entry.reopen') && (
                    <Button aria-label={`Reopen ${formatDate(e.shift_date)} ${e.shift_label}`} onClick={() => setReopening(e)}>
                      Reopen...
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {reopening && (
        <ReasonDialog
          title="Reopen this shift?"
          description="It goes back to Entered and has to be verified, approved and locked again. The reason is kept with the shift."
          label="What was wrong"
          submitLabel="Reopen"
          tone="danger"
          onConfirm={(reason) => reopen.mutateAsync({ id: reopening.shift_id, reason })}
          onClose={() => setReopening(null)}
        />
      )}
    </div>
  );
}
