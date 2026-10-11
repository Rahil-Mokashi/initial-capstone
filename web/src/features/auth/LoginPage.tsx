import { Eye, EyeOff, Fuel, Moon, Sun } from 'lucide-react';
import { useEffect, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ApiError } from '@/api/errors';
import { useGet } from '@/api/hooks';
import { useAuth } from '@/auth/AuthContext';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';
import { enterToAdvance } from '@/lib/enterToAdvance';
import {
  STRINGS,
  getLoginLocale,
  getRecentUsernames,
  recordRecentUsername,
  setLoginLocale,
  type LoginLocale,
} from '@/lib/loginLocale';
import { isDark, setTheme } from '@/lib/theme';
import { ForgotPasswordDialog } from './ForgotPasswordDialog';

/** Whole seconds from now until an ISO timestamp, floored at 0 (the lockout countdown). */
export function secondsUntil(iso: unknown, now = Date.now()): number {
  if (typeof iso !== 'string') return 0;
  const ms = Date.parse(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`) - now;
  return Number.isFinite(ms) ? Math.max(0, Math.floor(ms / 1000)) : 0;
}

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

export function LoginPage() {
  const { user, login } = useAuth();
  const location = useLocation();
  const [locale, setLocale] = useState<LoginLocale>(getLoginLocale);
  const t = STRINGS[locale];
  const device = useGet<{ device: string }>(['system', 'device'], '/system/device');
  const [username, setUsername] = useState('');
  const [credential, setCredential] = useState('');
  const [pinMode, setPinMode] = useState(false);
  const [reveal, setReveal] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [dark, setDark] = useState(() => isDark());
  const [errors, setErrors] = useState<{ username?: string; credential?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<number | null>(null);
  const [lockedFor, setLockedFor] = useState(0);
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  const recent = getRecentUsernames();

  // The lockout countdown ticks down locally (no polling).
  useEffect(() => {
    if (lockedFor <= 0) return;
    const id = window.setTimeout(() => setLockedFor((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearTimeout(id);
  }, [lockedFor]);

  if (user) {
    const from = (location.state as { from?: string } | null)?.from ?? '/';
    return <Navigate to={from} replace />;
  }

  const watchCaps = (e: KeyboardEvent) => setCapsLock(e.getModifierState('CapsLock'));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setAttempts(null);
    setLockedFor(0);
    const found: typeof errors = {};
    if (!username.trim()) found.username = t.usernameRequired;
    if (!credential) found.credential = pinMode ? t.pinRequired : t.passwordRequired;
    setErrors(found);
    if (found.username || found.credential) return;
    setBusy(true);
    try {
      await login(username.trim(), credential, pinMode);
      recordRecentUsername(username.trim());
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        const d = err.details as { attempts_remaining?: number; locked_until?: string };
        if (typeof d.attempts_remaining === 'number') setAttempts(d.attempts_remaining);
        setLockedFor(secondsUntil(d.locked_until));
      } else {
        setError('Could not sign in. Please try again.');
      }
      setCredential('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <section className="hidden flex-col justify-between bg-ink p-12 text-ink-fg lg:flex">
        <div className="flex items-center gap-3">
          <span className="flex size-12 items-center justify-center rounded-lg bg-primary text-primary-fg">
            <Fuel className="size-6" aria-hidden />
          </span>
          <span className="text-xl font-bold">Petrol Pump ERP</span>
        </div>
        <div>
          <h1 className="max-w-md text-4xl leading-tight font-bold">Every litre accounted for.</h1>
          <p className="mt-4 max-w-md text-ink-muted">
            Tanks, shifts, sales and cash in one place - working entirely on this PC, with no
            internet needed.
          </p>
        </div>
        <p className="text-xs text-ink-muted">
          Works offline. Your data stays on this computer.
          {device.data?.device ? ` Device: ${device.data.device}.` : ''}
        </p>
      </section>

      <main className="relative flex items-center justify-center p-6">
        <div className="absolute top-4 right-4 flex gap-2">
          <Button
            variant="ghost"
            aria-label={locale === 'hi' ? 'Switch to English' : 'Switch to Hindi'}
            onClick={() => {
              const next: LoginLocale = locale === 'hi' ? 'en' : 'hi';
              setLocale(next);
              setLoginLocale(next);
            }}
          >
            {locale === 'hi' ? 'EN' : '\u0939\u093F\u0902'}
          </Button>
          <Button
            variant="ghost"
            aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
            onClick={() => {
              setTheme(dark ? 'light' : 'dark');
              setDark(!dark);
            }}
          >
            {dark ? (
              <Sun className="size-5" aria-hidden />
            ) : (
              <Moon className="size-5" aria-hidden />
            )}
          </Button>
        </div>

        <form
          onKeyDown={enterToAdvance}
          onSubmit={(e) => void submit(e)}
          noValidate
          className="flex w-full max-w-sm flex-col gap-5"
          aria-labelledby="login-title"
        >
          <div>
            <h2 id="login-title" className="text-2xl font-bold">
              {t.welcomeBack}
            </h2>
            <p className="mt-1 text-sm text-muted">{t.cantSignIn}</p>
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
            >
              <p>{error}</p>
              {lockedFor > 0 && <p className="mt-1">Try again in {clock(lockedFor)}.</p>}
              {attempts !== null && attempts >= 0 && lockedFor === 0 && (
                <p className="mt-1">
                  {attempts} {attempts === 1 ? 'attempt' : 'attempts'} left before this account is
                  locked.
                </p>
              )}
            </div>
          )}

          <TextField
            label={t.usernameLabel}
            placeholder={t.usernamePlaceholder}
            autoComplete="username"
            autoFocus
            list="recent-usernames"
            value={username}
            error={errors.username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <datalist id="recent-usernames">
            {recent.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>

          <div className="flex flex-col gap-1.5">
            <div className="relative">
              <TextField
                label={pinMode ? t.pinLabel : t.passwordLabel}
                placeholder={pinMode ? t.pinPlaceholder : t.passwordPlaceholder}
                type={reveal ? 'text' : 'password'}
                autoComplete="current-password"
                inputMode={pinMode ? 'numeric' : undefined}
                value={credential}
                error={errors.credential}
                onChange={(e) => setCredential(e.target.value)}
                onKeyDown={watchCaps}
                onKeyUp={watchCaps}
                className="pr-24"
              />
              <button
                type="button"
                onClick={() => setReveal((r) => !r)}
                aria-pressed={reveal}
                className="absolute top-[34px] right-2 inline-flex min-h-[32px] items-center gap-1 rounded px-2 text-sm font-semibold text-muted hover:text-fg"
              >
                {reveal ? (
                  <EyeOff className="size-4" aria-hidden />
                ) : (
                  <Eye className="size-4" aria-hidden />
                )}
                {reveal ? t.hide : t.show}
              </button>
            </div>
            {capsLock && (
              <p role="status" className="text-sm font-medium text-warn-fg">
                {t.capsLockOn}
              </p>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            loading={busy}
            disabled={lockedFor > 0}
            className="min-h-[48px] text-base"
          >
            {busy ? t.signingIn : t.signIn}
          </Button>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <button
              type="button"
              className="min-h-[44px] text-sm font-semibold underline underline-offset-4"
              onClick={() => {
                setPinMode((m) => !m);
                setCredential('');
                setErrors({});
              }}
            >
              {pinMode ? t.usePasswordInstead : t.usePinInstead}
            </button>
            <button
              type="button"
              className="min-h-[44px] text-sm font-semibold underline underline-offset-4"
              onClick={() => setForgot(true)}
            >
              {t.forgotPassword}
            </button>
          </div>
        </form>
      </main>
      {forgot && <ForgotPasswordDialog onClose={() => setForgot(false)} />}
    </div>
  );
}
