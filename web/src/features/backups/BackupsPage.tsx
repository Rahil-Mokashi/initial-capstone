import { useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Dialog } from '@/components/ui/Dialog';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { TextField } from '@/components/ui/Field';
import { formatDateTime } from '@/lib/format';

type S = components['schemas'];
type Backup = S['BackupOut'];
type Offsite = S['OffsiteStatus'];

export function formatSize(bytes: number): string {
  let size = bytes;
  for (const unit of ['B', 'KB', 'MB']) {
    if (size < 1024) return `${size.toFixed(1)} ${unit}`;
    size /= 1024;
  }
  return `${size.toFixed(1)} GB`;
}

/** The same four messages as the Qt screen (never made / unreachable / stale / nothing to say). */
export function offsiteMessage(o: Offsite): string | null {
  if (o.state === 'never')
    return 'No off-device backup has been made from this screen yet. Every backup listed below is on the same drive as the database.';
  if (o.state === 'unreachable')
    return `The off-device location (${o.destination}) is not reachable right now.`;
  if (o.state === 'stale')
    return `The most recent off-device backup is ${Math.round(o.age_days ?? 0)} days old. Copy a fresh one to a USB drive or network folder.`;
  return null;
}

function CopyDialog({
  backup,
  initial,
  onClose,
}: {
  backup: Backup;
  initial: string;
  onClose: () => void;
}) {
  const toast = useToast();
  const [folder, setFolder] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const copy = useWrite(
    (destination_dir: string) =>
      api.post<S['CopyOut']>(`/backups/${encodeURIComponent(backup.filename)}/copy`, {
        destination_dir,
      }),
    ['backups'],
  );
  return (
    <FormDialog
      title="Copy to USB / Network"
      description={`Copies ${backup.filename} to a folder that is not on this drive, then checks the copy.`}
      submitLabel="Copy"
      busy={busy}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          const out = await copy.mutateAsync(folder);
          toast.success(`The backup was copied and verified at ${out.destination}`);
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        } finally {
          setBusy(false);
        }
      }}
      onClose={onClose}
    >
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <TextField
            label="Destination folder"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            autoFocus
          />
        </div>
        {window.pperp?.files.pickFolder && (
          <Button
            onClick={async () => {
              const picked = await window.pperp?.files.pickFolder();
              if (picked) setFolder(picked);
            }}
          >
            Browse...
          </Button>
        )}
      </div>
    </FormDialog>
  );
}

type Step =
  | { kind: 'restore-confirm'; backup: Backup }
  | { kind: 'restore-reason'; backup: Backup }
  | { kind: 'copy'; backup: Backup }
  | null;

export function BackupsPage() {
  const toast = useToast();
  const list = useGet<S['BackupListOut']>(['backups'], '/backups');
  const create = useWrite(() => api.post<Backup>('/backups'), ['backups']);
  const [step, setStep] = useState<Step>(null);
  const [integrity, setIntegrity] = useState<S['IntegrityOut'] | null>(null);
  const [checking, setChecking] = useState(false);
  const [restored, setRestored] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const restore = useWrite(
    ({ filename, reason }: { filename: string; reason: string }) =>
      api.post(`/backups/${encodeURIComponent(filename)}/restore`, { reason }),
    ['backups'],
  );

  const backUp = async () => {
    setProblem(null);
    try {
      const made = await create.mutateAsync(undefined);
      toast.success(`Backup created: ${made.filename}`);
    } catch (error) {
      setProblem(friendlyMessage(error));
    }
  };
  const check = async () => {
    setChecking(true);
    setProblem(null);
    try {
      setIntegrity(await api.post<S['IntegrityOut']>('/backups/check'));
    } catch (error) {
      setProblem(friendlyMessage(error));
    } finally {
      setChecking(false);
    }
  };

  if (list.isLoading) return <LoadingBlock label="Loading backups" rows={4} />;
  if (list.isError) return <ErrorState error={list.error} onRetry={() => void list.refetch()} />;
  const warning = list.data ? offsiteMessage(list.data.offsite) : null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        title="Backups"
        subtitle="Copies of the whole database. Keep at least one on a USB drive or network folder, away from this computer."
      >
        <Button variant="primary" loading={create.isPending} onClick={() => void backUp()}>
          Back Up Now
        </Button>
        <Button loading={checking} onClick={() => void check()}>
          Check Integrity
        </Button>
      </PageHeader>
      {warning && (
        <p
          role="status"
          className="rounded-md border border-warn bg-warn-bg p-3 text-sm font-medium text-warn-fg"
        >
          {warning}
        </p>
      )}
      {problem && (
        <p role="alert" className="text-sm font-medium text-danger-fg">
          {problem}
        </p>
      )}
      {restored && (
        <p
          role="status"
          className="rounded-md border border-ok bg-ok-bg p-3 text-sm font-medium text-ok-fg"
        >
          The database was restored. Close the application and open it again so everything uses the
          restored data.
        </p>
      )}
      <DataTable<Backup>
        caption="Backups"
        getRowId={(b) => b.filename}
        data={list.data?.backups ?? []}
        empty={<p className="text-sm text-muted">No backups yet. Use Back Up Now to make one.</p>}
        columns={[
          {
            accessorKey: 'created_at',
            header: 'Created',
            cell: ({ getValue }) => formatDateTime(getValue<string>()),
          },
          { accessorKey: 'filename', header: 'File' },
          {
            accessorKey: 'size_bytes',
            header: 'Size',
            meta: { numeric: true },
            cell: ({ getValue }) => formatSize(getValue<number>()),
          },
          {
            id: 'actions',
            header: () => <span className="sr-only">Actions</span>,
            cell: ({ row }) => (
              <div className="flex justify-end gap-2">
                <Button
                  aria-label={`Copy ${row.original.filename} to USB or network`}
                  onClick={() => setStep({ kind: 'copy', backup: row.original })}
                >
                  Copy to USB / Network...
                </Button>
                <Button
                  variant="danger"
                  aria-label={`Restore ${row.original.filename}`}
                  onClick={() => setStep({ kind: 'restore-confirm', backup: row.original })}
                >
                  Restore
                </Button>
              </div>
            ),
          },
        ]}
      />

      {integrity && (
        <Dialog
          open
          onOpenChange={(open) => !open && setIntegrity(null)}
          title={integrity.ok ? 'Database is healthy' : 'Database has problems'}
          description={
            integrity.ok
              ? 'The integrity check found no problems.'
              : 'The integrity check reported the following.'
          }
        >
          {!integrity.ok && (
            <ul className="mb-4 list-disc pl-5 text-sm">
              {integrity.messages.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
          <div className="flex justify-end">
            <Button variant="primary" onClick={() => setIntegrity(null)}>
              OK
            </Button>
          </div>
        </Dialog>
      )}

      {step?.kind === 'copy' && (
        <CopyDialog
          backup={step.backup}
          initial={list.data?.configured_offsite_dir ?? ''}
          onClose={() => setStep(null)}
        />
      )}
      {step?.kind === 'restore-confirm' && (
        <ConfirmDialog
          title="Restore this backup?"
          description={`This replaces ALL current data with the contents of ${step.backup.filename}. Anything entered since that backup was made will be lost. A safety copy of the current database is taken first.`}
          submitLabel="Continue"
          tone="danger"
          onConfirm={async () => setStep({ kind: 'restore-reason', backup: step.backup })}
          // ConfirmDialog calls this after a successful confirm too, by which time the step has moved on.
          onClose={() => setStep((now) => (now?.kind === 'restore-confirm' ? null : now))}
        />
      )}
      {step?.kind === 'restore-reason' && (
        <ReasonDialog
          title="Restore backup"
          description={`Restoring ${step.backup.filename}.`}
          label="Reason for restoring"
          submitLabel="Restore"
          tone="danger"
          onConfirm={async (reason) => {
            await restore.mutateAsync({ filename: step.backup.filename, reason });
            setRestored(true);
          }}
          onClose={() => setStep(null)}
        />
      )}
    </div>
  );
}
