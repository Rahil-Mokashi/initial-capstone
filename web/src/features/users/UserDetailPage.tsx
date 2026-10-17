import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowLeft, KeyRound, ShieldCheck, Unlock } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useParams } from 'react-router-dom';
import { z } from 'zod';
import { friendlyMessage } from '@/api/errors';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import {
  useChangeRole,
  useResetCode,
  useResetPassword,
  useRoles,
  useSetActive,
  useUnlock,
  useUsers,
  type UserRecord,
} from './queries';
import { statusTone } from './UsersPage';

type Dialog =
  | { kind: 'role' }
  | { kind: 'active' }
  | { kind: 'unlock' }
  | { kind: 'password' }
  | { kind: 'code' }
  | { kind: 'code-shown'; code: string }
  | null;

const passwordSchema = z.object({
  password: z.string().min(1, 'Enter a temporary password.'),
  reason: z.string(),
});

function ResetPasswordDialog({ user, onClose }: { user: UserRecord; onClose: () => void }) {
  const toast = useToast();
  const reset = useResetPassword(user.id);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { password: '', reason: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await reset.mutateAsync({ new_password: v.password, reason: v.reason.trim() });
      toast.success('Password reset. They will be asked to set their own on next sign-in.');
      onClose();
    } catch (error) {
      setFormError(friendlyMessage(error));
    }
  });
  return (
    <FormDialog
      title="Reset password"
      description={`Set a temporary password for ${user.username}.`}
      submitLabel="Reset password"
      busy={reset.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="New temporary password"
        hint="At least 8 characters, with a capital letter, a small letter and a number."
        type="password"
        autoComplete="new-password"
        autoFocus
        error={errors.password?.message}
        {...register('password')}
      />
      <TextField label="Reason" optional {...register('reason')} />
    </FormDialog>
  );
}

function CodeShownDialog({
  user,
  code,
  onClose,
}: {
  user: UserRecord;
  code: string;
  onClose: () => void;
}) {
  return (
    <FormDialog
      title="Password reset code"
      description={`One-time code for ${user.username}`}
      submitLabel="Done"
      onSubmit={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClose={onClose}
    >
      <p
        aria-label="Reset code"
        className="num rounded-md border border-line-strong bg-surface-2 p-4 text-center text-2xl font-bold tracking-widest"
      >
        {code}
      </p>
      <p className="text-sm text-muted">
        Give this to them directly (read it aloud, write it down). It is shown only once, works only
        once, and expires soon. They enter it on the sign-in screen&apos;s &quot;Forgot
        password?&quot; link along with a new password of their own choosing.
      </p>
    </FormDialog>
  );
}

function RoleDialog({ user, onClose }: { user: UserRecord; onClose: () => void }) {
  const roles = useRoles();
  const change = useChangeRole(user.id);
  const toast = useToast();
  const [roleId, setRoleId] = useState(user.role_id ?? '');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  return (
    <FormDialog
      title="Change role"
      description={user.username}
      submitLabel="Change role"
      busy={change.isPending}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await change.mutateAsync({ role_id: roleId, reason: reason.trim() });
          toast.success('Role changed.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
      onClose={onClose}
    >
      <SelectField label="Role" value={roleId} onChange={(e) => setRoleId(e.target.value)}>
        {roles.data?.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
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

export function UserDetailPage() {
  const { id = '' } = useParams();
  const users = useUsers();
  const user = users.data?.find((u) => u.id === id);
  const toast = useToast();
  const setActive = useSetActive(id);
  const unlock = useUnlock(id);
  const code = useResetCode(id);
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <Link
        to="/users"
        className="inline-flex min-h-[44px] w-fit items-center gap-1.5 text-sm font-semibold underline-offset-4 hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden /> All users
      </Link>
      {users.isLoading ? (
        <LoadingBlock label="Loading user" rows={3} />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => void users.refetch()} />
      ) : !user ? (
        <ErrorState error={new Error('User not found.')} />
      ) : (
        <>
          <PageHeader title={user.username} subtitle={user.email}>
            <StatusBadge tone={statusTone(user.status)}>{user.status}</StatusBadge>
          </PageHeader>
          <section
            aria-label="Account actions"
            className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 shadow-card"
          >
            <p className="text-sm text-muted">Role: {user.role ?? 'none'}</p>
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => setDialog({ kind: 'role' })}>
                <ShieldCheck className="size-4" aria-hidden /> Change role
              </Button>
              <Button onClick={() => setDialog({ kind: 'active' })}>
                {user.is_active ? 'Deactivate' : 'Activate'}
              </Button>
              <Button
                variant="danger"
                disabled={!user.is_locked}
                onClick={() => setDialog({ kind: 'unlock' })}
              >
                <Unlock className="size-4" aria-hidden /> Unlock account
              </Button>
              <Button onClick={() => setDialog({ kind: 'password' })}>
                <KeyRound className="size-4" aria-hidden /> Reset password
              </Button>
              <Button
                title="For someone who forgot their password and has no one to reset it in person right now. They enter the code themselves on the sign-in screen."
                onClick={() => setDialog({ kind: 'code' })}
              >
                Generate password reset code
              </Button>
            </div>
          </section>

          {dialog?.kind === 'role' && <RoleDialog user={user} onClose={close} />}
          {dialog?.kind === 'active' && (
            <ReasonDialog
              title={user.is_active ? 'Deactivate user' : 'Reactivate user'}
              description={user.username}
              label={user.is_active ? 'Reason to deactivate' : 'Reason to reactivate'}
              submitLabel={user.is_active ? 'Deactivate' : 'Activate'}
              tone={user.is_active ? 'danger' : 'primary'}
              onConfirm={async (reason) => {
                await setActive.mutateAsync({ is_active: !user.is_active, reason });
                toast.success(user.is_active ? 'User deactivated.' : 'User activated.');
              }}
              onClose={close}
            />
          )}
          {dialog?.kind === 'unlock' && (
            <ReasonDialog
              title="Unlock account"
              description={user.username}
              submitLabel="Unlock"
              onConfirm={async (reason) => {
                await unlock.mutateAsync(reason);
                toast.success('Account unlocked.');
              }}
              onClose={close}
            />
          )}
          {dialog?.kind === 'password' && <ResetPasswordDialog user={user} onClose={close} />}
          {dialog?.kind === 'code' && (
            <ReasonDialog
              title="Generate password reset code"
              description={user.username}
              submitLabel="Generate code"
              onConfirm={async (reason) => {
                const result = await code.mutateAsync(reason);
                // Swap to the "shown once" dialog; the code lives only in this state.
                setDialog({ kind: 'code-shown', code: result.code });
              }}
              onClose={() => setDialog((d) => (d?.kind === 'code-shown' ? d : null))}
            />
          )}
          {dialog?.kind === 'code-shown' && (
            <CodeShownDialog user={user} code={dialog.code} onClose={close} />
          )}
        </>
      )}
    </div>
  );
}
