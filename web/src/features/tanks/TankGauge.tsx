import { ArrowDown } from 'lucide-react';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { formatLitres, formatPercent, titleCase } from '@/lib/format';
import type { Tank } from '@/api/types';

export function statusTone(status: string): Tone {
  return status === 'active' ? 'ok' : status === 'maintenance' ? 'warn' : 'neutral';
}

/** Horizontal fill with the percentage printed - the level is never colour alone. */
export function GaugeBar({ percent, low }: { percent: string; low: boolean }) {
  const width = `${Math.max(0, Math.min(100, Number.parseFloat(percent) || 0))}%`; // layout only, not money
  return (
    <div
      role="meter"
      aria-label="Fill level"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Number.parseFloat(percent) || 0}
      aria-valuetext={formatPercent(percent)}
      className="h-3 w-full overflow-hidden rounded-full border border-line-strong bg-surface-2"
    >
      <div className={`h-full ${low ? 'bg-warn' : 'bg-primary'}`} style={{ width }} />
    </div>
  );
}

export function StockFigures({ tank }: { tank: Tank }) {
  return (
    <div>
      <p className="num text-3xl leading-none font-bold">
        {formatLitres(tank.current_stock).replace(' L', '')}
        <span className="ml-1 text-base font-semibold text-muted">L</span>
      </p>
      <p className="num mt-1 text-sm text-muted">of {formatLitres(tank.capacity)}</p>
    </div>
  );
}

export function LevelBadge({ tank }: { tank: Tank }) {
  return tank.is_low ? (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-warn-bg px-2.5 py-1 text-xs font-bold text-warn-fg">
      <ArrowDown className="size-3.5" aria-hidden />
      Low - {formatPercent(tank.fill_percent)}
    </span>
  ) : (
    <span className="num text-sm font-semibold">{formatPercent(tank.fill_percent)}</span>
  );
}

export function StatusPill({ status }: { status: string }) {
  return <StatusBadge tone={statusTone(status)}>{titleCase(status)}</StatusBadge>;
}
