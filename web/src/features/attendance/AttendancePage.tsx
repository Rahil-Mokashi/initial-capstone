import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Pencil, Plus } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { useEmployeeList } from '@/features/employees/queries';
import { applyApiError } from '@/lib/formErrors';
import { formatDateTime, titleCase, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Record_ = S['AttendanceOut'];
type ShiftOption = components['schemas']['ShiftOut'];

const STATUSES = ['present', 'absent', 'late', 'half_day', 'leave', 'holiday'] as const;
type Status = (typeof STATUSES)[number];

const tone = (s: string): Tone =>
  s === 'present'
    ? 'ok'
    : s === 'absent'
      ? 'danger'
      : s === 'late' || s === 'half_day'
        ? 'warn'
        : 'info';

const useDay = (date: string) =>
  useGet<Record_[]>(['attendance', 'day', date], `/attendance?date=${date}`);
const useShiftsOn = (date: string) =>
  useGet<ShiftOption[]>(['shifts', 'on', date], `/shifts?date_from=${date}&date_to=${date}`);
const useMark = () =>
  useWrite((b: S['MarkIn']) => api.post<Record_>('/attendance', b), ['attendance']);
const useCorrect = () =>
  useWrite(
    (v: { id: string; body: S['CorrectIn'] }) =>
      api.post<Record_>(`/attendance/${v.id}/correct`, v.body),
    ['attendance'],
  );

const time = (iso: string | null | undefined) =>
  iso ? (formatDateTime(iso).split(',').pop()?.trim() ?? '') : '';

// ----------------------------------------------------------- mark dialog
const markSchema = z.object({
  employee_id: z.string().min(1, 'Choose an employee.'),
  attendance_date: z.string().min(1, 'Pick the date.'),
  status: z.enum(STATUSES),
  shift_id: z.string(),
  overtime: z.string().regex(/^\d{1,4}$/, 'Enter whole minutes, such as 30.'),
});

function MarkDialog({ date, onClose }: { date: string; onClose: () => void }) {
  const toast = useToast();
  const employees = useEmployeeList();
  const mark = useMark();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors },
  } = useForm<z.infer<typeof markSchema>>({
    resolver: zodResolver(markSchema),
    defaultValues: {
      employee_id: '',
      attendance_date: date,
      status: 'present',
      shift_id: '',
      overtime: '0',
    },
  });
  const chosenDate = watch('attendance_date');
  const shifts = useShiftsOn(chosenDate || date);
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    const shift = shifts.data?.find((s) => s.id === v.shift_id);
    try {
      await mark.mutateAsync({
        employee_id: v.employee_id,
        attendance_date: v.attendance_date,
        status: v.status,
        shift_id: v.shift_id || undefined,
        shift_label: shift?.shift_label,
        overtime_minutes: Number(v.overtime),
      });
      toast.success('Attendance marked.');
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['employee_id', 'attendance_date', 'status']));
    }
  });
  return (
    <FormDialog
      title="Mark attendance"
      submitLabel="Save"
      busy={mark.isPending}
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
      <TextField
        label="Date"
        type="date"
        error={errors.attendance_date?.message}
        {...register('attendance_date')}
      />
      <SelectField label="Status" {...register('status')}>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </SelectField>
      <SelectField label="Shift" {...register('shift_id')}>
        <option value="">No shift</option>
        {shifts.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {s.shift_label}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Overtime (min)"
        inputMode="numeric"
        error={errors.overtime?.message}
        {...register('overtime')}
      />
    </FormDialog>
  );
}

// ------------------------------------------------------ correction dialog
const correctSchema = z.object({
  status: z.enum(STATUSES),
  shift_id: z.string(),
  overtime: z.string().regex(/^\d{1,4}$/, 'Enter whole minutes, such as 30.'),
  reason: z.string(),
});

function CorrectDialog({
  record,
  canManage,
  onClose,
}: {
  record: Record_;
  canManage: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const correct = useCorrect();
  const shifts = useShiftsOn(record.attendance_date);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof correctSchema>>({
    resolver: zodResolver(correctSchema),
    defaultValues: {
      status: record.status as Status,
      shift_id: record.shift_id ?? '',
      overtime: String(record.overtime_minutes),
      reason: '',
    },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await correct.mutateAsync({
        id: record.id,
        body: {
          status: v.status,
          shift_id: v.shift_id || undefined,
          overtime_minutes: Number(v.overtime),
          reason: v.reason.trim(),
        },
      });
      toast.success('Correction saved.');
      onClose();
    } catch (error) {
      setFormError(friendlyMessage(error));
    }
  });
  return (
    <FormDialog
      title="Attendance detail"
      description={`${record.employee ?? ''} - ${record.attendance_date}`}
      submitLabel="Save correction"
      busy={correct.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField label="Status" disabled={!canManage} {...register('status')}>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </SelectField>
      <SelectField label="Shift" disabled={!canManage} {...register('shift_id')}>
        <option value="">No shift</option>
        {shifts.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {s.shift_label}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Overtime (min)"
        inputMode="numeric"
        disabled={!canManage}
        error={errors.overtime?.message}
        {...register('overtime')}
      />
      <TextField label="Correction reason" optional disabled={!canManage} {...register('reason')} />
    </FormDialog>
  );
}

// ------------------------------------------------------------------- page
interface Row {
  employee_id: string;
  name: string;
  record?: Record_;
}

type Dialog = { kind: 'mark' } | { kind: 'correct'; record: Record_ } | null;

export function AttendancePage() {
  const { can } = useAuth();
  const canManage = can(P.ATTENDANCE_MANAGE);
  const [date, setDate] = useState(todayIso());
  const employees = useEmployeeList();
  const day = useDay(date);
  const mark = useMark();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  // The roster is every ACTIVE employee, marked or not, so Present / Absent can be one click per row.
  const rows = useMemo<Row[]>(() => {
    const byEmployee = new Map((day.data ?? []).map((r) => [r.employee_id, r]));
    return (employees.data ?? [])
      .filter((e) => e.status === 'active')
      .sort((a, b) =>
        `${a.first_name} ${a.last_name}`.localeCompare(`${b.first_name} ${b.last_name}`),
      )
      .map((e) => ({
        employee_id: e.id,
        name: `${e.first_name} ${e.last_name}`,
        record: byEmployee.get(e.id),
      }));
  }, [employees.data, day.data]);

  async function quick(employee_id: string, status: 'present' | 'absent') {
    setRowError(null);
    try {
      await mark.mutateAsync({ employee_id, attendance_date: date, status, overtime_minutes: 0 });
    } catch (e) {
      setRowError(friendlyMessage(e));
    }
  }

  const columns: ColumnDef<Row>[] = [
    { accessorKey: 'name', header: 'Employee' },
    {
      id: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const { record, employee_id, name } = row.original;
        if (record)
          return <StatusBadge tone={tone(record.status)}>{titleCase(record.status)}</StatusBadge>;
        if (!canManage) return <span className="text-muted">Not marked</span>;
        return (
          <div className="flex gap-2">
            <Button
              variant="primary"
              onClick={() => void quick(employee_id, 'present')}
              aria-label={`Mark ${name} present`}
            >
              Present
            </Button>
            <Button
              onClick={() => void quick(employee_id, 'absent')}
              aria-label={`Mark ${name} absent`}
            >
              Absent
            </Button>
          </div>
        );
      },
    },
    { id: 'in', header: 'Check in', cell: ({ row }) => time(row.original.record?.check_in_time) },
    {
      id: 'out',
      header: 'Check out',
      cell: ({ row }) => time(row.original.record?.check_out_time),
    },
    {
      id: 'ot',
      header: 'Overtime (min)',
      meta: { numeric: true },
      cell: ({ row }) => (row.original.record ? row.original.record.overtime_minutes : ''),
    },
    {
      id: 'corrected',
      header: 'Corrected',
      cell: ({ row }) => (row.original.record?.corrected_at ? 'Yes' : ''),
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) =>
        row.original.record && canManage ? (
          <button
            type="button"
            aria-label={`Correct attendance of ${row.original.name}`}
            onClick={() => setDialog({ kind: 'correct', record: row.original.record! })}
            className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2"
          >
            <Pencil className="size-4" aria-hidden />
          </button>
        ) : null,
    },
  ];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Attendance"
        subtitle="Pick a day, then mark who is in. Mistakes are corrected, never deleted."
      >
        <div className="w-44">
          <TextField
            label="Date"
            type="date"
            value={date}
            onChange={(e) => e.target.value && setDate(e.target.value)}
          />
        </div>
        {canManage && (
          <Button variant="primary" onClick={() => setDialog({ kind: 'mark' })}>
            <Plus className="size-4" aria-hidden /> Mark attendance
          </Button>
        )}
      </PageHeader>
      {rowError && (
        <p
          role="alert"
          className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
        >
          {rowError}
        </p>
      )}
      {employees.isLoading || day.isLoading ? (
        <LoadingBlock label="Loading attendance" rows={5} />
      ) : employees.isError || day.isError ? (
        <ErrorState
          error={employees.error ?? day.error}
          onRetry={() => {
            void employees.refetch();
            void day.refetch();
          }}
        />
      ) : (
        <DataTable
          caption={`Attendance for ${date}`}
          columns={columns}
          data={rows}
          getRowId={(r) => r.employee_id}
          empty={<p className="text-sm text-muted">There are no active employees.</p>}
        />
      )}
      {dialog?.kind === 'mark' && <MarkDialog date={date} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'correct' && (
        <CorrectDialog
          record={dialog.record}
          canManage={canManage}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
