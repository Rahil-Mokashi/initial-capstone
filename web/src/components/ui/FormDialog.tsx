import type { FormEventHandler, ReactNode } from 'react';
import { enterToAdvance } from '@/lib/enterToAdvance';
import { Button } from './Button';
import { Dialog } from './Dialog';

export function FormError({ message }: { message: string | null }) {
  return message ? (
    <p
      role="alert"
      className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
    >
      {message}
    </p>
  ) : null;
}

interface Props {
  title: string;
  description?: string;
  submitLabel: string;
  busy?: boolean;
  error?: string | null;
  /** 'danger' for destructive confirmations. */
  tone?: 'primary' | 'danger';
  onSubmit: FormEventHandler<HTMLFormElement>;
  onClose: () => void;
  children: ReactNode;
}

/**
 * The standard data-entry dialog: labelled modal, Enter moves to the next field and the last Enter
 * saves, Esc/Cancel close it, a failure is shown inside it and what was typed is kept.
 * Mount it only while it is open (one dialog state value per page, so two can never stack).
 */
export function FormDialog({
  title,
  description,
  submitLabel,
  busy = false,
  error = null,
  tone = 'primary',
  onSubmit,
  onClose,
  children,
}: Props) {
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={title}
      description={description}
    >
      <form
        onSubmit={onSubmit}
        onKeyDown={enterToAdvance}
        noValidate
        className="flex flex-col gap-4"
      >
        <FormError message={error} />
        {children}
        <div className="mt-2 flex justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={tone === 'danger' ? 'danger' : 'primary'} loading={busy}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
