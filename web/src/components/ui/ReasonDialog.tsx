import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { friendlyMessage } from '@/api/errors';
import { TextField } from './Field';
import { FormDialog } from './FormDialog';

const schema = z.object({ reason: z.string().trim().min(1, 'Give a reason.') });

interface Props {
  title: string;
  description?: string;
  /** Label of the reason box, for example "Reason for status change". */
  label?: string;
  submitLabel: string;
  tone?: 'primary' | 'danger';
  /** Do the action. Throw to keep the dialog open and show the message. */
  onConfirm: (reason: string) => Promise<unknown>;
  onClose: () => void;
}

/**
 * "Are you sure, and why?" - the confirmation the Qt screens build from a confirm box plus a reason prompt
 * (status changes, exits, removals, cancellations). One dialog, one required reason, errors shown inside.
 */
export function ReasonDialog({
  title,
  description,
  label = 'Reason',
  submitLabel,
  tone = 'primary',
  onConfirm,
  onClose,
}: Props) {
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { reason: '' },
  });

  const submit = handleSubmit(async ({ reason }) => {
    setError(null);
    try {
      await onConfirm(reason.trim());
      onClose();
    } catch (e) {
      setError(friendlyMessage(e));
    }
  });

  return (
    <FormDialog
      title={title}
      description={description}
      submitLabel={submitLabel}
      tone={tone}
      busy={isSubmitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField label={label} autoFocus error={errors.reason?.message} {...register('reason')} />
    </FormDialog>
  );
}
