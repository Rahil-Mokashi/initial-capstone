import { useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';
import { FormError } from '@/components/ui/FormDialog';
import { TabbedPanel } from '@/components/ui/TabbedPanel';
import { useToast } from '@/components/ui/Toast';
import { addDaysIso, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';
import { Attention, DaysTable, StatementLines, Suggestions } from './DayTab';
import { ImportTab } from './ImportTab';

type S = components['schemas'];

/** Which payment modes settle into which account is not known yet (H-02), so it is a setting per account. */
function AccountsTab() {
  const toast = useToast();
  const { can } = useAuth();
  const modes = useGet<S['BankModeOut'][]>(['bank', 'modes'], '/bank/modes');
  const accounts = useGet<S['BankAccountOut'][]>(['bank', 'accounts'], '/bank/accounts');
  const [name, setName] = useState('');
  const [mask, setMask] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useWrite((b: S['BankAccountIn']) => api.post('/bank/accounts', b), ['bank']);
  const setModes = useWrite(
    (v: { id: string; modes: string[] }) =>
      api.put(`/bank/accounts/${v.id}/modes`, { modes: v.modes }),
    ['bank'],
  );
  const manage = can(P.BANK_RECON_MANAGE);
  return (
    <section aria-labelledby="acc" className="flex flex-col gap-4">
      <h2 id="acc" className="text-base font-bold">
        Bank accounts and what settles into each
      </h2>
      <p className="text-sm text-muted">
        Tick the payment modes whose money lands in each account. Cash deposits are matched to the
        account whose name is written on the deposit in the cash book. Only the last digits of an
        account number are kept.
      </p>
      <ul className="flex flex-col gap-3">
        {(accounts.data ?? []).map((a) => (
          <li key={a.id} className="rounded-lg border border-line bg-surface p-4">
            <p className="font-semibold">
              {a.name} {a.account_mask && <span className="text-muted">({a.account_mask})</span>}
            </p>
            <div
              role="group"
              aria-label={`Modes for ${a.name}`}
              className="mt-2 flex flex-wrap gap-4"
            >
              {(modes.data ?? []).map((m) => (
                <label key={m.mode} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    disabled={!manage}
                    checked={a.modes.includes(m.mode)}
                    onChange={(e) =>
                      setModes.mutate({
                        id: a.id,
                        modes: e.target.checked
                          ? [...a.modes, m.mode]
                          : a.modes.filter((x) => x !== m.mode),
                      })
                    }
                  />
                  {m.label}
                </label>
              ))}
            </div>
          </li>
        ))}
        {(accounts.data ?? []).length === 0 && (
          <li className="text-sm text-muted">No bank account yet.</li>
        )}
      </ul>
      {manage && (
        <form
          aria-label="Add a bank account"
          className="flex flex-wrap items-end gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await create.mutateAsync({ name, account_mask: mask || null, modes: [] });
              toast.success(`${name} added. Now tick what settles into it.`);
              setName('');
              setMask('');
            } catch (err) {
              setError(friendlyMessage(err));
            }
          }}
        >
          <TextField
            label="Account name"
            placeholder="Bank of India"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <TextField
            label="Last digits"
            optional
            placeholder="XXXX1234"
            value={mask}
            onChange={(e) => setMask(e.target.value)}
          />
          <Button type="submit" variant="primary" loading={create.isPending}>
            Add account
          </Button>
          <FormError message={error} />
        </form>
      )}
    </section>
  );
}

export function BankPage() {
  const { can } = useAuth();
  const toast = useToast();
  const [from, setFrom] = useState(addDaysIso(-7));
  const [to, setTo] = useState(todayIso());
  const run = useWrite(
    () => api.post<S['BankRunOut']>('/bank/match/run', { date_from: from, date_to: to }),
    ['bank', 'checks'],
  );
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Bank Matching"
        subtitle="What the books say should reach the bank, against what the bank statement shows. Nothing is forced: what cannot be matched stays visible."
      >
        {can(P.BANK_RECON_MANAGE) && (
          <Button
            variant="primary"
            loading={run.isPending}
            onClick={() =>
              run
                .mutateAsync()
                .then((r) =>
                  toast.success(
                    `${r.auto} matched, ${r.suggested} to confirm${r.reversals ? `, ${r.reversals} reversal(s)` : ''}.`,
                  ),
                )
            }
          >
            Check the books against the bank
          </Button>
        )}
      </PageHeader>
      <div className="flex flex-wrap items-end gap-3">
        <TextField
          label="From"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <TextField label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <TabbedPanel
        label="Bank matching"
        tabs={[
          {
            value: 'days',
            label: 'Day by day',
            content: (
              <>
                <DaysTable from={from} to={to} />
                <Suggestions />
                <Attention from={from} to={to} />
              </>
            ),
          },
          {
            value: 'lines',
            label: 'Statement lines',
            content: <StatementLines from={from} to={to} />,
          },
          ...(can(P.BANK_RECON_MANAGE)
            ? [{ value: 'import', label: 'Import a statement', content: <ImportTab /> }]
            : []),
          { value: 'accounts', label: 'Bank accounts', content: <AccountsTab /> },
        ]}
      />
    </div>
  );
}
