import { Inbox, RefreshCw, ShieldAlert, WifiOff, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { ApiError, friendlyMessage } from '@/api/errors';
import { Button } from './Button';

export function LoadingBlock({ label = 'Loading', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton h-12 w-full" />
      ))}
    </div>
  );
}

function Panel({
  Icon,
  title,
  children,
}: {
  Icon: LucideIcon;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-line-strong bg-surface px-6 py-10 text-center">
      <Icon className="size-8 text-muted" aria-hidden />
      <h3 className="text-lg font-semibold">{title}</h3>
      {children}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Panel Icon={Inbox} title={title}>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </Panel>
  );
}

/** What happened, what to try, and a Retry - permission errors explain who can help instead. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const denied = error instanceof ApiError && error.code === 'permission_denied';
  const offline = error instanceof ApiError && error.code === 'network_error';
  return (
    <div role="alert">
      <Panel
        Icon={denied ? ShieldAlert : offline ? WifiOff : RefreshCw}
        title={denied ? 'You do not have access to this' : 'Could not load this'}
      >
        <p className="max-w-md text-sm text-muted">{friendlyMessage(error)}</p>
        {!denied && onRetry && (
          <Button onClick={onRetry}>
            <RefreshCw className="size-4" aria-hidden /> Try again
          </Button>
        )}
      </Panel>
    </div>
  );
}
