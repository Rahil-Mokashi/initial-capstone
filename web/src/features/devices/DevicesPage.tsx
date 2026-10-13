import { useState } from 'react';
import { api } from '@/api/client';
import { ApiError, friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDateTime } from '@/lib/format';

type S = components['schemas'];
type Device = S['DeviceOut'];

/** 4F2A 91C0 ...: how a fingerprint is read aloud and compared between two screens. */
export const groupFingerprint = (hex: string): string => (hex.match(/.{1,4}/g) ?? []).join(' ').toUpperCase();

function PairingDialog({
  pairing,
  onCancelCode,
  onClose,
}: {
  pairing: S['PairingCodeOut'];
  onCancelCode: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Add a device"
      description={`On the other PC choose Network setup, then Client PC. Type this address and the code. The code works once and lasts ${pairing.minutes} minutes.`}
    >
      <dl className="grid gap-3 text-sm">
        <div>
          <dt className="text-muted">Pairing code</dt>
          <dd className="num text-3xl font-bold tracking-widest" aria-label="Pairing code">
            {pairing.code}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Main PC address, port and pairing port</dt>
          <dd className="num">
            {pairing.address}, {pairing.port}, {pairing.pairing_port}
          </dd>
        </div>
        <div>
          <dt className="text-muted">The other PC will show this fingerprint. Check it is the same:</dt>
          <dd className="num font-semibold break-words" aria-label="Fingerprint">
            {groupFingerprint(pairing.ca_fingerprint)}
          </dd>
        </div>
      </dl>
      <div className="mt-5 flex justify-end gap-2">
        <Button onClick={onCancelCode}>Cancel this code</Button>
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </div>
    </Dialog>
  );
}

/** The owner's list of PCs allowed to use this Main PC: add one with a short code, remove one that is lost or replaced. */
export function DevicesPage() {
  const list = useGet<Device[]>(['devices'], '/devices');
  const [pairing, setPairing] = useState<S['PairingCodeOut'] | null>(null);
  const [removing, setRemoving] = useState<Device | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const start = useWrite(() => api.post<S['PairingCodeOut']>('/devices/pairing'), ['devices']);
  const cancel = useWrite(() => api.post('/devices/pairing/cancel'), ['devices']);
  const remove = useWrite(
    ({ id, reason }: { id: string; reason: string }) => api.post(`/devices/${id}/revoke`, { reason }),
    ['devices'],
  );

  if (list.isLoading) return <LoadingBlock label="Loading devices" rows={3} />;
  if (list.isError) {
    if (list.error instanceof ApiError && list.error.code === 'not_found') {
      return (
        <div className="mx-auto flex max-w-2xl flex-col gap-3">
          <PageHeader title="Devices" />
          <p role="status" className="rounded-md border border-line bg-surface p-4 text-sm">
            This PC works on its own, so there are no other devices to manage. Devices are added on the Main PC of a
            pump that uses several computers.
          </p>
        </div>
      );
    }
    return <ErrorState error={list.error} onRetry={() => void list.refetch()} />;
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        title="Devices"
        subtitle="The computers allowed to use this Main PC. Add one with a pairing code; remove one that is lost, stolen or replaced - it stops working at once."
      >
        <Button
          variant="primary"
          loading={start.isPending}
          onClick={async () => {
            setProblem(null);
            try {
              setPairing(await start.mutateAsync(undefined));
            } catch (error) {
              setProblem(friendlyMessage(error));
            }
          }}
        >
          Add a device
        </Button>
      </PageHeader>
      {problem && (
        <p role="alert" className="text-sm font-medium text-danger-fg">
          {problem}
        </p>
      )}
      <DataTable<Device>
        caption="Devices"
        getRowId={(d) => d.id}
        data={list.data ?? []}
        empty={<p className="text-sm text-muted">No devices yet. Use Add a device.</p>}
        columns={[
          { accessorKey: 'name', header: 'Name' },
          {
            accessorKey: 'enrolled_at',
            header: 'Added',
            cell: ({ getValue }) => formatDateTime(getValue<string>()),
          },
          {
            accessorKey: 'last_seen_at',
            header: 'Last seen',
            cell: ({ row }) =>
              row.original.last_seen_at
                ? `${formatDateTime(row.original.last_seen_at)} from ${row.original.last_ip ?? 'unknown'}`
                : 'Never',
          },
          {
            id: 'status',
            header: 'Status',
            cell: ({ row }) =>
              row.original.revoked_at ? (
                <StatusBadge tone="neutral">Removed</StatusBadge>
              ) : (
                <StatusBadge tone="ok">Active</StatusBadge>
              ),
          },
          {
            id: 'actions',
            header: () => <span className="sr-only">Actions</span>,
            cell: ({ row }) =>
              row.original.revoked_at ? null : (
                <div className="flex justify-end">
                  <Button
                    variant="danger"
                    aria-label={`Remove ${row.original.name}`}
                    onClick={() => setRemoving(row.original)}
                  >
                    Remove
                  </Button>
                </div>
              ),
          },
        ]}
      />
      {pairing && (
        <PairingDialog
          pairing={pairing}
          onClose={() => setPairing(null)}
          onCancelCode={() => {
            setPairing(null);
            void cancel.mutateAsync(undefined).catch(() => undefined);
          }}
        />
      )}
      {removing && (
        <ReasonDialog
          title="Remove this device?"
          description={`${removing.name} will stop working on the pump's network immediately. Its records stay in the audit log.`}
          label="Reason for removing"
          submitLabel="Remove"
          tone="danger"
          onConfirm={(reason) => remove.mutateAsync({ id: removing.id, reason })}
          onClose={() => setRemoving(null)}
        />
      )}
    </div>
  );
}
