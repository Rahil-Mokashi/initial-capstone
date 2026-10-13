import { useMemo, useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { DocumentActions } from '@/components/DocumentActions';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormError } from '@/components/ui/FormDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { CreditLimitPanel, OverrideDialog, isLimitError } from '@/features/credit/CreditLimit';
import { getReceiptHtml, useSalesPage, type Sale } from '@/features/sales/queries';
import { cn } from '@/lib/cn';
import { divide2, multiply2 } from '@/lib/decimalMath';
import { formatDateTime, formatMoney, formatQuantity, titleCase } from '@/lib/format';

type S = components['schemas'];
type Nozzle = S['TerminalNozzle'];

const useContext_ = () =>
  useGet<S['TerminalContext']>(['terminal', 'context'], '/terminal/context');
const useTerminalSale = () =>
  useWrite(
    (b: S['TerminalSaleIn']) => api.post<Sale>('/terminal/sales', b),
    ['sales', 'tanks', 'credit', 'terminal'],
  );

// What people actually hand over at the pump (same four as the Qt screen).
const PRESETS = ['200', '500', '1000', '2000'];
const METHODS = ['cash', 'upi', 'card', 'credit'] as const;
type Method = (typeof METHODS)[number];

function Chip({
  pressed,
  onClick,
  children,
  label,
}: {
  pressed: boolean;
  onClick: () => void;
  children: React.ReactNode;
  label?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={label}
      onClick={onClick}
      className={cn(
        'inline-flex min-h-[48px] min-w-[72px] items-center justify-center rounded-full border px-5 text-base font-semibold',
        pressed
          ? 'border-primary bg-primary text-primary-fg'
          : 'border-line-strong bg-surface hover:bg-surface-2',
      )}
    >
      {children}
    </button>
  );
}

function Recent({ nozzleId }: { nozzleId: string }) {
  // The Qt screen scans the newest 50 sales and shows the first 5 for this nozzle.
  const sales = useSalesPage(0);
  const rows = (sales.data?.items ?? []).filter((s) => s.nozzle_id === nozzleId).slice(0, 5);
  if (rows.length === 0) return null;
  return (
    <section aria-labelledby="recent-title" className="flex flex-col gap-2">
      <h2 id="recent-title" className="text-base font-bold">
        Recent sales on this nozzle
      </h2>
      <ul className="flex flex-col gap-1">
        {rows.map((s) => (
          <li key={s.id} className="num text-sm text-muted">
            {formatDateTime(s.sale_at).split(',').pop()?.trim()} - {formatQuantity(s.quantity)} L -{' '}
            {formatMoney(s.amount)} - {titleCase(s.payment_method)}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function TerminalPage() {
  const ctx = useContext_();
  const sell = useTerminalSale();
  const [shiftId, setShiftId] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [nozzleId, setNozzleId] = useState('');
  const [mode, setMode] = useState<'amount' | 'litres'>('amount');
  const [value, setValue] = useState('500');
  const [method, setMethod] = useState<Method>('cash');
  const [customerId, setCustomerId] = useState('');
  const [reference, setReference] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Sale | null>(null);
  // A credit bill that passed the customer's limit, waiting for an owner to allow it (V-14).
  const [limitIssue, setLimitIssue] = useState<{
    message: string;
    body: S['TerminalSaleIn'];
  } | null>(null);

  const c = ctx.data;
  const free = c?.can_pick_freely ?? false;
  const nozzle: Nozzle | undefined = free
    ? (c?.nozzles.find((n) => n.id === nozzleId) ?? c?.nozzles[0])
    : c?.my_assignment?.nozzle;
  const rate = nozzle?.rate_per_liter ?? null;

  // Live preview, exact decimals (the server does the real calculation on save).
  const preview = useMemo(() => {
    if (!rate || !/^\d+(\.\d+)?$/.test(value)) return null;
    return mode === 'amount'
      ? { quantity: divide2(value, rate), amount: multiply2(value, '1') }
      : { quantity: value, amount: multiply2(value, rate) };
  }, [mode, value, rate]);

  const canSubmit = free ? Boolean(c && c.nozzles.length > 0) : Boolean(c?.my_assignment);

  async function submit() {
    setError(null);
    if (free) {
      if (!(shiftId || c?.shifts[0])) return setError('No open shifts available.');
      if (!(employeeId || c?.employees[0])) return setError('No employees available.');
      if (!nozzle) return setError('Choose a nozzle first.');
    } else if (!c?.my_assignment) {
      return setError('You have no active nozzle assignment.');
    }
    if (!rate)
      return setError(
        'This fuel has no selling price set - a manager must set it before this can be sold.',
      );
    if (!/^\d{1,12}(\.\d{1,2})?$/.test(value) || Number(value) <= 0)
      return setError('Enter an amount above zero, such as 500.');
    const body: S['TerminalSaleIn'] = {
      mode,
      value,
      payment_method: method,
      customer_id: customerId || undefined,
      reference_number: reference.trim() || undefined,
      remarks: note.trim() || undefined,
      ...(free
        ? {
            shift_id: shiftId || c!.shifts[0]!.id,
            employee_id: employeeId || c!.employees[0]!.id,
            nozzle_id: nozzle!.id,
          }
        : {}),
    };
    try {
      setDone(await sell.mutateAsync(body));
    } catch (e) {
      if (isLimitError(e)) setLimitIssue({ message: e.message, body });
      else setError(friendlyMessage(e));
    }
  }

  function newSale() {
    setDone(null);
    setError(null);
    setMode('amount');
    setValue('500');
    setMethod('cash');
    setReference('');
    setNote('');
    void ctx.refetch();
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title="Terminal"
        subtitle="Fast fuel-sale entry - pick a nozzle, enter an amount, take payment."
      />
      {ctx.isLoading ? (
        <LoadingBlock label="Loading the terminal" rows={4} />
      ) : ctx.isError || !c ? (
        <ErrorState error={ctx.error} onRetry={() => void ctx.refetch()} />
      ) : done ? (
        <section
          aria-label="Sale recorded"
          className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-6 shadow-card"
        >
          <h2 className="text-2xl font-bold">Sale recorded</h2>
          <p className="text-sm text-muted">
            Receipt {done.receipt_number} - {formatDateTime(done.sale_at)}
          </p>
          <pre className="num rounded-md border border-line bg-surface-2 p-4 text-sm whitespace-pre-wrap">
            {[
              `Fuel: ${done.fuel_type ?? ''}`,
              `Nozzle: ${done.nozzle ?? ''}`,
              `Quantity: ${formatQuantity(done.quantity)} L`,
              `Rate/Litre: ${formatMoney(done.rate_per_liter)}`,
              `Amount: ${formatMoney(done.amount)}`,
              `Payment: ${titleCase(done.payment_method)}`,
              done.customer ? `Customer: ${done.customer}` : null,
            ]
              .filter(Boolean)
              .join('\n')}
          </pre>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <DocumentActions
              getHtml={() => getReceiptHtml(done.id)}
              previewLabel="Print receipt"
              files={[
                {
                  label: 'PDF',
                  path: `/sales/${done.id}/receipt.pdf`,
                  filename: `receipt_${done.receipt_number}.pdf`,
                },
              ]}
            />
            <Button variant="primary" onClick={newSale}>
              New sale
            </Button>
          </div>
        </section>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          noValidate
          className="flex flex-col gap-5 rounded-lg border border-line bg-surface p-6 shadow-card"
        >
          {free ? (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <SelectField
                  label="Shift"
                  value={shiftId}
                  onChange={(e) => setShiftId(e.target.value)}
                >
                  {c.shifts.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </SelectField>
                <SelectField
                  label="Attendant"
                  value={employeeId}
                  onChange={(e) => setEmployeeId(e.target.value)}
                >
                  {c.employees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.label}
                    </option>
                  ))}
                </SelectField>
              </div>
              <div role="group" aria-label="Nozzle" className="flex flex-wrap gap-2">
                {c.nozzles.length === 0 && (
                  <p className="text-sm text-muted">No active nozzles available.</p>
                )}
                {c.nozzles.map((n) => (
                  <Chip
                    key={n.id}
                    pressed={nozzle?.id === n.id}
                    onClick={() => setNozzleId(n.id)}
                    label={`${n.code} ${n.fuel_type ?? ''}`}
                  >
                    {n.code} {n.fuel_type ?? ''}
                  </Chip>
                ))}
              </div>
            </>
          ) : c.my_assignment ? (
            <p className="text-xl font-bold">
              Selling from your current assignment: {c.my_assignment.nozzle.code} -{' '}
              {c.my_assignment.nozzle.fuel_type ?? ''}
            </p>
          ) : (
            <p className="text-sm text-muted">
              You have no active nozzle assignment - ask a supervisor to assign you one first.
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-bold">{mode === 'amount' ? 'Amount' : 'Litres'}</h2>
            <div role="group" aria-label="Enter by" className="flex gap-2">
              <Chip pressed={mode === 'amount'} onClick={() => setMode('amount')}>
                ₹ Amount
              </Chip>
              <Chip pressed={mode === 'litres'} onClick={() => setMode('litres')}>
                Litres
              </Chip>
            </div>
          </div>
          <div role="group" aria-label="Quick amounts" className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <Chip
                key={p}
                pressed={mode === 'amount' && value === p}
                onClick={() => {
                  setMode('amount');
                  setValue(p);
                }}
              >
                ₹{p}
              </Chip>
            ))}
          </div>
          <DecimalField
            label={mode === 'amount' ? 'Amount (₹)' : 'Quantity (L)'}
            maxFraction={2}
            unit={mode === 'amount' ? 'rupees' : 'litres'}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <p className="num min-h-[2rem] text-2xl font-bold" aria-live="polite">
            {nozzle && !rate
              ? 'This fuel has no selling price set yet.'
              : preview?.quantity && preview.amount
                ? `Volume: ${formatQuantity(preview.quantity)} L    Total: ${formatMoney(preview.amount)}`
                : ''}
          </p>

          <h2 className="text-base font-bold">Payment method</h2>
          <div role="group" aria-label="Payment method" className="flex flex-wrap gap-2">
            {METHODS.map((m) => (
              <Chip key={m} pressed={method === m} onClick={() => setMethod(m)}>
                {titleCase(m)}
              </Chip>
            ))}
          </div>
          <SelectField
            label={method === 'credit' ? 'Customer (required for credit)' : 'Customer'}
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
          >
            <option value="">(none)</option>
            {c.customers.map((cu) => (
              <option key={cu.id} value={cu.id}>
                {cu.label}
              </option>
            ))}
          </SelectField>
          {method === 'credit' && customerId && (
            <CreditLimitPanel customerId={customerId} amount={preview?.amount ?? null} />
          )}
          {(method === 'upi' || method === 'card') && (
            <TextField
              label="UPI/Card reference"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          )}
          <TextField
            label="Note"
            optional
            placeholder="Optional - vehicle number, remark, etc."
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <FormError message={error} />
          <Button
            type="submit"
            variant="primary"
            loading={sell.isPending}
            disabled={!canSubmit}
            className="min-h-[56px] text-lg"
          >
            Complete sale
          </Button>
        </form>
      )}
      {nozzle && !done && <Recent nozzleId={nozzle.id} />}
      {limitIssue && (
        <OverrideDialog
          message={limitIssue.message}
          onClose={() => setLimitIssue(null)}
          onConfirm={async (override) =>
            setDone(await sell.mutateAsync({ ...limitIssue.body, credit_override: override }))
          }
        />
      )}
    </div>
  );
}
