import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';
import { ApiError, friendlyMessage } from '@/api/errors';

/**
 * Puts the server's per-field messages next to the matching inputs; anything
 * else becomes one form-level message. Returns that message (or null).
 */
export function applyApiError<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  known: ReadonlyArray<string>,
): string | null {
  if (error instanceof ApiError && error.code === 'validation_error') {
    let unplaced = false;
    for (const f of error.fieldErrors) {
      if (known.includes(f.field))
        setError(f.field as Path<T>, { type: 'server', message: f.message });
      else unplaced = true;
    }
    return unplaced || error.fieldErrors.length === 0 ? friendlyMessage(error) : null;
  }
  return friendlyMessage(error);
}
