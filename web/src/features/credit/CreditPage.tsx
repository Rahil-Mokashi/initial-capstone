import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Plus, UserPlus } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { DataTable } from '@/components/DataTable';
import { DocumentActions } from '@/components/DocumentActions';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { AddCustomerDialog } from '@/features/sales/SalesPage';
import { useCustomers } from '@/features/sales/queries';
import { applyApiError } from '@/lib/formErrors';
import { formatDate, formatMoney, titleCase } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Account = S['AccountOut'];

const K = 'credit';
const useAccounts = () => useGet<Account[]>([K, 'accounts'], '/credit/accounts');
const useStatement = (id: string) =>
  useGet<S['StatementOut']>([K, 'statement', id], `/credit/accounts/${id}/statement`);
const inv = [K, 'sales'];
const useOpenAccount = () =>
  useWrite((b: S['AccountIn']) => api.post<Account>('/credit/accounts', b), inv);
const useChangeLimit = (id: string) =>
  useWrite((b: S['LimitIn']) => api.post<Account>(`/credit/accounts/${id}/limit`, b), inv);
const useRecordPayment = () =>
  useWrite((b: S['CustomerPaymentIn']) => api.post('/credit/payments', b), inv);

const money = (label: string) =>
  z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,12}(\.\d{1,2})?$/.test(v) || Number(v) <= 0)
        ctx.addIssue({ code: 'custom', message: `Enter ${label} above zero, such as 10000.` });
    });

// ------------------------------------------------------------------ open account
const openSchema = z.object({
  customer_id: z.string().min(1, 'Choose a customer, or add a new one, first.'),
  credit_limit: money('a limit'),
  payment_due_days: z.string().regex(/^\d{1,3}$/, 'Enter whole days, 1 to 365.'),
});

function OpenAccountDialog({
  preselect,
  canAddCustomer,
  onAddCustomer,
  onClose,
}: {
  preselect?: string;
  canAddCustomer: boolean;
  onAddCustomer: () => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const customers = useCustomers();
  const open = useOpenAccount();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof openSchema>>({
    resolver: zodResolver(openSchema),
    defaultValues: { customer_id: preselect ?? '', credit_limit: '10000', payment_due_days: '30' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await open.mutateAsync({
        customer_id: v.customer_id,
        credit_limit: v.credit_limit,
        payment_due_days: Number(v.payment_due_days),
      });
      toast.success('Credit account opened.');
      onClose();
    } catch (error) {
      setFormError(
        applyApiError(error, setError, ['customer_id', 'credit_limit', 'payment_due_days']),
      );
    }
  });
  return (
    <FormDialog
      title="Open credit account"
      submitLabel="Open account"
      busy={open.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="Customer"
        error={errors.customer_id?.message}
        {...register('customer_id')}
      >
        <option value="">Choose a customer</option>
        {customers.data?.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectField>
      {canAddCustomer && (
        <div>
          <Button onClick={onAddCustomer}>
            <UserPlus className="size-4" aria-hidden /> Add new customer
          </Button>
        </div>
      )}
      <DecimalField
        label="Credit limit"
        maxFraction={2}
        unit="rupees"
        error={errors.credit_limit?.message}
        {...register('credit_limit')}
      />
      <TextField
        label="Payment due (days)"
        inputMode="numeric"
        error={errors.payment_due_days?.message}
        {...register('payment_due_days')}
      />
    </FormDialog>
  );
}

// -------------------------------------------------------------------- payment
const METHODS = ['cash', 'upi', 'card'] as const; // Credit is not a way to pay a credit balance (as in Qt)
const paymentSchema = z.object({
  customer_id: z.string().min(1, 'Choose a customer.'),
  amount: money('an amount'),
  payment_method: z.enum(METHODS),
  reference: z.string(),
  remarks: z.string(),
});

function PaymentDialog({
  initial,
  accounts,
  onClose,
}: {
  initial?: string;
  accounts: Account[];
  onClose: () => void;
}) {
  const toast = useToast();
  const record = useRecordPayment();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof paymentSchema>>({
    resolver: zodResolver(paymentSchema),
    defaultValues: {
      customer_id: initial ?? accounts[0]?.customer_id ?? '',
      amount: '1000',
      payment_method: 'cash',
      reference: '',
      remarks: '',
    },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await record.mutateAsync({
        customer_id: v.customer_id,
        amount: v.amount,
        payment_method: v.payment_method,
        reference: v.reference.trim() || undefined,
        remarks: v.remarks.trim() || undefined,
      });
      toast.success('Payment recorded.');
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['customer_id', 'amount', 'payment_method']));
    }
  });
  return (
    <FormDialog
      title="Record customer payment"
      submitLabel="Record payment"
      busy={record.isPending}
      error={
        formError ??
        (accounts.length === 0 ? 'No credit accounts exist yet - open one first.' : null)
      }
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="Customer"
        error={errors.customer_id?.message}
        {...register('customer_id')}
      >
        {accounts.map((a) => (
          <option key={a.customer_id} value={a.customer_id}>
            {a.customer}
          </option>
        ))}
      </SelectField>
      <DecimalField
        label="Amount"
        maxFraction={2}
        unit="rupees"
        error={errors.amount?.message}
        {...register('amount')}
      />
      <SelectField label="Method" {...register('payment_method')}>
        {METHODS.map((m) => (
          <option key={m} value={m}>
            {titleCase(m)}
          </option>
        ))}
      </SelectField>
      <TextField label="Reference" optional {...register('reference')} />
      <TextField label="Remarks" optional {...register('remarks')} />
    </FormDialog>
  );
}

// --------------------------------------------------------------------- limit
function LimitDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const toast = useToast();
  const change = useChangeLimit(account.customer_id);
  const [value, setValue] = useState(account.credit_limit);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  return (
    <FormDialog
      title="Change credit limit"
      description={`${account.customer ?? ''}: currently ${formatMoney(account.credit_limit)}`}
      submitLabel="Change limit"
      busy={change.isPending}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        const check = money('a limit').safeParse(value);
        if (!check.success) return setError(check.error.issues[0]!.message);
        try {
          await change.mutateAsync({ new_limit: value, reason: reason.trim() });
          toast.success('Credit limit changed.');
          onClose();
        } catch (err) {
          setError(applyApiError(err, () => undefined, []));
        }
      }}
      onClose={onClose}
    >
      <DecimalField
        label="New limit"
        maxFraction={2}
        unit="rupees"
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <TextField
        label="Reason"
        optional
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
    </FormDialog>
  );
}

// ----------------------------------------------------------------- statement
function StatementDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const statement = useStatement(account.customer_id);
  const s = statement.data;
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Customer statement"
      description={account.customer ?? undefined}
    >
      {statement.isLoading ? (
        <LoadingBlock label="Loading statement" rows={3} />
      ) : statement.isError || !s ? (
        <ErrorState error={statement.error} onRetry={() => void statement.refetch()} />
      ) : (
        <div className="flex flex-col gap-4">
          <DataTable
            caption={`Statement for ${account.customer ?? ''}`}
            data={s.entries}
            getRowId={(e) => `${e.entry_date}-${e.description}-${e.running_balance}`}
            empty={<p className="text-sm text-muted">No entries yet.</p>}
            columns={[
              {
                accessorKey: 'entry_date',
                header: 'Date',
                cell: ({ getValue }) => formatDate(getValue<string>()),
              },
              { accessorKey: 'description', header: 'Description' },
              {
                accessorKey: 'debit',
                header: 'Debit',
                meta: { numeric: true },
                cell: ({ getValue }) => (getValue() ? formatMoney(getValue<string>()) : ''),
              },
              {
                accessorKey: 'credit',
                header: 'Credit',
                meta: { numeric: true },
                cell: ({ getValue }) => (getValue() ? formatMoney(getValue<string>()) : ''),
              },
            ]}
          />
          <p className="num text-sm font-semibold">
            Running balance: {formatMoney(s.running_balance)}
          </p>
          <DocumentActions
            getHtml={async () => s.report.html}
            files={[
              {
                label: 'Excel',
                path: `/credit/accounts/${account.customer_id}/statement.xlsx`,
                filename: 'customer_statement.xlsx',
              },
              {
                label: 'PDF',
                path: `/credit/accounts/${account.customer_id}/statement.pdf`,
                filename: 'customer_statement.pdf',
              },
            ]}
          />
        </div>
      )}
    </Dialog>
  );
}

// --------------------------------------------------------------------- page
type DialogState =
  | { kind: 'open'; preselect?: string }
  | { kind: 'add-customer' }
  | { kind: 'payment' }
  | { kind: 'limit'; account: Account }
  | { kind: 'statement'; account: Account }
  | null;

export function CreditPage() {
  const { can } = useAuth();
  const canManage = can(P.CREDIT_MANAGE);
  const canAddCustomer = can(P.SALE_MANAGE);
  const accounts = useAccounts();
  const [selected, setSelected] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState>(null);
  const account = accounts.data?.find((a) => a.customer_id === selected) ?? null;

  const columns: ColumnDef<Account>[] = [
    {
      id: 'select',
      header: () => <span className="sr-only">Select</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <input
          type="radio"
          name="selected-account"
          aria-label={`Select ${row.original.customer}`}
          checked={selected === row.original.customer_id}
          onChange={() => setSelected(row.original.customer_id)}
          className="size-5"
        />
      ),
    },
    { accessorKey: 'customer', header: 'Customer', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'credit_limit',
      header: 'Credit limit',
      meta: { numeric: true },
      cell: ({ getValue }) => formatMoney(getValue<string>()),
    },
    {
      accessorKey: 'outstanding',
      header: 'Outstanding',
      meta: { numeric: true },
      cell: ({ getValue }) => formatMoney(getValue<string>()),
    },
    {
      accessorKey: 'overdue',
      header: 'Overdue',
      cell: ({ getValue }) =>
        getValue<boolean>() ? <StatusBadge tone="danger">Yes</StatusBadge> : <span>No</span>,
    },
    { accessorKey: 'payment_due_days', header: 'Due (days)', meta: { numeric: true } },
  ];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="Credit Management"
        subtitle="Customer credit accounts, balances, payments and statements."
      >
        <Button
          disabled={!account}
          onClick={() => account && setDialog({ kind: 'statement', account })}
        >
          View statement
        </Button>
        {canManage && (
          <>
            <Button onClick={() => setDialog({ kind: 'payment' })}>Record payment</Button>
            <Button
              disabled={!account}
              onClick={() => account && setDialog({ kind: 'limit', account })}
            >
              Change limit
            </Button>
            <Button variant="primary" onClick={() => setDialog({ kind: 'open' })}>
              <Plus className="size-4" aria-hidden /> Open credit account
            </Button>
          </>
        )}
      </PageHeader>
      {accounts.isLoading ? (
        <LoadingBlock label="Loading credit accounts" rows={4} />
      ) : accounts.isError ? (
        <ErrorState error={accounts.error} onRetry={() => void accounts.refetch()} />
      ) : (
        <DataTable
          caption="Credit accounts"
          columns={columns}
          data={accounts.data ?? []}
          getRowId={(a) => a.customer_id}
          empty={<EmptyState title="No credit accounts yet" />}
        />
      )}
      {dialog?.kind === 'open' && (
        <OpenAccountDialog
          preselect={dialog.preselect}
          canAddCustomer={canAddCustomer}
          onAddCustomer={() => setDialog({ kind: 'add-customer' })}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === 'add-customer' && (
        <AddCustomerDialog
          onClose={() => setDialog((d) => (d?.kind === 'add-customer' ? { kind: 'open' } : d))}
          onCreated={(c) => setDialog({ kind: 'open', preselect: c.id })}
        />
      )}
      {dialog?.kind === 'payment' && (
        <PaymentDialog
          initial={account?.customer_id}
          accounts={accounts.data ?? []}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === 'limit' && (
        <LimitDialog account={dialog.account} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === 'statement' && (
        <StatementDialog account={dialog.account} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}
