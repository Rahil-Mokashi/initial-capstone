import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { ArrowLeft, Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useParams } from 'react-router-dom';
import { z } from 'zod';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { formatDate, formatQuantity, titleCase, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';
import {
  useAssignNozzle,
  useAssignOptions,
  useAssignments,
  useCancelAssignment,
  useCloseShift,
  useCompleteAssignment,
  useMyShift,
  useOpenShift,
  useReopenShift,
  useShift,
  useShifts,
  type Assignment,
  type Shift,
} from './queries';

const tone = (status: string): Tone =>
  status === 'open' || status === 'active'
    ? 'ok'
    : status === 'cancelled'
      ? 'danger'
      : status === 'closed' || status === 'completed'
        ? 'neutral'
        : 'info';
const Status = ({ status }: { status: string }) => (
  <StatusBadge tone={tone(status)}>{titleCase(status)}</StatusBadge>
);

// ------------------------------------------------------------------- list
const LABELS = ['Morning', 'Afternoon', 'Evening', 'Night'];
const openSchema = z.object({
  shift_date: z.string().min(1, 'Pick the date.'),
  shift_label: z.string().trim().min(1, 'Enter the shift name.'),
  notes: z.string(),
});

function OpenShiftDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const open = useOpenShift();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof openSchema>>({
    resolver: zodResolver(openSchema),
    defaultValues: { shift_date: todayIso(), shift_label: LABELS[0], notes: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await open.mutateAsync({
        shift_date: v.shift_date,
        shift_label: v.shift_label.trim(),
        notes: v.notes.trim() || undefined,
      });
      toast.success(`${v.shift_label.trim()} shift opened.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['shift_date', 'shift_label']));
    }
  });
  return (
    <FormDialog
      title="Open shift"
      submitLabel="Open"
      busy={open.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Date"
        type="date"
        error={errors.shift_date?.message}
        {...register('shift_date')}
      />
      <TextField
        label="Shift"
        list="shift-labels"
        error={errors.shift_label?.message}
        {...register('shift_label')}
      />
      <datalist id="shift-labels">
        {LABELS.map((l) => (
          <option key={l} value={l} />
        ))}
      </datalist>
      <TextField label="Notes" optional {...register('notes')} />
    </FormDialog>
  );
}

export function ShiftsPage() {
  const { can } = useAuth();
  const shifts = useShifts();
  const [opening, setOpening] = useState(false);
  const columns: ColumnDef<Shift>[] = [
    {
      accessorKey: 'shift_date',
      header: 'Date',
      cell: ({ row }) => (
        <Link
          className="font-semibold underline-offset-4 hover:underline"
          to={`/shifts/${row.original.id}`}
        >
          {formatDate(row.original.shift_date)}
        </Link>
      ),
    },
    { accessorKey: 'shift_label', header: 'Shift' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <Status status={getValue<string>()} />,
    },
    { accessorKey: 'opened_by', header: 'Opened by', cell: ({ getValue }) => getValue() ?? '' },
    {
      id: 'open',
      header: () => <span className="sr-only">Open</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <Link
          to={`/shifts/${row.original.id}`}
          aria-label={`Open ${row.original.shift_label} shift ${row.original.shift_date}`}
          className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2"
        >
          <Pencil className="size-4" aria-hidden />
        </Link>
      ),
    },
  ];
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader title="Shifts" subtitle="Open and close shifts and assign attendants to nozzles.">
        {can(P.SHIFT_MANAGE) && (
          <Button variant="primary" onClick={() => setOpening(true)}>
            <Plus className="size-4" aria-hidden /> Open shift
          </Button>
        )}
      </PageHeader>
      {shifts.isLoading ? (
        <LoadingBlock label="Loading shifts" rows={4} />
      ) : shifts.isError ? (
        <ErrorState error={shifts.error} onRetry={() => void shifts.refetch()} />
      ) : (
        <DataTable
          caption="Shifts"
          columns={columns}
          data={shifts.data ?? []}
          getRowId={(s) => s.id}
          empty={<EmptyState title="No shifts yet" />}
        />
      )}
      {opening && <OpenShiftDialog onClose={() => setOpening(false)} />}
    </div>
  );
}

// ----------------------------------------------------------------- detail
const assignSchema = z.object({
  employee_id: z.string().min(1, 'Choose an employee.'),
  nozzle_id: z.string().min(1, 'Choose a nozzle.'),
  opening_meter: z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,9}(\.\d{1,3})?$/.test(v))
        ctx.addIssue({ code: 'custom', message: 'Enter the opening meter reading.' });
    }),
});

function AssignDialog({ shiftId, onClose }: { shiftId: string; onClose: () => void }) {
  const toast = useToast();
  const options = useAssignOptions();
  const assign = useAssignNozzle(shiftId);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof assignSchema>>({
    resolver: zodResolver(assignSchema),
    defaultValues: { employee_id: '', nozzle_id: '', opening_meter: '0' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await assign.mutateAsync({
        employee_id: v.employee_id,
        nozzle_id: v.nozzle_id,
        opening_meter: v.opening_meter,
      });
      toast.success('Nozzle assigned.');
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['employee_id', 'nozzle_id', 'opening_meter']));
    }
  });
  const empty =
    options.data && (options.data.employees.length === 0 || options.data.nozzles.length === 0);
  return (
    <FormDialog
      title="Assign nozzle"
      submitLabel="Assign"
      busy={assign.isPending}
      error={formError ?? (empty ? 'No employees or active nozzles available.' : null)}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="Employee"
        error={errors.employee_id?.message}
        {...register('employee_id')}
      >
        <option value="">Choose an employee</option>
        {options.data?.employees.map((e) => (
          <option key={e.id} value={e.id}>
            {e.label}
          </option>
        ))}
      </SelectField>
      <SelectField label="Nozzle" error={errors.nozzle_id?.message} {...register('nozzle_id')}>
        <option value="">Choose a nozzle</option>
        {options.data?.nozzles.map((n) => (
          <option key={n.id} value={n.id}>
            {n.label}
          </option>
        ))}
      </SelectField>
      <DecimalField
        label="Opening meter"
        error={errors.opening_meter?.message}
        {...register('opening_meter')}
      />
    </FormDialog>
  );
}

const meter = z
  .string()
  .trim()
  .superRefine((v, ctx) => {
    if (!/^\d{1,9}(\.\d{1,3})?$/.test(v))
      ctx.addIssue({ code: 'custom', message: 'Enter a number such as 1250.500.' });
  });
const completeSchema = z.object({
  closing_meter: meter,
  testing_volume: meter,
  internal_consumption_volume: meter,
});

function CompleteDialog({ assignment, onClose }: { assignment: Assignment; onClose: () => void }) {
  const toast = useToast();
  const complete = useCompleteAssignment();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof completeSchema>>({
    resolver: zodResolver(completeSchema),
    defaultValues: { closing_meter: '', testing_volume: '0', internal_consumption_volume: '0' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await complete.mutateAsync({ id: assignment.id, body: v });
      toast.success('Assignment completed.');
      onClose();
    } catch (error) {
      setFormError(
        applyApiError(error, setError, [
          'closing_meter',
          'testing_volume',
          'internal_consumption_volume',
        ]),
      );
    }
  });
  return (
    <FormDialog
      title="Complete assignment"
      description={`${assignment.employee ?? ''} on nozzle ${assignment.nozzle ?? ''} - opening meter ${formatQuantity(assignment.opening_meter)}`}
      submitLabel="Complete assignment"
      busy={complete.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <DecimalField
        label="Closing meter reading"
        autoFocus
        error={errors.closing_meter?.message}
        {...register('closing_meter')}
      />
      <DecimalField
        label="Litres tested and poured back into the tank (0 if none)"
        error={errors.testing_volume?.message}
        {...register('testing_volume')}
      />
      <DecimalField
        label="Litres used for the pump's own vehicle or generator (0 if none)"
        error={errors.internal_consumption_volume?.message}
        {...register('internal_consumption_volume')}
      />
    </FormDialog>
  );
}

type Dialog =
  | { kind: 'assign' }
  | { kind: 'complete'; assignment: Assignment }
  | { kind: 'cancel'; assignment: Assignment }
  | { kind: 'close' }
  | { kind: 'reopen' }
  | null;

export function ShiftDetailPage() {
  const { id = '' } = useParams();
  const { can } = useAuth();
  const canManage = can(P.SHIFT_MANAGE);
  const canReopen = can(P.SHIFT_REOPEN);
  const toast = useToast();
  const shift = useShift(id);
  const assignments = useAssignments(id);
  const close = useCloseShift(id);
  const reopen = useReopenShift(id);
  const cancel = useCancelAssignment();
  const [dialog, setDialog] = useState<Dialog>(null);
  const s = shift.data;
  const isOpen = s?.status === 'open';

  const columns: ColumnDef<Assignment>[] = [
    { accessorKey: 'employee', header: 'Employee', cell: ({ getValue }) => getValue() ?? '' },
    { accessorKey: 'nozzle', header: 'Nozzle', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'opening_meter',
      header: 'Opening',
      meta: { numeric: true },
      cell: ({ getValue }) => formatQuantity(getValue<string>()),
    },
    {
      accessorKey: 'closing_meter',
      header: 'Closing',
      meta: { numeric: true },
      cell: ({ getValue }) => {
        const v = getValue<string | null>();
        return v ? formatQuantity(v) : '';
      },
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <Status status={getValue<string>()} />,
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) =>
        row.original.status === 'active' && canManage ? (
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDialog({ kind: 'complete', assignment: row.original })}>
              Complete<span className="sr-only"> assignment for {row.original.employee}</span>
            </Button>
            <Button
              variant="danger"
              onClick={() => setDialog({ kind: 'cancel', assignment: row.original })}
            >
              Cancel<span className="sr-only"> assignment for {row.original.employee}</span>
            </Button>
          </div>
        ) : null,
    },
  ];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <Link
        to="/shifts"
        className="inline-flex min-h-[44px] w-fit items-center gap-1.5 text-sm font-semibold underline-offset-4 hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden /> All shifts
      </Link>
      {shift.isLoading ? (
        <LoadingBlock label="Loading shift" rows={3} />
      ) : shift.isError || !s ? (
        <ErrorState error={shift.error} onRetry={() => void shift.refetch()} />
      ) : (
        <>
          <PageHeader title={`${s.shift_label} shift`} subtitle={formatDate(s.shift_date)}>
            <Status status={s.status} />
          </PageHeader>
          {s.notes && <p className="text-sm text-muted">Notes: {s.notes}</p>}
          <div className="flex flex-wrap gap-3">
            <Button
              variant="primary"
              disabled={!canManage || !isOpen}
              onClick={() => setDialog({ kind: 'assign' })}
            >
              Assign nozzle
            </Button>
            <Button
              variant="danger"
              disabled={!canManage || !isOpen}
              onClick={() => setDialog({ kind: 'close' })}
            >
              Close shift
            </Button>
            <Button
              variant="danger"
              disabled={!canReopen || isOpen}
              onClick={() => setDialog({ kind: 'reopen' })}
            >
              Reopen shift
            </Button>
          </div>
          {assignments.isLoading ? (
            <LoadingBlock label="Loading assignments" rows={3} />
          ) : assignments.isError ? (
            <ErrorState error={assignments.error} onRetry={() => void assignments.refetch()} />
          ) : (
            <DataTable
              caption="Nozzle assignments"
              columns={columns}
              data={assignments.data ?? []}
              getRowId={(a) => a.id}
              empty={<EmptyState title="No nozzles assigned yet" />}
            />
          )}

          {dialog?.kind === 'assign' && (
            <AssignDialog shiftId={id} onClose={() => setDialog(null)} />
          )}
          {dialog?.kind === 'complete' && (
            <CompleteDialog assignment={dialog.assignment} onClose={() => setDialog(null)} />
          )}
          {dialog?.kind === 'cancel' && (
            <ReasonDialog
              title="Cancel assignment"
              description={`${dialog.assignment.employee ?? ''} on nozzle ${dialog.assignment.nozzle ?? ''}`}
              submitLabel="Cancel assignment"
              tone="danger"
              onConfirm={async (reason) => {
                await cancel.mutateAsync({ id: dialog.assignment.id, reason });
                toast.success('Assignment cancelled.');
              }}
              onClose={() => setDialog(null)}
            />
          )}
          {dialog?.kind === 'close' && (
            <ConfirmDialog
              title="Close shift"
              description="Close this shift? Active assignments must be completed or cancelled first."
              submitLabel="Close shift"
              tone="danger"
              onConfirm={async () => {
                await close.mutateAsync(undefined);
                toast.success('Shift closed.');
              }}
              onClose={() => setDialog(null)}
            />
          )}
          {dialog?.kind === 'reopen' && (
            <ReasonDialog
              title="Reopen shift"
              label="Reason for reopening"
              submitLabel="Reopen shift"
              tone="danger"
              onConfirm={async (reason) => {
                await reopen.mutateAsync(reason);
                toast.success('Shift reopened.');
              }}
              onClose={() => setDialog(null)}
            />
          )}
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------- my shift
export function MyShiftPage() {
  const mine = useMyShift();
  const a = mine.data;
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6">
      <PageHeader title="My Shift" subtitle="Your current nozzle assignment." />
      {mine.isLoading ? (
        <LoadingBlock label="Loading your shift" rows={3} />
      ) : mine.isError ? (
        <ErrorState error={mine.error} onRetry={() => void mine.refetch()} />
      ) : !a ? (
        <EmptyState title="No nozzle assigned">
          You&apos;re not currently assigned to a nozzle. Check with your shift supervisor.
        </EmptyState>
      ) : (
        <section
          aria-label="Current assignment"
          className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-6 shadow-card"
        >
          <h2 className="text-lg font-bold">
            {a.shift_label} shift - {formatDate(a.shift_date)}
          </h2>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-base">
            <dt className="text-muted">Nozzle</dt>
            <dd>{a.nozzle ?? '-'}</dd>
            <dt className="text-muted">Fuel type</dt>
            <dd>{a.fuel_type ?? '-'}</dd>
            <dt className="text-muted">Dispenser</dt>
            <dd>{a.dispenser ?? '-'}</dd>
            <dt className="text-muted">Opening meter</dt>
            <dd className="num">{formatQuantity(a.opening_meter)}</dd>
            <dt className="text-muted">Status</dt>
            <dd>
              <Status status={a.status} />
            </dd>
          </dl>
        </section>
      )}
    </div>
  );
}
