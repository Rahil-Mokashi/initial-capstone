import { Link } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { components } from '@/api/schema';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDate, formatMoney } from '@/lib/format';

type S = components['schemas'];

/** Who to chase today: promises that have come due first, then customers past their payment terms. In-app only. */
export function ChaseList({ limit }: { limit?: number }) {
  const due = useGet<S['DueOut'][]>(['credit', 'chase'], '/credit/chase', true, 120_000);
  const items = (due.data ?? []).slice(0, limit);
  return (
    <section aria-labelledby="chase-title" className="flex flex-col gap-2">
      <h2 id="chase-title" className="text-base font-bold">
        To chase today
      </h2>
      {due.isLoading ? (
        <p className="text-sm text-muted">Looking for promises that have come due…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">Nobody needs chasing today.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((i) => (
            <li
              key={`${i.customer_id}-${i.follow_up_id ?? 'overdue'}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-surface p-3 text-sm"
            >
              <span>
                <Link className="font-semibold underline" to={`/credit/customers/${i.customer_id}`}>
                  {i.name}
                </Link>{' '}
                owes {formatMoney(i.balance)}. {i.detail}
                {i.promised_amount ? ` (${formatMoney(i.promised_amount)}` : ''}
                {i.promised_amount && i.promised_date
                  ? ` by ${formatDate(i.promised_date)})`
                  : i.promised_amount
                    ? ')'
                    : ''}
              </span>
              <StatusBadge tone={i.reason === 'promise' ? 'warn' : 'danger'}>
                {i.reason === 'promise' ? 'Promise due' : 'Overdue'}
              </StatusBadge>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
