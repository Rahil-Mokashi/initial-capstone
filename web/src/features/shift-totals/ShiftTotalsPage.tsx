import { useState, type FormEvent } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { formatDate, formatMoney } from '@/lib/format';

type S = components['schemas'];
type Row = S['TenderTotalOut'];

function ModeRow({ shiftId, row }: { shiftId: string; row: Row }) {
  const toast = useToast();
  const [amount, setAmount] = useState(row.amount ?? '');
  const [reference, setReference] = useState(row.reference ?? '');
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['TotalIn']) => api.put(`/shift-totals/${shiftId}/${row.tender_id}`, b),
    ['shift-totals', 'daily-report', 'checks'],
  );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await save.mutateAsync({ amount: amount || '0', reference: reference || null, reason: '' });
      toast.success(`${row.label} saved.`);
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  return (
    <li>
      <form
        onSubmit={submit}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-3"
        aria-label={row.label}
      >
        <p className="w-32 pb-3 font-semibold">{row.label}</p>
        <DecimalField
          label={`${row.label} total (Rs)`}
          maxFraction={2}
          unit="rupees"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <TextField
          label="Slip / batch no."
          optional
          value={reference}
          onChange={(e) => setReference(e.target.value)}
        />
        <Button type="submit" loading={save.isPending}>
          Save
        </Button>
        {row.amount != null && (
          <p className="pb-3 text-sm text-muted">Saved: {formatMoney(row.amount)}</p>
        )}
        {error && (
          <p role="alert" className="w-full text-sm font-medium text-danger-fg">
            {error}
          </p>
        )}
      </form>
    </li>
  );
}

function InternalFuel({ shiftId }: { shiftId: string }) {
  const toast = useToast();
  const options = useGet<S['SaleOptions']>(['shift-totals', 'options'], '/sales/options');
  const fuels = useGet<S['FuelOut'][]>(['shift-totals', 'fuels'], '/lookups/fuels');
  const [v, setV] = useState({ employee: '', fuel: '', litres: '', vehicle: '' });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['InternalFuelIn']) => api.post('/internal-fuel', b),
    ['expenses', 'daily-report', 'checks'],
  );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await save.mutateAsync({
        shift_id: shiftId,
        employee_id: v.employee,
        fuel_id: v.fuel,
        litres: v.litres,
        vehicle: v.vehicle,
      });
      toast.success('Internal fuel use recorded as an expense.');
      setV({ ...v, litres: '', vehicle: '' });
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };
  return (
    <section aria-labelledby="internal-fuel" className="flex flex-col gap-3">
      <h2 id="internal-fuel" className="text-base font-bold">
        Own vehicle / genset fuel
      </h2>
      <p className="text-sm text-muted">
        Recorded as an expense at the selling price with the litres, the way the old report shows
        it. It does not reduce tank stock a second time: that fuel already went through the nozzle
        meters.
      </p>
      <form
        onSubmit={submit}
        className="flex flex-wrap items-end gap-3"
        aria-label="Internal fuel use"
      >
        <SelectField
          label="Taken by"
          value={v.employee}
          onChange={(e) => setV({ ...v, employee: e.target.value })}
        >
          <option value="">Choose</option>
          {(options.data?.employees ?? []).map((x) => (
            <option key={x.id} value={x.id}>
              {x.label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Fuel"
          value={v.fuel}
          onChange={(e) => setV({ ...v, fuel: e.target.value })}
        >
          <option value="">Choose</option>
          {(fuels.data ?? []).map((x) => (
            <option key={x.id} value={x.id}>
              {x.fuel_type}
            </option>
          ))}
        </SelectField>
        <DecimalField
          label="Litres"
          value={v.litres}
          onChange={(e) => setV({ ...v, litres: e.target.value })}
        />
        <TextField
          label="Vehicle / machine"
          placeholder="MH12AB1234, Genset, Omni"
          value={v.vehicle}
          onChange={(e) => setV({ ...v, vehicle: e.target.value })}
        />
        <Button type="submit" variant="primary" loading={save.isPending}>
          Record
        </Button>
        {error && (
          <p role="alert" className="w-full text-sm font-medium text-danger-fg">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

export function ShiftTotalsPage() {
  const shifts = useGet<S['ShiftOut'][]>(['shift-totals', 'shifts'], '/shifts');
  const [chosen, setChosen] = useState('');
  const list = (shifts.data ?? []).slice(0, 30);
  const shiftId = chosen || list[0]?.id || '';
  const rows = useGet<Row[]>(
    ['shift-totals', 'rows', shiftId],
    `/shift-totals/${shiftId}`,
    shiftId !== '',
  );
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Card, DTP Card, Phone Pay and PTM totals"
        subtitle="One total per payment mode for the shift, from the attendants' slips. These are the lines of Shift Transaction Details on the daily report."
      />
      {shifts.isLoading ? (
        <LoadingBlock rows={2} />
      ) : shifts.isError ? (
        <ErrorState error={shifts.error} onRetry={() => void shifts.refetch()} />
      ) : list.length === 0 ? (
        <p className="text-sm text-muted">There is no shift yet. Open a shift first.</p>
      ) : (
        <>
          <SelectField label="Shift" value={shiftId} onChange={(e) => setChosen(e.target.value)}>
            {list.map((s) => (
              <option key={s.id} value={s.id}>
                {formatDate(s.shift_date)} - {s.shift_label} ({s.status})
              </option>
            ))}
          </SelectField>
          {rows.isLoading ? (
            <LoadingBlock rows={3} />
          ) : rows.isError ? (
            <ErrorState error={rows.error} onRetry={() => void rows.refetch()} />
          ) : (
            <ul className="flex flex-col gap-2" aria-label="Payment mode totals">
              {(rows.data ?? []).map((r) => (
                <ModeRow key={`${shiftId}-${r.tender_id}-${r.amount}`} shiftId={shiftId} row={r} />
              ))}
            </ul>
          )}
          <InternalFuel shiftId={shiftId} />
        </>
      )}
    </div>
  );
}
