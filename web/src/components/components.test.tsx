import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ColumnDef } from '@tanstack/react-table';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/errors';
import { DataTable } from './DataTable';
import { ErrorBoundary } from './ErrorBoundary';
import { visibleGroups } from './nav';
import { Button } from './ui/Button';
import { Dialog } from './ui/Dialog';
import { SelectField, TextField } from './ui/Field';
import { EmptyState, ErrorState, LoadingBlock } from './ui/States';
import { StatusBadge } from './ui/StatusBadge';
import { ToastProvider, useToast } from './ui/Toast';

interface Row {
  code: string;
  stock: string;
}
const columns: ColumnDef<Row>[] = [
  { accessorKey: 'code', header: 'Code' },
  { accessorKey: 'stock', header: 'Stock', meta: { numeric: true } },
];

describe('DataTable', () => {
  const data: Row[] = [
    { code: 'T2', stock: '20.000' },
    { code: 'T1', stock: '10.000' },
  ];

  it('is a real table with a caption, column headers and right-aligned numbers', () => {
    render(<DataTable caption="All tanks" columns={columns} data={data} empty={null} />);
    expect(screen.getByRole('table', { name: 'All tanks' })).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Code',
      'Stock',
    ]);
    expect(screen.getByText('20.000').className).toContain('text-right');
  });

  it('sorts when a header is activated and reports aria-sort', async () => {
    render(<DataTable caption="All tanks" columns={columns} data={data} empty={null} />);
    await userEvent.click(screen.getByRole('button', { name: /code/i }));
    const body = screen.getAllByRole('row').slice(1);
    expect(within(body[0]!).getByText('T1')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /code/i })).toHaveAttribute(
      'aria-sort',
      'ascending',
    );
  });

  it('shows the empty state instead of an empty table', () => {
    render(
      <DataTable
        caption="x"
        columns={columns}
        data={[]}
        empty={<EmptyState title="Nothing here" />}
      />,
    );
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
  });
});

describe('form primitives', () => {
  it('ties label, hint and error to the control for screen readers', () => {
    render(<TextField label="Quantity" hint="In litres" error="Enter a number." />);
    const input = screen.getByLabelText('Quantity');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    const described = input.getAttribute('aria-describedby') ?? '';
    expect(document.getElementById(described)?.textContent).toContain('Enter a number.');
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a number.');
  });

  it('shows the hint when there is no error, and marks optional fields', () => {
    render(<TextField label="Reference" optional hint="Invoice number" />);
    expect(screen.getByText('Invoice number')).toBeInTheDocument();
    expect(screen.getByText('(optional)')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders a labelled select', () => {
    render(
      <SelectField label="Fuel type">
        <option>Petrol</option>
      </SelectField>,
    );
    expect(screen.getByRole('combobox', { name: 'Fuel type' })).toBeInTheDocument();
  });

  it('buttons are touch-sized and a loading button is disabled and busy', () => {
    render(<Button loading>Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button.className).toContain('min-h-[44px]');
  });
});

describe('StatusBadge', () => {
  it('never relies on colour alone: it always has text and an icon', () => {
    const { container } = render(<StatusBadge tone="warn">Low - 18.0%</StatusBadge>);
    expect(screen.getByText('Low - 18.0%')).toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();
  });
});

describe('Dialog', () => {
  function Harness() {
    const [open, setOpen] = useState(true);
    return (
      <>
        <button onClick={() => setOpen(true)}>Open</button>
        <Dialog open={open} onOpenChange={setOpen} title="Add tank">
          <input aria-label="Code" />
        </Dialog>
      </>
    );
  }

  it('is a labelled modal that Esc closes', async () => {
    render(<Harness />);
    expect(screen.getByRole('dialog', { name: 'Add tank' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('has a Close button with an accessible name', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('Toast', () => {
  function Fire() {
    const toast = useToast();
    return (
      <>
        <button onClick={() => toast.success('Saved')}>ok</button>
        <button onClick={() => toast.error('Failed')}>bad</button>
      </>
    );
  }

  it('announces success politely and errors assertively; errors can be dismissed', async () => {
    render(
      <ToastProvider>
        <Fire />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByText('ok'));
    expect(screen.getByRole('status')).toHaveTextContent('Saved');
    await userEvent.click(screen.getByText('bad'));
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Failed');
    await userEvent.click(within(alert).getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('ErrorBoundary', () => {
  it('shows a recoverable message instead of a blank screen', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    let explode = true;
    function Bomb() {
      if (explode) throw new Error('kaboom');
      return <p>recovered</p>;
    }
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/something went wrong/i);
    explode = false;
    await userEvent.click(screen.getByRole('button', { name: /reload this screen/i }));
    expect(screen.getByText('recovered')).toBeInTheDocument();
  });
});

describe('states', () => {
  it('loading is announced and has hidden text', () => {
    render(<LoadingBlock label="Loading tanks" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading tanks');
  });

  it('error state offers Try again for ordinary errors', async () => {
    const retry = vi.fn();
    render(
      <ErrorState error={new ApiError(500, 'internal_error', 'Server broke')} onRetry={retry} />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Server broke');
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(retry).toHaveBeenCalled();
  });

  it('permission errors explain instead of offering a pointless retry', () => {
    render(<ErrorState error={new ApiError(403, 'permission_denied', 'x')} onRetry={vi.fn()} />);
    expect(screen.getByText(/do not have access/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /try again/i })).toBeNull();
  });
});

describe('permission-aware navigation', () => {
  const only =
    (...granted: string[]) =>
    (p: string) =>
      granted.includes(p);

  it('hides items the role cannot use and drops empty groups', () => {
    const groups = visibleGroups(only('inventory.view'));
    expect(groups.map((g) => g.label)).toEqual(['Masters']);
    expect(groups[0]?.items.map((i) => i.label)).toEqual(['Tanks']);
  });

  it('shows nothing for a role with no permissions', () => {
    expect(visibleGroups(only())).toEqual([]);
  });

  it('routable items have a path; the rest are marked as not migrated', () => {
    const all = visibleGroups(() => true).flatMap((g) => g.items);
    expect(all.filter((i) => i.to).every((i) => i.to?.startsWith('/'))).toBe(true);
    expect(all.length).toBeGreaterThan(10);
  });
});
