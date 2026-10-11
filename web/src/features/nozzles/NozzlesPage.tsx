import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { TabbedPanel } from '@/components/ui/TabbedPanel';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { titleCase } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Dispenser = S['DispenserOut'];
type Nozzle = S['NozzleOut'];

const useDispensers = () => useGet<Dispenser[]>(['nozzles', 'dispensers'], '/dispensers');
const useNozzles = () => useGet<Nozzle[]>(['nozzles', 'nozzles'], '/nozzles');
const useOptions = () => useGet<S['NozzleOptions']>(['nozzles', 'options'], '/nozzles/options');
const useCreateDispenser = () =>
  useWrite((code: string) => api.post<Dispenser>('/dispensers', { code }), ['nozzles']);
const useDispenserStatus = (id: string) =>
  useWrite(
    (body: S['DispenserStatusIn']) => api.post<Dispenser>(`/dispensers/${id}/status`, body),
    ['nozzles'],
  );
const useCreateNozzle = () =>
  useWrite((body: S['NozzleIn']) => api.post<Nozzle>('/nozzles', body), ['nozzles']);
const useNozzleStatus = (id: string) =>
  useWrite(
    (body: S['NozzleStatusIn']) => api.post<Nozzle>(`/nozzles/${id}/status`, body),
    ['nozzles'],
  );

const NOZZLE_STATUSES = ['active', 'inactive', 'maintenance'] as const;
const tone = (status: string): Tone =>
  status === 'active' ? 'ok' : status === 'maintenance' ? 'warn' : 'neutral';

// ---- dialogs -------------------------------------------------------------------------
const codeSchema = z.object({ code: z.string().trim().min(1, 'Enter a code.') });

function AddDispenserDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const create = useCreateDispenser();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof codeSchema>>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync(v.code.trim());
      toast.success(`Dispenser ${v.code.trim()} added.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['code']));
    }
  });
  return (
    <FormDialog
      title="Add dispenser"
      submitLabel="Save"
      busy={create.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Code"
        placeholder="e.g. D1"
        autoFocus
        error={errors.code?.message}
        {...register('code')}
      />
    </FormDialog>
  );
}

const nozzleSchema = z.object({
  code: z.string().trim().min(1, 'Enter a code.'),
  dispenser_id: z.string().min(1, 'Choose a dispenser.'),
  fuel_id: z.string().min(1, 'Choose a fuel type.'),
  tank_id: z.string(),
});

function AddNozzleDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const options = useOptions();
  const create = useCreateNozzle();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof nozzleSchema>>({
    resolver: zodResolver(nozzleSchema),
    defaultValues: { code: '', dispenser_id: '', fuel_id: '', tank_id: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({
        code: v.code.trim(),
        dispenser_id: v.dispenser_id,
        fuel_id: v.fuel_id,
        tank_id: v.tank_id || undefined,
      });
      toast.success(`Nozzle ${v.code.trim()} added.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['code', 'dispenser_id', 'fuel_id', 'tank_id']));
    }
  });
  const noDispensers = options.data && options.data.dispensers.length === 0;
  return (
    <FormDialog
      title="Add nozzle"
      submitLabel="Save"
      busy={create.isPending}
      error={formError ?? (noDispensers ? 'No active dispensers available. Add one first.' : null)}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Code"
        placeholder="e.g. N1"
        autoFocus
        error={errors.code?.message}
        {...register('code')}
      />
      <SelectField
        label="Dispenser"
        error={errors.dispenser_id?.message}
        {...register('dispenser_id')}
      >
        <option value="">Choose a dispenser</option>
        {options.data?.dispensers.map((d) => (
          <option key={d.id} value={d.id}>
            {d.code}
          </option>
        ))}
      </SelectField>
      <SelectField label="Fuel type" error={errors.fuel_id?.message} {...register('fuel_id')}>
        <option value="">Choose a fuel type</option>
        {options.data?.fuels.map((f) => (
          <option key={f.id} value={f.id}>
            {f.fuel_type}
          </option>
        ))}
      </SelectField>
      <SelectField label="Tank" {...register('tank_id')}>
        <option value="">(auto - single tank for fuel type)</option>
        {options.data?.tanks.map((t) => (
          <option key={t.id} value={t.id}>
            {t.label}
          </option>
        ))}
      </SelectField>
    </FormDialog>
  );
}

function NozzleStatusDialog({ nozzle, onClose }: { nozzle: Nozzle; onClose: () => void }) {
  const toast = useToast();
  const change = useNozzleStatus(nozzle.id);
  const [status, setStatus] = useState(nozzle.status);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  return (
    <FormDialog
      title="Change status"
      description={`Nozzle ${nozzle.code}`}
      submitLabel="Change status"
      busy={change.isPending}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await change.mutateAsync({
            status: status as S['NozzleStatusIn']['status'],
            reason: reason.trim(),
          });
          toast.success('Status changed.');
          onClose();
        } catch (err) {
          setError(applyApiError(err, () => undefined, []));
        }
      }}
      onClose={onClose}
    >
      <SelectField label="New status" value={status} onChange={(e) => setStatus(e.target.value)}>
        {NOZZLE_STATUSES.map((s) => (
          <option key={s} value={s}>
            {titleCase(s)}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Reason"
        optional
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
    </FormDialog>
  );
}

// ---- tabs ----------------------------------------------------------------------------
type Dialog =
  | { kind: 'add-dispenser' }
  | { kind: 'add-nozzle' }
  | { kind: 'dispenser'; dispenser: Dispenser }
  | { kind: 'nozzle'; nozzle: Nozzle }
  | null;

function Panel<T>({
  query,
  caption,
  columns,
  getRowId,
  addLabel,
  onAdd,
  emptyTitle,
}: {
  query: {
    isLoading: boolean;
    isError: boolean;
    error: unknown;
    data?: T[];
    refetch: () => unknown;
  };
  caption: string;
  columns: ColumnDef<T>[];
  getRowId: (r: T) => string;
  addLabel?: string;
  onAdd: () => void;
  emptyTitle: string;
}) {
  return (
    <>
      {addLabel && (
        <div className="flex justify-end">
          <Button variant="primary" onClick={onAdd}>
            <Plus className="size-4" aria-hidden /> {addLabel}
          </Button>
        </div>
      )}
      {query.isLoading ? (
        <LoadingBlock label={`Loading ${caption}`} rows={3} />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          caption={caption}
          columns={columns}
          data={query.data ?? []}
          getRowId={getRowId}
          empty={<EmptyState title={emptyTitle} />}
        />
      )}
    </>
  );
}

export function NozzlesPage() {
  const { can } = useAuth();
  const canManage = can(P.NOZZLE_MANAGE);
  const dispensers = useDispensers();
  const nozzles = useNozzles();
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);

  const editButton = (label: string, onClick: () => void) =>
    canManage ? (
      <button
        type="button"
        aria-label={label}
        onClick={onClick}
        className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2"
      >
        <Pencil className="size-4" aria-hidden />
      </button>
    ) : null;

  const dispenserColumns: ColumnDef<Dispenser>[] = [
    { accessorKey: 'code', header: 'Code' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => (
        <StatusBadge tone={tone(getValue<string>())}>{titleCase(getValue<string>())}</StatusBadge>
      ),
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) =>
        editButton(
          `${row.original.status === 'active' ? 'Mark inactive' : 'Mark active'} - dispenser ${row.original.code}`,
          () => setDialog({ kind: 'dispenser', dispenser: row.original }),
        ),
    },
  ];

  const nozzleColumns: ColumnDef<Nozzle>[] = [
    { accessorKey: 'code', header: 'Code' },
    { accessorKey: 'dispenser', header: 'Dispenser', cell: ({ getValue }) => getValue() ?? '' },
    { accessorKey: 'fuel_type', header: 'Fuel type', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => (
        <StatusBadge tone={tone(getValue<string>())}>{titleCase(getValue<string>())}</StatusBadge>
      ),
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) =>
        editButton(`Change status - nozzle ${row.original.code}`, () =>
          setDialog({ kind: 'nozzle', nozzle: row.original }),
        ),
    },
  ];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="Nozzle Management"
        subtitle="Dispensers and the nozzles on them, with the fuel and tank each one draws from."
      />
      <TabbedPanel
        label="Nozzle management"
        tabs={[
          {
            value: 'dispensers',
            label: 'Dispensers',
            content: (
              <Panel
                query={dispensers}
                caption="Dispensers"
                columns={dispenserColumns}
                getRowId={(d) => d.id}
                addLabel={canManage ? 'Add dispenser' : undefined}
                onAdd={() => setDialog({ kind: 'add-dispenser' })}
                emptyTitle="No dispensers yet"
              />
            ),
          },
          {
            value: 'nozzles',
            label: 'Nozzles',
            content: (
              <Panel
                query={nozzles}
                caption="Nozzles"
                columns={nozzleColumns}
                getRowId={(n) => n.id}
                addLabel={canManage ? 'Add nozzle' : undefined}
                onAdd={() => setDialog({ kind: 'add-nozzle' })}
                emptyTitle="No nozzles yet"
              />
            ),
          },
        ]}
      />
      {dialog?.kind === 'add-dispenser' && <AddDispenserDialog onClose={close} />}
      {dialog?.kind === 'add-nozzle' && <AddNozzleDialog onClose={close} />}
      {dialog?.kind === 'nozzle' && <NozzleStatusDialog nozzle={dialog.nozzle} onClose={close} />}
      {dialog?.kind === 'dispenser' && (
        <DispenserToggle dispenser={dialog.dispenser} onClose={close} />
      )}
    </div>
  );
}

function DispenserToggle({ dispenser, onClose }: { dispenser: Dispenser; onClose: () => void }) {
  const toast = useToast();
  const change = useDispenserStatus(dispenser.id);
  const next = dispenser.status === 'active' ? 'inactive' : 'active';
  return (
    <ReasonDialog
      title="Change status"
      description={`Dispenser ${dispenser.code}`}
      label={`Reason to mark ${next}`}
      submitLabel={`Mark ${next}`}
      tone={next === 'inactive' ? 'danger' : 'primary'}
      onConfirm={async (reason) => {
        await change.mutateAsync({ status: next, reason });
        toast.success(`Dispenser ${dispenser.code} marked ${next}.`);
      }}
      onClose={onClose}
    />
  );
}
