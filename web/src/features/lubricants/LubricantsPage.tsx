import { useState, type FormEvent } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { useToast } from '@/components/ui/Toast';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { formatDate, formatMoney, groupDigits } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Item = S['LubricantOut'];
type Move = S['MovementOut'];

const KINDS = [
  { value: 'purchase', label: 'Purchase (stock received)' },
  { value: 'sale', label: 'Sale (oil sold in a shift)' },
  { value: 'adjustment', label: 'Adjustment (+ or -, with a reason)' },
  { value: 'opening', label: 'Opening stock (first time only)' },
];

function AddItem({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [v, setV] = useState({ name: '', pack: '', rate: '' });
  const [error, setError] = useState<string | null>(null);
  const create = useWrite((b: S['LubricantIn']) => api.post('/lubricants', b), ['lubricants']);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await create.mutateAsync({ name: v.name, pack_size: v.pack || null, default_rate: v.rate });
      toast.success(`${v.name} added.`);
      onClose();
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  return (
    <FormDialog
      title="Add an oil item"
      submitLabel="Add item"
      busy={create.isPending}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Name"
        value={v.name}
        onChange={(e) => setV({ ...v, name: e.target.value })}
      />
      <TextField
        label="Pack size"
        optional
        placeholder="1 ltr"
        value={v.pack}
        onChange={(e) => setV({ ...v, pack: e.target.value })}
      />
      <DecimalField
        label="Selling rate (Rs)"
        maxFraction={2}
        unit="rupees"
        value={v.rate}
        onChange={(e) => setV({ ...v, rate: e.target.value })}
      />
    </FormDialog>
  );
}

function Record({ item, onClose }: { item: Item; onClose: () => void }) {
  const toast = useToast();
  const shifts = useGet<S['ShiftOut'][]>(['lubricants', 'shifts'], '/shifts');
  const [v, setV] = useState({
    kind: 'sale',
    qty: '',
    shift: '',
    customer: '',
    rate: '',
    remarks: '',
  });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['MovementIn']) => api.post(`/lubricants/${item.id}/movements`, b),
    ['lubricants'],
  );
  const open = (shifts.data ?? []).slice(0, 20);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await save.mutateAsync({
        kind: v.kind as S['MovementIn']['kind'],
        quantity: v.qty,
        shift_id: v.kind === 'sale' ? v.shift || null : null,
        customer_name: v.customer || null,
        unit_rate: v.rate || null,
        remarks: v.remarks || null,
      });
      toast.success('Saved.');
      onClose();
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  return (
    <FormDialog
      title={`Record - ${item.name}`}
      submitLabel="Save"
      busy={save.isPending}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="What happened"
        value={v.kind}
        onChange={(e) => setV({ ...v, kind: e.target.value })}
      >
        {KINDS.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </SelectField>
      <DecimalField
        label="Quantity"
        maxFraction={3}
        negative={v.kind === 'adjustment'}
        unit="units"
        value={v.qty}
        onChange={(e) => setV({ ...v, qty: e.target.value })}
      />
      {v.kind === 'sale' && (
        <>
          <SelectField
            label="Shift"
            value={v.shift}
            onChange={(e) => setV({ ...v, shift: e.target.value })}
          >
            <option value="">Choose the shift</option>
            {open.map((s) => (
              <option key={s.id} value={s.id}>
                {formatDate(s.shift_date)} - {s.shift_label}
              </option>
            ))}
          </SelectField>
          <DecimalField
            label="Rate (blank = the item's rate)"
            optional
            maxFraction={2}
            unit="rupees"
            value={v.rate}
            onChange={(e) => setV({ ...v, rate: e.target.value })}
          />
          <TextField
            label="Customer"
            optional
            value={v.customer}
            onChange={(e) => setV({ ...v, customer: e.target.value })}
          />
        </>
      )}
      <TextField
        label={v.kind === 'adjustment' ? 'Reason' : 'Note'}
        optional={v.kind !== 'adjustment'}
        value={v.remarks}
        onChange={(e) => setV({ ...v, remarks: e.target.value })}
      />
    </FormDialog>
  );
}

function History({ item }: { item: Item }) {
  const moves = useGet<Move[]>(
    ['lubricants', 'moves', item.id],
    `/lubricants/${item.id}/movements`,
  );
  if (moves.isLoading) return <LoadingBlock rows={1} />;
  return (
    <DataTable<Move>
      caption={`Movements of ${item.name}`}
      getRowId={(m) => m.id}
      data={moves.data ?? []}
      empty={<p className="text-sm text-muted">Nothing recorded yet.</p>}
      columns={[
        {
          accessorKey: 'movement_date',
          header: 'Date',
          cell: ({ getValue }) => formatDate(getValue<string>()),
        },
        { accessorKey: 'kind', header: 'Kind' },
        {
          accessorKey: 'quantity',
          header: 'Quantity',
          cell: ({ getValue }) => groupDigits(getValue<string>()),
        },
        {
          accessorKey: 'unit_rate',
          header: 'Rate',
          cell: ({ getValue }) =>
            getValue<string | null>() ? formatMoney(getValue<string>()) : '',
        },
        {
          accessorKey: 'amount',
          header: 'Amount',
          cell: ({ getValue }) =>
            getValue<string | null>() ? formatMoney(getValue<string>()) : '',
        },
        { accessorKey: 'customer_name', header: 'Customer' },
        { accessorKey: 'remarks', header: 'Note' },
      ]}
    />
  );
}

export function LubricantsPage() {
  const { can } = useAuth();
  const items = useGet<Item[]>(['lubricants', 'list'], '/lubricants');
  const [adding, setAdding] = useState(false);
  const [recording, setRecording] = useState<Item | null>(null);
  const [showing, setShowing] = useState<string | null>(null);
  const manage = can(P.LUBRICANT_MANAGE);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Oil and Lubricants"
        subtitle="Stock and sales of oil by item. These feed the Oil figure and the Oil sale table on the daily report."
      >
        {manage && (
          <Button variant="primary" onClick={() => setAdding(true)}>
            Add oil item
          </Button>
        )}
      </PageHeader>
      {items.isLoading ? (
        <LoadingBlock label="Loading oil items" rows={3} />
      ) : items.isError ? (
        <ErrorState error={items.error} onRetry={() => void items.refetch()} />
      ) : (
        <ul className="flex flex-col gap-3" aria-label="Oil items">
          {(items.data ?? []).map((i) => (
            <li key={i.id} className="rounded-lg border border-line bg-surface p-4 shadow-card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-bold">{i.name}</h2>
                  <p className="text-sm text-muted">
                    {i.pack_size ? `${i.pack_size} - ` : ''}Rate {formatMoney(i.default_rate)}
                  </p>
                </div>
                <p className="num text-2xl font-bold" aria-label={`Stock of ${i.name}`}>
                  {groupDigits(i.stock.replace(/\.?0+$/, '') || '0')} in stock
                </p>
                <div className="flex gap-2">
                  {manage && <Button onClick={() => setRecording(i)}>Record</Button>}
                  <Button
                    aria-pressed={showing === i.id}
                    onClick={() => setShowing(showing === i.id ? null : i.id)}
                  >
                    {showing === i.id ? 'Hide history' : 'History'}
                  </Button>
                </div>
              </div>
              {showing === i.id && (
                <div className="mt-3">
                  <History item={i} />
                </div>
              )}
            </li>
          ))}
          {(items.data ?? []).length === 0 && (
            <li className="text-sm text-muted">No oil items yet.</li>
          )}
        </ul>
      )}
      {adding && <AddItem onClose={() => setAdding(false)} />}
      {recording && <Record item={recording} onClose={() => setRecording(null)} />}
    </div>
  );
}
