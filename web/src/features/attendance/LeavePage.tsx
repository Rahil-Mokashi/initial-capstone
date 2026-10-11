import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
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
import { useToast } from '@/components/ui/Toast';
import { useEmployeeList } from '@/features/employees/queries';
import { applyApiError } from '@/lib/formErrors';
import { formatDate, titleCase, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Leave = S['LeaveOut'];

const useLeave = () => useGet<Leave[]>(['leave', 'list'], '/leave');
const useRequest = () =>
  useWrite((b: S['LeaveRequestIn']) => api.post<Leave>('/leave', b), ['leave', 'attendance']);
const useDecide = () =>
  useWrite(
    (v: { id: string; action: 'approve' | 'reject' | 'cancel'; body: unknown }) =>
      api.post<Leave>(`/leave/${v.id}/${v.action}`, v.body),
    // Approving writes the leave days into attendance.
    ['leave', 'attendance'],
  );

const tone = (s: string): Tone =>
  s === 'approved' ? 'ok' : s === 'rejected' ? 'danger' : s === 'cancelled' ? 'neutral' : 'warn';

const requestSchema = z
  .object({
    employee_id: z.string().min(1, 'Choose an employee.'),
    date_from: z.string().min(1, 'Pick the first day.'),
    date_to: z.string().min(1, 'Pick the last day.'),
    reason: z.string(),
  })
  .refine((v) => !v.date_from || !v.date_to || v.date_from <= v.date_to, {
    path: ['date_to'],
    message: 'The last day cannot be before the first day.',
  });

function RequestDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const employees = useEmployeeList();
  const request = useRequest();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof requestSchema>>({
    resolver: zodResolver(requestSchema),
    defaultValues: { employee_id: '', date_from: todayIso(), date_to: todayIso(), reason: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await request.mutateAsync({ ...v, reason: v.reason.trim() });
      toast.success('Leave requested.');
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['employee_id', 'date_from', 'date_to']));
    }
  });
  return (
    <FormDialog
      title="Request leave"
      submitLabel="Request leave"
      busy={request.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="Employee"
        error={errors.employee_id?.message}
        {...register('employee_id')}
      >
        <option value="">Choose an employee</option>
        {employees.data?.map((e) => (
          <option key={e.id} value={e.id}>
            {e.employee_code} - {e.first_name} {e.last_name}
          </option>
        ))}
      </SelectField>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="From"
          type="date"
          error={errors.date_from?.message}
          {...register('date_from')}
        />
        <TextField
          label="To"
          type="date"
          error={errors.date_to?.message}
          {...register('date_to')}
        />
      </div>
      <TextField label="Reason" optional {...register('reason')} />
    </FormDialog>
  );
}

type Dialog = { kind: 'request' } | { kind: 'approve' | 'reject' | 'cancel'; leave: Leave } | null;

export function LeavePage() {
  const { can } = useAuth();
  const canManage = can(P.LEAVE_MANAGE);
  const canApprove = can(P.LEAVE_APPROVE);
  const toast = useToast();
  const leave = useLeave();
  const decide = useDecide();
  const [dialog, setDialog] = useState<Dialog>(null);

  const columns: ColumnDef<Leave>[] = [
    { accessorKey: 'employee', header: 'Employee', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'date_from',
      header: 'From',
      cell: ({ getValue }) => formatDate(getValue<string>()),
    },
    {
      accessorKey: 'date_to',
      header: 'To',
      cell: ({ getValue }) => formatDate(getValue<string>()),
    },
    { accessorKey: 'reason', header: 'Reason' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => (
        <StatusBadge tone={tone(getValue<string>())}>{titleCase(getValue<string>())}</StatusBadge>
      ),
    },
    { accessorKey: 'decided_by', header: 'Decided by', cell: ({ getValue }) => getValue() ?? '' },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const l = row.original;
        // Only a pending request can still be decided; the other states are final.
        if (l.status !== 'pending') return null;
        return (
          <div className="flex justify-end gap-2">
            {canApprove && (
              <>
                <Button
                  aria-label={`Approve leave of ${l.employee}`}
                  onClick={() => setDialog({ kind: 'approve', leave: l })}
                >
                  Approve
                </Button>
                <Button
                  variant="danger"
                  aria-label={`Reject leave of ${l.employee}`}
                  onClick={() => setDialog({ kind: 'reject', leave: l })}
                >
                  Reject
                </Button>
              </>
            )}
            {canManage && (
              <Button
                aria-label={`Cancel leave of ${l.employee}`}
                onClick={() => setDialog({ kind: 'cancel', leave: l })}
              >
                Cancel
              </Button>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Leave"
        subtitle="Request, approve, reject or cancel leave. Approved days are written to attendance."
      >
        {canManage && (
          <Button variant="primary" onClick={() => setDialog({ kind: 'request' })}>
            <Plus className="size-4" aria-hidden /> Request leave
          </Button>
        )}
      </PageHeader>
      {leave.isLoading ? (
        <LoadingBlock label="Loading leave requests" rows={4} />
      ) : leave.isError ? (
        <ErrorState error={leave.error} onRetry={() => void leave.refetch()} />
      ) : (
        <DataTable
          caption="Leave requests"
          columns={columns}
          data={leave.data ?? []}
          getRowId={(l) => l.id}
          empty={<EmptyState title="No leave requests yet" />}
        />
      )}
      {dialog?.kind === 'request' && <RequestDialog onClose={() => setDialog(null)} />}
      {dialog && dialog.kind !== 'request' && (
        <ReasonDialog
          title={
            dialog.kind === 'approve'
              ? 'Approve leave'
              : dialog.kind === 'reject'
                ? 'Reject leave'
                : 'Cancel leave request'
          }
          description={`${dialog.leave.employee ?? ''}: ${formatDate(dialog.leave.date_from)} to ${formatDate(dialog.leave.date_to)}`}
          label={dialog.kind === 'approve' ? 'Remarks' : 'Reason'}
          submitLabel={titleCase(dialog.kind)}
          tone={dialog.kind === 'approve' ? 'primary' : 'danger'}
          onConfirm={async (text) => {
            await decide.mutateAsync({
              id: dialog.leave.id,
              action: dialog.kind,
              body: dialog.kind === 'approve' ? { remarks: text } : { reason: text },
            });
            toast.success(
              `Leave ${dialog.kind === 'approve' ? 'approved' : dialog.kind === 'reject' ? 'rejected' : 'cancelled'}.`,
            );
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
