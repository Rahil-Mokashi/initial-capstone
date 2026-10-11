import { useState } from 'react';
import { friendlyMessage } from '@/api/errors';
import { FormDialog } from './FormDialog';

/** "Are you sure?" with no extra input (closing a shift, voiding something). Errors stay inside it. */
export function ConfirmDialog({
  title,
  description,
  submitLabel,
  tone = 'primary',
  onConfirm,
  onClose,
}: {
  title: string;
  description: string;
  submitLabel: string;
  tone?: 'primary' | 'danger';
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <FormDialog
      title={title}
      description={description}
      submitLabel={submitLabel}
      tone={tone}
      busy={busy}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await onConfirm();
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        } finally {
          setBusy(false);
        }
      }}
      onClose={onClose}
    >
      {null}
    </FormDialog>
  );
}
