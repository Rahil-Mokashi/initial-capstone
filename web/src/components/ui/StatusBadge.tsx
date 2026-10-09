import { AlertTriangle, CheckCircle2, Info, OctagonAlert, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/cn';

export type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral';

const TONES: Record<Tone, { cls: string; Icon: LucideIcon }> = {
  ok: { cls: 'bg-ok-bg text-ok-fg', Icon: CheckCircle2 },
  warn: { cls: 'bg-warn-bg text-warn-fg', Icon: AlertTriangle },
  danger: { cls: 'bg-danger-bg text-danger-fg', Icon: OctagonAlert },
  info: { cls: 'bg-info-bg text-info-fg', Icon: Info },
  neutral: { cls: 'bg-surface-2 text-muted border border-line', Icon: Info },
};

/** Status is ALWAYS colour + icon + words - never colour alone. */
export function StatusBadge({ tone, children }: { tone: Tone; children: string }) {
  const { cls, Icon } = TONES[tone];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold',
        cls,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {children}
    </span>
  );
}
