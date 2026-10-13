import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { DocumentActions } from '@/components/DocumentActions';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { FormDialog } from '@/components/ui/FormDialog';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { addDaysIso, formatDate, formatMoney, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Bill = S['LedgerBillOut'];
type Detail = S['CustomerDetailOut'];

function Tile({ label, value, tone }: { label: string; value: string; tone?: 'warn' }) {
  return (
    <li
      className={`flex flex-col gap-1 rounded-lg border bg-surface p-4 shadow-card ${tone === 'warn' ? 'border-warn' : 'border-line'}`}
    >
      <p className="num text-xl font-bold">{value}</p>
      <p className="text-sm text-muted">{label}</p>
    </li>
  );
}

function BillDetails({ bill, onClose }: { bill: Bill; onClose: () => void }) {
  const toast = useToast();
  const [v, setV] = useState({ vehicle: bill.vehicle_no ?? '', slip: bill.slip_no ?? '' });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['BillDetailsIn']) => api.put(`/credit/bills/${bill.sale_id}/details`, b),
    ['credit'],
  );
  return (
    <FormDialog
      title={`Vehicle and slip for bill ${bill.ref}`}
      description="They are printed on the customer's statement."
      submitLabel="Save"
      busy={save.isPending}
      error={error}
      onClose={onClose}
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await save.mutateAsync({ vehicle_no: v.vehicle || null, slip_no: v.slip || null });
          toast.success('Saved.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
    >
      <TextField
        label="Vehicle number"
        optional
        value={v.vehicle}
        onChange={(e) => setV({ ...v, vehicle: e.target.value })}
      />
      <TextField
        label="Slip number"
        optional
        value={v.slip}
        onChange={(e) => setV({ ...v, slip: e.target.value })}
      />
    </FormDialog>
  );
}

function Recovery({ d }: { d: Detail }) {
  const { can } = useAuth();
  const toast = useToast();
  const [v, setV] = useState({ method: 'call', note: '', date: '', amount: '' });
  const [error, setError] = useState<string | null>(null);
  const add = useWrite(
    (b: S['FollowUpIn']) => api.post(`/credit/customers/${d.customer_id}/follow-ups`, b),
    ['credit'],
  );
  const close = useWrite(
    (x: { id: string; outcome: 'kept' | 'broken' | 'cancelled' }) =>
      api.post(`/credit/follow-ups/${x.id}/close`, { outcome: x.outcome }),
    ['credit'],
  );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await add.mutateAsync({
        method: v.method as S['FollowUpIn']['method'],
        note: v.note || null,
        promised_date: v.date || null,
        promised_amount: v.amount || null,
      });
      toast.success('Follow-up recorded.');
      setV({ method: 'call', note: '', date: '', amount: '' });
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  return (
    <section aria-labelledby="recovery" className="flex flex-col gap-3">
      <h2 id="recovery" className="text-base font-bold">
        Recovery: who was contacted and what they promised
      </h2>
      {can(P.CREDIT_RECOVERY) && (
        <form
          onSubmit={submit}
          aria-label="Log a follow-up"
          className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-3"
        >
          <SelectField
            label="How"
            value={v.method}
            onChange={(e) => setV({ ...v, method: e.target.value })}
          >
            <option value="call">Phone call</option>
            <option value="visit">Visit</option>
            <option value="message">Message</option>
            <option value="other">Other</option>
          </SelectField>
          <TextField
            label="What was said"
            optional
            value={v.note}
            onChange={(e) => setV({ ...v, note: e.target.value })}
          />
          <TextField
            label="Promised date"
            type="date"
            optional
            value={v.date}
            onChange={(e) => setV({ ...v, date: e.target.value })}
          />
          <DecimalField
            label="Promised amount (₹)"
            optional
            maxFraction={2}
            unit="rupees"
            value={v.amount}
            onChange={(e) => setV({ ...v, amount: e.target.value })}
          />
          <Button type="submit" variant="primary" loading={add.isPending}>
            Log follow-up
          </Button>
          {error && (
            <p role="alert" className="w-full text-sm font-medium text-danger-fg">
              {error}
            </p>
          )}
        </form>
      )}
      <ul className="flex flex-col gap-2" aria-label="Follow-ups">
        {d.follow_ups.length === 0 && (
          <li className="text-sm text-muted">Nobody has followed this customer up yet.</li>
        )}
        {d.follow_ups.map((f) => (
          <li
            key={f.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line p-3 text-sm"
          >
            <span>
              <strong>{formatDate(f.followed_on)}</strong> by {f.by ?? 'someone'}, {f.method}
              {f.note ? `: ${f.note}` : ''}
              {f.promised_date
                ? `. Promised ${f.promised_amount ? formatMoney(f.promised_amount) + ' ' : ''}by ${formatDate(f.promised_date)}`
                : ''}
            </span>
            <span className="flex items-center gap-2">
              <StatusBadge
                tone={
                  f.status === 'kept'
                    ? 'ok'
                    : f.status === 'broken'
                      ? 'danger'
                      : f.status === 'open'
                        ? 'info'
                        : 'neutral'
                }
              >
                {f.status === 'open'
                  ? 'Open'
                  : f.status === 'kept'
                    ? 'Kept'
                    : f.status === 'broken'
                      ? 'Broken'
                      : 'Cancelled'}
              </StatusBadge>
              {f.status === 'open' && can(P.CREDIT_RECOVERY) && (
                <>
                  <Button onClick={() => close.mutate({ id: f.id, outcome: 'kept' })}>Kept</Button>
                  <Button onClick={() => close.mutate({ id: f.id, outcome: 'broken' })}>
                    Broken
                  </Button>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Statement({ id }: { id: string }) {
  const [from, setFrom] = useState(addDaysIso(-30));
  const [to, setTo] = useState(todayIso());
  const q = `date_from=${from}&date_to=${to}`;
  return (
    <section aria-labelledby="statement" className="flex flex-col gap-3">
      <h2 id="statement" className="text-base font-bold">
        Statement
      </h2>
      <div className="flex flex-wrap items-end gap-3">
        <TextField
          label="From"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <TextField label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        <DocumentActions
          previewLabel="Print preview"
          getHtml={async () =>
            (await api.get<S['CustomerStatementOut']>(`/credit/customers/${id}/statement?${q}`))
              .report.html
          }
          files={[
            {
              label: 'PDF',
              path: `/credit/customers/${id}/statement.pdf?${q}`,
              filename: 'statement.pdf',
            },
            {
              label: 'Excel',
              path: `/credit/customers/${id}/statement.xlsx?${q}`,
              filename: 'statement.xlsx',
            },
          ]}
        />
      </div>
      <p className="text-sm text-muted">
        Date by date with the running balance, then bill by bill with what is still unpaid. Vehicle
        and slip numbers are shown where they were recorded.
      </p>
    </section>
  );
}

export function CustomerPage() {
  const { id = '' } = useParams();
  const { can } = useAuth();
  const toast = useToast();
  const data = useGet<Detail>(['credit', 'customer', id], `/credit/customers/${id}`);
  const [editing, setEditing] = useState<Bill | null>(null);
  const decide = useWrite(
    (approve: boolean) => api.post(`/credit/approvals/${id}`, { approve, note: '' }),
    ['credit'],
  );
  if (data.isLoading) return <LoadingBlock label="Loading the customer" rows={4} />;
  if (data.isError) return <ErrorState error={data.error} onRetry={() => void data.refetch()} />;
  const d = data.data!;
  const old = d.oldest_unpaid;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={d.name}
        subtitle="Every bill and payment, what is still owed, and how long it has been owed."
      >
        <Link to="/credit" className="text-sm font-semibold underline">
          All credit customers
        </Link>
        {d.approval === 'pending' && can(P.CREDIT_APPROVE) && (
          <Button
            variant="primary"
            onClick={() => decide.mutateAsync(true).then(() => toast.success('Credit approved.'))}
          >
            Approve credit for this customer
          </Button>
        )}
      </PageHeader>
      <div className="flex flex-wrap gap-2">
        {d.overdue && (
          <StatusBadge tone="danger">{`Overdue by ${d.overdue_days} day(s)`}</StatusBadge>
        )}
        {d.approval === 'pending' && (
          <StatusBadge tone="warn">Waiting for an owner to approve credit</StatusBadge>
        )}
        {d.approval === 'rejected' && (
          <StatusBadge tone="danger">Credit was not approved</StatusBadge>
        )}
        {d.approved_by && (
          <StatusBadge tone="ok">{`Credit allowed by ${d.approved_by}${d.approved_at ? ' on ' + formatDate(d.approved_at.slice(0, 10)) : ''}`}</StatusBadge>
        )}
      </div>
      <ul aria-label="Summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Owes now" value={formatMoney(d.balance)} />
        <Tile
          label="Credit limit"
          value={d.credit_limit != null ? formatMoney(d.credit_limit) : 'No credit account'}
        />
        <Tile
          label="Still available"
          value={d.available != null ? formatMoney(d.available) : '-'}
          tone={d.available != null && d.available.startsWith('-') ? 'warn' : undefined}
        />
        <Tile
          label="Average days to pay a bill"
          value={d.average_days_to_pay ?? 'Not enough history'}
        />
        <Tile label="Most ever owed at once" value={formatMoney(d.largest_outstanding_ever)} />
        <Tile
          label="Oldest unpaid bill"
          value={old ? `${old.ref}: ${old.age_days} days` : 'None'}
          tone={d.overdue ? 'warn' : undefined}
        />
        <Tile label="Total billed" value={formatMoney(d.total_billed)} />
        <Tile label="Total paid" value={formatMoney(d.total_paid)} />
      </ul>
      <section aria-labelledby="owed-by-age">
        <h2 id="owed-by-age" className="mb-2 text-base font-bold">
          What is owed, by age
        </h2>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(d.buckets).map(([name, amount]) => (
            <li key={name} className="rounded-md border border-line bg-surface p-3">
              <p className="text-sm text-muted">{name} days</p>
              <p className="num font-bold">{formatMoney(amount)}</p>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="bills">
        <h2 id="bills" className="mb-2 text-base font-bold">
          Bills
        </h2>
        <DataTable<Bill>
          caption="Bills"
          getRowId={(b) => `${b.kind}-${b.ref}`}
          data={d.bills}
          empty={<p className="text-sm text-muted">No bills yet.</p>}
          columns={[
            {
              accessorKey: 'bill_date',
              header: 'Date',
              cell: ({ getValue }) => formatDate(getValue<string>()),
            },
            {
              accessorKey: 'ref',
              header: 'Bill',
              cell: ({ row }) =>
                `${row.original.kind === 'bowser' ? 'Bouser ' : ''}${row.original.ref}`,
            },
            {
              accessorKey: 'amount',
              header: 'Amount',
              cell: ({ getValue }) => formatMoney(getValue<string>()),
            },
            {
              accessorKey: 'paid',
              header: 'Paid',
              cell: ({ getValue }) => formatMoney(getValue<string>()),
            },
            {
              accessorKey: 'outstanding',
              header: 'Still owed',
              cell: ({ getValue }) => formatMoney(getValue<string>()),
            },
            { accessorKey: 'age_days', header: 'Age (days)' },
            {
              id: 'vs',
              header: 'Vehicle / slip',
              cell: ({ row }) => (
                <span className="flex items-center gap-2">
                  {[row.original.vehicle_no, row.original.slip_no].filter(Boolean).join(' / ')}
                  {row.original.sale_id && can(P.CREDIT_MANAGE) && (
                    <Button onClick={() => setEditing(row.original)}>Edit</Button>
                  )}
                </span>
              ),
            },
          ]}
        />
      </section>
      <section aria-labelledby="payments">
        <h2 id="payments" className="mb-2 text-base font-bold">
          Payments received
        </h2>
        <DataTable<S['PaymentRowOut']>
          caption="Payments"
          getRowId={(p) => `${p.pay_date}-${p.amount}-${p.reference ?? ''}`}
          data={d.payments}
          empty={<p className="text-sm text-muted">No payments yet.</p>}
          columns={[
            {
              accessorKey: 'pay_date',
              header: 'Date',
              cell: ({ getValue }) => formatDate(getValue<string>()),
            },
            {
              accessorKey: 'amount',
              header: 'Amount',
              cell: ({ getValue }) => formatMoney(getValue<string>()),
            },
            { accessorKey: 'method', header: 'How' },
            { accessorKey: 'reference', header: 'Reference' },
          ]}
        />
      </section>
      {d.overrides.length > 0 && (
        <section aria-labelledby="overrides">
          <h2 id="overrides" className="mb-2 text-base font-bold">
            Bills an owner allowed past the limit
          </h2>
          <ul className="flex flex-col gap-1 text-sm">
            {d.overrides.map((o) => (
              <li key={o.created_at}>
                {formatDate(o.created_at.slice(0, 10))}: {formatMoney(o.amount)} while owing{' '}
                {formatMoney(o.outstanding_before)} (limit {formatMoney(o.credit_limit)}), allowed
                by {o.approved_by}. {o.reason}
              </li>
            ))}
          </ul>
        </section>
      )}
      <Recovery d={d} />
      <Statement id={id} />
      {editing && <BillDetails bill={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
