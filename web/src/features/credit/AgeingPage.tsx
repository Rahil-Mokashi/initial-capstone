import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { PageHeader } from '@/components/PageHeader';
import { TextField } from '@/components/ui/Field';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDate, formatMoney, todayIso } from '@/lib/format';
import { ChaseList } from './ChaseList';

type S = components['schemas'];

const cell = 'border border-line px-3 py-2';

export function AgeingPage() {
  const [asOf, setAsOf] = useState(todayIso());
  const data = useGet<S['AgeingOut']>(['credit', 'ageing', asOf], `/credit/ageing?as_of=${asOf}`);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Credit Ageing"
        subtitle="Who owes what, and for how long. Payments are counted against the oldest bill first."
      >
        <Link to="/credit" className="text-sm font-semibold underline">
          Credit accounts
        </Link>
      </PageHeader>
      <ChaseList />
      <TextField label="As of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
      {data.isLoading ? (
        <LoadingBlock label="Loading ageing" rows={4} />
      ) : data.isError ? (
        <ErrorState error={data.error} onRetry={() => void data.refetch()} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm" aria-label="Ageing of credit">
            <thead>
              <tr className="bg-surface-2 text-left">
                <th className={cell}>Customer</th>
                {data.data!.bucket_names.map((b) => (
                  <th key={b} className={`${cell} text-right`}>
                    {b} days
                  </th>
                ))}
                <th className={`${cell} text-right`}>Total owed</th>
                <th className={cell}>Oldest unpaid bill</th>
                <th className={cell} />
              </tr>
            </thead>
            <tbody>
              {data.data!.rows.map((r) => (
                <tr key={r.customer_id}>
                  <th scope="row" className={`${cell} text-left`}>
                    <Link
                      className="font-semibold underline"
                      to={`/credit/customers/${r.customer_id}`}
                    >
                      {r.name}
                    </Link>
                  </th>
                  {data.data!.bucket_names.map((b) => (
                    <td key={b} className={`${cell} num text-right`}>
                      {formatMoney(r.buckets[b] ?? '0.00')}
                    </td>
                  ))}
                  <td className={`${cell} num text-right font-semibold`}>
                    {formatMoney(r.balance)}
                  </td>
                  <td className={cell}>
                    {r.oldest_unpaid_ref
                      ? `${r.oldest_unpaid_ref}, ${r.oldest_unpaid_date ? formatDate(r.oldest_unpaid_date) : ''} (${r.oldest_unpaid_age} days)`
                      : 'None'}
                  </td>
                  <td className={cell}>
                    {r.over_limit && <StatusBadge tone="danger">Over limit</StatusBadge>}{' '}
                    {r.overdue && <StatusBadge tone="warn">Overdue</StatusBadge>}
                  </td>
                </tr>
              ))}
              <tr className="bg-surface-2 font-bold">
                <th scope="row" className={`${cell} text-left`}>
                  Total
                </th>
                {data.data!.bucket_names.map((b) => (
                  <td key={b} className={`${cell} num text-right`}>
                    {formatMoney(data.data!.totals[b] ?? '0.00')}
                  </td>
                ))}
                <td className={`${cell} num text-right`}>
                  {formatMoney(data.data!.total_balance)}
                </td>
                <td className={cell} colSpan={2} />
              </tr>
            </tbody>
          </table>
          {data.data!.rows.length === 0 && (
            <p className="mt-3 text-sm text-muted">Nobody owes anything.</p>
          )}
        </div>
      )}
    </div>
  );
}
