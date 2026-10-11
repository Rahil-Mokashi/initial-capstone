import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { useToast } from '@/components/ui/Toast';

const schema = z
  .object({
    username: z.string().trim().min(1, 'Enter your username.'),
    code: z.string().trim().min(1, 'Enter the reset code.'),
    new_password: z.string().min(1, 'Choose a new password.'),
    confirm: z.string().min(1, 'Type the new password again.'),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ['confirm'],
    message: 'New password and confirmation do not match.',
  });

/** Finish an administrator-issued one-time reset code. Needs no sign-in (the person cannot sign in). */
export function ForgotPasswordDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await api.post('/auth/forgot-password', {
        username: v.username.trim(),
        code: v.code.trim(),
        new_password: v.new_password,
      });
      toast.success('Password changed. You can sign in with it now.');
      onClose();
    } catch (error) {
      setFormError(friendlyMessage(error));
    }
  });
  return (
    <FormDialog
      title="Reset your password"
      description="Ask the person who manages this computer for a reset code, then enter it below along with a new password. The code only works once and stops working after a short while."
      submitLabel="Reset password"
      busy={isSubmitting}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Username"
        autoFocus
        autoComplete="username"
        error={errors.username?.message}
        {...register('username')}
      />
      <TextField
        label="Reset code"
        autoComplete="one-time-code"
        error={errors.code?.message}
        {...register('code')}
      />
      <TextField
        label="New password"
        type="password"
        autoComplete="new-password"
        hint="At least 8 characters, with upper case, lower case and a digit."
        error={errors.new_password?.message}
        {...register('new_password')}
      />
      <TextField
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        error={errors.confirm?.message}
        {...register('confirm')}
      />
    </FormDialog>
  );
}
