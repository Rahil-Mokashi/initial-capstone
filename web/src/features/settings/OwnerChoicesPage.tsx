import { useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';

type S = components['schemas'];

// Plain words for the stored values. A choice not listed here shows its stored value.
const WORDS: Record<string, string> = {
  per_bill: 'Round every bill to paise, then add the bills',
  per_total: 'Add the exact amounts, round once at the end',
  on: 'Yes',
  off: 'No',
  warn: 'Warn, and let an owner allow it',
  block: 'Block it',
  classic: 'Classic (a copy of the old report)',
  plus: 'Plus (the old report with checks and extras)',
};

function Choice({ s }: { s: S['PumpSettingOut'] }) {
  const toast = useToast();
  const [value, setValue] = useState(s.value);
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (v: string) => api.put(`/pump-settings/${s.key}`, { value: v }),
    ['pump-settings', 'daily-report', 'checks', 'bank', 'credit'],
  );
  const changed = value !== s.value;
  return (
    <li className="rounded-lg border border-line bg-surface p-4">
      <form
        aria-label={s.label}
        className="flex flex-wrap items-end gap-3"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            await save.mutateAsync(value);
            toast.success(`${s.label} saved.`);
          } catch (err) {
            setError(friendlyMessage(err));
          }
        }}
      >
        {s.choices ? (
          <SelectField label={s.label} value={value} onChange={(e) => setValue(e.target.value)}>
            {s.choices.map((c) => (
              <option key={c} value={c}>
                {WORDS[c] ?? c}
              </option>
            ))}
          </SelectField>
        ) : (
          <TextField
            label={s.label}
            value={value}
            inputMode="decimal"
            onChange={(e) => setValue(e.target.value)}
          />
        )}
        <Button type="submit" variant="primary" disabled={!changed} loading={save.isPending}>
          Save
        </Button>
        {value !== s.default && (
          <span className="pb-3 text-sm text-muted">Standard: {WORDS[s.default] ?? s.default}</span>
        )}
        <p className="w-full text-sm text-muted">
          {s.help} <span className="whitespace-nowrap">(Question {s.question_id})</span>
        </p>
        {error && (
          <p role="alert" className="w-full text-sm font-medium text-danger-fg">
            {error}
          </p>
        )}
      </form>
    </li>
  );
}

/** The decisions the owners have not made yet, each with a safe standard answer and the question it belongs to. */
export function OwnerChoicesPage() {
  const list = useGet<S['PumpSettingOut'][]>(['pump-settings'], '/pump-settings');
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Owner Choices"
        subtitle="Rules the pump owners decide. Each starts at a safe standard answer; every change is written to the audit log."
      />
      {list.isLoading ? (
        <LoadingBlock rows={4} label="Loading the choices" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : (
        <ul className="flex flex-col gap-3" aria-label="Owner choices">
          {(list.data ?? []).map((s) => (
            <Choice key={`${s.key}-${s.value}`} s={s} />
          ))}
        </ul>
      )}
    </div>
  );
}
