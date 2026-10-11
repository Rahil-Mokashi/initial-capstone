import { RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { DocumentActions } from '@/components/DocumentActions';
import { PageHeader } from '@/components/PageHeader';
import { ReportTable } from '@/components/ReportTable';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { TabbedPanel } from '@/components/ui/TabbedPanel';
import { todayIso } from '@/lib/format';

type S = components['schemas'];
type View = S['ReportView'];

const PERIODS = [
  ['day', 'Daily'],
  ['week', 'Weekly'],
  ['month', 'Monthly'],
  ['quarter', 'Quarterly'],
  ['year', 'Yearly'],
] as const;

function PerformanceTab() {
  const [period, setPeriod] = useState<string>('day');
  const [asOf, setAsOf] = useState(todayIso());
  // Generate applies what is typed; the table, print and exports then all use that same selection.
  const [applied, setApplied] = useState({ period: 'day', asOf: todayIso() });
  const qs = (p: { period: string; asOf: string }) => `?period=${p.period}&as_of=${p.asOf}`;
  const report = useGet<View>(
    ['analytics', 'performance', applied],
    `/analytics/performance${qs(applied)}`,
  );
  const files = (['csv', 'xlsx', 'pdf'] as const).map((k) => ({
    label: k === 'xlsx' ? 'Excel' : k.toUpperCase(),
    path: `/analytics/performance/export.${k}${qs(applied)}`,
    filename: `business_performance.${k}`,
  }));
  return (
    <>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-44">
          <SelectField label="Period" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {PERIODS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </SelectField>
        </div>
        <div className="w-44">
          <TextField
            label="As of"
            type="date"
            value={asOf}
            onChange={(e) => e.target.value && setAsOf(e.target.value)}
          />
        </div>
        <Button
          variant="primary"
          loading={report.isFetching}
          onClick={() => setApplied({ period, asOf })}
        >
          <RefreshCw className="size-4" aria-hidden /> Generate
        </Button>
        <div className="ml-auto">
          <DocumentActions
            previewLabel="Print"
            disabled={!report.data}
            getHtml={async () => report.data!.html}
            files={files}
          />
        </div>
      </div>
      <p className="text-sm text-muted">
        Profit figures use the weighted-average purchase cost for each fuel type as of the period
        end - &quot;N/A&quot; means no purchase history exists yet for that fuel.
      </p>
      {report.isLoading ? (
        <LoadingBlock label="Loading performance" rows={4} />
      ) : report.isError ? (
        <ErrorState error={report.error} onRetry={() => void report.refetch()} />
      ) : report.data ? (
        <ReportTable report={report.data} />
      ) : null}
    </>
  );
}

function ForecastTab() {
  const forecast = useGet<S['ForecastOut']>(['analytics', 'forecast'], '/analytics/forecast');
  const files = (['csv', 'xlsx', 'pdf'] as const).map((k) => ({
    label: k === 'xlsx' ? 'Excel' : k.toUpperCase(),
    path: `/analytics/forecast/export.${k}`,
    filename: `sales_forecast.${k}`,
  }));
  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          loading={forecast.isFetching}
          onClick={() => void forecast.refetch()}
        >
          <RefreshCw className="size-4" aria-hidden /> Refresh
        </Button>
        <div className="ml-auto">
          <DocumentActions
            previewLabel="Print"
            disabled={!forecast.data}
            getHtml={async () => forecast.data!.report.html}
            files={files}
          />
        </div>
      </div>
      {forecast.isLoading ? (
        <LoadingBlock label="Loading forecast" rows={3} />
      ) : forecast.isError ? (
        <ErrorState error={forecast.error} onRetry={() => void forecast.refetch()} />
      ) : forecast.data ? (
        <>
          <ReportTable report={forecast.data.report} />
          <div className="flex flex-col gap-3 text-sm text-muted">
            {forecast.data.explanations.map((e, i) => (
              <p key={i}>{e}</p>
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}

export function AnalyticsPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Business Insights"
        subtitle="Period performance and a trend-based sales forecast."
      />
      <TabbedPanel
        label="Business insights"
        tabs={[
          { value: 'performance', label: 'Performance', content: <PerformanceTab /> },
          { value: 'forecast', label: 'Sales Forecast', content: <ForecastTab /> },
        ]}
      />
    </div>
  );
}
