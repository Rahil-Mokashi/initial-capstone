import { useId, useState } from 'react';
import type { Tank } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { cn } from '@/lib/cn';
import { formatDateTime, formatLitres, formatPercent } from '@/lib/format';
import { useShowNumbers } from '@/lib/tankNumbers';

// The colour tells the fuel (the words are always there too): petrol green, diesel amber, anything else the app colour.
const FUEL_FILL: Record<string, string> = { petrol: 'var(--ok)', diesel: 'var(--warn)' };
const fuelFill = (fuelType: string) => FUEL_FILL[fuelType.toLowerCase()] ?? 'var(--primary)';

const W = 320;
const H = 130;
const TOP = 22; // the tank body runs from y=22 to y=108
const BOTTOM = 108;
const BODY = BOTTOM - TOP;

const BASIS_NOTE: Record<string, string> = {
  dip_chart: "Level drawn from this tank's dip chart.",
  round_tank: "Level drawn from the shape of a round tank (no dip chart entered yet), so it is close, not exact.",
  approximate: 'Level is approximate: drawn as a plain percentage.',
};

function heightOf(tank: Tank): { fraction: number; low: number; basis: string } {
  const plain = Math.max(0, Math.min(100, Number.parseFloat(tank.fill_percent) || 0)) / 100; // layout only, not money
  const given = tank.fill_height != null ? Number.parseFloat(tank.fill_height) : Number.NaN;
  if (Number.isFinite(given)) {
    const low = tank.low_height != null ? Number.parseFloat(tank.low_height) : Number.NaN;
    return { fraction: Math.max(0, Math.min(1, given)), low: Number.isFinite(low) ? low : 0, basis: tank.fill_basis ?? 'round_tank' };
  }
  return { fraction: plain, low: 0, basis: 'approximate' };
}

/** The litres, the percentage, the capacity and the last dip: what the picture leaves out. */
export function TankNumbers({ tank }: { tank: Tank }) {
  const { basis } = heightOf(tank);
  return (
    <dl className="num grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      <dt className="text-muted">In the tank (book stock)</dt>
      <dd className="text-right font-semibold">{formatLitres(tank.current_stock)}</dd>
      <dt className="text-muted">Full</dt>
      <dd className="text-right font-semibold">{formatPercent(tank.fill_percent)}</dd>
      <dt className="text-muted">Capacity</dt>
      <dd className="text-right font-semibold">{formatLitres(tank.capacity)}</dd>
      <dt className="text-muted">Last dip</dt>
      <dd className="text-right font-semibold">
        {tank.last_dip_at && tank.last_dip_litres
          ? `${formatLitres(tank.last_dip_litres)} on ${formatDateTime(tank.last_dip_at)}`
          : 'none recorded'}
      </dd>
      <dd className="col-span-2 text-xs text-muted">{BASIS_NOTE[basis]}</dd>
    </dl>
  );
}

/**
 * An underground petrol-pump tank, lying on its side: a long body with rounded ends, the fuel standing inside it, and a dashed line
 * where "low" starts. The picture is the main view. The figures show when the picture is tapped or hovered, or all the time when
 * "Show numbers" is on (remembered for each person).
 */
export function TankDrawing({ tank, className }: { tank: Tank; className?: string }) {
  const { user } = useAuth();
  const [always] = useShowNumbers(user?.username ?? '');
  const [tapped, setTapped] = useState(false);
  const [hover, setHover] = useState(false);
  const clip = useId();
  const { fraction, low, basis } = heightOf(tank);
  const fuelTop = BOTTOM - fraction * BODY;
  const lowY = BOTTOM - low * BODY;
  const shown = always || tapped || hover;
  const approx = basis !== 'dip_chart' ? (basis === 'approximate' ? 'approximately' : 'about') : 'about';
  const label = `${tank.code} ${tank.fuel_type} tank, ${approx} ${formatPercent(tank.fill_percent)} full${tank.is_low ? ', low' : ''}`;

  return (
    <div
      className={cn('flex flex-col gap-2', className)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <button
        type="button"
        aria-expanded={shown}
        aria-label={`${label}. ${shown ? 'Hide' : 'Show'} the numbers.`}
        onClick={() => setTapped((t) => !t)}
        className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="h-auto w-full">
          <defs>
            <clipPath id={clip}>
              <rect x="16" y={TOP} width={W - 32} height={BODY} rx={BODY / 2} />
            </clipPath>
          </defs>
          {/* the ground above the tank */}
          <line x1="0" y1="10" x2={W} y2="10" stroke="var(--line-strong)" strokeWidth="2" strokeDasharray="2 6" />
          {/* the body, then the fuel inside it */}
          <rect x="16" y={TOP} width={W - 32} height={BODY} rx={BODY / 2} fill="var(--surface-2)" stroke="var(--line-strong)" strokeWidth="3" />
          <g clipPath={`url(#${clip})`}>
            <rect x="16" y={fuelTop} width={W - 32} height={BOTTOM - fuelTop} fill={fuelFill(tank.fuel_type)} opacity="0.85" />
            <line x1="16" y1={fuelTop} x2={W - 16} y2={fuelTop} stroke="var(--text)" strokeWidth="1.5" opacity="0.5" />
          </g>
          {/* where "low" starts */}
          {low > 0 && (
            <g>
              <line x1="16" y1={lowY} x2={W - 16} y2={lowY} stroke="var(--danger)" strokeWidth="2" strokeDasharray="6 4" />
              <text x={W - 20} y={lowY - 4} textAnchor="end" fontSize="10" fill="var(--danger)">
                low
              </text>
            </g>
          )}
          {/* the manhole on top */}
          <rect x={W / 2 - 14} y="14" width="28" height="8" rx="2" fill="var(--line-strong)" />
        </svg>
      </button>
      {shown && <TankNumbers tank={tank} />}
    </div>
  );
}
