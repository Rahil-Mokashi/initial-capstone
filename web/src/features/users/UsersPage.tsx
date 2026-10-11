import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router-dom';
import { z } from 'zod';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { P } from '@/lib/permissions';
import { useCreateUser, useRoles, useUsers, type UserRecord } from './queries';

export function statusTone(status: string) {
  return status === 'Active' ? 'ok' : status === 'Locked' ? 'danger' : 'warn';
}

const FIELDS = ['username', 'email', 'first_name', 'last_name', 'password', 'role_id'] as const;

// Only "is it filled in" here; username/email/password rules live in the backend and arrive as field errors.
const schema = z.object({
  username: z.string().trim().min(1, 'Enter a username.'),
  email: z.string().trim().min(1, 'Enter an email address.'),
  first_name: z.string(),
  last_name: z.string(),
  password: z.string().min(1, 'Enter a password.'),
  role_id: z.string().min(1, 'Choose a role.'),
});
type Values = z.infer<typeof schema>;

function AddUserDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const roles = useRoles();
  const create = useCreateUser();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      username: '',
      email: '',
      first_name: '',
      last_name: '',
      password: '',
      role_id: '',
    },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({
        username: v.username,
        email: v.email,
        password: v.password,
        role_id: v.role_id,
        first_name: v.first_name.trim() || undefined,
        last_name: v.last_name.trim() || undefined,
      });
      toast.success(`User ${v.username.trim()} added.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, FIELDS));
    }
  });
  return (
    <FormDialog
      title="Add user"
      submitLabel="Save"
      busy={create.isPending}
      error={formError ?? (roles.isError ? 'Could not load the roles.' : null)}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Username"
        autoFocus
        error={errors.username?.message}
        {...register('username')}
      />
      <TextField label="Email" error={errors.email?.message} {...register('email')} />
      <TextField label="First name" optional {...register('first_name')} />
      <TextField label="Last name" optional {...register('last_name')} />
      <TextField
        label="Password"
        type="password"
        autoComplete="new-password"
        hint="At least 8 characters with upper case, lower case and a digit."
        error={errors.password?.message}
        {...register('password')}
      />
      <SelectField label="Role" error={errors.role_id?.message} {...register('role_id')}>
        <option value="">Choose a role</option>
        {roles.data?.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </SelectField>
    </FormDialog>
  );
}

export function UsersPage() {
  const { can } = useAuth();
  const users = useUsers();
  const [adding, setAdding] = useState(false);

  const columns: ColumnDef<UserRecord>[] = [
    {
      accessorKey: 'username',
      header: 'Username',
      cell: ({ row }) => (
        <Link
          className="font-semibold underline-offset-4 hover:underline"
          to={`/users/${row.original.id}`}
        >
          {row.original.username}
        </Link>
      ),
    },
    { accessorKey: 'email', header: 'Email' },
    { accessorKey: 'role', header: 'Role', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => (
        <StatusBadge tone={statusTone(getValue<string>())}>{getValue<string>()}</StatusBadge>
      ),
    },
    {
      id: 'open',
      header: () => <span className="sr-only">Open</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <Link
          to={`/users/${row.original.id}`}
          aria-label={`Open ${row.original.username}`}
          className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2"
        >
          <Pencil className="size-4" aria-hidden />
        </Link>
      ),
    },
  ];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader title="Users" subtitle="Sign-in accounts and their roles.">
        {can(P.USER_MANAGE) && (
          <Button variant="primary" onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden /> Add user
          </Button>
        )}
      </PageHeader>
      {users.isLoading ? (
        <LoadingBlock label="Loading users" rows={4} />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => void users.refetch()} />
      ) : (
        <DataTable
          caption="All users"
          columns={columns}
          data={users.data ?? []}
          getRowId={(u) => u.id}
          empty={<EmptyState title="No users yet" />}
        />
      )}
      {adding && <AddUserDialog onClose={() => setAdding(false)} />}
    </div>
  );
}
