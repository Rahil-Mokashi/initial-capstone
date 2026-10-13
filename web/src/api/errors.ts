// Maps every failure into one ApiError the UI can switch on. The backend sends
// {"error": {code, message, details}} (api/errors.py); anything else is mapped here.
export type ErrorCode =
  | 'permission_denied'
  | 'validation_error'
  | 'rule_violation'
  | 'not_found'
  | 'conflict'
  | 'credit_limit_exceeded'
  | 'invalid_credentials'
  | 'account_locked'
  | 'authentication_failed'
  | 'weak_password'
  | 'session_expired'
  | 'not_authenticated'
  | 'password_change_required'
  | 'launch_secret_invalid'
  | 'internal_error'
  | 'network_error'
  | 'unknown';

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: ErrorCode,
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }

  get fieldErrors(): FieldError[] {
    const fields = this.details.fields;
    return Array.isArray(fields) ? (fields as FieldError[]) : [];
  }

  get isAuthLoss(): boolean {
    return this.code === 'session_expired' || this.code === 'not_authenticated';
  }
}

const KNOWN: ReadonlySet<string> = new Set<ErrorCode>([
  'permission_denied',
  'validation_error',
  'rule_violation',
  'not_found',
  'conflict',
  'credit_limit_exceeded',
  'invalid_credentials',
  'account_locked',
  'authentication_failed',
  'weak_password',
  'session_expired',
  'not_authenticated',
  'password_change_required',
  'launch_secret_invalid',
  'internal_error',
]);

export async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = undefined;
  }
  const err = (
    body as { error?: { code?: string; message?: string; details?: unknown } } | undefined
  )?.error;
  if (err && typeof err.message === 'string') {
    const code = KNOWN.has(err.code ?? '') ? (err.code as ErrorCode) : 'unknown';
    const details =
      err.details && typeof err.details === 'object'
        ? (err.details as Record<string, unknown>)
        : {};
    return new ApiError(res.status, code, err.message, details);
  }
  return new ApiError(
    res.status,
    'unknown',
    `The server answered with an unexpected error (${res.status}).`,
  );
}

export function networkError(): ApiError {
  return new ApiError(
    0,
    'network_error',
    'Cannot reach the application service. Close and reopen the app; if this keeps happening, contact your administrator.',
  );
}

/** One sentence a person can act on. */
export function friendlyMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'permission_denied') {
      return "You don't have permission to do that. Ask a manager or administrator if you need it.";
    }
    if (error.code === 'validation_error' && error.fieldErrors.length > 0) {
      return error.fieldErrors
        .map((f) => (f.field ? `${f.field}: ${f.message}` : f.message))
        .join('; ');
    }
    return error.message;
  }
  return 'Something went wrong. Please try again.';
}
