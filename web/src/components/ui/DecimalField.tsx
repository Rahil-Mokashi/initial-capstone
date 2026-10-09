import {
  forwardRef,
  useRef,
  useState,
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
} from 'react';
import { cn } from '@/lib/cn';
import { checkPartialDecimal, explain } from '@/lib/decimalGuard';
import { TextField } from './Field';

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string;
  error?: string;
  optional?: boolean;
  /** Decimal places the database keeps: 3 for litres, 2 for money. */
  maxFraction?: number;
  negative?: boolean;
  /** Used in the explanation, for example "litres". */
  unit?: string;
}

/**
 * A number box that refuses (never rounds) anything the backend would reject: too many decimal
 * places, letters, too many digits. An edit that would break the rule is undone, as a whole (a
 * too-precise paste is not trimmed to fit), and the person is told why, right below the box.
 * Works with react-hook-form's register(): valid edits are passed on unchanged, refused ones never are.
 */
export const DecimalField = forwardRef<HTMLInputElement, Props>(function DecimalField(
  { maxFraction = 3, negative = false, unit = 'litres', className, onChange, onFocus, ...rest },
  ref,
) {
  const rules = { maxFraction, negative };
  const [note, setNote] = useState<string | null>(null);
  const lastValid = useRef('');

  return (
    <TextField
      ref={ref}
      inputMode="decimal"
      autoComplete="off"
      className={cn('num', className)}
      hint={note ?? undefined}
      onFocus={(event: FocusEvent<HTMLInputElement>) => {
        lastValid.current = event.currentTarget.value;
        onFocus?.(event);
      }}
      onChange={(event: ChangeEvent<HTMLInputElement>) => {
        const input = event.currentTarget;
        const result = checkPartialDecimal(input.value, rules);
        if (!result.ok) {
          input.value = lastValid.current; // undo the edit; nothing is cut or rounded
          setNote(explain(result, rules, unit));
          return;
        }
        lastValid.current = input.value;
        setNote(null);
        onChange?.(event);
      }}
      {...rest}
    />
  );
});
