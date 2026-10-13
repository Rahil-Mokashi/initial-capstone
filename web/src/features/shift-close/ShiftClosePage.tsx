import { useState } from 'react';
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
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { formatDate, groupDigits } from '@/lib/format';

type S = components['schemas'];
const cell = 'border border-line px-3 py-2';
const trim = (v: string | null | undefined) =>
  v == null ? '' : v.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');

/** The shift's closing master readings, typed in one go. Credit bills should already be entered (they are billed first). */
export function ShiftClosePage() {
  const toast = useToast();
  const shifts = useGet<S['ShiftOut'][]>(['shift-close', 'shifts'], '/shifts');
  const open = (shifts.data ?? []).slice(0, 20);
  const [chosen, setChosen] = useState('');
  const shiftId = chosen || open.find((s) => s.status === 'open')?.id || open[0]?.id || '';
  const sheet = useGet<S['CloseLineOut'][]>(
    ['shift-close', 'sheet', shiftId],
    `/shift-close/${shiftId}`,
    shiftId !== '',
  );
  const [closing, setClosing] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState<Record<string, string>>({});
  const [opening, setOpening] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['CloseEntryIn']) => api.post(`/shift-close/${shiftId}`, b),
    ['shift-close', 'tanks', 'sales', 'checks', 'daily-report', 'shifts'],
  );
  const lines = sheet.data ?? [];
  const typed = lines.filter((l) => !l.closed && closing[l.nozzle_id]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Shift Close"
        subtitle="Type the closing master reading of each nozzle. The opening reading is the last closing. Whatever was not billed to a credit customer is recorded as the shift's cash and card sale."
      />
      {shifts.isLoading ? (
        <LoadingBlock rows={2} />
      ) : (
        <SelectField label="Shift" value={shiftId} onChange={(e) => setChosen(e.target.value)}>
          {open.map((s) => (
            <option key={s.id} value={s.id}>
              {formatDate(s.shift_date)} - {s.shift_label} ({s.status})
            </option>
          ))}
        </SelectField>
      )}
      <p className="text-sm text-muted">
        Enter the shift&apos;s{' '}
        <Link className="underline" to="/terminal">
          credit bills
        </Link>{' '}
        first: they are subtracted from what the meters show. After this, type the{' '}
        <Link className="underline" to="/shift-totals">
          Card, DTP Card, Phone Pay and PTM totals
        </Link>
        , expenses, Advance, Final and bank deposits.
      </p>
      {shifts.isLoading || sheet.isLoading || (shiftId !== '' && !sheet.data && !sheet.isError) ? (
        <LoadingBlock rows={3} />
      ) : sheet.isError ? (
        <ErrorState error={sheet.error} onRetry={() => void sheet.refetch()} />
      ) : (
        <form
          aria-label="Closing readings"
          className="flex flex-col gap-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await save.mutateAsync({
                readings: typed.map((l) => ({
                  nozzle_id: l.nozzle_id,
                  closing: closing[l.nozzle_id]!,
                  testing: testing[l.nozzle_id] || '0',
                  opening: l.opening == null ? opening[l.nozzle_id] || null : null,
                })),
              });
              toast.success(`${typed.length} nozzle(s) closed.`);
              setClosing({});
              setTesting({});
            } catch (err) {
              setError(friendlyMessage(err));
            }
          }}
        >
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm" aria-label="Nozzle readings">
              <thead>
                <tr className="bg-surface-2 text-left">
                  <th className={cell}>Nozzle</th>
                  <th className={cell}>Fuel / tank</th>
                  <th className={`${cell} text-right`}>Opening</th>
                  <th className={cell}>Closing reading</th>
                  <th className={cell}>Testing (L)</th>
                  <th className={cell} />
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.nozzle_id}>
                    <th scope="row" className={`${cell} text-left`}>
                      {l.code}
                    </th>
                    <td className={cell}>
                      {l.fuel}
                      {l.tank ? ` / ${l.tank}` : ''}
                    </td>
                    <td className={`${cell} num text-right`}>
                      {l.opening != null ? (
                        groupDigits(trim(l.opening))
                      ) : (
                        <DecimalField
                          label={`Opening for ${l.code}`}
                          value={opening[l.nozzle_id] ?? ''}
                          onChange={(e) =>
                            setOpening({ ...opening, [l.nozzle_id]: e.target.value })
                          }
                        />
                      )}
                    </td>
                    <td className={cell}>
                      {l.closed ? (
                        <span className="num">{groupDigits(trim(l.closing))}</span>
                      ) : (
                        <DecimalField
                          label={`Closing for ${l.code}`}
                          value={closing[l.nozzle_id] ?? ''}
                          onChange={(e) =>
                            setClosing({ ...closing, [l.nozzle_id]: e.target.value })
                          }
                        />
                      )}
                    </td>
                    <td className={cell}>
                      {l.closed ? (
                        trim(l.testing)
                      ) : (
                        <DecimalField
                          label={`Testing for ${l.code}`}
                          value={testing[l.nozzle_id] ?? ''}
                          onChange={(e) =>
                            setTesting({ ...testing, [l.nozzle_id]: e.target.value })
                          }
                        />
                      )}
                    </td>
                    <td className={cell}>
                      {l.closed && <StatusBadge tone="ok">Closed</StatusBadge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <FormError message={error} />
          <div>
            <Button
              type="submit"
              variant="primary"
              loading={save.isPending}
              disabled={typed.length === 0}
            >
              Close {typed.length || ''} nozzle(s)
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
