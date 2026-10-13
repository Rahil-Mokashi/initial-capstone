import { CheckCircle2, OctagonAlert, TriangleAlert } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField } from '@/components/ui/Field';
import { FormError } from '@/components/ui/FormDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { formatDate, formatMoney, groupDigits } from '@/lib/format';

type S = components['schemas'];
type Desk = S['DeskOut'];
type Tally = S['DeskTallyOut'];

const cell = 'border border-line px-3 py-2';
const trim = (v: string | null | undefined) => (v == null ? '' : v.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, ''));
const rupees = (v: string) => formatMoney(v);

/** What the person has typed so far. Nothing here is a total: the Main PC does every sum. */
interface Typed {
  closing: Record<string, string>;
  testing: Record<string, string>;
  opening: Record<string, string>;
  modes: Record<string, string>;
  advance: string;
  final: string;
}
const EMPTY: Typed = { closing: {}, testing: {}, opening: {}, modes: {}, advance: '', final: '' };

export function buildBody(desk: Desk, t: Typed): S['DeskIn'] {
  return {
    readings: desk.nozzles
      .filter((n) => !n.closed && t.closing[n.nozzle_id])
      .map((n) => ({
        nozzle_id: n.nozzle_id,
        closing: t.closing[n.nozzle_id]!,
        testing: t.testing[n.nozzle_id] || '0',
        opening: n.opening == null ? t.opening[n.nozzle_id] || null : null,
      })),
    modes: desk.modes.filter((m) => t.modes[m.tender_id] !== undefined && t.modes[m.tender_id] !== '').map((m) => ({ tender_id: m.tender_id, amount: t.modes[m.tender_id]! })),
    advance: desk.cash.recorded || t.advance === '' ? null : t.advance,
    final: desk.cash.recorded || t.final === '' ? null : t.final,
  };
}

function Verdict({ tally, working }: { tally: Tally; working: boolean }) {
  const amount = rupees(tally.difference.replace('-', ''));
  const look =
    tally.status === 'balanced'
      ? { cls: 'border-ok bg-ok-bg text-ok-fg', Icon: CheckCircle2, text: 'Balanced', note: 'The money collected matches the sale.' }
      : tally.status === 'short'
        ? { cls: 'border-danger bg-danger-bg text-danger-fg', Icon: OctagonAlert, text: `Short ${amount}`, note: 'Less money was collected than the meters say was sold.' }
        : { cls: 'border-warn bg-warn-bg text-warn-fg', Icon: TriangleAlert, text: `Excess ${amount}`, note: 'More money was collected than the meters say was sold.' };
  return (
    <div role="status" aria-live="polite" className={`rounded-lg border-2 p-4 ${look.cls}`}>
      <div className="flex items-center gap-2 text-2xl font-bold">
        <look.Icon className="size-6" aria-hidden /> {look.text}
      </div>
      <p className="mt-1 text-sm">{working ? 'Checking...' : look.note}</p>
    </div>
  );
}

/**
 * Close a shift on ONE screen: type the closing master readings and how the money was collected, and watch the tally
 * (and any shortage) update as you type. Saving writes everything together or nothing.
 */
export function CloseShiftPage() {
  const toast = useToast();
  const shifts = useGet<S['ShiftOut'][]>(['close-desk', 'shifts'], '/shifts');
  const list = (shifts.data ?? []).slice(0, 20);
  const [chosen, setChosen] = useState('');
  const shiftId = chosen || list.find((s) => s.status === 'open')?.id || list[0]?.id || '';
  const desk = useGet<Desk>(['close-desk', 'desk', shiftId], `/close-shift/${shiftId}`, shiftId !== '');
  const [typed, setTyped] = useState<Typed>(EMPTY);
  const [preview, setPreview] = useState<Tally | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const data = desk.data;
  const seeded = useRef('');

  // A different shift starts clean; the usual testing litres are filled in once per shift.
  useEffect(() => {
    setTyped(EMPTY);
    setPreview(null);
    setError(null);
    seeded.current = '';
  }, [shiftId]);
  useEffect(() => {
    if (!data || seeded.current === data.shift_id) return;
    seeded.current = data.shift_id;
    setTyped((t) => ({ ...t, testing: Object.fromEntries(data.nozzles.filter((n) => !n.closed).map((n) => [n.nozzle_id, trim(data.default_testing)])) }));
  }, [data]);

  const body = useMemo(() => (data ? buildBody(data, typed) : null), [data, typed]);
  const anything = !!body && (body.readings!.length > 0 || body.modes!.length > 0 || body.advance != null || body.final != null);

  // The tally follows the typing (half a second after the last key). The Main PC runs the real save and rolls it back.
  useEffect(() => {
    if (!body || !anything) {
      setPreview(null);
      return;
    }
    let live = true;
    setWorking(true);
    const timer = window.setTimeout(async () => {
      try {
        const out = await api.post<Desk>(`/close-shift/${shiftId}/tally`, body);
        if (live) {
          setPreview(out.tally);
          setError(null);
        }
      } catch (err) {
        if (live) {
          setPreview(null);
          setError(friendlyMessage(err));
        }
      } finally {
        if (live) setWorking(false);
      }
    }, 500);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [body, anything, shiftId]);

  const save = useWrite((b: S['DeskIn']) => api.post<Desk>(`/close-shift/${shiftId}`, b), ['close-desk', 'tanks', 'sales', 'checks', 'daily-report', 'shifts', 'shift-close', 'shift-totals']);

  if (shifts.isLoading || (shiftId && desk.isLoading)) return <LoadingBlock label="Loading the shift" rows={4} />;
  if (desk.isError) return <ErrorState error={desk.error} onRetry={() => void desk.refetch()} />;
  const tally = preview ?? data?.tally;
  const typedCount = body ? body.readings!.length : 0;

  const submit = async () => {
    if (!body) return;
    setError(null);
    try {
      await save.mutateAsync(body);
      toast.success('Shift closed and saved.');
      setTyped(EMPTY);
      setPreview(null);
      seeded.current = '';
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader title="Close Shift" subtitle="Type the closing readings and how the money was collected. The tally and any shortage appear as you type; nothing is saved until you press Close shift." />
      <SelectField label="Shift" value={shiftId} onChange={(e) => setChosen(e.target.value)}>
        {list.map((s) => (
          <option key={s.id} value={s.id}>
            {formatDate(s.shift_date)} - {s.shift_label} ({s.status})
          </option>
        ))}
      </SelectField>
      {data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
          <div className="flex flex-col gap-6">
            <section aria-labelledby="h-readings" className="rounded-lg border border-line bg-surface p-4 shadow-card">
              <h2 id="h-readings" className="mb-1 text-lg font-semibold">1. Meter readings</h2>
              <p className="mb-3 text-sm text-muted">
                The opening reading is the last closing, filled in for you. Testing litres go back into the tank, so they are not counted as sold.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm" aria-label="Nozzle readings">
                  <thead>
                    <tr className="bg-surface-2 text-left">
                      <th className={cell}>Nozzle</th>
                      <th className={cell}>Fuel</th>
                      <th className={`${cell} text-right`}>Opening</th>
                      <th className={cell}>Closing reading</th>
                      <th className={cell}>Testing (L)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.nozzles.map((n) => (
                      <tr key={n.nozzle_id}>
                        <th scope="row" className={`${cell} text-left`}>{n.code}</th>
                        <td className={cell}>{n.fuel}</td>
                        <td className={`${cell} num text-right`}>
                          {n.opening != null ? (
                            groupDigits(trim(n.opening))
                          ) : (
                            <DecimalField label={`Opening for ${n.code}`} value={typed.opening[n.nozzle_id] ?? ''} onChange={(e) => setTyped({ ...typed, opening: { ...typed.opening, [n.nozzle_id]: e.target.value } })} />
                          )}
                        </td>
                        <td className={cell}>
                          {n.closed ? (
                            <span className="num">{groupDigits(trim(n.closing))} (closed)</span>
                          ) : (
                            <DecimalField label={`Closing for ${n.code}`} value={typed.closing[n.nozzle_id] ?? ''} onChange={(e) => setTyped({ ...typed, closing: { ...typed.closing, [n.nozzle_id]: e.target.value } })} />
                          )}
                        </td>
                        <td className={cell}>
                          {n.closed ? (
                            trim(n.testing)
                          ) : (
                            <DecimalField label={`Testing for ${n.code}`} value={typed.testing[n.nozzle_id] ?? ''} onChange={(e) => setTyped({ ...typed, testing: { ...typed.testing, [n.nozzle_id]: e.target.value } })} />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section aria-labelledby="h-money" className="rounded-lg border border-line bg-surface p-4 shadow-card">
              <h2 id="h-money" className="mb-1 text-lg font-semibold">2. Money collected</h2>
              <p className="mb-3 text-sm text-muted">
                Cash is what was handed to the office (Advance and Final). Credit bills are typed during the shift on the{' '}
                <Link className="underline" to="/terminal">Terminal</Link>; expenses on{' '}
                <Link className="underline" to="/expenses">Expenses</Link>. Both are counted for you.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <DecimalField label={data.cash.recorded ? 'Advance (recorded earlier)' : 'Advance'} maxFraction={2} unit="rupees" disabled={data.cash.recorded} value={data.cash.recorded ? trim(data.cash.advance) : typed.advance} onChange={(e) => setTyped({ ...typed, advance: e.target.value })} />
                <DecimalField label={data.cash.recorded ? 'Final (recorded earlier)' : 'Final'} maxFraction={2} unit="rupees" disabled={data.cash.recorded} value={data.cash.recorded ? trim(data.cash.final) : typed.final} onChange={(e) => setTyped({ ...typed, final: e.target.value })} />
                {data.modes.map((m) => (
                  <DecimalField key={m.tender_id} label={m.label} maxFraction={2} unit="rupees" value={typed.modes[m.tender_id] ?? (m.amount != null ? trim(m.amount) : '')} onChange={(e) => setTyped({ ...typed, modes: { ...typed.modes, [m.tender_id]: e.target.value } })} />
                ))}
              </div>
            </section>
          </div>

          {tally && (
            <aside aria-label="Tally" className="flex h-fit flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-card lg:sticky lg:top-4">
              <h2 className="text-lg font-semibold">Tally</h2>
              <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-sm">
                <dt>Fuel sold (from the meters)</dt>
                <dd className="num text-right">{rupees(tally.fuel_rs)}</dd>
                {tally.oil_rs !== '0.00' && (
                  <>
                    <dt>Oil sold</dt>
                    <dd className="num text-right">{rupees(tally.oil_rs)}</dd>
                  </>
                )}
                <dt className="font-semibold">Total sale</dt>
                <dd className="num text-right font-semibold">{rupees(tally.total_sale)}</dd>
              </dl>
              <hr className="border-line" />
              <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-sm" aria-label="Collected">
                {tally.lines.filter((l) => l.amount !== '0.00' || ['Advance', 'Final', 'CARD'].includes(l.label)).map((l) => (
                  <div key={l.label} className="contents">
                    <dt>{l.label === 'CreditSale' ? `Credit bills (${tally.credit_count})` : l.label === 'Expenses' ? `Expenses (${tally.expenses_count})` : l.label}</dt>
                    <dd className="num text-right">{rupees(l.amount)}</dd>
                  </div>
                ))}
                <dt className="font-semibold">Collected</dt>
                <dd className="num text-right font-semibold">{rupees(tally.collected)}</dd>
              </dl>
              <Verdict tally={tally} working={working} />
              {tally.pending_expenses > 0 && (
                <p className="text-sm text-warn-fg">{tally.pending_expenses} expense(s) are not approved yet; they are counted.</p>
              )}
              <FormError message={error} />
              <Button variant="primary" loading={save.isPending} disabled={!anything || !!error} onClick={() => void submit()}>
                Close shift{typedCount ? ` (${typedCount} nozzle${typedCount > 1 ? 's' : ''})` : ''}
              </Button>
            </aside>
          )}
        </div>
      )}
    </div>
  );
}
