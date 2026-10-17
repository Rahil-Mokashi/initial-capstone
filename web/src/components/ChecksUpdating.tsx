import { useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { useGet } from '@/api/hooks';

/** Shown while the Main PC is still re-running the checks after a save; when it finishes, every screen's data is refreshed. */
export function ChecksUpdating() {
  const status = useGet<{ updating: boolean }>(['checks-status'], '/checks/status', true, 1500);
  const queryClient = useQueryClient();
  const was = useRef(false);
  const updating = status.data?.updating ?? false;
  useEffect(() => {
    if (was.current && !updating) {
      void queryClient.invalidateQueries({
        predicate: (q) => q.queryKey[0] !== 'checks-status',
      });
    }
    was.current = updating;
  }, [updating, queryClient]);
  if (!updating) return null;
  return (
    <span
      role="status"
      className="inline-flex items-center gap-1.5 rounded-full border border-warn bg-warn-bg px-3 py-1 text-xs font-semibold text-warn-fg"
    >
      <RefreshCw className="size-3.5 animate-spin" aria-hidden /> Checks updating…
    </span>
  );
}
