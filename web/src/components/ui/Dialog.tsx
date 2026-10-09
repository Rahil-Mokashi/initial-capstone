import * as RadixDialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
}

/** Modal with focus trap, Esc to close, and a labelled title (Radix handles the a11y plumbing). */
export function Dialog({ open, onOpenChange, title, description, children }: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay
          className="fixed inset-0 z-40"
          style={{ background: 'var(--overlay)' }}
        />
        <RadixDialog.Content
          // A stray click (or the second half of a double-click) outside must not throw away
          // what was typed. Esc, the Close button and Cancel still close it.
          onInteractOutside={(event) => event.preventDefault()}
          className="fixed top-1/2 left-1/2 z-50 max-h-[90vh] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-pop"
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <RadixDialog.Title className="text-xl font-bold">{title}</RadixDialog.Title>
              <RadixDialog.Description
                className={description ? 'mt-1 text-sm text-muted' : 'sr-only'}
              >
                {description ?? title}
              </RadixDialog.Description>
            </div>
            <RadixDialog.Close
              aria-label="Close"
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-surface-2"
            >
              <X className="size-5" aria-hidden />
            </RadixDialog.Close>
          </div>
          {children}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
