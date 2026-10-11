import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowLeft, FilePlus2, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useParams } from 'react-router-dom';
import { z } from 'zod';
import { friendlyMessage } from '@/api/errors';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormDialog, FormError } from '@/components/ui/FormDialog';
import { ReasonDialog } from '@/components/ui/ReasonDialog';
import { ErrorState, LoadingBlock } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { applyApiError } from '@/lib/formErrors';
import { formatDate, titleCase } from '@/lib/format';
import { P } from '@/lib/permissions';
import {
  EMPLOYEE_STATUSES,
  useAddDocument,
  useChangeStatus,
  useDocuments,
  useEmployee,
  useRecordExit,
  useRemoveDocument,
  useUpdateEmployee,
  type EmployeeDocument,
  type EmployeeRecord,
  type EmployeeStatus,
} from './queries';

const profileSchema = z.object({
  contact_number: z.string().trim().min(1, 'Enter a contact number.'),
  designation: z.string(),
  department: z.string(),
});
type ProfileValues = z.infer<typeof profileSchema>;

function ProfileSection({ employee, canManage }: { employee: EmployeeRecord; canManage: boolean }) {
  const toast = useToast();
  const update = useUpdateEmployee(employee.id);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      contact_number: employee.contact_number,
      designation: employee.designation ?? '',
      department: employee.department ?? '',
    },
  });
  // Re-sync when the server record changes (after a save).
  useEffect(() => {
    reset({
      contact_number: employee.contact_number,
      designation: employee.designation ?? '',
      department: employee.department ?? '',
    });
  }, [employee, reset]);

  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await update.mutateAsync({
        contact_number: v.contact_number.trim(),
        // Blank clears the field, as in the Qt screen.
        designation: v.designation.trim() || null,
        department: v.department.trim() || null,
      });
      toast.success('Profile saved.');
    } catch (error) {
      setFormError(applyApiError(error, setError, ['contact_number', 'designation', 'department']));
    }
  });

  return (
    <section
      aria-labelledby="profile-title"
      className="rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <h2 id="profile-title" className="mb-4 text-base font-bold">
        Profile
      </h2>
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField
            label="Contact number"
            disabled={!canManage}
            error={errors.contact_number?.message}
            {...register('contact_number')}
          />
          <TextField label="Designation" disabled={!canManage} {...register('designation')} />
          <TextField label="Department" disabled={!canManage} {...register('department')} />
        </div>
        {canManage && (
          <div>
            <Button type="submit" variant="primary" loading={update.isPending}>
              Save profile
            </Button>
          </div>
        )}
      </form>
    </section>
  );
}

type Dialog = { kind: 'status'; status: EmployeeStatus } | { kind: 'exit' } | null;

function StatusSection({ employee, canManage }: { employee: EmployeeRecord; canManage: boolean }) {
  const toast = useToast();
  const changeStatus = useChangeStatus();
  const recordExit = useRecordExit(employee.id);
  const [pick, setPick] = useState<EmployeeStatus>(employee.status as EmployeeStatus);
  const [dialog, setDialog] = useState<Dialog>(null);
  useEffect(() => setPick(employee.status as EmployeeStatus), [employee.status]);
  const close = () => setDialog(null);

  return (
    <section
      aria-labelledby="status-title"
      className="rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <h2 id="status-title" className="mb-1 text-base font-bold">
        Status
      </h2>
      {employee.exit_date && (
        <p className="mb-3 text-sm text-muted">Left on {formatDate(employee.exit_date)}.</p>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48">
          <SelectField
            label="Status"
            value={pick}
            disabled={!canManage}
            onChange={(e) => setPick(e.target.value as EmployeeStatus)}
          >
            {EMPLOYEE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </SelectField>
        </div>
        <Button
          disabled={!canManage || pick === employee.status}
          onClick={() => setDialog({ kind: 'status', status: pick })}
        >
          Apply
        </Button>
        <Button variant="danger" disabled={!canManage} onClick={() => setDialog({ kind: 'exit' })}>
          Record exit
        </Button>
      </div>

      {dialog?.kind === 'status' && (
        <ReasonDialog
          title="Change status"
          description={`${titleCase(employee.status)} to ${titleCase(dialog.status)}`}
          label="Reason for status change"
          submitLabel="Change status"
          onConfirm={async (reason) => {
            await changeStatus.mutateAsync({ id: employee.id, status: dialog.status, reason });
            toast.success('Status changed.');
          }}
          onClose={close}
        />
      )}
      {dialog?.kind === 'exit' && (
        <ReasonDialog
          title="Record exit"
          description="This will mark the employee as terminated, effective today."
          label="Reason for exit"
          submitLabel="Mark as exited"
          tone="danger"
          onConfirm={async (reason) => {
            await recordExit.mutateAsync(reason);
            toast.success('Exit recorded.');
          }}
          onClose={close}
        />
      )}
    </section>
  );
}

const documentSchema = z.object({ document_type: z.string().trim().min(1, 'Enter a type.') });

function AddDocumentDialog({
  employeeId,
  path,
  onClose,
}: {
  employeeId: string;
  path: string;
  onClose: () => void;
}) {
  const toast = useToast();
  const add = useAddDocument(employeeId);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof documentSchema>>({
    resolver: zodResolver(documentSchema),
    defaultValues: { document_type: '' },
  });
  const submit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await add.mutateAsync({ document_type: v.document_type.trim(), file_reference: path });
      toast.success('Document added.');
      onClose();
    } catch (error) {
      setFormError(friendlyMessage(error));
    }
  });
  return (
    <FormDialog
      title="Add document"
      description={path}
      submitLabel="Add document"
      busy={add.isPending}
      error={formError}
      onSubmit={submit}
      onClose={onClose}
    >
      <TextField
        label="Document type"
        placeholder="e.g. ID Proof, Address Proof, Photo"
        autoFocus
        error={errors.document_type?.message}
        {...register('document_type')}
      />
    </FormDialog>
  );
}

function DocumentsSection({ employeeId, canManage }: { employeeId: string; canManage: boolean }) {
  const documents = useDocuments(employeeId);
  const remove = useRemoveDocument();
  const toast = useToast();
  const [picked, setPicked] = useState<string | null>(null);
  const [removing, setRemoving] = useState<EmployeeDocument | null>(null);
  const [pickError, setPickError] = useState<string | null>(null);

  async function choose() {
    setPickError(null);
    // The Windows file dialog runs in the app's main process; the page only gets the chosen path.
    const path = (await window.pperp?.files.pickPath()) ?? null;
    if (path) setPicked(path);
    else if (!window.pperp) setPickError('Choosing a file works in the desktop app only.');
  }

  return (
    <section
      aria-labelledby="documents-title"
      className="rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="documents-title" className="text-base font-bold">
          Documents
        </h2>
        {canManage && (
          <Button onClick={() => void choose()}>
            <FilePlus2 className="size-4" aria-hidden /> Add document
          </Button>
        )}
      </div>
      <FormError message={pickError} />
      {documents.isLoading ? (
        <LoadingBlock label="Loading documents" rows={2} />
      ) : documents.isError ? (
        <ErrorState error={documents.error} onRetry={() => void documents.refetch()} />
      ) : documents.data && documents.data.length > 0 ? (
        <ul className="flex flex-col divide-y divide-line">
          {documents.data.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm font-semibold">{d.document_type}</p>
                <p className="truncate text-sm text-muted">{d.file_reference}</p>
              </div>
              {canManage && (
                <Button
                  variant="danger"
                  aria-label={`Remove ${d.document_type}`}
                  onClick={() => setRemoving(d)}
                >
                  <Trash2 className="size-4" aria-hidden /> Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">No documents added yet.</p>
      )}

      {picked && (
        <AddDocumentDialog employeeId={employeeId} path={picked} onClose={() => setPicked(null)} />
      )}
      {removing && (
        <ReasonDialog
          title="Remove document"
          description={`${removing.document_type} - ${removing.file_reference}`}
          submitLabel="Remove"
          tone="danger"
          onConfirm={async (reason) => {
            await remove.mutateAsync({ documentId: removing.id, reason });
            toast.success('Document removed.');
          }}
          onClose={() => setRemoving(null)}
        />
      )}
    </section>
  );
}

export function EmployeeDetailPage() {
  const { id = '' } = useParams();
  const { can } = useAuth();
  const canManage = can(P.EMPLOYEE_MANAGE);
  const employee = useEmployee(id);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <Link
        to="/employees"
        className="inline-flex min-h-[44px] w-fit items-center gap-1.5 text-sm font-semibold underline-offset-4 hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden /> All employees
      </Link>
      {employee.isLoading ? (
        <LoadingBlock label="Loading employee" rows={4} />
      ) : employee.isError || !employee.data ? (
        <ErrorState error={employee.error} onRetry={() => void employee.refetch()} />
      ) : (
        <>
          <PageHeader
            title={`${employee.data.first_name} ${employee.data.last_name}`}
            subtitle={`${employee.data.employee_code} - joined ${formatDate(employee.data.joining_date)}`}
          />
          <ProfileSection employee={employee.data} canManage={canManage} />
          <StatusSection employee={employee.data} canManage={canManage} />
          <DocumentsSection employeeId={id} canManage={canManage} />
        </>
      )}
    </div>
  );
}
