import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { App } from '@/App';
import { AuthProvider } from '@/auth/AuthContext';
import { ToastProvider } from '@/components/ui/Toast';
import { apiError, json, mockApi, user } from '@/test/mockApi';

const MANAGE = ['employee.view', 'employee.manage'];
const VIEW_ONLY = ['employee.view'];

const employee = (over: Record<string, unknown> = {}) => ({
  id: 'e1',
  employee_code: 'EMP-0001',
  first_name: 'Ravi',
  last_name: 'Kumar',
  contact_number: '+91 9876543210',
  email: null,
  designation: 'Attendant',
  department: 'Forecourt',
  assigned_outlet: 'Main Outlet',
  joining_date: '2026-01-05',
  exit_date: null,
  status: 'active',
  emergency_contact_name: null,
  emergency_contact_phone: null,
  ...over,
});

type Routes = Parameters<typeof mockApi>[0];

async function setup(permissions: string[], extra: Routes = {}, path = '/employees') {
  const api = mockApi({
    'POST /api/auth/login': () =>
      json(200, { token: 'tok', expires_at: '2099-01-01T00:00:00', user: user(permissions) }),
    'GET /api/employees': () =>
      json(200, [
        employee(),
        employee({ id: 'e2', employee_code: 'EMP-0002', first_name: 'Sita' }),
      ]),
    'GET /api/employees/e1': () => json(200, employee()),
    'GET /api/employees/e1/documents': () => json(200, []),
    ...extra,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AuthProvider>
          <MemoryRouter initialEntries={[path]}>
            <App />
          </MemoryRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  await signIn();
  return api;
}

// Opening a protected path signs out-state users in first, then returns them to that path.
async function signIn() {
  await userEvent.type(await screen.findByLabelText('Username'), 'manager1');
  await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!x');
  await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
}

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

describe('employee list', () => {
  it('lists employees and filters by name or code', async () => {
    await setup(MANAGE);
    await screen.findByRole('link', { name: 'EMP-0001' });
    expect(screen.getByRole('link', { name: 'EMP-0002' })).toBeInTheDocument();
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search employees' }), 'sita');
    expect(screen.queryByRole('link', { name: 'EMP-0001' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'EMP-0002' })).toBeInTheDocument();
  });

  it('view-only users get no Add button and a disabled status box', async () => {
    await setup(VIEW_ONLY);
    await screen.findByRole('link', { name: 'EMP-0001' });
    expect(screen.queryByRole('button', { name: /Add employee/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Status of Ravi Kumar')).toBeDisabled();
  });

  it('changing status asks for a reason, sends it, and cancelling changes nothing', async () => {
    const api = await setup(MANAGE, {
      'POST /api/employees/e1/status': () => json(200, employee({ status: 'on_leave' })),
    });
    await screen.findByRole('link', { name: 'EMP-0001' });
    const box = screen.getByLabelText('Status of Ravi Kumar');
    await userEvent.selectOptions(box, 'on_leave');
    // Cancel: no call, status stays as the server has it.
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.calls.some((c) => c.key === 'POST /api/employees/e1/status')).toBe(false);
    expect(screen.getByLabelText('Status of Ravi Kumar')).toHaveValue('active');

    await userEvent.selectOptions(screen.getByLabelText('Status of Ravi Kumar'), 'on_leave');
    await userEvent.type(screen.getByLabelText(/^Reason for status change/), 'Medical');
    await userEvent.click(screen.getByRole('button', { name: 'Change status' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/employees/e1/status')?.body).toEqual({
        status: 'on_leave',
        reason: 'Medical',
      }),
    );
  });
});

describe('add employee', () => {
  it('defaults the outlet and joining date, requires names, and posts the form', async () => {
    const api = await setup(MANAGE, {
      'POST /api/employees': () => json(201, employee({ id: 'e3', first_name: 'Anil' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Add employee/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByLabelText(/Assigned outlet/)).toHaveValue('Main Outlet');
    expect(within(dialog).getByLabelText('Joining date')).not.toHaveValue('');

    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText('Enter the first name.')).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'POST /api/employees')).toBe(false);

    await userEvent.type(within(dialog).getByLabelText('First name'), 'Anil');
    await userEvent.type(within(dialog).getByLabelText('Last name'), 'Shah');
    await userEvent.type(within(dialog).getByLabelText('Contact number'), '9876500000');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const body = api.calls.find((c) => c.key === 'POST /api/employees')?.body as Record<
      string,
      unknown
    >;
    expect(body).toMatchObject({
      first_name: 'Anil',
      last_name: 'Shah',
      contact_number: '9876500000',
      assigned_outlet: 'Main Outlet',
    });
    expect(body).not.toHaveProperty('email'); // blank optional fields are left out
  });

  it('shows a server field error beside the field and keeps what was typed', async () => {
    await setup(MANAGE, {
      'POST /api/employees': () =>
        apiError(422, 'validation_error', 'Check the form.', {
          fields: [{ field: 'contact_number', message: 'Enter a valid phone number.' }],
        }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Add employee/ }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('First name'), 'Anil');
    await userEvent.type(within(dialog).getByLabelText('Last name'), 'Shah');
    await userEvent.type(within(dialog).getByLabelText('Contact number'), 'abc');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText('Enter a valid phone number.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('First name')).toHaveValue('Anil');
  });
});

describe('employee detail', () => {
  it('saves only the profile, sending a blank designation as null', async () => {
    const api = await setup(
      MANAGE,
      { 'PATCH /api/employees/e1': () => json(200, employee({ designation: null })) },
      '/employees/e1',
    );
    const designation = await screen.findByLabelText('Designation');
    await userEvent.clear(designation);
    await userEvent.click(screen.getByRole('button', { name: 'Save profile' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'PATCH /api/employees/e1')?.body).toEqual({
        contact_number: '+91 9876543210',
        designation: null,
        department: 'Forecourt',
      }),
    );
  });

  it('records an exit with a reason', async () => {
    const api = await setup(
      MANAGE,
      {
        'POST /api/employees/e1/exit': () =>
          json(200, employee({ status: 'terminated', exit_date: '2026-10-11' })),
      },
      '/employees/e1',
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Record exit' }));
    await userEvent.type(screen.getByLabelText(/^Reason for exit/), 'Resigned');
    await userEvent.click(screen.getByRole('button', { name: 'Mark as exited' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/employees/e1/exit')?.body).toEqual({
        reason: 'Resigned',
      }),
    );
  });

  it('adds a document using the path from the file dialog, and removes one with a reason', async () => {
    window.pperp = {
      apiBase: '',
      launchSecret: 's',
      files: { pickPath: async () => 'C:\\docs\\id.pdf' },
    } as never;
    let docs = [
      {
        id: 'd1',
        employee_id: 'e1',
        document_type: 'Photo',
        file_reference: 'C:\\p.png',
        description: null,
      },
    ];
    const api = await setup(
      MANAGE,
      {
        'GET /api/employees/e1/documents': () => json(200, docs),
        'POST /api/employees/e1/documents': (body) => {
          docs = [
            ...docs,
            { id: 'd2', employee_id: 'e1', description: null, ...(body as object) } as never,
          ];
          return json(201, docs[1]);
        },
        'POST /api/employees/documents/d1/remove': () => {
          docs = docs.filter((d) => d.id !== 'd1');
          return json(200, {});
        },
      },
      '/employees/e1',
    );
    await screen.findByText('Photo');
    await userEvent.click(screen.getByRole('button', { name: /Add document/ }));
    await userEvent.type(await screen.findByLabelText('Document type'), 'ID Proof');
    await userEvent.click(screen.getByRole('button', { name: 'Add document' }));
    await screen.findByText('ID Proof');
    expect(api.calls.find((c) => c.key === 'POST /api/employees/e1/documents')?.body).toEqual({
      document_type: 'ID Proof',
      file_reference: 'C:\\docs\\id.pdf',
    });

    await userEvent.click(screen.getByRole('button', { name: 'Remove Photo' }));
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Wrong file');
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(screen.queryByText('Photo')).not.toBeInTheDocument());
    expect(
      api.calls.find((c) => c.key === 'POST /api/employees/documents/d1/remove')?.body,
    ).toEqual({ reason: 'Wrong file' });
  });

  it('hides every edit control from a view-only user', async () => {
    await setup(VIEW_ONLY, {}, '/employees/e1');
    await screen.findByRole('heading', { name: 'Ravi Kumar' });
    expect(screen.queryByRole('button', { name: 'Save profile' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add document/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Record exit' })).toBeDisabled();
  });
});
