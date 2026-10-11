import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
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
import {
  addDaysIso,
  formatDate,
  formatMoney,
  formatQuantity,
  titleCase,
  todayIso,
} from '@/lib/format';
import { P } from '@/lib/permissions';
import {
  useCreateInvoice,
  useCreateOrder,
  useCreateSupplier,
  useInvoices,
  useOrderOptions,
  useOrders,
  useSupplierStatus,
  useSuppliers,
  type Invoice,
  type PurchaseOrder,
  type Supplier,
} from './queries';

export const statusTone = (status: string): Tone => {
  if (['active', 'paid', 'delivered', 'unloaded'].includes(status)) return 'ok';
  if (['cancelled', 'rejected', 'overdue'].includes(status)) return 'danger';
  if (['inactive'].includes(status)) return 'neutral';
  return 'info';
};
export const StatusText = ({ status }: { status: string }) => (
  <StatusBadge tone={statusTone(status)}>{titleCase(status)}</StatusBadge>
);

// The same "still owed to us" statuses the Qt card row and the dashboard use.
const PENDING = new Set(['draft', 'placed', 'partially_delivered']);
const PENDING_SHOWN = 3;

// ---------------------------------------------------------------- suppliers
const supplierSchema = z.object({
  name: z.string().trim().min(1, 'Enter the supplier name.'),
  contact_person: z.string(),
  phone: z.string(),
  email: z.string(),
  address: z.string(),
  gst_number: z.string(),
});
const blank = (s: string) => (s.trim() === '' ? undefined : s.trim());

function AddSupplierDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const create = useCreateSupplier();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof supplierSchema>>({
    resolver: zodResolver(supplierSchema),
    defaultValues: {
      name: '',
      contact_person: '',
      phone: '',
      email: '',
      address: '',
      gst_number: '',
    },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({
        name: v.name.trim(),
        contact_person: blank(v.contact_person),
        phone: blank(v.phone),
        email: blank(v.email),
        address: blank(v.address),
        gst_number: blank(v.gst_number),
      });
      toast.success(`Supplier ${v.name.trim()} added.`);
      onClose();
    } catch (error) {
      setFormError(
        applyApiError(error, setError, [
          'name',
          'contact_person',
          'phone',
          'email',
          'address',
          'gst_number',
        ]),
      );
    }
  });
  return (
    <FormDialog
      title="Add supplier"
      submitLabel="Save"
      busy={create.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField label="Name" autoFocus error={errors.name?.message} {...register('name')} />
      <TextField label="Contact person" optional {...register('contact_person')} />
      <TextField label="Phone" optional {...register('phone')} />
      <TextField label="Email" optional {...register('email')} />
      <TextField label="Address" optional {...register('address')} />
      <TextField label="GST number" optional {...register('gst_number')} />
    </FormDialog>
  );
}

function SuppliersPanel({ canManage }: { canManage: boolean }) {
  const suppliers = useSuppliers();
  const setStatus = useSupplierStatus();
  const [adding, setAdding] = useState(false);
  const [toggling, setToggling] = useState<Supplier | null>(null);
  const columns: ColumnDef<Supplier>[] = [
    { accessorKey: 'name', header: 'Name' },
    { accessorKey: 'contact_person', header: 'Contact', cell: ({ getValue }) => getValue() ?? '' },
    { accessorKey: 'phone', header: 'Phone', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <StatusText status={getValue<string>()} />,
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
  const next = toggling?.status === 'active' ? 'inactive' : 'active';
  return (
    <>
      {canManage && (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden /> Add supplier
          </Button>
        </div>
      )}
      {suppliers.isLoading ? (
        <LoadingBlock label="Loading suppliers" rows={3} />
      ) : suppliers.isError ? (
        <ErrorState error={suppliers.error} onRetry={() => void suppliers.refetch()} />
      ) : (
        <DataTable
          caption="Suppliers"
          columns={columns}
          data={suppliers.data ?? []}
          getRowId={(s) => s.id}
          empty={<EmptyState title="No suppliers yet" />}
        />
      )}
      {adding && <AddSupplierDialog onClose={() => setAdding(false)} />}
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

// ----------------------------------------------------------- purchase orders
interface DraftItem {
  fuel_id: string;
  fuel_type: string;
  quantity: string;
  rate: string;
}

const orderTop = z.object({
  supplier_id: z.string().min(1, 'Choose a supplier.'),
  expected: z.string(),
  remarks: z.string(),
  fuel_id: z.string(),
  quantity: z.string(),
  rate: z.string(),
});

function AddOrderDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const options = useOrderOptions();
  const create = useCreateOrder();
  const [items, setItems] = useState<DraftItem[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [itemError, setItemError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    getValues,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof orderTop>>({
    resolver: zodResolver(orderTop),
    // Same starting values as the Qt dialog: ETA in 3 days, 1000 L at 95.
    defaultValues: {
      supplier_id: '',
      expected: addDaysIso(3),
      remarks: '',
      fuel_id: '',
      quantity: '1000',
      rate: '95',
    },
  });

  function addItem() {
    setItemError(null);
    const { fuel_id, quantity, rate } = getValues();
    const fuel = options.data?.fuels.find((f) => f.id === (fuel_id || options.data?.fuels[0]?.id));
    if (!fuel) return setItemError('No fuel types available.');
    if (!/^\d{1,9}(\.\d{1,2})?$/.test(quantity.trim()) || Number(quantity) <= 0)
      return setItemError('Enter a quantity above zero, such as 1000.');
    if (!/^\d{1,8}(\.\d{1,2})?$/.test(rate.trim()) || Number(rate) <= 0)
      return setItemError('Enter a rate above zero, such as 95.50.');
    setItems((prev) => [
      ...prev,
      { fuel_id: fuel.id, fuel_type: fuel.fuel_type, quantity: quantity.trim(), rate: rate.trim() },
    ]);
  }

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    if (items.length === 0) return setFormError('Add at least one item to the order.');
    try {
      await create.mutateAsync({
        supplier_id: v.supplier_id,
        expected_delivery_date: v.expected || undefined,
        remarks: blank(v.remarks),
        items: items.map((i) => ({
          fuel_id: i.fuel_id,
          quantity_ordered: i.quantity,
          rate_per_liter: i.rate,
        })),
      });
      toast.success('Purchase order created.');
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['supplier_id']));
    }
  });

  const noSuppliers = options.data && options.data.suppliers.length === 0;
  return (
    <FormDialog
      title="Create purchase order"
      submitLabel="Create order"
      busy={create.isPending}
      error={formError ?? (noSuppliers ? 'No active suppliers available.' : null)}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="Supplier"
        error={errors.supplier_id?.message}
        {...register('supplier_id')}
      >
        <option value="">Choose a supplier</option>
        {options.data?.suppliers.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </SelectField>
      <TextField label="Expected delivery" type="date" optional {...register('expected')} />
      <TextField label="Remarks" optional {...register('remarks')} />

      <fieldset className="flex flex-col gap-3 rounded-md border border-line p-3">
        <legend className="px-1 text-sm font-semibold">Order items</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <SelectField label="Fuel" {...register('fuel_id')}>
            {options.data?.fuels.map((f) => (
              <option key={f.id} value={f.id}>
                {f.fuel_type}
              </option>
            ))}
          </SelectField>
          <DecimalField
            label="Quantity (L)"
            maxFraction={2}
            unit="litres"
            {...register('quantity')}
          />
          <DecimalField
            label="Rate per litre"
            maxFraction={2}
            unit="rupees"
            {...register('rate')}
          />
        </div>
        {itemError && (
          <p role="alert" className="text-sm font-medium text-danger-fg">
            {itemError}
          </p>
        )}
        <div>
          <Button onClick={addItem}>
            <Plus className="size-4" aria-hidden /> Add item
          </Button>
        </div>
        {items.length > 0 && (
          <table className="w-full text-sm">
            <caption className="sr-only">Items on this order</caption>
            <thead>
              <tr className="text-left text-xs text-muted uppercase">
                <th scope="col">Fuel</th>
                <th scope="col" className="text-right">
                  Quantity
                </th>
                <th scope="col" className="text-right">
                  Rate/L
                </th>
                <th scope="col">
                  <span className="sr-only">Remove</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((i, idx) => (
                <tr key={idx} className="border-t border-line">
                  <td className="py-1.5">{i.fuel_type}</td>
                  <td className="num text-right">{formatQuantity(i.quantity)}</td>
                  <td className="num text-right">{formatMoney(i.rate)}</td>
                  <td className="text-right">
                    <button
                      type="button"
                      aria-label={`Remove ${i.fuel_type} item`}
                      onClick={() => setItems((prev) => prev.filter((_, j) => j !== idx))}
                      className="inline-flex size-8 items-center justify-center rounded-md hover:bg-surface-2"
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </fieldset>
    </FormDialog>
  );
}

function PendingCards({ orders }: { orders: PurchaseOrder[] }) {
  const pending = orders.filter((o) => PENDING.has(o.status)).slice(0, PENDING_SHOWN);
  return (
    <section aria-labelledby="pending-title" className="flex flex-col gap-3">
      <h2 id="pending-title" className="text-base font-bold">
        Pending Deliveries
      </h2>
      {pending.length === 0 ? (
        <p className="text-sm text-muted">Nothing pending - every order is delivered or cleared.</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-3">
          {pending.map((po) => {
            const fuels =
              [...new Set(po.items.map((i) => i.fuel_type).filter(Boolean))].sort().join(', ') ||
              '-';
            return (
              <li
                key={po.id}
                className="flex flex-col gap-1.5 rounded-lg border border-line bg-surface p-4 shadow-card"
              >
                <div className="flex items-center justify-between gap-2">
                  <Link
                    className="font-semibold underline-offset-4 hover:underline"
                    to={`/procurement/orders/${po.id}`}
                  >
                    {po.po_number}
                  </Link>
                  <StatusText status={po.status} />
                </div>
                <p className="font-semibold">{po.supplier}</p>
                <p className="text-sm text-muted">
                  {fuels} - {formatQuantity(po.total_quantity)} L
                </p>
                <p className="text-sm text-muted">
                  {po.expected_delivery_date ? formatDate(po.expected_delivery_date) : 'No ETA set'}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function OrdersPanel({ canManage }: { canManage: boolean }) {
  const orders = useOrders();
  const [adding, setAdding] = useState(false);
  const columns: ColumnDef<PurchaseOrder>[] = [
    {
      accessorKey: 'po_number',
      header: 'PO Number',
      cell: ({ row }) => (
        <Link
          className="font-semibold underline-offset-4 hover:underline"
          to={`/procurement/orders/${row.original.id}`}
        >
          {row.original.po_number}
        </Link>
      ),
    },
    { accessorKey: 'supplier', header: 'Supplier', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'order_date',
      header: 'Order Date',
      cell: ({ getValue }) => formatDate(getValue<string>()),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <StatusText status={getValue<string>()} />,
    },
  ];
  return (
    <>
      {canManage && (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden /> Create purchase order
          </Button>
        </div>
      )}
      {orders.isLoading ? (
        <LoadingBlock label="Loading purchase orders" rows={3} />
      ) : orders.isError ? (
        <ErrorState error={orders.error} onRetry={() => void orders.refetch()} />
      ) : (
        <>
          <PendingCards orders={orders.data ?? []} />
          <DataTable
            caption="Purchase orders"
            columns={columns}
            data={orders.data ?? []}
            getRowId={(o) => o.id}
            empty={<EmptyState title="No purchase orders yet" />}
          />
        </>
      )}
      {adding && <AddOrderDialog onClose={() => setAdding(false)} />}
    </>
  );
}

// ------------------------------------------------------------------ invoices
const invoiceSchema = z.object({
  invoice_number: z.string().trim().min(1, 'Enter the invoice number.'),
  supplier_id: z.string().min(1, 'Choose a supplier.'),
  purchase_order_id: z.string(),
  invoice_date: z.string().min(1, 'Pick the invoice date.'),
  due_date: z.string(),
  amount: z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,12}(\.\d{1,2})?$/.test(v) || Number(v) <= 0)
        ctx.addIssue({ code: 'custom', message: 'Enter an amount above zero, such as 1500.00.' });
    }),
  remarks: z.string(),
});

function AddInvoiceDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const suppliers = useSuppliers();
  const orders = useOrders();
  const create = useCreateInvoice();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof invoiceSchema>>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: {
      invoice_number: '',
      supplier_id: '',
      purchase_order_id: '',
      invoice_date: todayIso(),
      due_date: addDaysIso(30),
      amount: '',
      remarks: '',
    },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({
        invoice_number: v.invoice_number.trim(),
        supplier_id: v.supplier_id,
        purchase_order_id: v.purchase_order_id || undefined,
        invoice_date: v.invoice_date,
        due_date: v.due_date || undefined,
        amount: v.amount,
        remarks: blank(v.remarks),
      });
      toast.success(`Invoice ${v.invoice_number.trim()} recorded.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['invoice_number', 'supplier_id', 'amount']));
    }
  });
  return (
    <FormDialog
      title="Record supplier invoice"
      submitLabel="Save"
      busy={create.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Invoice number"
        autoFocus
        error={errors.invoice_number?.message}
        {...register('invoice_number')}
      />
      <SelectField
        label="Supplier"
        error={errors.supplier_id?.message}
        {...register('supplier_id')}
      >
        <option value="">Choose a supplier</option>
        {suppliers.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </SelectField>
      <SelectField label="Purchase order" {...register('purchase_order_id')}>
        <option value="">(none)</option>
        {orders.data?.map((o) => (
          <option key={o.id} value={o.id}>
            {o.po_number}
          </option>
        ))}
      </SelectField>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="Invoice date"
          type="date"
          error={errors.invoice_date?.message}
          {...register('invoice_date')}
        />
        <TextField label="Due date" type="date" optional {...register('due_date')} />
      </div>
      <DecimalField
        label="Amount"
        maxFraction={2}
        unit="rupees"
        error={errors.amount?.message}
        {...register('amount')}
      />
      <TextField label="Remarks" optional {...register('remarks')} />
    </FormDialog>
  );
}

function InvoicesPanel({ canManage }: { canManage: boolean }) {
  const invoices = useInvoices();
  const [adding, setAdding] = useState(false);
  const columns: ColumnDef<Invoice>[] = [
    {
      accessorKey: 'invoice_number',
      header: 'Invoice #',
      cell: ({ row }) => (
        <Link
          className="font-semibold underline-offset-4 hover:underline"
          to={`/procurement/invoices/${row.original.id}`}
        >
          {row.original.invoice_number}
        </Link>
      ),
    },
    { accessorKey: 'supplier', header: 'Supplier', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'invoice_date',
      header: 'Date',
      cell: ({ getValue }) => formatDate(getValue<string>()),
    },
    {
      accessorKey: 'amount',
      header: 'Amount',
      meta: { numeric: true },
      cell: ({ getValue }) => formatMoney(getValue<string>()),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <StatusText status={getValue<string>()} />,
    },
  ];
  return (
    <>
      {canManage && (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden /> Record invoice
          </Button>
        </div>
      )}
      {invoices.isLoading ? (
        <LoadingBlock label="Loading invoices" rows={3} />
      ) : invoices.isError ? (
        <ErrorState error={invoices.error} onRetry={() => void invoices.refetch()} />
      ) : (
        <DataTable
          caption="Supplier invoices"
          columns={columns}
          data={invoices.data ?? []}
          getRowId={(i) => i.id}
          empty={<EmptyState title="No invoices yet" />}
        />
      )}
      {adding && <AddInvoiceDialog onClose={() => setAdding(false)} />}
    </>
  );
}

// -------------------------------------------------------------------- page
export function ProcurementPage() {
  const { can } = useAuth();
  const canManage = can(P.PROCUREMENT_MANAGE);
  const [params] = useSearchParams();
  // The Suppliers tile and the Procurement tile open the same screen on different tabs, as in Qt.
  const tab =
    params.get('tab') === 'suppliers'
      ? 'suppliers'
      : params.get('tab') === 'invoices'
        ? 'invoices'
        : 'orders';
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="Procurement"
        subtitle="Suppliers, purchase orders, tanker deliveries and supplier invoices."
      />
      <TabbedPanel
        key={tab}
        label="Procurement"
        defaultValue={tab}
        tabs={[
          {
            value: 'suppliers',
            label: 'Suppliers',
            content: <SuppliersPanel canManage={canManage} />,
          },
          {
            value: 'orders',
            label: 'Purchase Orders',
            content: <OrdersPanel canManage={canManage} />,
          },
          {
            value: 'invoices',
            label: 'Invoices',
            content: <InvoicesPanel canManage={canManage} />,
          },
        ]}
      />
    </div>
  );
}
