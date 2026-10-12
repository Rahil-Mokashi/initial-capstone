import { useState, type FormEvent } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { formatMoney, groupDigits, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];

interface DayData {
  stock_lines: Array<{ label: string; litres: string; rupees: string }>;
  stock_litres: string;
  stock_rupees: string;
  bills: Array<{
    id: string;
    bill_no: string;
    customer: string;
    quantity: string;
    rate: string;
    amount: string;
    transport: string;
    total: string;
  }>;
  bills_qty: string;
  bills_amount: string;
  bills_transport: string;
  bills_total: string;
  closing_litres: string;
  closing_rupees: string;
  meter: { start_reading: string; testing: string; end_reading: string } | null;
  meter_net: string | null;
}

const L = (v: string | null | undefined) =>
  v == null ? '' : groupDigits(v.includes('.') ? v.replace(/0+$/, '').replace(/\.$/, '') : v);
type Dialog = null | 'transfer' | 'bill' | 'meter' | 'opening' | { void: string };

function useDone(onClose: () => void) {
  const toast = useToast();
  return (message: string) => {
    toast.success(message);
    onClose();
  };
}

function Transfer({ day, onClose }: { day: string; onClose: () => void }) {
  const done = useDone(onClose);
  const options = useGet<S['SaleOptions']>(['bowser', 'options'], '/sales/options');
  const [v, setV] = useState({ shift: '', nozzle: '', employee: '', litres: '' });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['TransferIn']) => api.post('/bowser/transfers', b),
    ['bowser', 'daily-report', 'checks'],
  );
  const o = options.data;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await save.mutateAsync({
        shift_id: v.shift,
        nozzle_id: v.nozzle,
        employee_id: v.employee,
        litres: v.litres,
      });
      done('Stock Transfer to the Bouser recorded.');
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  const pick = (
    label: string,
    key: 'shift' | 'nozzle' | 'employee',
    list: Array<{ id: string; label: string }> = [],
  ) => (
    <SelectField
      label={label}
      value={v[key]}
      onChange={(e) => setV({ ...v, [key]: e.target.value })}
    >
      <option value="">Choose</option>
      {list.map((x) => (
        <option key={x.id} value={x.id}>
          {x.label}
        </option>
      ))}
    </SelectField>
  );
  return (
    <FormDialog
      title="Stock Transfer to the Bouser"
      description={`Fuel leaves the pump for the bowser on ${day}. It is billed as a credit sale to the internal account.`}
      submitLabel="Record transfer"
      busy={save.isPending}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      {pick('Shift', 'shift', o?.shifts)}
      {pick('Nozzle it came through', 'nozzle', o?.nozzles)}
      {pick('Attendant', 'employee', o?.employees)}
      <DecimalField
        label="Litres"
        value={v.litres}
        onChange={(e) => setV({ ...v, litres: e.target.value })}
      />
    </FormDialog>
  );
}

function Bill({ day, onClose }: { day: string; onClose: () => void }) {
  const done = useDone(onClose);
  const customers = useGet<S['CustomerOut'][]>(['bowser', 'customers'], '/customers');
  const [v, setV] = useState({
    no: '',
    customer: '',
    qty: '',
    rate: '',
    transport: '',
    vehicle: '',
    slip: '',
  });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['BillIn']) => api.post('/bowser/bills', b),
    ['bowser', 'daily-report', 'checks', 'credit'],
  );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await save.mutateAsync({
        bill_no: v.no,
        bill_date: day,
        customer_id: v.customer,
        quantity: v.qty,
        rate: v.rate,
        transport: v.transport || '0',
        vehicle_no: v.vehicle || null,
        slip_no: v.slip || null,
      });
      done(`Bill ${v.no} recorded.`);
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  return (
    <FormDialog
      title="Bowser bill"
      submitLabel="Save bill"
      busy={save.isPending}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Bill No"
        value={v.no}
        onChange={(e) => setV({ ...v, no: e.target.value })}
      />
      <SelectField
        label="Customer"
        value={v.customer}
        onChange={(e) => setV({ ...v, customer: e.target.value })}
      >
        <option value="">Choose</option>
        {(customers.data ?? [])
          .filter((c) => c.name !== 'Stock Transfer (Bouser)')
          .map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
      </SelectField>
      <DecimalField
        label="Qty (litres)"
        value={v.qty}
        onChange={(e) => setV({ ...v, qty: e.target.value })}
      />
      <DecimalField
        label="Rate (Rs per litre)"
        maxFraction={2}
        unit="rupees"
        value={v.rate}
        onChange={(e) => setV({ ...v, rate: e.target.value })}
      />
      <DecimalField
        label="Transport (Rs)"
        optional
        maxFraction={2}
        unit="rupees"
        value={v.transport}
        onChange={(e) => setV({ ...v, transport: e.target.value })}
      />
      <TextField
        label="Vehicle no."
        optional
        value={v.vehicle}
        onChange={(e) => setV({ ...v, vehicle: e.target.value })}
      />
      <TextField
        label="Slip no."
        optional
        value={v.slip}
        onChange={(e) => setV({ ...v, slip: e.target.value })}
      />
    </FormDialog>
  );
}

function Meter({
  day,
  current,
  onClose,
}: {
  day: string;
  current: DayData['meter'];
  onClose: () => void;
}) {
  const done = useDone(onClose);
  const [v, setV] = useState({
    start: current?.start_reading ?? '',
    testing: current?.testing ?? '0',
    end: current?.end_reading ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['MeterIn']) => api.post('/bowser/meter', b),
    ['bowser', 'daily-report', 'checks'],
  );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await save.mutateAsync({
        day,
        start_reading: v.start,
        testing: v.testing || '0',
        end_reading: v.end,
      });
      done('Bowser meter saved.');
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  return (
    <FormDialog
      title="Bowser meter"
      description="Net Sale = End Reading - Start Reading - Testing. A new reading replaces the old one; the old one is kept as void."
      submitLabel="Save meter"
      busy={save.isPending}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <DecimalField
        label="Start Reading"
        value={v.start}
        onChange={(e) => setV({ ...v, start: e.target.value })}
      />
      <DecimalField
        label="Testing"
        value={v.testing}
        onChange={(e) => setV({ ...v, testing: e.target.value })}
      />
      <DecimalField
        label="End Reading"
        value={v.end}
        onChange={(e) => setV({ ...v, end: e.target.value })}
      />
    </FormDialog>
  );
}

function Opening({ day, onClose }: { day: string; onClose: () => void }) {
  const done = useDone(onClose);
  const [v, setV] = useState({ litres: '', rupees: '', reason: '' });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['OpeningIn']) => api.post('/bowser/opening', b),
    ['bowser', 'daily-report', 'checks'],
  );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await save.mutateAsync({ day, litres: v.litres, rupees: v.rupees, reason: v.reason });
      done('Opening stock saved.');
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  return (
    <FormDialog
      title="Set opening stock by hand"
      description="Normally yesterday's Closing Stock carries forward by itself. Use this for the first day, or to correct it."
      submitLabel="Save"
      busy={save.isPending}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <DecimalField
        label="Litres"
        value={v.litres}
        onChange={(e) => setV({ ...v, litres: e.target.value })}
      />
      <DecimalField
        label="Worth (Rs)"
        maxFraction={2}
        unit="rupees"
        value={v.rupees}
        onChange={(e) => setV({ ...v, rupees: e.target.value })}
      />
      <TextField
        label="Reason"
        value={v.reason}
        onChange={(e) => setV({ ...v, reason: e.target.value })}
      />
    </FormDialog>
  );
}

const cell = 'border border-line px-3 py-2';

export function BowserPage() {
  const { can } = useAuth();
  const toast = useToast();
  const [day, setDay] = useState(todayIso());
  const [dialog, setDialog] = useState<Dialog>(null);
  const data = useGet<S['BowserDayOut']>(['bowser', 'day', day], `/bowser/day?day=${day}`);
  const d = data.data?.day_report as unknown as DayData | undefined;
  const voidBill = useWrite(
    (v: { id: string; reason: string }) =>
      api.post(`/bowser/bills/${v.id}/void`, { reason: v.reason }),
    ['bowser', 'daily-report', 'checks', 'credit'],
  );
  const manage = can(P.BOWSER_MANAGE);
  const matches =
    d && d.meter_net != null
      ? d.meter_net === d.bills_qty || Number(d.meter_net) === Number(d.bills_qty)
      : null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Bowser Van"
        subtitle="Diesel delivered to clients: stock in, bills out, and the bowser's own meter."
      >
        {manage && (
          <>
            <Button onClick={() => setDialog('transfer')}>Stock Transfer</Button>
            <Button variant="primary" onClick={() => setDialog('bill')}>
              Add bill
            </Button>
            <Button onClick={() => setDialog('meter')}>Meter</Button>
            <Button onClick={() => setDialog('opening')}>Opening stock</Button>
          </>
        )}
      </PageHeader>
      <TextField label="Day" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
      {data.isLoading ? (
        <LoadingBlock label="Loading the bowser day" rows={3} />
      ) : data.isError ? (
        <ErrorState error={data.error} onRetry={() => void data.refetch()} />
      ) : d ? (
        <>
          <section aria-labelledby="bow-a">
            <h2 id="bow-a" className="mb-2 text-base font-bold">
              A] Internal stock
            </h2>
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-surface-2 text-left">
                  <th className={cell}>Details</th>
                  <th className={`${cell} text-right`}>Ltr</th>
                  <th className={`${cell} text-right`}>Rs</th>
                </tr>
              </thead>
              <tbody>
                {d.stock_lines.map((l, i) => (
                  <tr key={i}>
                    <td className={cell}>{l.label}</td>
                    <td className={`${cell} num text-right`}>{L(l.litres)}</td>
                    <td className={`${cell} num text-right`}>{formatMoney(l.rupees)}</td>
                  </tr>
                ))}
                <tr className="font-bold">
                  <td className={cell}>Total</td>
                  <td className={`${cell} num text-right`}>{L(d.stock_litres)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(d.stock_rupees)}</td>
                </tr>
              </tbody>
            </table>
          </section>
          <section aria-labelledby="bow-b">
            <h2 id="bow-b" className="mb-2 text-base font-bold">
              B] Bills
            </h2>
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-surface-2 text-left">
                  <th className={cell}>Bill No</th>
                  <th className={cell}>Cust Name</th>
                  <th className={`${cell} text-right`}>Qty</th>
                  <th className={`${cell} text-right`}>Amount</th>
                  <th className={`${cell} text-right`}>Transport</th>
                  <th className={`${cell} text-right`}>Total</th>
                  {manage && <th className={cell} />}
                </tr>
              </thead>
              <tbody>
                {d.bills.map((b, i) => (
                  <tr key={b.bill_no + i}>
                    <td className={cell}>{b.bill_no}</td>
                    <td className={cell}>{b.customer}</td>
                    <td className={`${cell} num text-right`}>{L(b.quantity)}</td>
                    <td className={`${cell} num text-right`}>{formatMoney(b.amount)}</td>
                    <td className={`${cell} num text-right`}>{formatMoney(b.transport)}</td>
                    <td className={`${cell} num text-right`}>{formatMoney(b.total)}</td>
                    {manage && (
                      <td className={cell}>
                        <Button onClick={() => setDialog({ void: b.id })}>Void</Button>
                      </td>
                    )}
                  </tr>
                ))}
                <tr className="font-bold">
                  <td className={cell} colSpan={2}>
                    Total
                  </td>
                  <td className={`${cell} num text-right`}>{L(d.bills_qty)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(d.bills_amount)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(d.bills_transport)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(d.bills_total)}</td>
                  {manage && <td className={cell} />}
                </tr>
                <tr className="font-bold">
                  <td className={cell} colSpan={2}>
                    Closing Stock
                  </td>
                  <td className={`${cell} num text-right`}>{L(d.closing_litres)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(d.closing_rupees)}</td>
                  <td className={cell} colSpan={manage ? 3 : 2} />
                </tr>
              </tbody>
            </table>
          </section>
          <section aria-labelledby="bow-c">
            <h2 id="bow-c" className="mb-2 text-base font-bold">
              C] Bowser meter
            </h2>
            {d.meter ? (
              <dl className="grid max-w-md grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm">
                <dt>Start Reading</dt>
                <dd className="num text-right">{L(d.meter.start_reading)}</dd>
                <dt>Testing</dt>
                <dd className="num text-right">{L(d.meter.testing)}</dd>
                <dt>End Reading</dt>
                <dd className="num text-right">{L(d.meter.end_reading)}</dd>
                <dt className="font-bold">Net Sale</dt>
                <dd className="num text-right font-bold">{L(d.meter_net)}</dd>
              </dl>
            ) : (
              <p className="text-sm text-muted">No meter reading for this day yet.</p>
            )}
            {matches !== null && (
              <p className="mt-2">
                {matches ? (
                  <StatusBadge tone="ok">Net Sale equals the litres on the bills</StatusBadge>
                ) : (
                  <StatusBadge tone="danger">{`Net Sale ${L(d.meter_net)} L, bills ${L(d.bills_qty)} L`}</StatusBadge>
                )}
              </p>
            )}
          </section>
        </>
      ) : null}
      {dialog === 'transfer' && <Transfer day={day} onClose={() => setDialog(null)} />}
      {dialog === 'bill' && <Bill day={day} onClose={() => setDialog(null)} />}
      {dialog === 'meter' && (
        <Meter day={day} current={d?.meter ?? null} onClose={() => setDialog(null)} />
      )}
      {dialog === 'opening' && <Opening day={day} onClose={() => setDialog(null)} />}
      {dialog && typeof dialog === 'object' && (
        <ReasonDialog
          title="Void this bill"
          description="The bill stays in the records, marked void. It no longer counts."
          submitLabel="Void bill"
          tone="danger"
          onConfirm={async (reason) => {
            await voidBill.mutateAsync({ id: dialog.void, reason });
            toast.success('Bill voided.');
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
