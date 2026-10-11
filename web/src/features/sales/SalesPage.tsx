import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { ChevronLeft, ChevronRight, Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { DocumentActions } from '@/components/DocumentActions';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge, type Tone } from '@/components/ui/StatusBadge';
import { TabbedPanel } from '@/components/ui/TabbedPanel';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { formatDateTime, formatMoney, formatQuantity, titleCase } from '@/lib/format';
import { P } from '@/lib/permissions';
import {
  PAGE_SIZE,
  getReceiptHtml,
  useCancelSale,
  useCreateCustomer,
  useCreateMySale,
  useCreateSale,
  useCustomerStatus,
  useCustomers,
  usePaymentAction,
  useSaleOptions,
  useSalesPage,
  useTodayByFuel,
  type Customer,
  type Sale,
} from './queries';

const METHODS = ['cash', 'upi', 'card', 'credit'] as const;
const blank = (s: string) => (s.trim() === '' ? undefined : s.trim());
const tone = (s: string): Tone =>
  s === 'completed' || s === 'success' || s === 'paid'
    ? 'ok'
    : s === 'cancelled' || s === 'failed'
      ? 'danger'
      : s === 'refunded'
        ? 'warn'
        : 'info';
const Status = ({ status }: { status: string }) => (
  <StatusBadge tone={tone(status)}>{titleCase(status)}</StatusBadge>
);

// ------------------------------------------------------------ fuel revenue cards
function TodayCards() {
  const today = useTodayByFuel();
  // A broken card row must never block the whole screen (same as Qt): hide it on any error.
  if (today.isLoading || today.isError) return null;
  const cards = today.data ?? [];
  return (
    <ul className="grid gap-4 sm:grid-cols-3" aria-label="Today's revenue by fuel">
      {(cards.length
        ? cards
        : [{ fuel_type: 'No sales today', amount: '0.00', quantity: '0' }]
      ).map((c) => (
        <li
          key={c.fuel_type}
          className="flex flex-col gap-1 rounded-lg border border-line bg-surface p-4 shadow-card"
        >
          <p className="text-xs font-bold tracking-widest text-muted uppercase">{c.fuel_type}</p>
          <p className="num text-2xl font-bold">{formatMoney(c.amount)}</p>
          <p className="num text-sm text-muted">{formatQuantity(c.quantity)} L today</p>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ record sale
const saleSchema = z.object({
  shift_id: z.string(),
  nozzle_id: z.string(),
  employee_id: z.string(),
  quantity: z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,9}(\.\d{1,3})?$/.test(v) || Number(v) <= 0)
        ctx.addIssue({ code: 'custom', message: 'Enter a quantity above zero, such as 10.' });
    }),
  payment_method: z.enum(METHODS),
  customer_id: z.string(),
  reference_number: z.string(),
  remarks: z.string(),
});

function RecordSaleDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const options = useSaleOptions();
  const create = useCreateSale();
  const createMine = useCreateMySale();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors },
  } = useForm<z.infer<typeof saleSchema>>({
    resolver: zodResolver(saleSchema),
    defaultValues: {
      shift_id: '',
      nozzle_id: '',
      employee_id: '',
      quantity: '10',
      payment_method: 'cash',
      customer_id: '',
      reference_number: '',
      remarks: '',
    },
  });
  const method = watch('payment_method');
  const o = options.data;
  const free = o?.can_pick_freely ?? false;

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    if (!o) return;
    if (free) {
      if (!v.shift_id) return setFormError('No open shifts available.');
      if (!v.nozzle_id) return setFormError('No active nozzles available.');
      if (!v.employee_id) return setFormError('No employees available.');
    } else if (!o.my_assignment) {
      return setFormError('You have no active nozzle assignment.');
    }
    const common = {
      quantity: v.quantity,
      payment_method: v.payment_method,
      customer_id: v.customer_id || undefined,
      reference_number: blank(v.reference_number),
      remarks: blank(v.remarks),
    };
    try {
      if (free) {
        await create.mutateAsync({
          shift_id: v.shift_id,
          nozzle_id: v.nozzle_id,
          employee_id: v.employee_id,
          ...common,
        });
      } else {
        await createMine.mutateAsync(common);
      }
      toast.success('Sale recorded.');
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['quantity', 'payment_method']));
    }
  });

  return (
    <FormDialog
      title="Record sale"
      submitLabel="Record sale"
      busy={create.isPending || createMine.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      {free ? (
        <>
          <SelectField label="Shift" {...register('shift_id')}>
            <option value="">Choose an open shift</option>
            {o?.shifts.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </SelectField>
          <SelectField label="Nozzle" {...register('nozzle_id')}>
            <option value="">Choose a nozzle</option>
            {o?.nozzles.map((n) => (
              <option key={n.id} value={n.id}>
                {n.label}
              </option>
            ))}
          </SelectField>
          <SelectField label="Attendant" {...register('employee_id')}>
            <option value="">Choose an attendant</option>
            {o?.employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.label}
              </option>
            ))}
          </SelectField>
        </>
      ) : (
        o && (
          <p className="text-sm text-muted">
            {o.my_assignment
              ? `Selling from your current assignment: ${o.my_assignment.nozzle ?? ''}`
              : 'You have no active nozzle assignment - ask a supervisor to assign you one first.'}
          </p>
        )
      )}
      <DecimalField
        label="Quantity (L)"
        error={errors.quantity?.message}
        {...register('quantity')}
      />
      <SelectField label="Payment method" {...register('payment_method')}>
        {METHODS.map((m) => (
          <option key={m} value={m}>
            {titleCase(m)}
          </option>
        ))}
      </SelectField>
      <SelectField
        label={method === 'credit' ? 'Customer (required for credit)' : 'Customer'}
        {...register('customer_id')}
      >
        <option value="">(none)</option>
        {o?.customers.map((c) => (
          <option key={c.id} value={c.id}>
            {c.label}
          </option>
        ))}
      </SelectField>
      {(method === 'upi' || method === 'card') && (
        <TextField label="UPI/Card reference" {...register('reference_number')} />
      )}
      <TextField label="Remarks" optional {...register('remarks')} />
    </FormDialog>
  );
}

// -------------------------------------------------------------------- sales tab
type Dialog = { kind: 'record' } | { kind: 'cancel' | 'mark-failed' | 'refund'; sale: Sale } | null;

function SalesPanel({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const [page, setPage] = useState(0);
  const sales = useSalesPage(page);
  const cancel = useCancelSale();
  const paymentAction = usePaymentAction();
  const [selected, setSelected] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);

  const total = sales.data?.total ?? 0;
  const items = sales.data?.items ?? [];
  const lastPage = total ? Math.floor((total - 1) / PAGE_SIZE) : 0;
  const sale = items.find((s) => s.id === selected) ?? null;
  const first = items.length ? page * PAGE_SIZE + 1 : 0;

  const columns: ColumnDef<Sale>[] = [
    {
      id: 'select',
      header: () => <span className="sr-only">Select</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <input
          type="radio"
          name="selected-sale"
          aria-label={`Select sale ${row.original.receipt_number}`}
          checked={selected === row.original.id}
          onChange={() => setSelected(row.original.id)}
          className="size-5"
        />
      ),
    },
    { accessorKey: 'receipt_number', header: 'Receipt #' },
    {
      accessorKey: 'sale_at',
      header: 'When',
      cell: ({ getValue }) => formatDateTime(getValue<string>()),
    },
    { accessorKey: 'fuel_type', header: 'Fuel', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'quantity',
      header: 'Quantity',
      meta: { numeric: true },
      cell: ({ getValue }) => formatQuantity(getValue<string>()),
    },
    {
      accessorKey: 'amount',
      header: 'Amount',
      meta: { numeric: true },
      cell: ({ getValue }) => formatMoney(getValue<string>()),
    },
    {
      accessorKey: 'payment_method',
      header: 'Method',
      cell: ({ getValue }) => titleCase(getValue<string>()),
    },
    {
      accessorKey: 'status',
      header: 'Sale status',
      cell: ({ getValue }) => <Status status={getValue<string>()} />,
    },
    {
      accessorKey: 'payment_status',
      header: 'Payment status',
      cell: ({ getValue }) => (getValue() ? <Status status={getValue<string>()} /> : ''),
    },
  ];

  return (
    <>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <DocumentActions
          disabled={!sale}
          getHtml={() => getReceiptHtml(sale!.id)}
          previewLabel="Print receipt"
          files={
            sale
              ? [
                  {
                    label: 'PDF',
                    path: `/sales/${sale.id}/receipt.pdf`,
                    filename: `receipt_${sale.receipt_number}.pdf`,
                  },
                ]
              : []
          }
        />
        {canManage && (
          <>
            <Button
              disabled={!sale?.payment_id}
              onClick={() => sale && setDialog({ kind: 'refund', sale })}
            >
              Refund payment
            </Button>
            <Button
              disabled={!sale?.payment_id}
              onClick={() => sale && setDialog({ kind: 'mark-failed', sale })}
            >
              Mark payment failed
            </Button>
            <Button
              variant="danger"
              disabled={!sale}
              onClick={() => sale && setDialog({ kind: 'cancel', sale })}
            >
              Cancel selected
            </Button>
            <Button variant="primary" onClick={() => setDialog({ kind: 'record' })}>
              <Plus className="size-4" aria-hidden /> Record sale
            </Button>
          </>
        )}
      </div>
      {!sale && items.length > 0 && (
        <p className="text-sm text-muted">Select a sale to print its receipt or act on it.</p>
      )}
      {sales.isLoading ? (
        <LoadingBlock label="Loading sales" rows={5} />
      ) : sales.isError ? (
        <ErrorState error={sales.error} onRetry={() => void sales.refetch()} />
      ) : (
        <DataTable
          caption="Sales"
          columns={columns}
          data={items}
          getRowId={(s) => s.id}
          empty={<EmptyState title="No sales yet" />}
        />
      )}
      <div className="flex items-center gap-3">
        <Button
          disabled={page <= 0}
          onClick={() => {
            setPage(page - 1);
            setSelected(null);
          }}
        >
          <ChevronLeft className="size-4" aria-hidden /> Previous
        </Button>
        <Button
          disabled={page >= lastPage}
          onClick={() => {
            setPage(page + 1);
            setSelected(null);
          }}
        >
          Next <ChevronRight className="size-4" aria-hidden />
        </Button>
        <p className="text-sm text-muted" aria-live="polite">
          {total
            ? `Showing ${first}-${page * PAGE_SIZE + items.length} of ${total}`
            : 'No sales yet'}
        </p>
      </div>

      {dialog?.kind === 'record' && <RecordSaleDialog onClose={() => setDialog(null)} />}
      {dialog && dialog.kind !== 'record' && (
        <ReasonDialog
          title={
            dialog.kind === 'cancel'
              ? 'Cancel sale'
              : dialog.kind === 'refund'
                ? 'Refund payment'
                : 'Mark payment failed'
          }
          description={`Receipt ${dialog.sale.receipt_number}`}
          submitLabel={
            dialog.kind === 'cancel'
              ? 'Cancel sale'
              : dialog.kind === 'refund'
                ? 'Refund payment'
                : 'Mark payment failed'
          }
          tone="danger"
          onConfirm={async (reason) => {
            if (dialog.kind === 'cancel') await cancel.mutateAsync({ id: dialog.sale.id, reason });
            else
              await paymentAction.mutateAsync({
                id: dialog.sale.payment_id!,
                action: dialog.kind,
                reason,
              });
            toast.success('Done.');
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}

// -------------------------------------------------------------- customers tab
const customerSchema = z.object({
  name: z.string().trim().min(1, 'Enter the customer name.'),
  phone: z.string(),
  email: z.string(),
  address: z.string(),
});

export function AddCustomerDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated?: (c: Customer) => void;
}) {
  const toast = useToast();
  const create = useCreateCustomer();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof customerSchema>>({
    resolver: zodResolver(customerSchema),
    defaultValues: { name: '', phone: '', email: '', address: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      const created = await create.mutateAsync({
        name: v.name.trim(),
        phone: blank(v.phone),
        email: blank(v.email),
        address: blank(v.address),
      });
      toast.success(`Customer ${v.name.trim()} added.`);
      onCreated?.(created);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['name', 'phone', 'email', 'address']));
    }
  });
  return (
    <FormDialog
      title="Add customer"
      submitLabel="Save"
      busy={create.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField label="Name" autoFocus error={errors.name?.message} {...register('name')} />
      <TextField label="Phone" optional {...register('phone')} />
      <TextField label="Email" optional {...register('email')} />
      <TextField label="Address" optional {...register('address')} />
    </FormDialog>
  );
}

function CustomersPanel({ canManage }: { canManage: boolean }) {
  const customers = useCustomers();
  const setStatus = useCustomerStatus();
  const [adding, setAdding] = useState(false);
  const [toggling, setToggling] = useState<Customer | null>(null);
  const next = toggling?.status === 'active' ? 'inactive' : 'active';
  const columns: ColumnDef<Customer>[] = [
    { accessorKey: 'name', header: 'Name' },
    { accessorKey: 'phone', header: 'Phone', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => (
        <StatusBadge tone={getValue<string>() === 'active' ? 'ok' : 'neutral'}>
          {titleCase(getValue<string>())}
        </StatusBadge>
      ),
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) =>
        canManage ? (
          <button
            type="button"
            aria-label={`${row.original.status === 'active' ? 'Mark inactive' : 'Mark active'} - ${row.original.name}`}
            onClick={() => setToggling(row.original)}
            className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-2"
          >
            <Pencil className="size-4" aria-hidden />
          </button>
        ) : null,
    },
  ];
  return (
    <>
      {canManage && (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden /> Add customer
          </Button>
        </div>
      )}
      {customers.isLoading ? (
        <LoadingBlock label="Loading customers" rows={3} />
      ) : customers.isError ? (
        <ErrorState error={customers.error} onRetry={() => void customers.refetch()} />
      ) : (
        <DataTable
          caption="Customers"
          columns={columns}
          data={customers.data ?? []}
          getRowId={(c) => c.id}
          empty={<EmptyState title="No customers yet" />}
        />
      )}
      {adding && <AddCustomerDialog onClose={() => setAdding(false)} />}
      {toggling && (
        <ReasonDialog
          title="Change status"
          description={toggling.name}
          label={`Reason to mark ${next}`}
          submitLabel={`Mark ${next}`}
          tone={next === 'inactive' ? 'danger' : 'primary'}
          onConfirm={(reason) => setStatus.mutateAsync({ id: toggling.id, status: next, reason })}
          onClose={() => setToggling(null)}
        />
      )}
    </>
  );
}

export function SalesPage() {
  const { can } = useAuth();
  const canManage = can(P.SALE_MANAGE);
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Sales"
        subtitle="Record and review fuel sales, print receipts, and manage customers."
      />
      <TodayCards />
      <TabbedPanel
        label="Sales"
        tabs={[
          { value: 'sales', label: 'Sales', content: <SalesPanel canManage={canManage} /> },
          {
            value: 'customers',
            label: 'Customers',
            content: <CustomersPanel canManage={canManage} />,
          },
        ]}
      />
    </div>
  );
}
