import { Lock } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { friendlyMessage } from '@/api/errors';
import { useAuth } from '@/auth/AuthContext';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';

/**
 * Blocks the whole app behind a re-confirmation of the CURRENT person (password, or PIN if they set one).
 * The same session resumes - unlike signing out. There is no Escape and no close button; "Sign out
 * instead" is the deliberate way out. (Windows Hello is not offered: see JS_MIGRATION_LOG.md.)
 */
export function LockOverlay() {
  const { user, unlock, logout } = useAuth();
  const [usePin, setUsePin] = useState(false);
  const [credential, setCredential] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), [usePin]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!credential) return setError(`Please enter your ${usePin ? 'PIN' : 'password'}.`);
    setBusy(true);
    try {
      await unlock(credential, usePin);
      setCredential('');
    } catch (err) {
      setCredential('');
      setError(friendlyMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-6"
      style={{ background: 'var(--overlay)' }}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="lock-title"
        onSubmit={(e) => void submit(e)}
        onKeyDown={(e) => e.key === 'Escape' && e.stopPropagation()}
        className="flex w-full max-w-sm flex-col gap-4 rounded-lg border border-line bg-surface p-6 shadow-pop"
      >
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-full bg-surface-2">
            <Lock className="size-5" aria-hidden />
          </span>
          <div>
            <h2 id="lock-title" className="text-xl font-bold">
              Welcome back, {user?.first_name || user?.username}
            </h2>
            <p className="text-sm text-muted">
              Locked. Enter your {usePin ? 'PIN' : 'password'} to resume where you left off.
            </p>
          </div>
        </div>
        {error && (
          <p
            role="alert"
            className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
          >
            {error}
          </p>
        )}
        <TextField
          ref={input}
          label={usePin ? 'PIN' : 'Password'}
          type="password"
          autoComplete="current-password"
          inputMode={usePin ? 'numeric' : undefined}
          value={credential}
          onChange={(e) => setCredential(e.target.value)}
        />
        <Button type="submit" variant="primary" loading={busy}>
          Unlock
        </Button>
        {user?.has_pin && (
          <Button
            onClick={() => {
              setUsePin((p) => !p);
              setCredential('');
              setError(null);
            }}
          >
            {usePin ? 'Use password instead' : 'Use PIN instead'}
          </Button>
        )}
        <Button variant="ghost" onClick={() => void logout()}>
          Sign out instead
        </Button>
      </form>
    </div>
  );
}
