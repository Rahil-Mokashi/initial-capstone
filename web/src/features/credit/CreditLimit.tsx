import { useState, type FormEvent } from 'react';
import { friendlyMessage, ApiError } from '@/api/errors';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatMoney } from '@/lib/format';

type S = components['schemas'];
export type CreditOverride = S['CreditOverrideIn'];

/** True when the server refused a credit sale because it would pass the limit and an owner may allow it. */
export function isLimitError(error: unknown): error is ApiError {
  return error instanceof ApiError && (error.code as string) === 'credit_limit_exceeded';
}

/**
 * Shown while a credit bill is being entered: what the customer owes, the limit, and what this bill would
 * make it. Nothing is hidden: a customer who is not approved, or a bill that passes the limit, says so here
 * before the person presses save.
 */
export function CreditLimitPanel({
  customerId,
  amount,
}: {
  customerId: string;
  /** The bill's rupees, two places, or null while it is still being typed. */
  amount: string | null;
}) {
  const enabled = Boolean(customerId && amount);
  const check = useGet<S['LimitCheckOut']>(
    ['credit', 'check', customerId, amount],
    `/credit/check?customer_id=${customerId}&amount=${amount}`,
    enabled,
  );
  if (!enabled) return null;
  const c = check.data;
  if (!c) return null;
  return (
    <section
      aria-label="Credit limit"
      className="flex flex-col gap-1 rounded-md border border-line bg-surface-2 p-3 text-sm"
    >
      <p className="num">
        Owes <strong>{formatMoney(c.outstanding)}</strong>
        {c.credit_limit != null && (
          <>
            {' '}
            of a <strong>{formatMoney(c.credit_limit)}</strong> limit
            {c.available != null && ` (${formatMoney(c.available)} left)`}
          </>
        )}
        . With this bill: <strong>{formatMoney(c.would_become)}</strong>.
      </p>
      {c.problem ? (
        <StatusBadge tone="danger">{c.problem}</StatusBadge>
      ) : c.over_limit ? (
        <StatusBadge tone={c.mode === 'block' ? 'danger' : 'warn'}>
          {c.mode === 'block'
            ? 'Over the limit: credit over the limit is switched off in settings'
            : 'Over the limit: an owner has to allow this bill'}
        </StatusBadge>
      ) : (
        <StatusBadge tone="ok">Within the limit</StatusBadge>
      )}
    </section>
  );
}

/** The owner types their own password (or PIN) to allow one bill past the limit. It is recorded with their name. */
export function OverrideDialog({
  message,
  onConfirm,
  onClose,
}: {
  message: string;
  onConfirm: (override: CreditOverride) => Promise<unknown>;
  onClose: () => void;
}) {
  const approvers = useGet<S['ApproverOut'][]>(['credit', 'approvers'], '/credit/approvers');
  const [v, setV] = useState({ approver: '', credential: '', reason: '' });
  const [pin, setPin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const list = approvers.data ?? [];
  const chosen = v.approver || list[0]?.id || '';

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!chosen) return setError('Choose which owner is allowing this.');
    if (!v.credential) return setError(`Type the owner's ${pin ? 'PIN' : 'password'}.`);
    setBusy(true);
    try {
      await onConfirm({
        approver_id: chosen,
        credential: v.credential,
        use_pin: pin,
        reason: v.reason,
      });
      onClose();
    } catch (err) {
      setError(friendlyMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDialog
      title="An owner must allow this bill"
      description={message}
      submitLabel="Allow this bill"
      busy={busy}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="Owner"
        value={chosen}
        onChange={(e) => setV({ ...v, approver: e.target.value })}
      >
        {list.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </SelectField>
      <TextField
        label={pin ? "Owner's PIN" : "Owner's password"}
        type="password"
        autoComplete="off"
        value={v.credential}
        onChange={(e) => setV({ ...v, credential: e.target.value })}
      />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} /> Use their
        PIN instead
      </label>
      <TextField
        label="Why is this being allowed?"
        optional
        value={v.reason}
        onChange={(e) => setV({ ...v, reason: e.target.value })}
      />
      <p className="text-xs text-muted">
        This is recorded with the owner&apos;s name and your reason. It allows this one bill only;
        the customer&apos;s limit does not change.
      </p>
    </FormDialog>
  );
}
