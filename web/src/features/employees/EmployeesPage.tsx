import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Pencil, Plus } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router-dom';
import { z } from 'zod';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { SearchBox } from '@/components/ui/SearchBox';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { Button } from '@/components/ui/Button';
import { applyApiError } from '@/lib/formErrors';
import { formatDate, titleCase, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';
import {
  EMPLOYEE_STATUSES,
  useChangeStatus,
  useCreateEmployee,
  useEmployeeList,
  type EmployeeRecord,
  type EmployeeStatus,
} from './queries';

const FIELDS = [
  'first_name',
  'last_name',
  'contact_number',
  'email',
  'designation',
  'department',
  'assigned_outlet',
  'joining_date',
  'emergency_contact_name',
  'emergency_contact_phone',
] as const;

// Only "is it filled in" is checked here; the real rules (phone shape, e-mail, names) live in the backend.
const addSchema = z.object({
  first_name: z.string().trim().min(1, 'Enter the first name.'),
  last_name: z.string().trim().min(1, 'Enter the last name.'),
  contact_number: z.string().trim().min(1, 'Enter a contact number.'),
  email: z.string(),
  designation: z.string(),
  department: z.string(),
  assigned_outlet: z.string(),
  joining_date: z.string().min(1, 'Pick the joining date.'),
  emergency_contact_name: z.string(),
  emergency_contact_phone: z.string(),
});
type AddValues = z.infer<typeof addSchema>;

const blankToUndefined = (s: string) => (s.trim() === '' ? undefined : s.trim());

function AddEmployeeDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const create = useCreateEmployee();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<AddValues>({
    resolver: zodResolver(addSchema),
    defaultValues: {
      first_name: '',
      last_name: '',
      contact_number: '',
      email: '',
      designation: '',
      department: '',
      assigned_outlet: 'Main Outlet', // same default as the Qt form
      joining_date: todayIso(),
      emergency_contact_name: '',
      emergency_contact_phone: '',
    },
  });

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({
        first_name: v.first_name.trim(),
        last_name: v.last_name.trim(),
        contact_number: v.contact_number.trim(),
        joining_date: v.joining_date,
        email: blankToUndefined(v.email),
        designation: blankToUndefined(v.designation),
        department: blankToUndefined(v.department),
        assigned_outlet: blankToUndefined(v.assigned_outlet),
        emergency_contact_name: blankToUndefined(v.emergency_contact_name),
        emergency_contact_phone: blankToUndefined(v.emergency_contact_phone),
      });
      toast.success(`${v.first_name.trim()} ${v.last_name.trim()} added.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, FIELDS));
    }
  });

  return (
    <FormDialog
      title="Add employee"
      submitLabel="Save"
      busy={create.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="First name"
          autoFocus
          error={errors.first_name?.message}
          {...register('first_name')}
        />
        <TextField label="Last name" error={errors.last_name?.message} {...register('last_name')} />
        <TextField
          label="Contact number"
          placeholder="e.g. +91 9876543210"
          error={errors.contact_number?.message}
          {...register('contact_number')}
        />
        <TextField label="Email" optional error={errors.email?.message} {...register('email')} />
        <TextField label="Designation" optional {...register('designation')} />
        <TextField label="Department" optional {...register('department')} />
        <TextField label="Assigned outlet" optional {...register('assigned_outlet')} />
        <TextField
          label="Joining date"
          type="date"
          error={errors.joining_date?.message}
          {...register('joining_date')}
        />
        <TextField
          label="Emergency contact name"
          optional
          {...register('emergency_contact_name')}
        />
        <TextField
          label="Emergency contact phone"
          optional
          error={errors.emergency_contact_phone?.message}
          {...register('emergency_contact_phone')}
        />
      </div>
    </FormDialog>
  );
}

export function EmployeesPage() {
  const { can } = useAuth();
  const canManage = can(P.EMPLOYEE_MANAGE);
  const employees = useEmployeeList();
  const changeStatus = useChangeStatus();
  const [search, setSearch] = useState('');
  // ONE state value for "which dialog is open", so two can never stack.
  const [dialog, setDialog] = useState<
    { kind: 'add' } | { kind: 'status'; employee: EmployeeRecord; status: EmployeeStatus } | null
  >(null);
  const close = () => setDialog(null);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (employees.data ?? []).filter(
      (e) =>
        e.employee_code.toLowerCase().includes(q) ||
        `${e.first_name} ${e.last_name}`.toLowerCase().includes(q),
    );
  }, [employees.data, search]);

  const columns: ColumnDef<EmployeeRecord>[] = [
    {
      accessorKey: 'employee_code',
      header: 'Code',
      cell: ({ row }) => (
        <Link
          className="font-semibold underline-offset-4 hover:underline"
          to={`/employees/${row.original.id}`}
        >
          {row.original.employee_code}
        </Link>
      ),
    },
    {
      id: 'name',
      header: 'Name',
      accessorFn: (e) => `${e.first_name} ${e.last_name}`,
    },
    { accessorKey: 'designation', header: 'Designation', cell: ({ getValue }) => getValue() ?? '' },
    { accessorKey: 'department', header: 'Department', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const e = row.original;
        return (
          // Controlled by the server's value: cancelling the reason box leaves it unchanged.
          <select
            aria-label={`Status of ${e.first_name} ${e.last_name}`}
            value={e.status}
            disabled={!canManage || changeStatus.isPending}
            onChange={(ev) =>
              setDialog({ kind: 'status', employee: e, status: ev.target.value as EmployeeStatus })
            }
            className="min-h-[36px] rounded-md border border-line-strong bg-surface px-2 text-sm disabled:opacity-60"
          >
            {EMPLOYEE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
        );
      },
    },
    {
      accessorKey: 'joining_date',
      header: 'Joining date',
      cell: ({ getValue }) => formatDate(getValue<string>()),
    },
    {
      id: 'open',
      header: () => <span className="sr-only">Open</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <Link
          to={`/employees/${row.original.id}`}
          aria-label={`Open ${row.original.first_name} ${row.original.last_name}`}
          className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2"
        >
          <Pencil className="size-4" aria-hidden />
        </Link>
      ),
    },
  ];

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <PageHeader
        title="Employees"
        subtitle="Staff records. Open one to edit it or manage documents."
      >
        <SearchBox
          value={search}
          onChange={setSearch}
          label="Search employees"
          placeholder="Search by name or employee code..."
        />
        {canManage && (
          <Button variant="primary" onClick={() => setDialog({ kind: 'add' })}>
            <Plus className="size-4" aria-hidden /> Add employee
          </Button>
        )}
      </PageHeader>

      {employees.isLoading ? (
        <LoadingBlock label="Loading employees" rows={5} />
      ) : employees.isError ? (
        <ErrorState error={employees.error} onRetry={() => void employees.refetch()} />
      ) : (
        <DataTable
          caption="All employees"
          columns={columns}
          data={rows}
          getRowId={(e) => e.id}
          empty={
            <EmptyState title={search ? 'No employee matches' : 'No employees yet'}>
              {search
                ? 'Try a different name or code.'
                : canManage
                  ? 'Add the first employee to get started.'
                  : 'A manager needs to add the employees first.'}
            </EmptyState>
          }
        />
      )}

      {dialog?.kind === 'add' && <AddEmployeeDialog onClose={close} />}
      {dialog?.kind === 'status' && (
        <ReasonDialog
          title="Change status"
          description={`${dialog.employee.first_name} ${dialog.employee.last_name}: ${titleCase(dialog.employee.status)} to ${titleCase(dialog.status)}`}
          label="Reason for status change"
          submitLabel="Change status"
          onConfirm={(reason) =>
            changeStatus.mutateAsync({
              id: dialog.employee.id,
              status: dialog.status,
              reason,
            })
          }
          onClose={close}
        />
      )}
    </div>
  );
}
