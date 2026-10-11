import { ArrowLeft, BarChart3, FileText, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { DocumentActions, type ExportFile } from '@/components/DocumentActions';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { cn } from '@/lib/cn';
import { formatQuantity, titleCase } from '@/lib/format';

type S = components['schemas'];
type View = S['ReportView'];

const useHub = () => useGet<S['Hub']>(['reports', 'hub'], '/reports');
const useChoices = (enabled: boolean) =>
  useGet<S['FilterOptions']>(['reports', 'choices'], '/reports/filter-options', enabled);

interface Filters {
  date_from: string;
  date_to: string;
  employee_id: string;
  nozzle_id: string;
}
const NONE: Filters = { date_from: '', date_to: '', employee_id: '', nozzle_id: '' };

/** Only filters that are actually set go on the URL (never employee_id= as though it were a choice). */
function query(f: Filters): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : '';
}

// ------------------------------------------------------------------- hub
export function ReportsHubPage() {
  const hub = useHub();
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader title="Reports" subtitle="Choose a report to view, print, or export." />
      {hub.isLoading ? (
        <LoadingBlock label="Loading reports" rows={4} />
      ) : hub.isError ? (
        <ErrorState error={hub.error} onRetry={() => void hub.refetch()} />
      ) : (hub.data?.reports.length ?? 0) === 0 && !hub.data?.insights ? (
        <EmptyState title="No reports available for your role yet." />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {hub.data?.reports.map((r) => (
            <li key={r.key}>
              <Link
                to={`/reports/${r.key}`}
                className="flex min-h-[56px] items-center gap-3 rounded-lg border border-line bg-surface px-4 font-semibold shadow-card hover:bg-surface-2"
              >
                <FileText className="size-5 text-muted" aria-hidden /> {r.label}
              </Link>
            </li>
          ))}
          {hub.data?.insights && (
            <li>
              <Link
                to="/analytics"
                className="flex min-h-[56px] items-center gap-3 rounded-lg border border-line bg-surface px-4 font-semibold shadow-card hover:bg-surface-2"
              >
                <BarChart3 className="size-5 text-muted" aria-hidden /> Business Insights
                (Performance &amp; Forecast)
              </Link>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------- fuel type cards
function FuelCards() {
  const cards = useGet<S['FuelCard'][]>(
    ['reports', 'fuel-cards'],
    '/reports/fuel-type-summary/cards',
  );
  if (cards.isLoading) return <LoadingBlock label="Loading fuel summary" rows={3} />;
  if (cards.isError) return <ErrorState error={cards.error} onRetry={() => void cards.refetch()} />;
  if (!cards.data?.length)
    return <p className="text-sm text-muted">No fuel types configured yet.</p>;
  return (
    <ul className="grid gap-4 md:grid-cols-2">
      {cards.data.map((c) => (
        <li
          key={c.fuel_type}
          className="flex flex-col gap-1.5 rounded-lg border border-line bg-surface p-5 shadow-card"
        >
          <h2 className="text-lg font-bold">{c.fuel_type}</h2>
          <p>Tanks: {c.tank_count}</p>
          <p>Total capacity: {formatQuantity(c.total_capacity)} L</p>
          <p>Total current stock: {formatQuantity(c.total_current_stock)} L</p>
          <p>
            Nozzles: {c.active_nozzle_count} active / {c.nozzle_count} total
          </p>
          {c.latest_variance_classification && (
            <p>
              Latest reconciliation variance: {c.latest_variance_percent}% (
              {titleCase(c.latest_variance_classification)})
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------- one report
export function ReportPage() {
  const { key = '' } = useParams();
  const hub = useHub();
  const entry = hub.data?.reports.find((r) => r.key === key);
  const [draft, setDraft] = useState<Filters>(NONE);
  const [applied, setApplied] = useState<Filters>(NONE);
  const choices = useChoices(Boolean(entry?.filters.length));
  const report = useGet<View>(
    ['reports', 'run', key, applied],
    `/reports/${key}${query(applied)}`,
    Boolean(entry),
  );

  const employees = choices.data?.employees ?? [];
  const nozzles = choices.data?.nozzles ?? [];
  // Print / export fetch with the filters as they are NOW (the person may not have pressed Refresh), as in Qt.
  const files: ExportFile[] = [
    { label: 'CSV', path: `/reports/${key}/export.csv${query(draft)}`, filename: `${key}.csv` },
    { label: 'Excel', path: `/reports/${key}/export.xlsx${query(draft)}`, filename: `${key}.xlsx` },
    { label: 'PDF', path: `/reports/${key}/export.pdf${query(draft)}`, filename: `${key}.pdf` },
  ];
  const isMoney = new Set(report.data?.money_columns ?? []);
  const isVolume = new Set(report.data?.volume_columns ?? []);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <Link
        to="/reports"
        className="inline-flex min-h-[44px] w-fit items-center gap-1.5 text-sm font-semibold underline-offset-4 hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden /> All reports
      </Link>
      {hub.isLoading ? (
        <LoadingBlock label="Loading" rows={2} />
      ) : !entry ? (
        <EmptyState title="That report is not available to you." />
      ) : (
        <>
          <PageHeader title={report.data?.title ?? entry.label} />
          <div className="flex flex-wrap items-end gap-3">
            {entry.dates && (
              <>
                <div className="w-44">
                  <TextField
                    label="From"
                    type="date"
                    value={draft.date_from}
                    onChange={(e) => setDraft({ ...draft, date_from: e.target.value })}
                  />
                </div>
                <div className="w-44">
                  <TextField
                    label="To"
                    type="date"
                    value={draft.date_to}
                    onChange={(e) => setDraft({ ...draft, date_to: e.target.value })}
                  />
                </div>
              </>
            )}
            {entry.filters.includes('employee') && employees.length > 0 && (
              <div className="w-56">
                <SelectField
                  label="Employee"
                  value={draft.employee_id}
                  onChange={(e) => setDraft({ ...draft, employee_id: e.target.value })}
                >
                  <option value="">All employees</option>
                  {employees.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </SelectField>
              </div>
            )}
            {entry.filters.includes('nozzle') && nozzles.length > 0 && (
              <div className="w-48">
                <SelectField
                  label="Nozzle"
                  value={draft.nozzle_id}
                  onChange={(e) => setDraft({ ...draft, nozzle_id: e.target.value })}
                >
                  <option value="">All nozzles</option>
                  {nozzles.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </SelectField>
              </div>
            )}
            <Button
              variant="primary"
              onClick={() =>
                JSON.stringify(draft) === JSON.stringify(applied)
                  ? void report.refetch()
                  : setApplied(draft)
              }
              loading={report.isFetching}
            >
              <RefreshCw className="size-4" aria-hidden /> Refresh
            </Button>
            <div className="ml-auto">
              <DocumentActions
                previewLabel="Print"
                getHtml={async () => (await api.get<View>(`/reports/${key}${query(draft)}`)).html}
                files={files}
              />
            </div>
          </div>

          {key === 'fuel_type_summary' ? (
            <FuelCards />
          ) : report.isLoading ? (
            <LoadingBlock label="Loading report" rows={5} />
          ) : report.isError ? (
            <ErrorState error={report.error} onRetry={() => void report.refetch()} />
          ) : report.data ? (
            <div className="overflow-x-auto rounded-lg border border-line bg-surface shadow-card">
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">{report.data.title}</caption>
                <thead className="bg-surface-2">
                  <tr>
                    {report.data.headers.map((h, i) => (
                      <th
                        key={`${h}-${i}`}
                        scope="col"
                        className={cn(
                          'border-b border-line px-4 py-2 text-xs font-bold tracking-wide text-muted uppercase',
                          isMoney.has(i) || isVolume.has(i) ? 'text-right' : 'text-left',
                        )}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.data.rows.length === 0 ? (
                    <tr>
                      <td
                        colSpan={Math.max(report.data.headers.length, 1)}
                        className="px-4 py-6 text-center text-muted"
                      >
                        Nothing to report for this selection.
                      </td>
                    </tr>
                  ) : (
                    report.data.rows.map((row, r) => (
                      <tr key={r} className="border-b border-line last:border-0">
                        {row.map((cell, i) => (
                          <td
                            key={i}
                            className={cn(
                              'px-4 py-1.5',
                              isMoney.has(i) || isVolume.has(i) ? 'num text-right' : '',
                            )}
                          >
                            {isMoney.has(i) || isVolume.has(i) ? formatQuantity(cell) : cell}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
