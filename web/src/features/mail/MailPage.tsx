import { useEffect, useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormError } from '@/components/ui/FormDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { formatDateTime } from '@/lib/format';

type S = components['schemas'];

const KEYS = ['mail_enabled', 'mail_host', 'mail_port', 'mail_security', 'mail_user', 'mail_from', 'mail_to', 'mail_send_hour'] as const;
type Key = (typeof KEYS)[number];

/** The optional daily summary by email: off unless an owner turns it on. Only figures are sent; nothing connects in. */
export function MailPage() {
  const toast = useToast();
  const settings = useGet<S['PumpSettingOut'][]>(['pump-settings'], '/pump-settings');
  const status = useGet<S['MailStatusOut']>(['mail'], '/mail', true, 30_000);
  const [form, setForm] = useState<Record<Key, string> | null>(null);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(async (changes: Array<[Key, string]>) => {
    for (const [key, value] of changes) await api.put(`/pump-settings/${key}`, { value });
  }, ['pump-settings', 'mail']);
  const savePassword = useWrite((p: string) => api.put('/mail/password', { password: p }), ['mail']);
  const test = useWrite(() => api.post<S['MailTestOut']>('/mail/test'), ['mail']);

  useEffect(() => {
    if (!settings.data || form) return;
    const values = Object.fromEntries(settings.data.map((s) => [s.key, s.value]));
    setForm(Object.fromEntries(KEYS.map((k) => [k, values[k] ?? ''])) as Record<Key, string>);
  }, [settings.data, form]);

  if (settings.isLoading || status.isLoading) return <LoadingBlock label="Loading the email settings" rows={4} />;
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />;
  if (status.isError) return <ErrorState error={status.error} onRetry={() => void status.refetch()} />;
  if (!form) return null;
  const s = status.data!;
  const stored = Object.fromEntries((settings.data ?? []).map((x) => [x.key, x.value]));
  const set = (key: Key) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  const onSave = async () => {
    setError(null);
    try {
      await save.mutateAsync(KEYS.filter((k) => form[k] !== stored[k]).map((k) => [k, form[k]] as [Key, string]));
      if (password) {
        await savePassword.mutateAsync(password);
        setPassword('');
      }
      toast.success('Saved.');
    } catch (err) {
      setError(friendlyMessage(err));
    }
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title="Email summary"
        subtitle="Once a day the Main PC can email the owners a short summary: figures only, no names. It is off until you turn it on. Nothing ever connects in from the internet; this is the only thing that connects out."
      />
      <p role="status" className="flex flex-wrap items-center gap-2 text-sm">
        <StatusBadge tone={s.enabled ? (s.problems.length ? 'warn' : 'ok') : 'neutral'}>{s.enabled ? (s.problems.length ? 'Not ready' : 'On') : 'Off'}</StatusBadge>
        {s.problems.map((p) => (
          <span key={p}>{p}</span>
        ))}
        {s.last_sent && <span className="text-muted">Last sent {formatDateTime(s.last_sent)}.</span>}
        {s.pending > 0 && <span className="text-muted">{s.pending} waiting to be sent.</span>}
      </p>
      <form
        className="grid gap-4 rounded-lg border border-line bg-surface p-4 shadow-card sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void onSave();
        }}
      >
        <SelectField label="Send the daily summary" value={form.mail_enabled} onChange={set('mail_enabled')}>
          <option value="off">No (off)</option>
          <option value="on">Yes</option>
        </SelectField>
        <TextField label="Send after this hour (0-23)" value={form.mail_send_hour} onChange={set('mail_send_hour')} inputMode="numeric" />
        <TextField label="Mail server" value={form.mail_host} onChange={set('mail_host')} placeholder="smtp.example.com" />
        <TextField label="Port" value={form.mail_port} onChange={set('mail_port')} inputMode="numeric" />
        <SelectField label="Protection" value={form.mail_security} onChange={set('mail_security')}>
          <option value="starttls">STARTTLS (usual, port 587)</option>
          <option value="ssl">SSL (port 465)</option>
          <option value="none">None (only to this PC)</option>
        </SelectField>
        <TextField label="Mail account (user name)" value={form.mail_user} onChange={set('mail_user')} autoComplete="off" />
        <TextField
          label={s.password_set ? 'Mail password (saved; type to replace)' : 'Mail password'}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          hint="Kept on the Main PC under Windows data protection. It is never shown again."
        />
        <TextField label="Sent from (address)" value={form.mail_from} onChange={set('mail_from')} />
        <div className="sm:col-span-2">
          <TextField label="Send to (addresses, separated by commas)" value={form.mail_to} onChange={set('mail_to')} />
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
          <FormError message={error} />
          <Button type="submit" variant="primary" loading={save.isPending || savePassword.isPending}>
            Save
          </Button>
          <Button
            loading={test.isPending}
            onClick={async () => {
              setError(null);
              try {
                toast.success((await test.mutateAsync(undefined)).message);
              } catch (err) {
                setError(friendlyMessage(err));
              }
            }}
          >
            Send a test message
          </Button>
        </div>
      </form>
      <section aria-label="Recent messages">
        <h2 className="mb-2 text-sm font-bold tracking-widest text-muted uppercase">Recent messages</h2>
        {s.outbox.length === 0 ? (
          <p className="text-sm text-muted">Nothing has been queued yet.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {s.outbox.map((m) => (
              <li key={m.day} className="flex flex-wrap items-center gap-2">
                <span className="num">{m.day}</span>
                <StatusBadge tone={m.status === 'sent' ? 'ok' : m.status === 'pending' ? 'info' : 'danger'}>{m.status === 'gave_up' ? 'Gave up' : m.status[0]!.toUpperCase() + m.status.slice(1)}</StatusBadge>
                <span>{m.subject}</span>
                {m.last_error && <span className="text-danger-fg">{m.last_error}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
