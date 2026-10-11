import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { History, Pencil } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { useGet, useWrite } from '@/api/hooks';
import { api } from '@/api/client';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Dialog } from '@/components/ui/Dialog';
import { DecimalField } from '@/components/ui/DecimalField';
import { TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { formatDateTime, formatMoney } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Fuel = S['FuelPriceOut'];
type HistoryRow = S['PriceHistoryOut'];

const useFuelPrices = () => useGet<Fuel[]>(['fuel-prices', 'list'], '/fuel-prices');
const useHistory = (id: string) =>
  useGet<HistoryRow[]>(['fuel-prices', id, 'history'], `/fuel-prices/${id}/history`);
const useSetRate = (id: string) =>
  useWrite((body: S['RateIn']) => api.post<Fuel>(`/fuel-prices/${id}/rate`, body), ['fuel-prices']);

// Same limits as the Qt box: 0.01 up to 10,000, two decimal places. The server re-checks.
const schema = z.object({
  rate: z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,5}(\.\d{1,2})?$/.test(v)) {
        ctx.addIssue({ code: 'custom', message: 'Enter a rate such as 104.50.' });
      } else if (Number(v) < 0.01 || Number(v) > 10000) {
        ctx.addIssue({ code: 'custom', message: 'The rate must be between 0.01 and 10,000.' });
      }
    }),
  reason: z.string().trim().min(1, 'Give a reason for the change.').max(500),
});
type Values = z.infer<typeof schema>;

function ChangePriceDialog({ fuel, onClose }: { fuel: Fuel; onClose: () => void }) {
  const toast = useToast();
  const setRate = useSetRate(fuel.id);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { rate: fuel.priced ? (fuel.rate_per_liter ?? '') : '100.00', reason: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await setRate.mutateAsync({ new_rate_per_liter: v.rate, reason: v.reason });
      toast.success(`${fuel.fuel_type} price changed.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['new_rate_per_liter', 'reason']));
    }
  });
  return (
    <FormDialog
      title={`Change price - ${fuel.fuel_type}`}
      description={
        fuel.priced && fuel.rate_per_liter
          ? `Current rate: ${formatMoney(fuel.rate_per_liter)}`
          : 'Current rate: not set'
      }
      submitLabel="Save"
      busy={setRate.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <DecimalField
        label="New rate per litre"
        maxFraction={2}
        unit="rupees"
        autoFocus
        error={errors.rate?.message}
        {...register('rate')}
      />
      <TextField
        label="Reason"
        placeholder="e.g. Daily OMC revision, 17 Aug"
        maxLength={500}
        error={errors.reason?.message}
        {...register('reason')}
      />
    </FormDialog>
  );
}

function HistoryDialog({ fuel, onClose }: { fuel: Fuel; onClose: () => void }) {
  const history = useHistory(fuel.id);
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Price history - ${fuel.fuel_type}`}
      description="Every change ever made to this fuel's price, newest first."
    >
      {history.isLoading ? (
        <LoadingBlock label="Loading price history" rows={3} />
      ) : history.isError ? (
        <ErrorState error={history.error} onRetry={() => void history.refetch()} />
      ) : (
        <DataTable<HistoryRow>
          caption={`Price history for ${fuel.fuel_type}`}
          getRowId={(r) => r.id}
          data={history.data ?? []}
          empty={<p className="text-sm text-muted">No price changes recorded yet.</p>}
          columns={[
            {
              accessorKey: 'effective_from',
              header: 'Effective from',
              cell: ({ getValue }) => formatDateTime(getValue<string>()),
            },
            {
              accessorKey: 'old_rate_per_liter',
              header: 'From',
              meta: { numeric: true },
              cell: ({ getValue }) => {
                const v = getValue<string | null>();
                return v ? formatMoney(v) : '-';
              },
            },
            {
              accessorKey: 'new_rate_per_liter',
              header: 'To',
              meta: { numeric: true },
              cell: ({ getValue }) => formatMoney(getValue<string>()),
            },
            { accessorKey: 'reason', header: 'Reason' },
          ]}
        />
      )}
    </Dialog>
  );
}

export function FuelPricesPage() {
  const { can } = useAuth();
  const canManage = can(P.FUEL_PRICE_MANAGE);
  const fuels = useFuelPrices();
  const [dialog, setDialog] = useState<{ kind: 'change' | 'history'; fuel: Fuel } | null>(null);
  const unpriced = (fuels.data ?? []).filter((f) => !f.priced).length;

  const columns: ColumnDef<Fuel>[] = [
    { accessorKey: 'fuel_type', header: 'Fuel' },
    {
      accessorKey: 'rate_per_liter',
      header: 'Rate per litre',
      meta: { numeric: true },
      cell: ({ row }) =>
        row.original.priced && row.original.rate_per_liter
          ? formatMoney(row.original.rate_per_liter)
          : '-',
    },
    {
      id: 'status',
      header: 'Status',
      cell: ({ row }) =>
        row.original.priced ? (
          <StatusBadge tone="ok">Priced</StatusBadge>
        ) : (
          <StatusBadge tone="danger">No price set</StatusBadge>
        ),
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <button
            type="button"
            aria-label={`Price history for ${row.original.fuel_type}`}
            onClick={() => setDialog({ kind: 'history', fuel: row.original })}
            className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2"
          >
            <History className="size-4" aria-hidden />
          </button>
          {canManage && (
            <button
              type="button"
              aria-label={`Change price of ${row.original.fuel_type}`}
              onClick={() => setDialog({ kind: 'change', fuel: row.original })}
              className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2"
            >
              <Pencil className="size-4" aria-hidden />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        title="Fuel Prices"
        subtitle="The rate each fuel currently sells at. A sale keeps the rate it was made at, so changing a price never alters a past sale."
      />
      {unpriced > 0 && (
        <p
          role="status"
          className="rounded-md border border-warn bg-warn-bg p-3 text-sm font-medium text-warn-fg"
        >
          {unpriced} fuel type(s) have no selling price set and cannot be sold. Set a price before
          the next shift opens.
        </p>
      )}
      {fuels.isLoading ? (
        <LoadingBlock label="Loading fuel prices" rows={3} />
      ) : fuels.isError ? (
        <ErrorState error={fuels.error} onRetry={() => void fuels.refetch()} />
      ) : (
        <DataTable
          caption="Fuel prices"
          columns={columns}
          data={fuels.data ?? []}
          getRowId={(f) => f.id}
          empty={<p className="text-sm text-muted">No fuel types yet.</p>}
        />
      )}
      {dialog?.kind === 'change' && (
        <ChangePriceDialog fuel={dialog.fuel} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === 'history' && (
        <HistoryDialog fuel={dialog.fuel} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}
