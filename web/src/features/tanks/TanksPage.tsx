import type { ColumnDef } from '@tanstack/react-table';
import { ClipboardList, LayoutGrid, Plus, Table2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Tank, TankTransaction } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { Button } from '@/components/ui/Button';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { cn } from '@/lib/cn';
import { formatDateTime, formatQuantity, titleCase } from '@/lib/format';
import { P } from '@/lib/permissions';
import { AddTankDialog, ReadingDialog, TransactionDialog } from './dialogs';
import { useRecentTransactions, useTanks } from './queries';
import { GaugeBar, LevelBadge, StatusPill, StockFigures } from './TankGauge';

// ONE state value for "which dialog is open": two dialogs can never stack or duplicate.
type DialogState =
  { kind: 'add' } | { kind: 'receipt'; tank: Tank } | { kind: 'reading'; tank: Tank } | null;

function TankCard({
  tank,
  canManage,
  onAction,
}: {
  tank: Tank;
  canManage: boolean;
  onAction: (d: DialogState) => void;
}) {
  return (
    <li className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold">
            <Link to={`/tanks/${tank.id}`} className="rounded underline-offset-4 hover:underline">
              {tank.code}
            </Link>
          </h3>
          <p className="text-sm text-muted">{tank.fuel_type}</p>
        </div>
        <StatusPill status={tank.status} />
      </div>
      <StockFigures tank={tank} />
      <div className="flex flex-col gap-1.5">
        <GaugeBar percent={tank.fill_percent} low={tank.is_low} />
        <div className="flex justify-end">
          <LevelBadge tank={tank} />
        </div>
      </div>
      <div className="mt-auto flex flex-wrap gap-2">
        <Link
          to={`/tanks/${tank.id}`}
          className="inline-flex min-h-[44px] items-center rounded-md border border-line-strong px-4 text-sm font-semibold hover:bg-surface-2"
        >
          Open
        </Link>
        {canManage && (
          <>
            <Button onClick={() => onAction({ kind: 'reading', tank })}>Record reading</Button>
            <Button onClick={() => onAction({ kind: 'receipt', tank })}>Receipt</Button>
          </>
        )}
      </div>
    </li>
  );
}

const tankColumns: ColumnDef<Tank>[] = [
  {
    accessorKey: 'code',
    header: 'Code',
    cell: ({ row }) => (
      <Link
        className="font-semibold underline-offset-4 hover:underline"
        to={`/tanks/${row.original.id}`}
      >
        {row.original.code}
      </Link>
    ),
  },
  { accessorKey: 'fuel_type', header: 'Fuel' },
  {
    accessorKey: 'capacity',
    header: 'Capacity (L)',
    meta: { numeric: true },
    cell: ({ getValue }) => formatQuantity(getValue<string>()),
  },
  {
    accessorKey: 'current_stock',
    header: 'Stock (L)',
    meta: { numeric: true },
    cell: ({ getValue }) => formatQuantity(getValue<string>()),
  },
  {
    accessorKey: 'fill_percent',
    header: 'Level',
    meta: { numeric: true },
    cell: ({ row }) => <LevelBadge tank={row.original} />,
  },
  {
    accessorKey: 'status',
    header: 'Status',
    cell: ({ getValue }) => <StatusPill status={getValue<string>()} />,
  },
];

function RecentTransactions() {
  const recent = useRecentTransactions();
  return (
    <section
      aria-labelledby="recent-title"
      className="rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <h2 id="recent-title" className="mb-3 flex items-center gap-2 text-base font-bold">
        <ClipboardList className="size-4" aria-hidden /> Recent transactions
      </h2>
      {recent.isLoading ? (
        <LoadingBlock label="Loading recent transactions" rows={3} />
      ) : recent.isError ? (
        <ErrorState error={recent.error} onRetry={() => void recent.refetch()} />
      ) : recent.data && recent.data.length > 0 ? (
        <ul className="flex flex-col divide-y divide-line">
          {recent.data.map((t: TankTransaction) => (
            <li key={t.id} className="py-2.5">
              <p className="text-sm font-semibold">
                {titleCase(t.transaction_type)} - {t.tank_code}
              </p>
              <p className="num text-sm text-muted">
                {formatQuantity(t.quantity, { signed: true })} L -{' '}
                {formatDateTime(t.transaction_at)}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">No transactions recorded yet.</p>
      )}
    </section>
  );
}

export function TanksPage() {
  const { can } = useAuth();
  const canManage = can(P.INVENTORY_MANAGE);
  const tanks = useTanks();
  const [view, setView] = useState<'cards' | 'table'>('cards');
  const [dialog, setDialog] = useState<DialogState>(null);
  const close = () => setDialog(null);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Tanks &amp; Inventory</h1>
          <p className="text-sm text-muted">
            Stock level in every tank. Open one to record movements and reconcile.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div
            role="group"
            aria-label="View"
            className="flex overflow-hidden rounded-md border border-line-strong"
          >
            {(
              [
                ['cards', 'Cards', LayoutGrid],
                ['table', 'Table', Table2],
              ] as const
            ).map(([id, label, Icon]) => (
              <button
                key={id}
                type="button"
                aria-pressed={view === id}
                onClick={() => setView(id)}
                className={cn(
                  'inline-flex min-h-[44px] items-center gap-2 px-3 text-sm font-semibold',
                  view === id ? 'bg-primary text-primary-fg' : 'bg-surface hover:bg-surface-2',
                )}
              >
                <Icon className="size-4" aria-hidden /> {label}
              </button>
            ))}
          </div>
          {canManage && (
            <Button variant="primary" onClick={() => setDialog({ kind: 'add' })}>
              <Plus className="size-4" aria-hidden /> Add tank
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_20rem]">
        <section aria-label="Tanks">
          {tanks.isLoading ? (
            <LoadingBlock label="Loading tanks" rows={4} />
          ) : tanks.isError ? (
            <ErrorState error={tanks.error} onRetry={() => void tanks.refetch()} />
          ) : tanks.data && tanks.data.length === 0 ? (
            <EmptyState title="No tanks yet">
              {canManage
                ? 'Add your first tank to start tracking stock.'
                : 'A manager needs to add the tanks first.'}
            </EmptyState>
          ) : view === 'cards' ? (
            <ul className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
              {tanks.data?.map((t) => (
                <TankCard key={t.id} tank={t} canManage={canManage} onAction={setDialog} />
              ))}
            </ul>
          ) : (
            <DataTable
              caption="All tanks"
              columns={tankColumns}
              data={tanks.data ?? []}
              getRowId={(t) => t.id}
              empty={null}
            />
          )}
        </section>
        <RecentTransactions />
      </div>

      {dialog?.kind === 'add' && <AddTankDialog open onClose={close} />}
      {dialog?.kind === 'receipt' && (
        <TransactionDialog tank={dialog.tank} type="receipt" onClose={close} />
      )}
      {dialog?.kind === 'reading' && <ReadingDialog tank={dialog.tank} onClose={close} />}
    </div>
  );
}
