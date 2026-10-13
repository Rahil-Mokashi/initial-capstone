import { useState, type FormEvent } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { DocumentActions } from '@/components/DocumentActions';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { DecimalField } from '@/components/ui/DecimalField';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/FormDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TabbedPanel } from '@/components/ui/TabbedPanel';
import { useToast } from '@/components/ui/Toast';
import { formatDate, formatMoney, todayIso } from '@/lib/format';
import { P } from '@/lib/permissions';

type S = components['schemas'];
type Line = S['PayrollLineOut'];
const cell = 'border border-line px-3 py-2';
const REFRESH = ['payroll', 'checks', 'bank'];

function Deductions({ line, onClose }: { line: Line; onClose: () => void }) {
  const toast = useToast();
  const [v, setV] = useState({
    advance: line.advance_deduction,
    shortage: line.shortage_deduction,
    other: line.other_deduction,
    note: line.other_note ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['PayrollDeductionsIn']) => api.put(`/payroll/lines/${line.id}/deductions`, b),
    REFRESH,
  );
  return (
    <FormDialog
      title={`Deductions - ${line.employee_name}`}
      description={`Salary earned ${formatMoney(line.gross)}. Advance still to recover: ${formatMoney(line.advance_outstanding)}. Cash shortage still to recover: ${formatMoney(line.shortage_outstanding)}.`}
      submitLabel="Save"
      busy={save.isPending}
      error={error}
      onClose={onClose}
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        try {
          await save.mutateAsync({
            advance: v.advance || '0',
            shortage: v.shortage || '0',
            other: v.other || '0',
            other_note: v.note || null,
          });
          toast.success('Saved.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
    >
      <DecimalField
        label="Advance recovered (₹)"
        maxFraction={2}
        unit="rupees"
        value={v.advance}
        onChange={(e) => setV({ ...v, advance: e.target.value })}
      />
      <DecimalField
        label="Cash shortage recovered (₹)"
        maxFraction={2}
        unit="rupees"
        value={v.shortage}
        onChange={(e) => setV({ ...v, shortage: e.target.value })}
      />
      <DecimalField
        label="Other deduction (₹)"
        maxFraction={2}
        unit="rupees"
        value={v.other}
        onChange={(e) => setV({ ...v, other: e.target.value })}
      />
      <TextField
        label="What the other deduction is"
        optional
        value={v.note}
        onChange={(e) => setV({ ...v, note: e.target.value })}
      />
    </FormDialog>
  );
}

function PayDialog({ line, onClose }: { line: Line; onClose: () => void }) {
  const toast = useToast();
  const accounts = useGet<S['BankAccountOut'][]>(['bank', 'accounts-for-pay'], '/bank/accounts');
  const [v, setV] = useState({ method: 'cash', date: todayIso(), account: '', ref: '' });
  const [error, setError] = useState<string | null>(null);
  const save = useWrite(
    (b: S['PayrollPayIn']) => api.post(`/payroll/lines/${line.id}/pay`, b),
    REFRESH,
  );
  return (
    <FormDialog
      title={`Mark paid - ${line.employee_name}`}
      description={`Net pay ${formatMoney(line.net)}.`}
      submitLabel="Mark paid"
      busy={save.isPending}
      error={error}
      onClose={onClose}
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        try {
          await save.mutateAsync({
            method: v.method as 'cash' | 'bank',
            paid_on: v.date,
            bank_account_id: v.method === 'bank' ? v.account || null : null,
            reference: v.ref || null,
          });
          toast.success('Marked paid.');
          onClose();
        } catch (err) {
          setError(friendlyMessage(err));
        }
      }}
    >
      <SelectField
        label="Paid by"
        value={v.method}
        onChange={(e) => setV({ ...v, method: e.target.value })}
      >
        <option value="cash">Cash</option>
        <option value="bank">Bank</option>
      </SelectField>
      {v.method === 'bank' && (
        <SelectField
          label="From which account"
          value={v.account}
          onChange={(e) => setV({ ...v, account: e.target.value })}
        >
          <option value="">Choose</option>
          {(accounts.data ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </SelectField>
      )}
      <TextField
        label="Paid on"
        type="date"
        value={v.date}
        onChange={(e) => setV({ ...v, date: e.target.value })}
      />
      <TextField
        label="Reference"
        optional
        value={v.ref}
        onChange={(e) => setV({ ...v, ref: e.target.value })}
      />
    </FormDialog>
  );
}

function Register() {
  const { can } = useAuth();
  const toast = useToast();
  const [month, setMonth] = useState(todayIso().slice(0, 7));
  const reg = useGet<S['PayrollRegisterOut'] | null>(
    ['payroll', 'register', month],
    `/payroll/register/${month}`,
  );
  const [editing, setEditing] = useState<Line | null>(null);
  const [paying, setPaying] = useState<Line | null>(null);
  const prepare = useWrite(() => api.post('/payroll/runs', { month }), REFRESH);
  const approve = useWrite((id: string) => api.post(`/payroll/runs/${id}/approve`), REFRESH);
  const r = reg.data;
  const manage = can(P.PAYROLL_MANAGE);
  return (
    <section aria-labelledby="reg" className="flex flex-col gap-4">
      <h2 id="reg" className="sr-only">
        Salary register
      </h2>
      <div className="flex flex-wrap items-end gap-3">
        <TextField
          label="Month"
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        />
        {r == null && manage && !reg.isLoading && (
          <Button
            variant="primary"
            loading={prepare.isPending}
            onClick={() =>
              prepare
                .mutateAsync()
                .then(() => toast.success(`${month} prepared from attendance.`))
                .catch((e) => toast.error(friendlyMessage(e)))
            }
          >
            Prepare {month} from attendance
          </Button>
        )}
        {r && (
          <StatusBadge
            tone={r.status === 'paid' ? 'ok' : r.status === 'approved' ? 'info' : 'warn'}
          >
            {r.status === 'draft'
              ? 'Draft: not approved yet'
              : r.status === 'approved'
                ? `Approved by ${r.approved_by}`
                : 'All paid'}
          </StatusBadge>
        )}
        {r && r.status === 'draft' && can(P.PAYROLL_APPROVE) && (
          <Button
            variant="primary"
            onClick={() =>
              approve
                .mutateAsync(r.run_id)
                .then(() => toast.success('Month approved.'))
                .catch((e) => toast.error(friendlyMessage(e)))
            }
          >
            Approve this month
          </Button>
        )}
      </div>
      {reg.isLoading ? (
        <LoadingBlock rows={3} />
      ) : reg.isError ? (
        <ErrorState error={reg.error} onRetry={() => void reg.refetch()} />
      ) : r == null ? (
        <p className="text-sm text-muted">
          {month} has not been prepared yet. Set each employee&apos;s salary first (Salaries tab),
          mark attendance, then prepare it.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm" aria-label={`Salary register ${month}`}>
            <thead>
              <tr className="bg-surface-2 text-left">
                <th className={cell}>Employee</th>
                <th className={`${cell} text-right`}>Days paid</th>
                <th className={`${cell} text-right`}>Salary</th>
                <th className={`${cell} text-right`}>Earned</th>
                <th className={`${cell} text-right`}>Advance</th>
                <th className={`${cell} text-right`}>Shortage</th>
                <th className={`${cell} text-right`}>Other</th>
                <th className={`${cell} text-right`}>Net pay</th>
                <th className={cell}>Paid</th>
                <th className={cell} />
              </tr>
            </thead>
            <tbody>
              {r.lines.map((l) => (
                <tr key={l.id}>
                  <th scope="row" className={`${cell} text-left`}>
                    {l.employee_name}
                  </th>
                  <td className={`${cell} num text-right`}>
                    {l.paid_days} of {l.days_in_month}
                  </td>
                  <td className={`${cell} num text-right`}>{formatMoney(l.monthly_salary)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(l.gross)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(l.advance_deduction)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(l.shortage_deduction)}</td>
                  <td className={`${cell} num text-right`}>{formatMoney(l.other_deduction)}</td>
                  <td className={`${cell} num text-right font-semibold`}>{formatMoney(l.net)}</td>
                  <td className={cell}>
                    {l.payment
                      ? `${l.payment.method === 'cash' ? 'Cash' : 'Bank'}, ${formatDate(l.payment.paid_on)}`
                      : 'Not yet'}
                  </td>
                  <td className={cell}>
                    <span className="flex flex-wrap gap-2">
                      {manage && r.status === 'draft' && (
                        <Button onClick={() => setEditing(l)}>Deductions</Button>
                      )}
                      {manage && r.status !== 'draft' && !l.payment && (
                        <Button onClick={() => setPaying(l)}>Mark paid</Button>
                      )}
                      <DocumentActions
                        previewLabel="Payslip"
                        getHtml={async () =>
                          (await api.get<S['ReportView']>(`/payroll/lines/${l.id}/payslip`)).html
                        }
                        files={[
                          {
                            label: 'PDF',
                            path: `/payroll/lines/${l.id}/payslip.pdf`,
                            filename: `payslip-${l.employee_name}-${month}.pdf`,
                          },
                        ]}
                      />
                    </span>
                  </td>
                </tr>
              ))}
              <tr className="bg-surface-2 font-bold">
                <th scope="row" className={`${cell} text-left`}>
                  Total
                </th>
                <td className={cell} colSpan={2} />
                <td className={`${cell} num text-right`}>{formatMoney(r.gross)}</td>
                <td className={`${cell} num text-right`}>{formatMoney(r.advance)}</td>
                <td className={`${cell} num text-right`}>{formatMoney(r.shortage)}</td>
                <td className={`${cell} num text-right`}>{formatMoney(r.other)}</td>
                <td className={`${cell} num text-right`}>{formatMoney(r.net)}</td>
                <td className={cell} colSpan={2}>
                  Paid out: {formatMoney(r.paid)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {editing && <Deductions line={editing} onClose={() => setEditing(null)} />}
      {paying && <PayDialog line={paying} onClose={() => setPaying(null)} />}
    </section>
  );
}

function Salaries() {
  const { can } = useAuth();
  const toast = useToast();
  const rows = useGet<S['PayrollSalaryRowOut'][]>(['payroll', 'salaries'], '/payroll/salaries');
  const [edit, setEdit] = useState<{ id: string; value: string }>({ id: '', value: '' });
  const [adv, setAdv] = useState({ emp: '', amount: '', method: 'cash', note: '' });
  const [error, setError] = useState<string | null>(null);
  const setSalary = useWrite(
    (v: { id: string; value: string }) =>
      api.put(`/payroll/salaries/${v.id}`, {
        monthly_salary: v.value,
        effective_from: todayIso().slice(0, 8) + '01',
      }),
    REFRESH,
  );
  const advance = useWrite((b: S['PayrollAdvanceIn']) => api.post('/payroll/advances', b), REFRESH);
  const manage = can(P.PAYROLL_MANAGE);
  return (
    <section aria-labelledby="sal" className="flex flex-col gap-4">
      <h2 id="sal" className="text-base font-bold">
        Monthly salary and advances
      </h2>
      <p className="text-sm text-muted">
        A new salary applies from the first of this month. Earlier months keep the salary they had.
      </p>
      {rows.isLoading ? (
        <LoadingBlock rows={2} />
      ) : (
        <table className="w-full border-collapse text-sm" aria-label="Salaries">
          <thead>
            <tr className="bg-surface-2 text-left">
              <th className={cell}>Employee</th>
              <th className={`${cell} text-right`}>Monthly salary</th>
              <th className={`${cell} text-right`}>Advance still to recover</th>
              <th className={cell} />
            </tr>
          </thead>
          <tbody>
            {(rows.data ?? []).map((e) => (
              <tr key={e.employee_id}>
                <th scope="row" className={`${cell} text-left`}>
                  {e.employee_code} - {e.name}
                </th>
                <td className={`${cell} num text-right`}>
                  {e.monthly_salary ? formatMoney(e.monthly_salary) : 'Not set'}
                </td>
                <td className={`${cell} num text-right`}>{formatMoney(e.advance_outstanding)}</td>
                <td className={cell}>
                  {manage &&
                    (edit.id === e.employee_id ? (
                      <span className="flex gap-2">
                        <DecimalField
                          label="New salary"
                          maxFraction={2}
                          unit="rupees"
                          value={edit.value}
                          onChange={(ev) => setEdit({ ...edit, value: ev.target.value })}
                        />
                        <Button
                          variant="primary"
                          onClick={() =>
                            setSalary
                              .mutateAsync(edit)
                              .then(() => {
                                toast.success('Salary saved.');
                                setEdit({ id: '', value: '' });
                              })
                              .catch((er) => toast.error(friendlyMessage(er)))
                          }
                        >
                          Save
                        </Button>
                      </span>
                    ) : (
                      <Button
                        onClick={() =>
                          setEdit({ id: e.employee_id, value: e.monthly_salary ?? '' })
                        }
                      >
                        Set salary
                      </Button>
                    ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {manage && (
        <form
          aria-label="Give an advance"
          className="flex flex-wrap items-end gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await advance.mutateAsync({
                employee_id: adv.emp,
                amount: adv.amount,
                given_on: todayIso(),
                method: adv.method as 'cash' | 'bank',
                note: adv.note || null,
              });
              toast.success('Advance recorded.');
              setAdv({ emp: '', amount: '', method: 'cash', note: '' });
            } catch (err) {
              setError(friendlyMessage(err));
            }
          }}
        >
          <SelectField
            label="Advance to"
            value={adv.emp}
            onChange={(e) => setAdv({ ...adv, emp: e.target.value })}
          >
            <option value="">Choose</option>
            {(rows.data ?? []).map((e) => (
              <option key={e.employee_id} value={e.employee_id}>
                {e.name}
              </option>
            ))}
          </SelectField>
          <DecimalField
            label="Amount (₹)"
            maxFraction={2}
            unit="rupees"
            value={adv.amount}
            onChange={(e) => setAdv({ ...adv, amount: e.target.value })}
          />
          <SelectField
            label="Given"
            value={adv.method}
            onChange={(e) => setAdv({ ...adv, method: e.target.value })}
          >
            <option value="cash">In cash</option>
            <option value="bank">From the bank</option>
          </SelectField>
          <TextField
            label="Note"
            optional
            value={adv.note}
            onChange={(e) => setAdv({ ...adv, note: e.target.value })}
          />
          <Button type="submit" variant="primary" loading={advance.isPending}>
            Record advance
          </Button>
          {error && (
            <p role="alert" className="w-full text-sm font-medium text-danger-fg">
              {error}
            </p>
          )}
        </form>
      )}
    </section>
  );
}

export function PayrollPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Payroll"
        subtitle="Salaries from attendance, advances, deductions, owner approval and payment. The tallies appear under Checks."
      />
      <TabbedPanel
        label="Payroll"
        tabs={[
          { value: 'register', label: 'Salary register', content: <Register /> },
          { value: 'salaries', label: 'Salaries and advances', content: <Salaries /> },
        ]}
      />
    </div>
  );
}
