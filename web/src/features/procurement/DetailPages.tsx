import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { ArrowLeft, Truck } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useParams } from 'react-router-dom';
import { z } from 'zod';
import { friendlyMessage } from '@/api/errors';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { formatDate, formatDateTime, formatMoney, formatQuantity, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';
import { StatusText } from './ProcurementPage';
import {
  useArrivalOptions,
  useCancelOrder,
  useDeliveries,
  useDelivery,
  useDeliveryStep,
  useInvoice,
  useOrder,
  usePayments,
  useRecordArrival,
  useRecordPayment,
  type Delivery,
  type Payment,
} from './queries';

function Back({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-[44px] w-fit items-center gap-1.5 text-sm font-semibold underline-offset-4 hover:underline"
    >
      <ArrowLeft className="size-4" aria-hidden /> {children}
    </Link>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      aria-label={title}
      className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <h2 className="text-base font-bold">{title}</h2>
      {children}
    </section>
  );
}

const blank = (s: string) => (s.trim() === '' ? undefined : s.trim());

// ------------------------------------------------------------ purchase order
const arrivalSchema = z.object({
  tank_id: z.string().min(1, 'Choose a tank.'),
  received_by_employee_id: z.string().min(1, 'Choose who received it.'),
  tanker_number: z.string().trim().min(1, 'Enter the tanker number.'),
  driver_name: z.string(),
  remarks: z.string(),
});

function ArrivalDialog({ poId, onClose }: { poId: string; onClose: () => void }) {
  const toast = useToast();
  const options = useArrivalOptions();
  const record = useRecordArrival(poId);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof arrivalSchema>>({
    resolver: zodResolver(arrivalSchema),
    defaultValues: {
      tank_id: '',
      received_by_employee_id: '',
      tanker_number: '',
      driver_name: '',
      remarks: '',
    },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await record.mutateAsync({
        tank_id: v.tank_id,
        received_by_employee_id: v.received_by_employee_id,
        tanker_number: v.tanker_number.trim(),
        driver_name: blank(v.driver_name),
        remarks: blank(v.remarks),
      });
      toast.success('Tanker arrival recorded.');
      onClose();
    } catch (error) {
      setFormError(
        applyApiError(error, setError, ['tank_id', 'received_by_employee_id', 'tanker_number']),
      );
    }
  });
  const loadError = options.isError ? friendlyMessage(options.error) : null;
  return (
    <FormDialog
      title="Record delivery arrival"
      submitLabel="Record arrival"
      busy={record.isPending}
      error={formError ?? loadError}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField label="Tank" error={errors.tank_id?.message} {...register('tank_id')}>
        <option value="">Choose a tank</option>
        {options.data?.tanks.map((t) => (
          <option key={t.id} value={t.id}>
            {t.label}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="Received by"
        error={errors.received_by_employee_id?.message}
        {...register('received_by_employee_id')}
      >
        <option value="">Choose an employee</option>
        {options.data?.employees.map((e) => (
          <option key={e.id} value={e.id}>
            {e.label}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Tanker number"
        error={errors.tanker_number?.message}
        {...register('tanker_number')}
      />
      <TextField label="Driver name" optional {...register('driver_name')} />
      <TextField label="Remarks" optional {...register('remarks')} />
    </FormDialog>
  );
}

export function OrderDetailPage() {
  const { id = '' } = useParams();
  const { can } = useAuth();
  const canManage = can(P.PROCUREMENT_MANAGE);
  const order = useOrder(id);
  const deliveries = useDeliveries(id);
  const cancel = useCancelOrder(id);
  const toast = useToast();
  const [dialog, setDialog] = useState<'arrival' | 'cancel' | null>(null);

  const po = order.data;
  const canDeliver = po && (po.status === 'placed' || po.status === 'partially_delivered');
  const deliveryColumns: ColumnDef<Delivery>[] = [
    {
      accessorKey: 'tanker_number',
      header: 'Tanker',
      cell: ({ row }) => (
        <Link
          className="font-semibold underline-offset-4 hover:underline"
          to={`/procurement/deliveries/${row.original.id}`}
        >
          {row.original.tanker_number}
        </Link>
      ),
    },
    {
      accessorKey: 'arrived_at',
      header: 'Arrived',
      cell: ({ getValue }) => formatDateTime(getValue<string>()),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <StatusText status={getValue<string>()} />,
    },
    {
      accessorKey: 'quantity_received',
      header: 'Received (L)',
      meta: { numeric: true },
      cell: ({ getValue }) => {
        const v = getValue<string | null>();
        return v ? formatQuantity(v) : '';
      },
    },
  ];

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <Back to="/procurement?tab=orders">All purchase orders</Back>
      {order.isLoading ? (
        <LoadingBlock label="Loading purchase order" rows={3} />
      ) : order.isError || !po ? (
        <ErrorState error={order.error} onRetry={() => void order.refetch()} />
      ) : (
        <>
          <PageHeader
            title={po.po_number}
            subtitle={`${po.supplier ?? ''} - ordered ${formatDate(po.order_date)}`}
          >
            <StatusText status={po.status} />
          </PageHeader>
          <Card title="Items">
            <DataTable
              caption="Order items"
              data={po.items}
              getRowId={(i) => i.id}
              empty={null}
              columns={[
                {
                  accessorKey: 'fuel_type',
                  header: 'Fuel',
                  cell: ({ getValue }) => getValue() ?? '',
                },
                {
                  accessorKey: 'quantity_ordered',
                  header: 'Quantity (L)',
                  meta: { numeric: true },
                  cell: ({ getValue }) => formatQuantity(getValue<string>()),
                },
                {
                  accessorKey: 'rate_per_liter',
                  header: 'Rate/L',
                  meta: { numeric: true },
                  cell: ({ getValue }) => formatMoney(getValue<string>()),
                },
              ]}
            />
            {po.expected_delivery_date && (
              <p className="text-sm text-muted">
                Expected delivery: {formatDate(po.expected_delivery_date)}
              </p>
            )}
            {po.remarks && <p className="text-sm text-muted">Remarks: {po.remarks}</p>}
          </Card>
          {canManage && (
            <div className="flex flex-wrap gap-3">
              <Button variant="primary" disabled={!canDeliver} onClick={() => setDialog('arrival')}>
                <Truck className="size-4" aria-hidden /> Record delivery arrival
              </Button>
              <Button
                variant="danger"
                disabled={po.status !== 'placed'}
                onClick={() => setDialog('cancel')}
              >
                Cancel order
              </Button>
            </div>
          )}
          <Card title="Deliveries">
            {deliveries.isLoading ? (
              <LoadingBlock label="Loading deliveries" rows={2} />
            ) : deliveries.isError ? (
              <ErrorState error={deliveries.error} onRetry={() => void deliveries.refetch()} />
            ) : (
              <DataTable
                caption="Deliveries"
                columns={deliveryColumns}
                data={deliveries.data ?? []}
                getRowId={(d) => d.id}
                empty={<p className="text-sm text-muted">No deliveries yet.</p>}
              />
            )}
          </Card>
          {dialog === 'arrival' && <ArrivalDialog poId={id} onClose={() => setDialog(null)} />}
          {dialog === 'cancel' && (
            <ReasonDialog
              title="Cancel purchase order"
              description={po.po_number}
              submitLabel="Cancel order"
              tone="danger"
              onConfirm={async (reason) => {
                await cancel.mutateAsync(reason);
                toast.success('Purchase order cancelled.');
              }}
              onClose={() => setDialog(null)}
            />
          )}
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ delivery
const dipSchema = z.object({
  dip: z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,9}(\.\d{1,3})?$/.test(v))
        ctx.addIssue({ code: 'custom', message: 'Enter a dip value such as 2500.500.' });
    }),
});

function DipDialog({
  delivery,
  kind,
  onClose,
}: {
  delivery: Delivery;
  kind: 'pre' | 'post';
  onClose: () => void;
}) {
  const toast = useToast();
  const step = useDeliveryStep(delivery.id);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof dipSchema>>({
    resolver: zodResolver(dipSchema),
    defaultValues: { dip: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await step.mutateAsync({
        path: kind === 'pre' ? 'pre-dip' : 'post-dip',
        body: { dip_value: v.dip },
      });
      toast.success(
        kind === 'pre' ? 'Pre-dip recorded.' : 'Post-dip recorded and fuel unloaded into the tank.',
      );
      onClose();
    } catch (error) {
      setFormError(friendlyMessage(error));
    }
  });
  return (
    <FormDialog
      title={kind === 'pre' ? 'Pre-dip reading' : 'Post-dip reading and unload'}
      description={
        kind === 'post' && delivery.pre_dip_value
          ? `The quantity received is the post-dip value minus the pre-dip value (${formatQuantity(delivery.pre_dip_value)} L).`
          : undefined
      }
      submitLabel={kind === 'pre' ? 'Record pre-dip' : 'Record post-dip and unload'}
      busy={step.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <DecimalField
        label="Dip value (L)"
        autoFocus
        error={errors.dip?.message}
        {...register('dip')}
      />
    </FormDialog>
  );
}

function QualityDialog({ delivery, onClose }: { delivery: Delivery; onClose: () => void }) {
  const toast = useToast();
  const step = useDeliveryStep(delivery.id);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  return (
    <FormDialog
      title="Verify quality"
      submitLabel="Verify quality"
      busy={step.isPending}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await step.mutateAsync({
            path: 'verify-quality',
            body: { notes: notes.trim() || undefined },
          });
          toast.success('Quality verified.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
      onClose={onClose}
    >
      <TextField
        label="Notes"
        optional
        autoFocus
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
    </FormDialog>
  );
}

export function DeliveryDetailPage() {
  const { id = '' } = useParams();
  const { can } = useAuth();
  const canManage = can(P.PROCUREMENT_MANAGE);
  const delivery = useDelivery(id);
  const step = useDeliveryStep(id);
  const toast = useToast();
  const [dialog, setDialog] = useState<'quality' | 'pre' | 'post' | 'reject' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const d = delivery.data;

  async function run(path: 'verify-documents', done: string) {
    setActionError(null);
    try {
      await step.mutateAsync({ path });
      toast.success(done);
    } catch (e) {
      setActionError(friendlyMessage(e));
    }
  }

  const s = d?.status;
  // Only the action valid for the current status is enabled, so the workflow cannot be skipped from here.
  const can_ = {
    docs: s === 'arrived',
    quality: s === 'documents_verified',
    pre: s === 'quality_verified' && !d?.pre_dip_value,
    post: s === 'quality_verified' && !!d?.pre_dip_value,
    reject: s === 'arrived' || s === 'documents_verified' || s === 'quality_verified',
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <Back to={d ? `/procurement/orders/${d.purchase_order_id}` : '/procurement?tab=orders'}>
        Back to the purchase order
      </Back>
      {delivery.isLoading ? (
        <LoadingBlock label="Loading delivery" rows={3} />
      ) : delivery.isError || !d ? (
        <ErrorState error={delivery.error} onRetry={() => void delivery.refetch()} />
      ) : (
        <>
          <PageHeader
            title={`Tanker ${d.tanker_number}`}
            subtitle={`Arrived ${formatDateTime(d.arrived_at)}`}
          >
            <StatusText status={d.status} />
          </PageHeader>
          <Card title="Delivery">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              {d.driver_name && (
                <>
                  <dt className="text-muted">Driver</dt>
                  <dd>{d.driver_name}</dd>
                </>
              )}
              {d.pre_dip_value && (
                <>
                  <dt className="text-muted">Pre-dip</dt>
                  <dd className="num">{formatQuantity(d.pre_dip_value)}</dd>
                </>
              )}
              {d.post_dip_value && (
                <>
                  <dt className="text-muted">Post-dip</dt>
                  <dd className="num">{formatQuantity(d.post_dip_value)}</dd>
                </>
              )}
              {d.quantity_received && (
                <>
                  <dt className="text-muted">Received</dt>
                  <dd className="num">{formatQuantity(d.quantity_received)} L</dd>
                </>
              )}
              {d.quality_notes && (
                <>
                  <dt className="text-muted">Quality notes</dt>
                  <dd>{d.quality_notes}</dd>
                </>
              )}
              {d.rejection_reason && (
                <>
                  <dt className="text-muted">Rejected</dt>
                  <dd>{d.rejection_reason}</dd>
                </>
              )}
              {d.remarks && (
                <>
                  <dt className="text-muted">Remarks</dt>
                  <dd>{d.remarks}</dd>
                </>
              )}
            </dl>
          </Card>
          {actionError && (
            <p
              role="alert"
              className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
            >
              {actionError}
            </p>
          )}
          {canManage && (
            <div className="flex flex-wrap gap-3">
              <Button
                disabled={!can_.docs}
                loading={step.isPending}
                onClick={() => void run('verify-documents', 'Documents verified.')}
              >
                Verify documents
              </Button>
              <Button disabled={!can_.quality} onClick={() => setDialog('quality')}>
                Verify quality
              </Button>
              <Button disabled={!can_.pre} onClick={() => setDialog('pre')}>
                Record pre-dip reading
              </Button>
              <Button disabled={!can_.post} variant="primary" onClick={() => setDialog('post')}>
                Record post-dip and unload
              </Button>
              <Button disabled={!can_.reject} variant="danger" onClick={() => setDialog('reject')}>
                Reject delivery
              </Button>
            </div>
          )}
          {dialog === 'quality' && <QualityDialog delivery={d} onClose={() => setDialog(null)} />}
          {(dialog === 'pre' || dialog === 'post') && (
            <DipDialog delivery={d} kind={dialog} onClose={() => setDialog(null)} />
          )}
          {dialog === 'reject' && (
            <ReasonDialog
              title="Reject delivery"
              description={`Tanker ${d.tanker_number}`}
              submitLabel="Reject delivery"
              tone="danger"
              onConfirm={async (reason) => {
                await step.mutateAsync({ path: 'reject', body: { reason } });
                toast.success('Delivery rejected.');
              }}
              onClose={() => setDialog(null)}
            />
          )}
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- invoice
const METHODS = ['Bank Transfer', 'Cheque', 'UPI', 'Cash'];
const paymentSchema = z.object({
  amount: z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,12}(\.\d{1,2})?$/.test(v) || Number(v) <= 0)
        ctx.addIssue({ code: 'custom', message: 'Enter an amount above zero, such as 500.00.' });
    }),
  payment_date: z.string().min(1, 'Pick the payment date.'),
  payment_method: z.string().trim().min(1, 'Enter the payment method.'),
  reference: z.string(),
  remarks: z.string(),
});

function PaymentDialog({ invoiceId, onClose }: { invoiceId: string; onClose: () => void }) {
  const toast = useToast();
  const record = useRecordPayment(invoiceId);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof paymentSchema>>({
    resolver: zodResolver(paymentSchema),
    defaultValues: {
      amount: '',
      payment_date: todayIso(),
      payment_method: METHODS[0],
      reference: '',
      remarks: '',
    },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await record.mutateAsync({
        amount: v.amount,
        payment_date: v.payment_date,
        payment_method: v.payment_method.trim(),
        reference: blank(v.reference),
        remarks: blank(v.remarks),
      });
      toast.success('Payment recorded.');
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['amount', 'payment_date', 'payment_method']));
    }
  });
  return (
    <FormDialog
      title="Record payment"
      submitLabel="Save"
      busy={record.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <DecimalField
        label="Amount"
        maxFraction={2}
        unit="rupees"
        autoFocus
        error={errors.amount?.message}
        {...register('amount')}
      />
      <TextField
        label="Payment date"
        type="date"
        error={errors.payment_date?.message}
        {...register('payment_date')}
      />
      <TextField
        label="Method"
        list="payment-methods"
        error={errors.payment_method?.message}
        {...register('payment_method')}
      />
      <datalist id="payment-methods">
        {METHODS.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      <TextField label="Reference" optional {...register('reference')} />
      <TextField label="Remarks" optional {...register('remarks')} />
    </FormDialog>
  );
}

export function InvoiceDetailPage() {
  const { id = '' } = useParams();
  const { can } = useAuth();
  const canManage = can(P.PROCUREMENT_MANAGE);
  const invoice = useInvoice(id);
  const payments = usePayments(id);
  const [paying, setPaying] = useState(false);
  const inv = invoice.data;
  const columns: ColumnDef<Payment>[] = [
    {
      accessorKey: 'payment_date',
      header: 'Date',
      cell: ({ getValue }) => formatDate(getValue<string>()),
    },
    {
      accessorKey: 'amount',
      header: 'Amount',
      meta: { numeric: true },
      cell: ({ getValue }) => formatMoney(getValue<string>()),
    },
    { accessorKey: 'payment_method', header: 'Method' },
    { accessorKey: 'reference', header: 'Reference', cell: ({ getValue }) => getValue() ?? '' },
  ];
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <Back to="/procurement?tab=invoices">All invoices</Back>
      {invoice.isLoading ? (
        <LoadingBlock label="Loading invoice" rows={3} />
      ) : invoice.isError || !inv ? (
        <ErrorState error={invoice.error} onRetry={() => void invoice.refetch()} />
      ) : (
        <>
          <PageHeader
            title={inv.invoice_number}
            subtitle={`${inv.supplier ?? ''} - ${formatMoney(inv.amount)}`}
          >
            <StatusText status={inv.status} />
          </PageHeader>
          <p className="text-sm text-muted">
            Invoice date {formatDate(inv.invoice_date)}
            {inv.due_date ? ` - due ${formatDate(inv.due_date)}` : ''}
          </p>
          {canManage && (
            <div>
              <Button
                variant="primary"
                disabled={inv.status === 'paid'}
                onClick={() => setPaying(true)}
              >
                Record payment
              </Button>
            </div>
          )}
          <Card title="Payments">
            {payments.isLoading ? (
              <LoadingBlock label="Loading payments" rows={2} />
            ) : payments.isError ? (
              <ErrorState error={payments.error} onRetry={() => void payments.refetch()} />
            ) : (
              <DataTable
                caption="Payments"
                columns={columns}
                data={payments.data ?? []}
                getRowId={(p) => p.id}
                empty={<p className="text-sm text-muted">No payments recorded yet.</p>}
              />
            )}
          </Card>
          {paying && <PaymentDialog invoiceId={id} onClose={() => setPaying(false)} />}
        </>
      )}
    </div>
  );
}
