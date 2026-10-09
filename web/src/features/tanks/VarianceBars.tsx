import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { formatDate, formatLitres, formatQuantity, titleCase } from '@/lib/format';
import { varianceFractions, varianceTone, type VarianceTone } from '@/lib/variance';
import type { Reconciliation } from '@/api/types';

const BAR_COLOR: Record<VarianceTone, string> = {
  normal: 'var(--text)', // neutral ink; light in the dark theme, as in the Qt card
  warning: 'var(--warn)',
  critical: 'var(--danger)',
};

const BADGE_TONE: Record<VarianceTone, Tone> = {
  normal: 'neutral',
  warning: 'warn',
  critical: 'danger',
};

function Bar({
  label,
  value,
  fraction,
  tone,
}: {
  label: string;
  value: string;
  fraction: number;
  tone: VarianceTone;
}) {
  const valueText = formatLitres(value);
  return (
    <div className="flex flex-col gap-1">
      <p className="num text-sm">
        <span className="text-muted">{label}: </span>
        <strong>{valueText}</strong>
      </p>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fraction * 100)}
        aria-valuetext={`${label}: ${valueText}`}
        className="h-[22px] w-full overflow-hidden rounded-sm border border-line-strong bg-surface-2"
      >
        <div
          data-testid="variance-bar-fill"
          className="h-full"
          style={{ width: `${fraction * 100}%`, background: BAR_COLOR[tone] }}
        />
      </div>
    </div>
  );
}

/**
 * The latest reconciliation as paired Book vs Physical bars (same meaning as the Qt VarianceBarCard).
 * The numbers are printed beside the bars and the classification is named in a badge with an icon,
 * so the colour is never the only signal.
 */
export function VarianceBars({ reconciliation: r }: { reconciliation: Reconciliation }) {
  const tone = varianceTone(r.classification);
  const [book, physical] = varianceFractions(r.expected_closing_stock, r.physical_stock);
  const variance = `${formatQuantity(r.variance, { signed: true })} L (${r.variance_percent.startsWith('-') ? '' : '+'}${r.variance_percent}%)`;
  const summary = `Latest reconciliation, ${formatDate(r.reconciliation_date)}. Book ${formatLitres(r.expected_closing_stock)}, physical ${formatLitres(r.physical_stock)}, variance ${variance}, ${titleCase(r.classification)}.`;

  return (
    <figure
      aria-label={summary}
      data-tone={tone}
      className="m-0 flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-card"
    >
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-base font-bold">
          Latest reconciliation - {formatDate(r.reconciliation_date)}
        </span>
        <StatusBadge tone={BADGE_TONE[tone]}>{titleCase(r.classification)}</StatusBadge>
      </figcaption>
      <Bar label="Book (expected)" value={r.expected_closing_stock} fraction={book} tone={tone} />
      <Bar label="Physical (dipped)" value={r.physical_stock} fraction={physical} tone={tone} />
      <p className="num text-sm font-semibold">Variance: {variance}</p>
    </figure>
  );
}
