import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { DocumentActions } from '@/components/DocumentActions';
import { PageHeader } from '@/components/PageHeader';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TextField } from '@/components/ui/Field';
import { formatCheckValue } from '@/features/checks/checkText';
import { formatMoney, groupDigits, todayIso } from '@/lib/format';

type S = components['schemas'];

// The structure of the report JSON (app/services/daily_report_service.py report_to_dict). Numbers are strings.
interface Shift {
  number: number;
  shift_id: string | null;
  litres_by_tank: Record<string, string>;
  oil_rs: string;
  total_sale: string;
  lines: Array<[string, string]>;
  lines_total: string;
  cash_in_hand: string;
}
interface Report {
  tanks: Array<{ tank_id: string; code: string }>;
  shifts: Shift[];
  opening: Record<string, string>;
  purchase: Record<string, string>;
  testing: Record<string, string>;
  total_stock: Record<string, string>;
  closing: Record<string, string | null>;
  plus_minus: Record<string, string | null>;
  total_rs: string;
}

const litres = (v: string | null | undefined) => (v == null ? '' : groupDigits(v));
const trim = (v: string) => (v.includes('.') ? v.replace(/0+$/, '').replace(/\.$/, '') : v);

function sum(values: Array<string | null | undefined>): string | null {
  const nums = values.filter((v): v is string => v != null);
  if (nums.length === 0) return null;
  // litres have three places: add as integers of thousandths so nothing floats
  const thousandths = nums.reduce((a, v) => {
    const [i = '0', f = ''] = v.replace('-', '').split('.');
    const n = BigInt(i + f.padEnd(3, '0').slice(0, 3));
    return v.startsWith('-') ? a - n : a + n;
  }, 0n);
  const neg = thousandths < 0n;
  const s = (neg ? -thousandths : thousandths).toString().padStart(4, '0');
  return `${neg ? '-' : ''}${s.slice(0, -3)}.${s.slice(-3)}`;
}

function SaleDetails({ r }: { r: Report }) {
  const ids = r.tanks.map((t) => t.tank_id);
  const rows: Array<{
    label: string;
    per: Record<string, string | null>;
    oil?: string;
    sale?: string;
  }> = [
    { label: 'O/S', per: r.opening },
    { label: 'Purchase', per: r.purchase },
    ...r.shifts.map((s) => ({
      label: `Shift${s.number}`,
      per: s.litres_by_tank as Record<string, string | null>,
      oil: s.shift_id ? formatMoney(s.oil_rs) : '',
      sale: s.shift_id ? formatMoney(s.total_sale) : '',
    })),
    { label: 'Testing', per: r.testing },
    { label: 'Total Stock', per: r.total_stock },
    { label: '(+/-)', per: r.plus_minus },
    { label: 'Closing Stock', per: r.closing },
  ];
  return (
    <section aria-labelledby="sale-details" className="overflow-x-auto">
      <h2 id="sale-details" className="mb-2 text-base font-bold">
        Sale Details
      </h2>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-surface-2 text-left">
            <th className="border border-line px-3 py-2" />
            {r.tanks.map((t) => (
              <th key={t.tank_id} className="num border border-line px-3 py-2 text-right">
                {t.code}
              </th>
            ))}
            <th className="border border-line px-3 py-2 text-right">Total</th>
            <th className="border border-line px-3 py-2 text-right">Oil</th>
            <th className="border border-line px-3 py-2 text-right">Total Sale</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row" className="border border-line px-3 py-2 text-left font-semibold">
                {row.label}
              </th>
              {ids.map((id) => (
                <td key={id} className="num border border-line px-3 py-2 text-right">
                  {litres(row.per[id] ? trim(row.per[id]!) : row.per[id])}
                </td>
              ))}
              <td className="num border border-line px-3 py-2 text-right">
                {litres(sum(ids.map((id) => row.per[id])))}
              </td>
              <td className="num border border-line px-3 py-2 text-right">{row.oil ?? ''}</td>
              <td className="num border border-line px-3 py-2 text-right">{row.sale ?? ''}</td>
            </tr>
          ))}
          <tr className="bg-surface-2 font-bold">
            <th scope="row" className="border border-line px-3 py-2 text-left">
              Total Rs
            </th>
            <td colSpan={ids.length + 2} className="border border-line px-3 py-2" />
            <td className="num border border-line px-3 py-2 text-right">
              {formatMoney(r.total_rs)}
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

function ShiftTotals({ r }: { r: Report }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {r.shifts.map((s) => (
        <section
          key={s.number}
          aria-label={`Shift ${s.number} Transaction Details`}
          className="rounded-lg border border-line bg-surface p-4"
        >
          <h2 className="mb-2 text-base font-bold">Shift {s.number} Transaction Details</h2>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
            {s.lines.map(([label, amount]) => (
              <div key={label} className="contents">
                <dt>{label}</dt>
                <dd className="num text-right">{formatMoney(amount)}</dd>
              </div>
            ))}
            <dt className="border-t border-line pt-1 font-bold">Total</dt>
            <dd className="num border-t border-line pt-1 text-right font-bold">
              {s.shift_id ? formatMoney(s.lines_total) : ''}
            </dd>
          </dl>
          {s.shift_id &&
            (s.lines_total === s.total_sale ? (
              <p className="mt-2">
                <StatusBadge tone="ok">Equals the shift's Total Sale</StatusBadge>
              </p>
            ) : (
              <p className="mt-2">
                <StatusBadge tone="danger">
                  {`Does not equal Total Sale ${formatMoney(s.total_sale)}`}
                </StatusBadge>
              </p>
            ))}
        </section>
      ))}
    </div>
  );
}

export function DailyReportPage() {
  const [day, setDay] = useState(todayIso());
  const report = useGet<S['DailyReportOut']>(['daily-report', day], `/daily-report?day=${day}`);
  const checks = useGet<S['DayChecksOut']>(['checks', 'report', day], `/checks?day=${day}`);
  const data = report.data;
  const r = data?.report as unknown as Report | undefined;
  const failing = (checks.data?.results ?? []).filter(
    (c) => c.area !== 'Credit' && c.status === 'fail',
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Daily Report"
        subtitle="The two-sided report, built from the day's records. Print preview shows both sides exactly as they print."
      >
        <DocumentActions
          previewLabel="Print preview (both sides)"
          disabled={!data}
          getHtml={async () => data!.html}
        />
      </PageHeader>
      <div className="flex flex-wrap items-end gap-3">
        <TextField label="Day" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        {data && (
          <p className="pb-3 text-sm text-muted">
            Style: <strong>{data.style === 'plus' ? 'Plus' : 'Classic'}</strong>
          </p>
        )}
      </div>
      {report.isLoading ? (
        <LoadingBlock label="Building the report" rows={4} />
      ) : report.isError ? (
        <ErrorState error={report.error} onRetry={() => void report.refetch()} />
      ) : r ? (
        <>
          {checks.data && (
            <p
              role="status"
              className={failing.length > 0 ? 'font-bold text-danger-fg' : 'font-semibold'}
            >
              {checks.data.summary.passed} of {checks.data.summary.total} checks passed
              {failing.length > 0
                ? `. Not matching: ${failing.map((f) => f.sentence).join('; ')}`
                : ''}{' '}
              <Link className="underline" to="/checks">
                See all checks
              </Link>
            </p>
          )}
          <SaleDetails r={r} />
          <ShiftTotals r={r} />
          <p className="text-sm text-muted">
            Cash book, credit sales, expenses, oil sale and the bowser van are on the printout (see
            Print preview).
            {r.shifts[0] &&
              ` Shift 1 cash in hand: ${formatCheckValue('rs', r.shifts[0].cash_in_hand)}.`}
          </p>
        </>
      ) : null}
    </div>
  );
}
