import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/cn';

/**
 * A small dropdown panel: opens on click, closes on Escape, on a click outside, or when focus leaves.
 * The trigger carries aria-expanded / aria-controls; the panel is a plain region, so it can hold
 * anything (alert cards, an account header, buttons).
 */
export function Menu({
  label,
  trigger,
  children,
  align = 'right',
  triggerClassName,
}: {
  /** Accessible name of the trigger when it shows only an icon or a count. */
  label: string;
  trigger: ReactNode;
  /** Receives `close` so an item can close the menu after it acts. */
  children: (close: () => void) => ReactNode;
  align?: 'left' | 'right';
  triggerClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex min-h-[44px] items-center gap-2 rounded-md border border-line-strong bg-surface px-3 text-sm font-semibold hover:bg-surface-2',
          triggerClassName,
        )}
      >
        {trigger}
      </button>
      {open && (
        <div
          id={panelId}
          role="region"
          aria-label={label}
          className={cn(
            'absolute top-full z-30 mt-2 w-[min(26rem,calc(100vw-2rem))] rounded-lg border border-line bg-surface p-3 shadow-pop',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
