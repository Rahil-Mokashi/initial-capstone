import { describe, expect, it } from 'vitest';
import { entryScore, pageEntries, search, type SearchEntry } from './search';

const everyone = () => true;
const entries: SearchEntry[] = [
  { kind: 'Page', label: 'Employees', hint: 'Masters', to: '/employees' },
  { kind: 'Page', label: 'Nozzles', hint: 'Masters', to: '/nozzles' },
  { kind: 'Page', label: 'Payroll', hint: 'Operations', to: '/payroll' },
  { kind: 'Page', label: 'Credit', hint: 'Operations', to: '/credit' },
  { kind: 'Page', label: 'Sales', hint: 'Operations', to: '/sales' },
  { kind: 'Tank', label: 'Tank HSD-16', hint: 'Diesel', to: '/tanks/t2' },
  { kind: 'Tank', label: 'Tank MS-22', hint: 'Petrol', to: '/tanks/t1' },
  { kind: 'Employee', label: 'Asha Patil', hint: 'EMP-0001', to: '/employees/e1' },
];
const first = (q: string) => search(entries, q)[0]?.to;

describe('search matching', () => {
  it('finds the right page through typos and partial words', () => {
    expect(first('employes')).toBe('/employees');
    expect(first('nozel')).toBe('/nozzles');
    expect(first('empl')).toBe('/employees');
    expect(first('payrol')).toBe('/payroll');
  });
  it('finds a tank from letters left out', () => {
    expect(search(entries, 'dsl').map((e) => e.to)).toContain('/tanks/t2');
  });
  it('knows the pump words: petrol is MS, diesel is HSD, salary is payroll, udhaar is credit', () => {
    expect(first('petrol')).toBe('/tanks/t1');
    expect(first('diesel')).toBe('/tanks/t2');
    expect(first('salary')).toBe('/payroll');
    expect(first('udhaar')).toBe('/credit');
    expect(first('sales')).toBe('/sales');
  });
  it('finds a record by name or code, and needs every typed word to match something', () => {
    expect(first('asha')).toBe('/employees/e1');
    expect(first('emp-0001')).toBe('/employees/e1');
    expect(search(entries, 'asha zzzzzz')).toEqual([]);
    expect(search(entries, 'qqqq')).toEqual([]);
    expect(search(entries, '   ')).toEqual([]);
  });
  it('scores an exact word above a fuzzy one', () => {
    expect(entryScore('credit', entries[3]!)).toBeGreaterThan(entryScore('credt', entries[3]!));
  });
});

describe('search by role', () => {
  const has = (...permissions: string[]) => (p: string) => permissions.includes(p);
  it('offers an action only to a role that can do it, and pages only the sidebar would show', () => {
    const attendant = pageEntries(has('my_assignment.view', 'sale.view'), 'ATTENDANT');
    expect(attendant.some((e) => e.label === 'Add an employee')).toBe(false);
    expect(attendant.some((e) => e.to === '/payroll')).toBe(false);
    const manager = pageEntries(has('shift.manage', 'shift.view', 'employee.manage', 'employee.view'), 'MANAGER');
    expect(manager.some((e) => e.label === 'Open a shift')).toBe(true);
    expect(manager.some((e) => e.label === 'Add an employee')).toBe(true);
    expect(manager.some((e) => e.label === 'Prepare salaries')).toBe(false);
  });
  it('finds "open shift" and "record dip" for the role that may', () => {
    const owner = pageEntries(everyone, 'OWNER');
    expect(search(owner, 'open shift')[0]?.label).toBe('Open a shift');
    expect(search(owner, 'record dip')[0]?.label).toBe('Record a dip reading');
    expect(search(owner, 'add employee')[0]?.label).toBe('Add an employee');
  });
});
