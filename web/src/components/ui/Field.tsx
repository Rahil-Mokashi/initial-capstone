import { AlertCircle } from 'lucide-react';
import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { cn } from '@/lib/cn';

const CONTROL =
  'min-h-[44px] w-full rounded-md border border-line-strong bg-surface px-3 text-base text-fg ' +
  'placeholder:text-muted disabled:opacity-60 aria-[invalid=true]:border-danger aria-[invalid=true]:border-2';

interface FieldShellProps {
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
  children: (ids: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
}

/** Label + control + hint + inline error, wired with aria so screen readers read them together. */
export function FieldShell({ label, hint, error, optional, children }: FieldShellProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const describedBy =
    [hint && !error ? hintId : null, error ? errId : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
        {optional && <span className="ml-1 font-normal text-muted">(optional)</span>}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint && !error && (
        <p id={hintId} aria-live="polite" className="text-xs text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={errId}
          role="alert"
          className="flex items-start gap-1.5 text-sm font-medium text-danger-fg"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          {error}
        </p>
      )}
    </div>
  );
}

interface Common {
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
}

export const TextField = forwardRef<
  HTMLInputElement,
  Common & InputHTMLAttributes<HTMLInputElement>
>(function TextField({ label, hint, error, optional, className, ...rest }, ref) {
  return (
    <FieldShell label={label} hint={hint} error={error} optional={optional}>
      {({ id, describedBy, invalid }) => (
        <input
          ref={ref}
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className={cn(CONTROL, className)}
          {...rest}
        />
      )}
    </FieldShell>
  );
});

export const SelectField = forwardRef<
  HTMLSelectElement,
  Common & SelectHTMLAttributes<HTMLSelectElement>
>(function SelectField({ label, hint, error, optional, className, children, ...rest }, ref) {
  return (
    <FieldShell label={label} hint={hint} error={error} optional={optional}>
      {({ id, describedBy, invalid }) => (
        <select
          ref={ref}
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className={cn(CONTROL, className)}
          {...rest}
        >
          {children}
        </select>
      )}
    </FieldShell>
  );
});

export const TextAreaField = forwardRef<
  HTMLTextAreaElement,
  Common & TextareaHTMLAttributes<HTMLTextAreaElement>
>(function TextAreaField({ label, hint, error, optional, className, ...rest }, ref) {
  return (
    <FieldShell label={label} hint={hint} error={error} optional={optional}>
      {({ id, describedBy, invalid }) => (
        <textarea
          ref={ref}
          id={id}
          rows={2}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className={cn(CONTROL, 'py-2', className)}
          {...rest}
        />
      )}
    </FieldShell>
  );
});
