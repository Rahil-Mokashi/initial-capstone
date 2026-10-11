import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useAuth } from '@/auth/AuthContext';
import { TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { useToast } from '@/components/ui/Toast';

const PIN_LENGTH = 6;

const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password.'),
    new_password: z.string().min(1, 'Choose a new password.'),
    confirm: z.string().min(1, 'Type the new password again.'),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ['confirm'],
    message: 'The two passwords do not match.',
  });

/** A voluntary password change from the account menu (the forced first-login one is its own full-screen page). */
export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof passwordSchema>>({ resolver: zodResolver(passwordSchema) });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await api.post('/auth/change-password', {
        current_password: v.current_password,
        new_password: v.new_password,
      });
      toast.success('Password changed.');
      onClose();
    } catch (error) {
      setFormError(friendlyMessage(error));
    }
  });
  return (
    <FormDialog
      title="Change password"
      submitLabel="Save new password"
      busy={isSubmitting}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
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
        hint="At least 8 characters, with upper case, lower case and a digit."
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
    </FormDialog>
  );
}

const pinSchema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password.'),
    pin: z
      .string()
      .regex(new RegExp(`^\\d{${PIN_LENGTH}}$`), `The PIN must be exactly ${PIN_LENGTH} digits.`),
    confirm: z.string().min(1, 'Type the PIN again.'),
  })
  .refine((v) => v.pin === v.confirm, {
    path: ['confirm'],
    message: 'New PIN and confirmation do not match.',
  });

/** Set or change this person's quick sign-in PIN. Needs the current password, like a password change. */
export function SetPinDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const { refreshUser } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof pinSchema>>({ resolver: zodResolver(pinSchema) });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await api.post('/auth/pin', { current_password: v.current_password, pin: v.pin });
      await refreshUser();
      toast.success('Quick sign-in PIN saved.');
      onClose();
    } catch (error) {
      setFormError(friendlyMessage(error));
    }
  });
  const digits = { inputMode: 'numeric' as const, maxLength: PIN_LENGTH, autoComplete: 'off' };
  return (
    <FormDialog
      title="Set a quick sign-in PIN"
      description={`A ${PIN_LENGTH}-digit PIN lets you sign in faster on this device without typing your full password every time. It shares the same account lockout as your password.`}
      submitLabel="Set PIN"
      busy={isSubmitting}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Current password"
        type="password"
        autoComplete="current-password"
        autoFocus
        error={errors.current_password?.message}
        {...register('current_password')}
      />
      <TextField
        label="New PIN"
        type="password"
        placeholder={`${PIN_LENGTH} digits`}
        error={errors.pin?.message}
        {...digits}
        {...register('pin')}
      />
      <TextField
        label="Confirm PIN"
        type="password"
        error={errors.confirm?.message}
        {...digits}
        {...register('confirm')}
      />
    </FormDialog>
  );
}
