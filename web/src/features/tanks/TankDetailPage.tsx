import * as Tabs from '@radix-ui/react-tabs';
import type { ColumnDef } from '@tanstack/react-table';
import { ArrowLeft } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import type {
  Reconciliation,
  Tank,
  TankReading,
  TankTransaction,
  TransactionType,
} from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { Button } from '@/components/ui/Button';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDate, formatDateTime, formatQuantity, titleCase } from '@/lib/format';
import { P } from '@/lib/permissions';
import { ReadingDialog, ReconcileDialog, StatusDialog, TransactionDialog } from './dialogs';
import { useReadings, useReconciliations, useTank, useTransactions } from './queries';
import { VarianceBars } from './VarianceBars';
import { GaugeBar, LevelBadge, StatusPill, StockFigures } from './TankGauge';

type DialogState =
  | { kind: 'txn'; type: TransactionType }
  | { kind: 'reading' }
  | { kind: 'reconcile' }
  | { kind: 'status' }
  | null;

const txnColumns: ColumnDef<TankTransaction>[] = [
  {
    accessorKey: 'transaction_at',
    header: 'Date',
    cell: ({ getValue }) => formatDateTime(getValue<string>()),
  },
  {
    accessorKey: 'transaction_type',
    header: 'Type',
    cell: ({ getValue }) => titleCase(getValue<string>()),
  },
  {
    accessorKey: 'quantity',
    header: 'Quantity (L)',
    meta: { numeric: true },
    cell: ({ getValue }) => formatQuantity(getValue<string>(), { signed: true }),
  },
  {
    accessorKey: 'reference',
    header: 'Reference',
    cell: ({ getValue }) => getValue<string | null>() ?? '',
  },
  { accessorKey: 'recorded_by', header: 'Recorded by' },
];

const readingColumns: ColumnDef<TankReading>[] = [
  {
    accessorKey: 'reading_at',
    header: 'Date',
    cell: ({ getValue }) => formatDateTime(getValue<string>()),
  },
  {
    accessorKey: 'physical_stock',
    header: 'Physical stock (L)',
    meta: { numeric: true },
    cell: ({ getValue }) => formatQuantity(getValue<string>()),
  },
  {
    accessorKey: 'dip_value',
    header: 'Dip',
    meta: { numeric: true },
    cell: ({ getValue }) => {
      const v = getValue<string | null>();
      return v ? formatQuantity(v) : '';
    },
  },
  { accessorKey: 'employee_name', header: 'Taken by' },
];

function classificationTone(c: string) {
  return c === 'normal' ? 'ok' : c === 'warning' ? 'warn' : 'danger';
}

const reconColumns: ColumnDef<Reconciliation>[] = [
  {
    accessorKey: 'reconciliation_date',
    header: 'Date',
    cell: ({ getValue }) => formatDate(getValue<string>()),
  },
  {
    accessorKey: 'expected_closing_stock',
    header: 'Expected (L)',
    meta: { numeric: true },
    cell: ({ getValue }) => formatQuantity(getValue<string>()),
  },
  {
    accessorKey: 'physical_stock',
    header: 'Physical (L)',
    meta: { numeric: true },
    cell: ({ getValue }) => formatQuantity(getValue<string>()),
  },
  {
    accessorKey: 'variance',
    header: 'Variance (L)',
    meta: { numeric: true },
    cell: ({ getValue }) => formatQuantity(getValue<string>(), { signed: true }),
  },
  {
    accessorKey: 'classification',
    header: 'Classification',
    cell: ({ getValue }) => (
      <StatusBadge tone={classificationTone(getValue<string>())}>
        {titleCase(getValue<string>())}
      </StatusBadge>
    ),
  },
];

function TabPanel<T>({
  query,
  caption,
  columns,
  emptyTitle,
}: {
  query: {
    isLoading: boolean;
    isError: boolean;
    error: unknown;
    data: T[] | undefined;
    refetch: () => unknown;
  };
  caption: string;
  columns: ColumnDef<T>[];
  emptyTitle: string;
}) {
  if (query.isLoading) return <LoadingBlock label={`Loading ${caption.toLowerCase()}`} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <DataTable
      caption={caption}
      columns={columns}
      data={query.data ?? []}
      empty={<EmptyState title={emptyTitle} />}
    />
  );
}

function Body({ tank }: { tank: Tank }) {
  const { can } = useAuth();
  const canManage = can(P.INVENTORY_MANAGE);
  const [dialog, setDialog] = useState<DialogState>(null);
  const close = () => setDialog(null);
  const transactions = useTransactions(tank.id);
  const readings = useReadings(tank.id);
  const recons = useReconciliations(tank.id);
  const latest = recons.data?.[0];
  const why = canManage ? undefined : 'Needs the inventory.manage permission';

  const actions: Array<[string, () => void, 'primary' | 'secondary' | 'danger']> = [
    ['Receipt', () => setDialog({ kind: 'txn', type: 'receipt' }), 'primary'],
    ['Issue', () => setDialog({ kind: 'txn', type: 'issue' }), 'primary'],
    ['Adjustment', () => setDialog({ kind: 'txn', type: 'adjustment' }), 'secondary'],
    ['Record reading', () => setDialog({ kind: 'reading' }), 'secondary'],
    ['Reconcile', () => setDialog({ kind: 'reconcile' }), 'danger'],
    ['Change status', () => setDialog({ kind: 'status' }), 'secondary'],
  ];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div>
        <Link
          to="/tanks"
          className="inline-flex min-h-[44px] items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
        >
          <ArrowLeft className="size-4" aria-hidden /> All tanks
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">Tank {tank.code}</h1>
          <span className="text-muted">{tank.fuel_type}</span>
          <StatusPill status={tank.status} />
        </div>
      </div>

      <section
        aria-label="Stock"
        className="grid items-center gap-5 rounded-lg border border-line bg-surface p-5 shadow-card sm:grid-cols-[auto_1fr]"
      >
        <StockFigures tank={tank} />
        <div className="flex flex-col gap-1.5">
          <GaugeBar percent={tank.fill_percent} low={tank.is_low} />
          <div className="flex justify-end">
            <LevelBadge tank={tank} />
          </div>
        </div>
      </section>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Actions">
        {actions.map(([label, run, variant]) => (
          <Button key={label} variant={variant} onClick={run} disabled={!canManage} title={why}>
            {label}
          </Button>
        ))}
      </div>
      {!canManage && (
        <p className="text-sm text-muted">
          You can look at this tank but not change it. Ask a manager to record movements.
        </p>
      )}

      <Tabs.Root defaultValue="transactions">
        <Tabs.List aria-label="Tank history" className="flex gap-1 border-b border-line">
          {[
            ['transactions', 'Transactions'],
            ['readings', 'Readings'],
            ['reconciliation', 'Reconciliation'],
          ].map(([v, l]) => (
            <Tabs.Trigger
              key={v}
              value={v!}
              className="min-h-[44px] border-b-2 border-transparent px-4 text-sm font-semibold text-muted data-[state=active]:border-primary data-[state=active]:text-fg"
            >
              {l}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="transactions" className="pt-4">
          <TabPanel
            query={transactions}
            caption="Transactions"
            columns={txnColumns}
            emptyTitle="No transactions for this tank yet"
          />
        </Tabs.Content>
        <Tabs.Content value="readings" className="pt-4">
          <TabPanel
            query={readings}
            caption="Readings"
            columns={readingColumns}
            emptyTitle="No readings for this tank yet"
          />
        </Tabs.Content>
        <Tabs.Content value="reconciliation" className="flex flex-col gap-4 pt-4">
          {latest && <VarianceBars reconciliation={latest} />}
          <TabPanel
            query={recons}
            caption="Reconciliations"
            columns={reconColumns}
            emptyTitle="No reconciliations yet"
          />
        </Tabs.Content>
      </Tabs.Root>

      {dialog?.kind === 'txn' && (
        <TransactionDialog tank={tank} type={dialog.type} onClose={close} />
      )}
      {dialog?.kind === 'reading' && <ReadingDialog tank={tank} onClose={close} />}
      {dialog?.kind === 'reconcile' && <ReconcileDialog tank={tank} onClose={close} />}
      {dialog?.kind === 'status' && <StatusDialog tank={tank} onClose={close} />}
    </div>
  );
}

export function TankDetailPage() {
  const { id = '' } = useParams();
  const tank = useTank(id);
  if (tank.isLoading) return <LoadingBlock label="Loading tank" rows={4} />;
  if (tank.isError || !tank.data)
    return <ErrorState error={tank.error} onRetry={() => void tank.refetch()} />;
  return <Body tank={tank.data} />;
}
