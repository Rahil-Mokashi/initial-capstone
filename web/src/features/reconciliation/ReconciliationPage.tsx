import { zodResolver } from '@hookform/resolvers/zod';
import type { ColumnDef } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
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
import { useToast } from '@/components/ui/Toast';
import { useEmployeeList } from '@/features/employees/queries';
import { applyApiError } from '@/lib/formErrors';
import { formatMoney, formatQuantity, titleCase } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Recon = S['ShiftReconciliationOut'];
type CashBook = S['CashBookOut'];
type Shortage = S['ShortageOut'];
type ShiftRow = components['schemas']['ShiftOut'];

const K = 'reconciliation';
// Reconciliation reads sales, expenses and cash, and writes cash-book / shortage expenses.
const inv = [K, 'expenses'];
const post = <T,>(path: string, body: unknown) => api.post<T>(path, body);

const useRecons = () => useGet<Recon[]>([K, 'list'], '/reconciliation');
const useCashBooks = () => useGet<CashBook[]>([K, 'cash-book'], '/cash-book');
const useShortages = () => useGet<Shortage[]>([K, 'shortages'], '/shortages');
const useShortageOptions = () =>
  useGet<S['ShortageOptions']>([K, 'shortage-options'], '/shortages/options');
const useShifts = () => useGet<ShiftRow[]>(['shifts', 'list'], '/shifts');
const useExpected = (shiftId: string) =>
  useGet<S['ExpectedOut'][]>(
    [K, 'expected', shiftId],
    `/reconciliation/expected?shift_id=${shiftId}`,
    Boolean(shiftId),
  );

const shiftLabel = (s: ShiftRow) => `${s.shift_date} ${s.shift_label} (${s.status})`;
const tone = (v: string): Tone =>
  v === 'normal' || v === 'accepted' || v === 'approved'
    ? 'ok'
    : v === 'warning'
      ? 'warn'
      : v === 'pending_approval' || v === 'approval_required' || v === 'investigation_required'
        ? 'danger'
        : 'info';
const moneyField = (zero: boolean) =>
  z
    .string()
    .trim()
    .superRefine((v, ctx) => {
      if (!/^\d{1,12}(\.\d{1,2})?$/.test(v))
        ctx.addIssue({ code: 'custom', message: 'Enter an amount such as 1500.00.' });
      else if (!zero && Number(v) <= 0)
        ctx.addIssue({ code: 'custom', message: 'The amount must be above zero.' });
    });

// ------------------------------------------------------------ reconcile a shift
function ReconcileDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const shifts = useShifts();
  const perform = useWrite((b: S['PerformIn']) => post<Recon>('/reconciliation', b), inv);
  const [shiftId, setShiftId] = useState('');
  const [declared, setDeclared] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [remarks, setRemarks] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const expected = useExpected(shiftId);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!shiftId) return setFormError('Choose a shift.');
    const found: Record<string, string> = {};
    for (const t of expected.data ?? []) {
      const r = moneyField(true).safeParse(declared[t.tender_id] ?? '');
      if (!r.success) found[t.tender_id] = 'Enter the declared amount (0 if none).';
    }
    setErrors(found);
    if (Object.keys(found).length) return;
    try {
      await perform.mutateAsync({
        shift_id: shiftId,
        declared_amounts: Object.fromEntries(
          (expected.data ?? []).map((t) => [t.tender_id, declared[t.tender_id]!.trim()]),
        ),
        remarks: remarks.trim() || undefined,
      });
      toast.success('Shift reconciled.');
      onClose();
    } catch (error) {
      setFormError(friendlyMessage(error));
    }
  }

  return (
    <FormDialog
      title="Reconcile shift"
      submitLabel="Reconcile"
      busy={perform.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField
        label="Shift"
        value={shiftId}
        onChange={(e) => {
          setShiftId(e.target.value);
          setDeclared({});
          setErrors({});
        }}
      >
        <option value="">Choose a shift</option>
        {shifts.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {shiftLabel(s)}
          </option>
        ))}
      </SelectField>
      {shiftId && expected.isLoading && <LoadingBlock label="Loading expected amounts" rows={2} />}
      {shiftId && expected.isError && (
        <p role="alert" className="text-sm font-medium text-danger-fg">
          {friendlyMessage(expected.error)}
        </p>
      )}
      {shiftId && expected.data && expected.data.length === 0 && (
        <p className="text-sm text-muted">This shift has no reconcilable tender activity.</p>
      )}
      {expected.data?.map((t) => (
        <DecimalField
          key={t.tender_id}
          label={`Declared ${t.tender} (expected ${t.expected})`}
          maxFraction={2}
          unit="rupees"
          value={declared[t.tender_id] ?? ''}
          error={errors[t.tender_id]}
          onChange={(e) => setDeclared({ ...declared, [t.tender_id]: e.target.value })}
        />
      ))}
      <TextField
        label="Remarks"
        optional
        value={remarks}
        onChange={(e) => setRemarks(e.target.value)}
      />
    </FormDialog>
  );
}

// -------------------------------------------------------------- cash book dialogs
function MovementsDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const shifts = useShifts();
  const record = useWrite((b: S['MovementsIn']) => post('/cash-book/movements', b), inv);
  const [shiftId, setShiftId] = useState('');
  const [advance, setAdvance] = useState('0');
  const [final, setFinal] = useState('0');
  const [error, setError] = useState<string | null>(null);
  return (
    <FormDialog
      title="Record shift cash movements"
      submitLabel="Record"
      busy={record.isPending}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        if (!shiftId) return setError('Choose a shift.');
        for (const v of [advance, final])
          if (!moneyField(true).safeParse(v).success)
            return setError('Enter amounts such as 1500.00 (0 if none).');
        try {
          await record.mutateAsync({
            shift_id: shiftId,
            advance_amount: advance,
            final_amount: final,
          });
          toast.success('Cash movements recorded.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
      onClose={onClose}
    >
      <SelectField label="Shift" value={shiftId} onChange={(e) => setShiftId(e.target.value)}>
        <option value="">Choose a shift</option>
        {shifts.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {shiftLabel(s)}
          </option>
        ))}
      </SelectField>
      <DecimalField
        label="Advance handed over"
        maxFraction={2}
        unit="rupees"
        value={advance}
        onChange={(e) => setAdvance(e.target.value)}
      />
      <DecimalField
        label="Final handed over"
        maxFraction={2}
        unit="rupees"
        value={final}
        onChange={(e) => setFinal(e.target.value)}
      />
    </FormDialog>
  );
}

const depositSchema = z.object({
  shift_id: z.string().min(1, 'Choose a shift.'),
  bank_name: z.string().trim().min(1, 'Enter the bank.'),
  amount: moneyField(false),
});

function DepositDialog({ books, onClose }: { books: CashBook[]; onClose: () => void }) {
  const toast = useToast();
  const record = useWrite((b: S['DepositIn']) => post('/cash-book/deposits', b), inv);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof depositSchema>>({
    resolver: zodResolver(depositSchema),
    defaultValues: { shift_id: '', bank_name: '', amount: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await record.mutateAsync({
        shift_id: v.shift_id,
        bank_name: v.bank_name.trim(),
        amount: v.amount,
      });
      toast.success('Bank deposit recorded.');
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['shift_id', 'bank_name', 'amount']));
    }
  });
  return (
    <FormDialog
      title="Record bank deposit"
      description="Only shifts whose cash movements are already recorded can take a deposit."
      submitLabel="Record"
      busy={record.isPending}
      error={
        formError ?? (books.length === 0 ? 'No shifts with recorded cash movements yet.' : null)
      }
      onSubmit={submit}
      onClose={onClose}
    >
      <SelectField label="Shift" error={errors.shift_id?.message} {...register('shift_id')}>
        <option value="">Choose a shift</option>
        {books.map((b) => (
          <option key={b.shift_id} value={b.shift_id}>
            {b.shift ?? b.shift_id}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Bank"
        placeholder="e.g. HDFC Bank"
        error={errors.bank_name?.message}
        {...register('bank_name')}
      />
      <DecimalField
        label="Amount deposited"
        maxFraction={2}
        unit="rupees"
        error={errors.amount?.message}
        {...register('amount')}
      />
    </FormDialog>
  );
}

// ------------------------------------------------------------------ shortages
function ShortageDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const options = useShortageOptions();
  const employees = useEmployeeList();
  const record = useWrite((b: S['ShortageIn']) => post('/shortages', b), inv);
  const [lineId, setLineId] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const none = options.data && options.data.unbooked_lines.length === 0;
  return (
    <FormDialog
      title="Record cash shortage"
      submitLabel="Record"
      busy={record.isPending}
      error={error ?? (none ? 'No unbooked cash shortages to record.' : null)}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        if (!lineId) return setError('Choose the reconciliation line.');
        if (!employeeId) return setError('Choose the responsible employee.');
        try {
          await record.mutateAsync({
            shift_reconciliation_line_id: lineId,
            employee_id: employeeId,
            notes: notes.trim() || undefined,
          });
          toast.success('Cash shortage recorded.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
      onClose={onClose}
    >
      <SelectField
        label="Reconciliation line"
        value={lineId}
        onChange={(e) => setLineId(e.target.value)}
      >
        <option value="">Choose a line</option>
        {options.data?.unbooked_lines.map((l) => (
          <option key={l.id} value={l.id}>
            {l.label}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="Responsible employee"
        value={employeeId}
        onChange={(e) => setEmployeeId(e.target.value)}
      >
        <option value="">Choose an employee</option>
        {employees.data?.map((e) => (
          <option key={e.id} value={e.id}>
            {e.employee_code} - {e.first_name} {e.last_name}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Notes"
        optional
        placeholder="Optional notes"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
    </FormDialog>
  );
}

function RecoveryDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const options = useShortageOptions();
  const shifts = useShifts();
  const record = useWrite((b: S['RecoveryIn']) => post('/shortages/recoveries', b), inv);
  const [shortageId, setShortageId] = useState('');
  const [shiftId, setShiftId] = useState('');
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const none = options.data && options.data.outstanding_shortages.length === 0;
  return (
    <FormDialog
      title="Record shortage recovery"
      description="The shift chosen is the one whose cash book receives the repayment; its cash movements must already be recorded."
      submitLabel="Record"
      busy={record.isPending}
      error={error ?? (none ? 'No outstanding shortages to record a recovery against.' : null)}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        if (!shortageId) return setError('Choose the shortage.');
        if (!shiftId) return setError('Choose the shift the money was repaid into.');
        if (!moneyField(false).safeParse(amount).success)
          return setError('Enter an amount above zero, such as 500.00.');
        try {
          await record.mutateAsync({
            employee_cash_shortage_id: shortageId,
            shift_id: shiftId,
            amount,
            notes: notes.trim() || undefined,
          });
          toast.success('Recovery recorded.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
      onClose={onClose}
    >
      <SelectField
        label="Shortage"
        value={shortageId}
        onChange={(e) => setShortageId(e.target.value)}
      >
        <option value="">Choose a shortage</option>
        {options.data?.outstanding_shortages.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="Repaid into shift"
        value={shiftId}
        onChange={(e) => setShiftId(e.target.value)}
      >
        <option value="">Choose a shift</option>
        {shifts.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {shiftLabel(s)}
          </option>
        ))}
      </SelectField>
      <DecimalField
        label="Amount recovered"
        maxFraction={2}
        unit="rupees"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
      />
      <TextField
        label="Notes"
        optional
        placeholder="Optional notes"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
    </FormDialog>
  );
}

// ----------------------------------------------------------------------- page
type Dialog =
  'reconcile' | 'movements' | 'deposit' | 'shortage' | 'recovery' | { approve: Recon } | null;

function Section({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">{title}</h2>
        <div className="flex flex-wrap gap-2">{actions}</div>
      </div>
      {children}
    </section>
  );
}

function Query({
  q,
  children,
}: {
  q: { isLoading: boolean; isError: boolean; error: unknown; refetch: () => unknown };
  children: React.ReactNode;
}) {
  return q.isLoading ? (
    <LoadingBlock rows={3} />
  ) : q.isError ? (
    <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  ) : (
    <>{children}</>
  );
}

export function ReconciliationPage() {
  const { can } = useAuth();
  const canManage = can(P.RECONCILIATION_MANAGE);
  const canApprove = can(P.RECONCILIATION_APPROVE);
  const canShortage = can(P.SHORTAGE_MANAGE);
  const toast = useToast();
  const recons = useRecons();
  const books = useCashBooks();
  const shortages = useShortages();
  const approve = useWrite(
    (v: { id: string; remarks: string }) =>
      post<Recon>(`/reconciliation/${v.id}/approve`, { remarks: v.remarks }),
    inv,
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const picked = recons.data?.find((r) => r.id === selected) ?? null;
  const close = () => setDialog(null);

  const reconColumns: ColumnDef<Recon>[] = [
    ...(canApprove
      ? [
          {
            id: 'select',
            header: () => <span className="sr-only">Select</span>,
            enableSorting: false,
            cell: ({ row }: { row: { original: Recon } }) => (
              <input
                type="radio"
                name="selected-recon"
                aria-label={`Select reconciliation ${row.original.shift ?? ''}`}
                checked={selected === row.original.id}
                onChange={() => setSelected(row.original.id)}
                className="size-5"
              />
            ),
          } as ColumnDef<Recon>,
        ]
      : []),
    { accessorKey: 'shift', header: 'Shift', cell: ({ getValue }) => getValue() ?? '' },
    {
      id: 'variance',
      header: 'Variance by tender',
      cell: ({ row }) =>
        row.original.lines.length
          ? row.original.lines
              .map((l) => `${l.tender}: ${formatQuantity(l.variance, { signed: true })}`)
              .join(', ')
          : 'No tenders had activity',
    },
    {
      accessorKey: 'classification',
      header: 'Classification',
      cell: ({ getValue }) => (
        <StatusBadge tone={tone(getValue<string>())}>{titleCase(getValue<string>())}</StatusBadge>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => (
        <StatusBadge tone={tone(getValue<string>())}>{titleCase(getValue<string>())}</StatusBadge>
      ),
    },
  ];
  const cashColumns: ColumnDef<CashBook>[] = [
    { accessorKey: 'shift', header: 'Shift', cell: ({ getValue }) => getValue() ?? '' },
    ...(
      [
        'opening_balance',
        'advance_amount',
        'final_amount',
        'bank_deposits_total',
        'closing_cash_in_hand',
      ] as const
    ).map(
      (key, i) =>
        ({
          accessorKey: key,
          header: ['Opening balance', 'Advance', 'Final', 'Bank deposits', 'Closing cash-in-hand'][
            i
          ]!,
          meta: { numeric: true },
          cell: ({ getValue }: { getValue: () => unknown }) => formatMoney(getValue() as string),
        }) as ColumnDef<CashBook>,
    ),
    { accessorKey: 'recorded_by', header: 'Recorded by', cell: ({ getValue }) => getValue() ?? '' },
  ];
  const shortageColumns: ColumnDef<Shortage>[] = [
    { accessorKey: 'employee', header: 'Employee', cell: ({ getValue }) => getValue() ?? '' },
    { accessorKey: 'shift', header: 'Shift', cell: ({ getValue }) => getValue() ?? '' },
    { accessorKey: 'tender', header: 'Tender', cell: ({ getValue }) => getValue() ?? '' },
    {
      accessorKey: 'amount',
      header: 'Amount',
      meta: { numeric: true },
      cell: ({ getValue }) => formatMoney(getValue<string>()),
    },
    {
      accessorKey: 'recovered',
      header: 'Recovered',
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
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => (
        <StatusBadge tone={getValue<string>() === 'Recovered' ? 'ok' : 'warn'}>
          {getValue<string>()}
        </StatusBadge>
      ),
    },
  ];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8">
      <PageHeader
        title="Shift Reconciliation"
        subtitle="Declared against expected, cash custody, and employee cash shortages."
      />

      <Section
        title="Reconciliations"
        actions={
          <>
            {canApprove && (
              <Button disabled={!picked} onClick={() => picked && setDialog({ approve: picked })}>
                Approve selected
              </Button>
            )}
            {canManage && (
              <Button variant="primary" onClick={() => setDialog('reconcile')}>
                <Plus className="size-4" aria-hidden /> Reconcile shift
              </Button>
            )}
          </>
        }
      >
        <Query q={recons}>
          <DataTable
            caption="Reconciliations"
            columns={reconColumns}
            data={recons.data ?? []}
            getRowId={(r) => r.id}
            empty={<EmptyState title="No reconciliations yet" />}
          />
        </Query>
      </Section>

      <Section
        title="Shift Cash Custody (Advance / Final)"
        actions={
          canManage && (
            <>
              <Button onClick={() => setDialog('deposit')}>
                <Plus className="size-4" aria-hidden /> Record bank deposit
              </Button>
              <Button variant="primary" onClick={() => setDialog('movements')}>
                <Plus className="size-4" aria-hidden /> Record cash movements
              </Button>
            </>
          )
        }
      >
        <Query q={books}>
          <DataTable
            caption="Shift cash book"
            columns={cashColumns}
            data={books.data ?? []}
            getRowId={(b) => b.shift_id}
            empty={<EmptyState title="No cash movements recorded yet" />}
          />
        </Query>
      </Section>

      <Section
        title="Employee Cash Shortages"
        actions={
          canShortage && (
            <>
              <Button onClick={() => setDialog('recovery')}>
                <Plus className="size-4" aria-hidden /> Record recovery
              </Button>
              <Button variant="primary" onClick={() => setDialog('shortage')}>
                <Plus className="size-4" aria-hidden /> Record shortage
              </Button>
            </>
          )
        }
      >
        <Query q={shortages}>
          <DataTable
            caption="Employee cash shortages"
            columns={shortageColumns}
            data={shortages.data ?? []}
            getRowId={(s) => s.id}
            empty={<EmptyState title="No cash shortages recorded" />}
          />
        </Query>
      </Section>

      {dialog === 'reconcile' && <ReconcileDialog onClose={close} />}
      {dialog === 'movements' && <MovementsDialog onClose={close} />}
      {dialog === 'deposit' && <DepositDialog books={books.data ?? []} onClose={close} />}
      {dialog === 'shortage' && <ShortageDialog onClose={close} />}
      {dialog === 'recovery' && <RecoveryDialog onClose={close} />}
      {dialog && typeof dialog === 'object' && (
        <ReasonDialog
          title="Approve reconciliation"
          description={dialog.approve.shift ?? undefined}
          label="Remarks"
          submitLabel="Approve"
          onConfirm={async (remarks) => {
            await approve.mutateAsync({ id: dialog.approve.id, remarks });
            toast.success('Reconciliation approved.');
          }}
          onClose={close}
        />
      )}
    </div>
  );
}
