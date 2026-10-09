import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Reconciliation } from '@/api/types';
import { VarianceBars } from './VarianceBars';

const rec = (over: Partial<Reconciliation> = {}): Reconciliation => ({
  id: 'r1',
  tank_id: 't1',
  reconciliation_date: '2026-10-09',
  opening_stock: '2500.500',
  received_quantity: '0.000',
  sold_quantity: '500.000',
  testing_quantity: '0.000',
  internal_consumption_quantity: '0.000',
  expected_closing_stock: '2000.500',
  physical_stock: '1990.500',
  variance: '-10.000',
  variance_percent: '-0.50',
  classification: 'normal',
  remarks: null,
  ...over,
});

describe('VarianceBars', () => {
  it('is an accessible figure whose label states every number and the classification', () => {
    render(<VarianceBars reconciliation={rec({ classification: 'warning' })} />);
    const figure = screen.getByRole('figure');
    const label = figure.getAttribute('aria-label') ?? '';
    expect(label).toContain('Book 2,000.500 L');
    expect(label).toContain('physical 1,990.500 L');
    expect(label).toContain('variance -10.000 L (-0.50%)');
    expect(label).toContain('Warning');
  });

  it('prints the numbers next to the bars, never colour alone', () => {
    render(<VarianceBars reconciliation={rec({ classification: 'approval_required' })} />);
    expect(screen.getByText('Variance: -10.000 L (-0.50%)')).toBeInTheDocument();
    expect(screen.getByText('2,000.500 L')).toBeInTheDocument();
    expect(screen.getByText('1,990.500 L')).toBeInTheDocument();
    expect(screen.getByText('Approval Required')).toBeInTheDocument(); // named in words, with an icon
  });

  it('exposes two labelled meters with their own values', () => {
    render(<VarianceBars reconciliation={rec()} />);
    const meters = screen.getAllByRole('meter');
    expect(meters.map((m) => m.getAttribute('aria-label'))).toEqual([
      'Book (expected)',
      'Physical (dipped)',
    ]);
    expect(meters[0]).toHaveAttribute('aria-valuenow', '100');
    expect(meters[1]).toHaveAttribute('aria-valuenow', '100'); // 99.5% rounds for the announcement only
    expect(meters[1]).toHaveAttribute('aria-valuetext', 'Physical (dipped): 1,990.500 L');
  });

  it('sizes the physical bar against the larger figure', () => {
    render(
      <VarianceBars
        reconciliation={rec({ expected_closing_stock: '1000.000', physical_stock: '500.000' })}
      />,
    );
    const fills = screen.getAllByTestId('variance-bar-fill');
    expect(fills[0]).toHaveStyle({ width: '100%' });
    expect(fills[1]).toHaveStyle({ width: '50%' });
  });

  it.each([
    ['normal', 'normal', 'var(--text)'],
    ['warning', 'warning', 'var(--warn)'],
    ['investigation_required', 'warning', 'var(--warn)'],
    ['approval_required', 'critical', 'var(--danger)'],
  ])(
    '%s uses the %s colour token (theme-aware CSS variable, so light and dark both work)',
    (classification, tone, token) => {
      render(<VarianceBars reconciliation={rec({ classification })} />);
      expect(screen.getByRole('figure')).toHaveAttribute('data-tone', tone);
      for (const fill of screen.getAllByTestId('variance-bar-fill')) {
        expect(fill.style.background).toContain(token);
      }
    },
  );

  it('shows a positive variance with a plus sign', () => {
    render(<VarianceBars reconciliation={rec({ variance: '5.000', variance_percent: '0.25' })} />);
    expect(
      within(screen.getByRole('figure')).getByText('Variance: +5.000 L (+0.25%)'),
    ).toBeInTheDocument();
  });
});
