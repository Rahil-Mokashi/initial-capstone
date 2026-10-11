import type { components } from '@/api/schema';
import { cn } from '@/lib/cn';
import { formatQuantity } from '@/lib/format';

type View = components['schemas']['ReportView'];

/**
 * A generic report table: strings as the server formatted them, except money / litre columns,
 * which are right-aligned and grouped the Indian way (12,34,567.00), as in the Qt tables.
 */
export function ReportTable({
  report,
  empty = 'Nothing to report for this selection.',
}: {
  report: View;
  empty?: string;
}) {
  const numeric = new Set([...report.money_columns, ...report.volume_columns]);
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface shadow-card">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{report.title}</caption>
        <thead className="bg-surface-2">
          <tr>
            {report.headers.map((h, i) => (
              <th
                key={`${h}-${i}`}
                scope="col"
                className={cn(
                  'border-b border-line px-4 py-2 text-xs font-bold tracking-wide text-muted uppercase',
                  numeric.has(i) ? 'text-right' : 'text-left',
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {report.rows.length === 0 ? (
            <tr>
              <td
                colSpan={Math.max(report.headers.length, 1)}
                className="px-4 py-6 text-center text-muted"
              >
                {empty}
              </td>
            </tr>
          ) : (
            report.rows.map((row, r) => (
              <tr key={r} className="border-b border-line last:border-0">
                {row.map((cell, i) => (
                  <td key={i} className={cn('px-4 py-1.5', numeric.has(i) && 'num text-right')}>
                    {numeric.has(i) ? formatQuantity(cell) : cell}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
