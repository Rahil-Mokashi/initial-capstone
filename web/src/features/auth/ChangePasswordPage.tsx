import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import { useAuth } from '@/auth/AuthContext';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';

const schema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password.'),
    new_password: z.string().min(1, 'Choose a new password.'),
    confirm: z.string().min(1, 'Type the new password again.'),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ['confirm'],
    message: 'The two passwords do not match.',
  });
type Values = z.infer<typeof schema>;

/** Shown full-screen until done, like the Qt forced-change dialog. The server also blocks every other call. */
export function ChangePasswordPage() {
  const { logout, refreshUser } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async ({ current_password, new_password }) => {
    setFormError(null);
    try {
      await api.post('/auth/change-password', { current_password, new_password });
      await refreshUser();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Could not change the password.');
    }
  });

  return (
    <main className="flex min-h-full items-center justify-center p-6">
      <form onSubmit={onSubmit} noValidate className="flex w-full max-w-sm flex-col gap-5">
        <div>
          <h1 className="text-2xl font-bold">Choose a new password</h1>
          <p className="mt-1 text-sm text-muted">
            You must change your password before you can continue. Use at least 8 characters with
            upper and lower case, a number and a symbol.
          </p>
        </div>
        {formError && (
          <p
            role="alert"
            className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
          >
            {formError}
          </p>
        )}
        <TextField
          label="Current password"
          type="password"
          autoComplete="current-password"
          autoFocus
          error={errors.current_password?.message}
          {...register('current_password')}
        />
        <TextField
          label="New password"
          type="password"
          autoComplete="new-password"
          error={errors.new_password?.message}
          {...register('new_password')}
        />
        <TextField
          label="New password again"
          type="password"
          autoComplete="new-password"
          error={errors.confirm?.message}
          {...register('confirm')}
        />
        <Button type="submit" variant="primary" loading={isSubmitting}>
          Save new password
        </Button>
        <Button variant="ghost" onClick={() => void logout()}>
          Log out instead
        </Button>
      </form>
    </main>
  );
}
