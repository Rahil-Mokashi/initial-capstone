import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
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
import { formatDate, formatMoney, titleCase } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Expense = S['ExpenseOut'];
type Category = S['CategoryOut'];

const K = 'expenses';
const useExpenses = () => useGet<Expense[]>([K, 'list'], '/expenses');
const useCategories = () => useGet<Category[]>([K, 'categories'], '/expense-categories');
const useOptions = () => useGet<S['ExpenseOptions']>([K, 'options'], '/expenses/options');
// Expenses also feed cash reconciliation and the dashboard.
const inv = [K, 'reconciliation'];
const useRecord = () => useWrite((b: S['ExpenseIn']) => api.post<Expense>('/expenses', b), inv);
const useDecide = () =>
  useWrite(
    (v: { id: string; action: 'approve' | 'reject'; body: unknown }) =>
      api.post<Expense>(`/expenses/${v.id}/${v.action}`, v.body),
    inv,
  );
const useAddCategory = () =>
  useWrite((name: string) => api.post<Category>('/expense-categories', { name }), [K]);

const METHODS = ['cash', 'upi', 'card'] as const; // never credit: an expense cannot be paid on credit
const tone = (s: string): Tone => (s === 'approved' ? 'ok' : s === 'rejected' ? 'danger' : 'warn');

const schema = z.object({
  category_id: z.string().min(1, 'Choose a category.'),
  amount: z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,12}(\.\d{1,2})?$/.test(v) || Number(v) <= 0)
        ctx.addIssue({ code: 'custom', message: 'Enter an amount above zero, such as 500.' });
    }),
  payment_method: z.enum(METHODS),
  employee_id: z.string().min(1, 'Choose an employee.'),
  shift_id: z.string(),
  receipt_reference: z.string(),
  description: z.string(),
});

function RecordDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const options = useOptions();
  const record = useRecord();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      category_id: '',
      amount: '500',
      payment_method: 'cash',
      employee_id: '',
      shift_id: '',
      receipt_reference: '',
      description: '',
    },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await record.mutateAsync({
        category_id: v.category_id,
        amount: v.amount,
        payment_method: v.payment_method,
        employee_id: v.employee_id,
        shift_id: v.shift_id || undefined,
        receipt_reference: v.receipt_reference.trim() || undefined,
        description: v.description.trim() || undefined,
      });
      toast.success('Expense recorded.');
      onClose();
    } catch (error) {
      setFormError(
        applyApiError(error, setError, ['category_id', 'amount', 'payment_method', 'employee_id']),
      );
    }
  });
  const noCategories = options.data && options.data.categories.length === 0;
  return (
    <FormDialog
      title="Record expense"
      submitLabel="Record expense"
      busy={record.isPending}
      error={
        formError ??
        (noCategories
          ? 'No expense categories available - add one from the Categories tab first.'
          : null)
      }
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="Category"
        error={errors.category_id?.message}
        {...register('category_id')}
      >
        <option value="">Choose a category</option>
        {options.data?.categories.map((c) => (
          <option key={c.id} value={c.id}>
            {c.label}
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
      <SelectField label="Payment method" {...register('payment_method')}>
        {METHODS.map((m) => (
          <option key={m} value={m}>
            {titleCase(m)}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="Employee"
        error={errors.employee_id?.message}
        {...register('employee_id')}
      >
        <option value="">Choose an employee</option>
        {options.data?.employees.map((e) => (
          <option key={e.id} value={e.id}>
            {e.label}
          </option>
        ))}
      </SelectField>
      <SelectField label="Shift" {...register('shift_id')}>
        <option value="">(none)</option>
        {options.data?.shifts.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </SelectField>
      <TextField label="Receipt reference" optional {...register('receipt_reference')} />
      <TextField label="Description" optional {...register('description')} />
    </FormDialog>
  );
}

function CategoryDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const add = useAddCategory();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  return (
    <FormDialog
      title="Add expense category"
      submitLabel="Save"
      busy={add.isPending}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        if (!name.trim()) return setError('Enter the category name.');
        try {
          await add.mutateAsync(name.trim());
          toast.success('Category added.');
          onClose();
        } catch (err) {
          setError(applyApiError(err, () => undefined, []));
        }
      }}
      onClose={onClose}
    >
      <TextField label="Name" autoFocus value={name} onChange={(e) => setName(e.target.value)} />
    </FormDialog>
  );
}

type Dialog =
  | { kind: 'record' }
  | { kind: 'approve' | 'reject'; expense: Expense }
  | { kind: 'category' }
  | null;

function ExpensesPanel({
  canManage,
  canApprove,
  setDialog,
}: {
  canManage: boolean;
  canApprove: boolean;
  setDialog: (d: Dialog) => void;
}) {
  const expenses = useExpenses();
  const [selected, setSelected] = useState<string | null>(null);
  const exp = expenses.data?.find((e) => e.id === selected) ?? null;
  const columns: ColumnDef<Expense>[] = [
    ...(canApprove
      ? [
          {
            id: 'select',
            header: () => <span className="sr-only">Select</span>,
            enableSorting: false,
            cell: ({ row }: { row: { original: Expense } }) => (
              <input
                type="radio"
                name="selected-expense"
                aria-label={`Select expense ${row.original.category ?? ''} ${row.original.amount}`}
                checked={selected === row.original.id}
                onChange={() => setSelected(row.original.id)}
                className="size-5"
              />
            ),
          } as ColumnDef<Expense>,
        ]
      : []),
    {
      accessorKey: 'expense_date',
      header: 'Date',
      cell: ({ getValue }) => formatDate(getValue<string>()),
    },
    { accessorKey: 'category', header: 'Category', cell: ({ getValue }) => getValue() ?? '' },
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
    { accessorKey: 'employee', header: 'Employee', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => (
        <StatusBadge tone={tone(getValue<string>())}>{titleCase(getValue<string>())}</StatusBadge>
      ),
    },
  ];
  return (
    <>
      <div className="flex flex-wrap justify-end gap-2">
        {canApprove && (
          <>
            <Button
              variant="danger"
              disabled={!exp}
              onClick={() => exp && setDialog({ kind: 'reject', expense: exp })}
            >
              Reject selected
            </Button>
            <Button
              disabled={!exp}
              onClick={() => exp && setDialog({ kind: 'approve', expense: exp })}
            >
              Approve selected
            </Button>
          </>
        )}
        {canManage && (
          <Button variant="primary" onClick={() => setDialog({ kind: 'record' })}>
            <Plus className="size-4" aria-hidden /> Record expense
          </Button>
        )}
      </div>
      {expenses.isLoading ? (
        <LoadingBlock label="Loading expenses" rows={4} />
      ) : expenses.isError ? (
        <ErrorState error={expenses.error} onRetry={() => void expenses.refetch()} />
      ) : (
        <DataTable
          caption="Expenses"
          columns={columns}
          data={expenses.data ?? []}
          getRowId={(e) => e.id}
          empty={<EmptyState title="No expenses yet" />}
        />
      )}
    </>
  );
}

function CategoriesPanel({
  canManage,
  setDialog,
}: {
  canManage: boolean;
  setDialog: (d: Dialog) => void;
}) {
  const categories = useCategories();
  return (
    <>
      {canManage && (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => setDialog({ kind: 'category' })}>
            <Plus className="size-4" aria-hidden /> Add category
          </Button>
        </div>
      )}
      {categories.isLoading ? (
        <LoadingBlock label="Loading categories" rows={3} />
      ) : categories.isError ? (
        <ErrorState error={categories.error} onRetry={() => void categories.refetch()} />
      ) : (
        <DataTable
          caption="Expense categories"
          data={categories.data ?? []}
          getRowId={(c) => c.id}
          empty={<EmptyState title="No categories yet" />}
          columns={[
            { accessorKey: 'name', header: 'Name' },
            {
              accessorKey: 'status',
              header: 'Status',
              cell: ({ getValue }) => titleCase(getValue<string>()),
            },
          ]}
        />
      )}
    </>
  );
}

export function ExpensesPage() {
  const { can } = useAuth();
  const canManage = can(P.EXPENSE_MANAGE);
  const canApprove = can(P.EXPENSE_APPROVE);
  const toast = useToast();
  const decide = useDecide();
  const [dialog, setDialog] = useState<Dialog>(null);
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader title="Expenses" subtitle="Record, approve and categorise day-to-day expenses." />
      <TabbedPanel
        label="Expenses"
        tabs={[
          {
            value: 'expenses',
            label: 'Expenses',
            content: (
              <ExpensesPanel canManage={canManage} canApprove={canApprove} setDialog={setDialog} />
            ),
          },
          {
            value: 'categories',
            label: 'Categories',
            content: <CategoriesPanel canManage={canManage} setDialog={setDialog} />,
          },
        ]}
      />
      {dialog?.kind === 'record' && <RecordDialog onClose={() => setDialog(null)} />}
      {dialog?.kind === 'category' && <CategoryDialog onClose={() => setDialog(null)} />}
      {dialog && (dialog.kind === 'approve' || dialog.kind === 'reject') && (
        <ReasonDialog
          title={dialog.kind === 'approve' ? 'Approve expense' : 'Reject expense'}
          description={`${dialog.expense.category ?? ''} - ${formatMoney(dialog.expense.amount)}`}
          label={dialog.kind === 'approve' ? 'Remarks' : 'Reason'}
          submitLabel={dialog.kind === 'approve' ? 'Approve' : 'Reject'}
          tone={dialog.kind === 'approve' ? 'primary' : 'danger'}
          onConfirm={async (text) => {
            await decide.mutateAsync({
              id: dialog.expense.id,
              action: dialog.kind as 'approve' | 'reject',
              body: dialog.kind === 'approve' ? { remarks: text } : { reason: text },
            });
            toast.success(dialog.kind === 'approve' ? 'Expense approved.' : 'Expense rejected.');
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
