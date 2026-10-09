import { CheckCircle2, OctagonAlert, X } from 'lucide-react';
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

type ToastKind = 'success' | 'error';
interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}
interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

/** Announced politely (success) or assertively (error); errors stay until dismissed. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);

  const dismiss = useCallback(
    (id: number) => setItems((all) => all.filter((t) => t.id !== id)),
    [],
  );
  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = next.current++;
      setItems((all) => [...all, { id, kind, message }]);
      if (kind === 'success') window.setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );
  const api = useMemo<ToastApi>(
    () => ({ success: (m) => push('success', m), error: (m) => push('error', m) }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="fixed right-4 bottom-4 z-[60] flex w-[min(26rem,calc(100vw-2rem))] flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={`flex items-start gap-3 rounded-md border p-3 shadow-pop ${
              t.kind === 'error'
                ? 'border-danger bg-danger-bg text-danger-fg'
                : 'border-ok bg-ok-bg text-ok-fg'
            }`}
          >
            {t.kind === 'error' ? (
              <OctagonAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
            ) : (
              <CheckCircle2 className="mt-0.5 size-5 shrink-0" aria-hidden />
            )}
            <p className="flex-1 text-sm font-medium">{t.message}</p>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => dismiss(t.id)}
              className="inline-flex size-8 items-center justify-center rounded hover:brightness-90"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const value = useContext(ToastContext);
  if (!value) throw new Error('useToast must be used inside <ToastProvider>');
  return value;
}
