import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { P } from '@/lib/permissions';

type Settings = components['schemas']['SettingsOut'];

const FIELDS = [
  'company_name',
  'address_line1',
  'address_line2',
  'city',
  'state',
  'postal_code',
  'phone',
  'email',
  'gst_number',
  'licence_number',
  'receipt_footer',
  'offsite_backup_dir',
] as const;
type Key = (typeof FIELDS)[number];

// Every box is optional; the server checks the shape of what was typed (GST, phone, email) and names the box.
const schema = z.object(
  Object.fromEntries(FIELDS.map((k) => [k, z.string()])) as Record<Key, z.ZodString>,
);
type Values = z.infer<typeof schema>;

const toValues = (s: Settings | undefined): Values =>
  Object.fromEntries(FIELDS.map((k) => [k, s?.[k] ?? ''])) as Values;

function SettingsForm({ current }: { current: Settings }) {
  const { can } = useAuth();
  const canManage = can(P.SETTINGS_MANAGE);
  const toast = useToast();
  const save = useWrite<Values, Settings>(
    (body) => api.put<Settings>('/settings', body),
    ['settings'],
  );
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setValue,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(current),
  });

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      const saved = await save.mutateAsync(v);
      reset(toValues(saved));
      toast.success('Company profile saved.');
    } catch (error) {
      setFormError(applyApiError(error, setError, FIELDS));
    }
  });

  const field = (key: Key, label: string, extra: { hint?: string; placeholder?: string } = {}) => (
    <TextField
      label={label}
      optional
      readOnly={!canManage}
      error={errors[key]?.message}
      {...extra}
      {...register(key)}
    />
  );

  return (
    <form onSubmit={submit} noValidate className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title="Company Profile"
        subtitle="The name and details printed at the top of every receipt, statement and report."
      />
      {!current.has_company_profile && (
        <p
          role="status"
          className="rounded-md border border-warn bg-warn-bg p-3 text-sm font-medium text-warn-fg"
        >
          No business name is set. Printed receipts and reports will carry no name or address until
          you fill this in.
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">{field('company_name', 'Business name')}</div>
        {field('address_line1', 'Address line 1')}
        {field('address_line2', 'Address line 2')}
        {field('city', 'City')}
        {field('state', 'State')}
        {field('postal_code', 'Postal code')}
        {field('phone', 'Phone')}
        {field('email', 'Email')}
        {field('gst_number', 'GST number', {
          hint: '15 letters and digits, for example 27AAPFU0939F1ZV.',
        })}
        {field('licence_number', 'Licence number')}
        <div className="sm:col-span-2">
          {field('receipt_footer', 'Receipt footer', {
            hint: 'A line printed at the bottom of every receipt, for example "Thank you, drive safe".',
          })}
        </div>
        <div className="sm:col-span-2">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              {field('offsite_backup_dir', 'Off-device backup folder', {
                hint: 'A USB drive or network folder. The Backups screen copies verified backups here.',
              })}
            </div>
            {canManage && window.pperp?.files.pickFolder && (
              <Button
                onClick={async () => {
                  const picked = await window.pperp?.files.pickFolder();
                  if (picked) setValue('offsite_backup_dir', picked, { shouldDirty: true });
                }}
              >
                Browse...
              </Button>
            )}
          </div>
        </div>
      </div>
      {formError && (
        <p role="alert" className="text-sm font-medium text-danger-fg">
          {formError}
        </p>
      )}
      {canManage ? (
        <div className="flex gap-3">
          <Button type="submit" variant="primary" loading={isSubmitting}>
            Save
          </Button>
          <Button
            disabled={!isDirty}
            onClick={() => {
              setFormError(null);
              reset(toValues(current));
            }}
          >
            Discard changes
          </Button>
        </div>
      ) : (
        <p className="text-sm text-muted">You can view the company profile but not change it.</p>
      )}
    </form>
  );
}

export function SettingsPage() {
  const settings = useGet<Settings>(['settings'], '/settings');
  if (settings.isLoading) return <LoadingBlock label="Loading company profile" rows={4} />;
  if (settings.isError || !settings.data)
    return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />;
  // Keyed on the saved row so a save (or a refetch after one) starts the form from what is stored.
  return <SettingsForm key={JSON.stringify(settings.data)} current={settings.data} />;
}
