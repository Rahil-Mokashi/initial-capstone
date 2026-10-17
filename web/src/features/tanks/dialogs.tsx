import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import type { Reconciliation, Tank, TankStatus, TransactionType } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { checkDecimal, formatLitres, formatQuantity, titleCase, todayIso } from '@/lib/format';
import {
  useCreateTank,
  useEmployees,
  useFuels,
  useReconcile,
  useRecordReading,
  useRecordTransaction,
  useSetStatus,
} from './queries';
import { enterToAdvance } from '@/lib/enterToAdvance';

// ---- shared pieces ------------------------------------------------------------------
const decimal = (rules?: Parameters<typeof checkDecimal>[1]) =>
  z.string().superRefine((value, ctx) => {
    const problem = checkDecimal(value, rules);
    if (problem) ctx.addIssue({ code: 'custom', message: problem });
  });

const optionalDecimal = z.string().superRefine((value, ctx) => {
  if (value.trim() === '') return;
  const problem = checkDecimal(value);
  if (problem) ctx.addIssue({ code: 'custom', message: problem });
});

const blankToUndefined = (s: string) => (s.trim() === '' ? undefined : s.trim());

function FormError({ message }: { message: string | null }) {
  return message ? (
    <p
      role="alert"
      className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
    >
      {message}
    </p>
  ) : null;
}

function Actions({
  onCancel,
  submitLabel,
  busy,
}: {
  onCancel: () => void;
  submitLabel: string;
  busy: boolean;
}) {
  return (
    <div className="mt-2 flex justify-end gap-3">
      <Button onClick={onCancel}>Cancel</Button>
      <Button type="submit" variant="primary" loading={busy}>
        {submitLabel}
      </Button>
    </div>
  );
}

interface DialogBase {
  open: boolean;
  onClose: () => void;
}

// ---- add tank ---------------------------------------------------------------------------
const addSchema = z.object({
  code: z.string().trim().min(1, 'Enter a tank code, for example MS-22.'),
  fuel_id: z.string().min(1, 'Choose a fuel type.'),
  capacity: decimal({ nonZero: true }),
  opening_stock: decimal(),
  calibration_info: z.string(),
});
type AddValues = z.infer<typeof addSchema>;

export function AddTankDialog({ open, onClose }: DialogBase) {
  const toast = useToast();
  const fuels = useFuels(open);
  const create = useCreateTank();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<AddValues>({
    resolver: zodResolver(addSchema),
    defaultValues: {
      code: '',
      fuel_id: '',
      capacity: '10000.000',
      opening_stock: '0',
      calibration_info: '',
    },
  });

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({
        code: v.code.trim(),
        fuel_id: v.fuel_id,
        capacity: v.capacity.trim(),
        opening_stock: v.opening_stock.trim(),
        calibration_info: blankToUndefined(v.calibration_info),
      });
      toast.success(`Tank ${v.code.trim()} added.`);
      reset();
      onClose();
    } catch (error) {
      setFormError(
        applyApiError(error, setError, ['code', 'fuel_id', 'capacity', 'opening_stock']),
      );
    }
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} title="Add tank">
      <form onKeyDown={enterToAdvance} onSubmit={submit} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <TextField
          label="Tank code"
          autoFocus
          placeholder="e.g. MS-22 (petrol) or HSD-16 (diesel)"
          error={errors.code?.message}
          {...register('code')}
        />
        <SelectField
          label="Fuel type"
          error={
            errors.fuel_id?.message ?? (fuels.isError ? 'Could not load fuel types.' : undefined)
          }
          {...register('fuel_id')}
        >
          <option value="">Choose…</option>
          {fuels.data?.map((f) => (
            <option key={f.id} value={f.id}>
              {f.fuel_type}
            </option>
          ))}
        </SelectField>
        <div className="grid grid-cols-2 gap-4">
          <DecimalField
            label="Capacity (L)"
            inputMode="decimal"
            className="num"
            error={errors.capacity?.message}
            {...register('capacity')}
          />
          <DecimalField
            label="Opening stock (L)"
            inputMode="decimal"
            className="num"
            error={errors.opening_stock?.message}
            {...register('opening_stock')}
          />
        </div>
        <TextField
          label="Calibration info"
          optional
          placeholder="Calibration chart reference"
          {...register('calibration_info')}
        />
        <Actions onCancel={onClose} submitLabel="Add tank" busy={create.isPending} />
      </form>
    </Dialog>
  );
}

// ---- receipt / issue / adjustment ------------------------------------------------------------
const TXN_COPY: Record<TransactionType, { title: string; hint: string; submit: string }> = {
  receipt: {
    title: 'Record receipt',
    hint: 'Fuel delivered into this tank.',
    submit: 'Record receipt',
  },
  issue: { title: 'Record issue', hint: 'Fuel taken out of this tank.', submit: 'Record issue' },
  adjustment: {
    title: 'Record adjustment',
    hint: 'A correction to the book stock. Use a negative number to reduce it. A reason is welcome but optional.',
    submit: 'Record adjustment',
  },
};

export function TransactionDialog({
  tank,
  type,
  onClose,
}: {
  tank: Tank;
  type: TransactionType;
  onClose: () => void;
}) {
  const toast = useToast();
  const record = useRecordTransaction(tank.id);
  const [formError, setFormError] = useState<string | null>(null);
  const copy = TXN_COPY[type];

  const schema = z.object({
    quantity: decimal({ negative: type === 'adjustment', nonZero: true }),
    reference: z.string(),
    remarks: z.string(),
  });
  type Values = z.infer<typeof schema>;

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { quantity: '', reference: '', remarks: '' },
  });

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await record.mutateAsync({
        transaction_type: type,
        quantity: v.quantity.trim(),
        reference: blankToUndefined(v.reference),
        remarks: blankToUndefined(v.remarks),
      });
      toast.success(`${titleCase(type)} recorded for ${tank.code}.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['quantity', 'remarks', 'reference']));
    }
  });

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`${copy.title} - ${tank.code}`}
      description={copy.hint}
    >
      <form onKeyDown={enterToAdvance} onSubmit={submit} noValidate className="flex flex-col gap-4">
        <p className="num rounded-md bg-surface-2 p-3 text-sm">
          Now in tank: <strong>{formatLitres(tank.current_stock)}</strong> of{' '}
          {formatLitres(tank.capacity)}
        </p>
        <FormError message={formError} />
        <DecimalField
          label="Quantity (L)"
          negative={type === 'adjustment'}
          autoFocus
          inputMode="decimal"
          className="num"
          placeholder="0.000"
          error={errors.quantity?.message}
          {...register('quantity')}
        />
        <TextField
          label="Reference"
          optional
          placeholder="Invoice or slip number"
          error={errors.reference?.message}
          {...register('reference')}
        />
        <TextField
          label="Remarks"
          optional
          error={errors.remarks?.message}
          {...register('remarks')}
        />
        <Actions onCancel={onClose} submitLabel={copy.submit} busy={record.isPending} />
      </form>
    </Dialog>
  );
}

// ---- dip reading -----------------------------------------------------------------------------
const LAST_EMPLOYEE_KEY = 'pperp.lastReadingEmployee';

function rememberedEmployee(): string {
  try {
    return window.localStorage.getItem(LAST_EMPLOYEE_KEY) ?? '';
  } catch {
    return '';
  }
}

const readingSchema = z.object({
  employee_id: z.string().min(1, 'Choose who took the reading.'),
  physical_stock: decimal(),
  dip_value: optionalDecimal,
  remarks: z.string(),
});
type ReadingValues = z.infer<typeof readingSchema>;

export function ReadingDialog({ tank, onClose }: { tank: Tank; onClose: () => void }) {
  const toast = useToast();
  const employees = useEmployees(true);
  const record = useRecordReading(tank.id);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ReadingValues>({
    resolver: zodResolver(readingSchema),
    // Sensible default: whoever took the last reading on this PC.
    defaultValues: {
      employee_id: rememberedEmployee(),
      physical_stock: '',
      dip_value: '',
      remarks: '',
    },
  });

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await record.mutateAsync({
        employee_id: v.employee_id,
        physical_stock: v.physical_stock.trim(),
        dip_value: blankToUndefined(v.dip_value),
        remarks: blankToUndefined(v.remarks),
      });
      try {
        window.localStorage.setItem(LAST_EMPLOYEE_KEY, v.employee_id);
      } catch {
        // Remembering the person is a convenience only.
      }
      toast.success(`Reading recorded for ${tank.code}.`);
      onClose();
    } catch (error) {
      setFormError(
        applyApiError(error, setError, ['employee_id', 'physical_stock', 'dip_value', 'remarks']),
      );
    }
  });

  const employeeProblem = employees.isError
    ? 'You need employee access to choose who took the reading. Ask a manager.'
    : undefined;

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Record reading - ${tank.code}`}
      description="A dip reading is an observation. It does not change the book stock; reconcile for that."
    >
      <form onKeyDown={enterToAdvance} onSubmit={submit} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <SelectField
          label="Taken by"
          error={errors.employee_id?.message ?? employeeProblem}
          {...register('employee_id')}
        >
          <option value="">Choose…</option>
          {employees.data?.map((e) => (
            <option key={e.id} value={e.id}>
              {e.employee_code} - {e.first_name} {e.last_name}
            </option>
          ))}
        </SelectField>
        <DecimalField
          label="Physical stock (L)"
          autoFocus
          inputMode="decimal"
          className="num"
          placeholder="0.000"
          error={errors.physical_stock?.message}
          {...register('physical_stock')}
        />
        <DecimalField
          label="Dip value"
          optional
          inputMode="decimal"
          className="num"
          error={errors.dip_value?.message}
          {...register('dip_value')}
        />
        <TextField label="Remarks" optional {...register('remarks')} />
        <Actions onCancel={onClose} submitLabel="Save reading" busy={record.isPending} />
      </form>
    </Dialog>
  );
}

// ---- reconcile --------------------------------------------------------------------------------
const reconcileSchema = z.object({
  reconciliation_date: z.string().min(1, 'Choose a date.'),
  physical_stock: decimal(),
  remarks: z.string(),
});
type ReconcileValues = z.infer<typeof reconcileSchema>;

export function ReconcileDialog({ tank, onClose }: { tank: Tank; onClose: () => void }) {
  const reconcile = useReconcile(tank.id);
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<Reconciliation | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ReconcileValues>({
    resolver: zodResolver(reconcileSchema),
    defaultValues: { reconciliation_date: todayIso(), physical_stock: '', remarks: '' },
  });

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      setResult(
        await reconcile.mutateAsync({
          reconciliation_date: v.reconciliation_date,
          physical_stock: v.physical_stock.trim(),
          remarks: blankToUndefined(v.remarks),
        }),
      );
    } catch (error) {
      setFormError(
        applyApiError(error, setError, ['reconciliation_date', 'physical_stock', 'remarks']),
      );
    }
  });

  if (result) {
    const tone = result.classification === 'normal' ? 'text-ok-fg' : 'text-warn-fg';
    return (
      <Dialog open onOpenChange={(o) => !o && onClose()} title="Reconciliation complete">
        <div className="flex flex-col gap-4">
          <dl className="num grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted">Expected</dt>
            <dd className="text-right font-semibold">
              {formatLitres(result.expected_closing_stock)}
            </dd>
            <dt className="text-muted">Physical</dt>
            <dd className="text-right font-semibold">{formatLitres(result.physical_stock)}</dd>
            <dt className="text-muted">Variance</dt>
            <dd className="text-right font-semibold">
              {formatQuantity(result.variance, { signed: true })} L ({result.variance_percent}%)
            </dd>
            <dt className="text-muted">Classification</dt>
            <dd className={`text-right font-bold ${tone}`}>{titleCase(result.classification)}</dd>
          </dl>
          <p className="text-sm text-muted">
            The tank's book stock now matches the physical figure.
          </p>
          <div className="flex justify-end">
            <Button variant="primary" onClick={onClose} autoFocus>
              Done
            </Button>
          </div>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Reconcile - ${tank.code}`}
      description="Compares the expected stock with what you measured, then resets the book stock to the measured figure."
    >
      <form onKeyDown={enterToAdvance} onSubmit={submit} noValidate className="flex flex-col gap-4">
        <p className="num rounded-md bg-surface-2 p-3 text-sm">
          Book stock now: <strong>{formatLitres(tank.current_stock)}</strong>
        </p>
        <FormError message={formError} />
        <TextField
          label="Date"
          type="date"
          error={errors.reconciliation_date?.message}
          {...register('reconciliation_date')}
        />
        <DecimalField
          label="Physical stock (L)"
          autoFocus
          inputMode="decimal"
          className="num"
          placeholder="0.000"
          error={errors.physical_stock?.message}
          {...register('physical_stock')}
        />
        <TextField label="Remarks" optional {...register('remarks')} />
        <Actions onCancel={onClose} submitLabel="Reconcile" busy={reconcile.isPending} />
      </form>
    </Dialog>
  );
}

// ---- change status -------------------------------------------------------------------------------
const STATUSES: TankStatus[] = ['active', 'inactive', 'maintenance'];

const statusSchema = z.object({
  status: z.enum(['active', 'inactive', 'maintenance']),
  reason: z.string().trim(),
});
type StatusValues = z.infer<typeof statusSchema>;

export function StatusDialog({ tank, onClose }: { tank: Tank; onClose: () => void }) {
  const toast = useToast();
  const setStatus = useSetStatus(tank.id);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<StatusValues>({
    resolver: zodResolver(statusSchema),
    defaultValues: {
      status: (STATUSES.find((s) => s !== tank.status) ?? 'inactive') as TankStatus,
      reason: '',
    },
  });

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await setStatus.mutateAsync({ status: v.status, reason: v.reason.trim() });
      toast.success(`${tank.code} is now ${v.status}.`);
      onClose();
    } catch (error) {
      setFormError(applyApiError(error, setError, ['status', 'reason']));
    }
  });

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Change status - ${tank.code}`}
      description={`Currently ${tank.status}.`}
    >
      <form onKeyDown={enterToAdvance} onSubmit={submit} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <SelectField label="New status" {...register('status')}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {titleCase(s)}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Reason"
          optional
          autoFocus
          error={errors.reason?.message}
          {...register('reason')}
        />
        <Actions onCancel={onClose} submitLabel="Change status" busy={setStatus.isPending} />
      </form>
    </Dialog>
  );
}
