import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DecimalField } from './DecimalField';

describe('DecimalField', () => {
  it('stops at the third decimal place, keeps what was typed, and explains', async () => {
    render(<DecimalField label="Quantity (L)" />);
    const box = screen.getByLabelText('Quantity (L)');
    await userEvent.type(box, '12.3456');
    expect(box).toHaveValue('12.345'); // the 4th place was refused, nothing was rounded
    expect(screen.getByText(/at most 3 decimal places/)).toBeInTheDocument();
  });

  it('clears the explanation once the person carries on correctly', async () => {
    render(<DecimalField label="Quantity (L)" />);
    const box = screen.getByLabelText('Quantity (L)');
    await userEvent.type(box, '1.2345');
    expect(screen.getByText(/at most 3 decimal places/)).toBeInTheDocument();
    await userEvent.type(box, '{Backspace}');
    expect(screen.queryByText(/at most 3 decimal places/)).toBeNull();
    expect(box).toHaveValue('1.23');
  });

  it('money fields stop at two places', async () => {
    render(<DecimalField label="Amount" maxFraction={2} unit="amounts" />);
    const box = screen.getByLabelText('Amount');
    await userEvent.type(box, '10.999');
    expect(box).toHaveValue('10.99');
    expect(screen.getByText(/at most 2 decimal places/)).toBeInTheDocument();
  });

  it('refuses letters and a second decimal point', async () => {
    render(<DecimalField label="Quantity (L)" />);
    const box = screen.getByLabelText('Quantity (L)');
    await userEvent.type(box, '1a.2.3');
    expect(box).toHaveValue('1.23');
  });

  it('a paste that is too precise is refused as a whole, not cut or rounded', async () => {
    render(<DecimalField label="Quantity (L)" />);
    const box = screen.getByLabelText('Quantity (L)');
    await userEvent.click(box);
    await userEvent.paste('12.34567');
    expect(box).toHaveValue('');
    expect(screen.getByText(/Extra digits are not accepted/)).toBeInTheDocument();
    await userEvent.paste('12.345');
    expect(box).toHaveValue('12.345');
  });

  it('minus is refused unless negatives are allowed', async () => {
    render(<DecimalField label="Qty" />);
    const box = screen.getByLabelText('Qty');
    await userEvent.type(box, '-');
    expect(box).toHaveValue('');
    expect(screen.getByText('This cannot be negative.')).toBeInTheDocument();
    await userEvent.type(box, '5');
    expect(box).toHaveValue('5');
  });

  it('minus is accepted when negatives are allowed (stock adjustments)', async () => {
    render(<DecimalField label="Adj" negative />);
    await userEvent.type(screen.getByLabelText('Adj'), '-5.25');
    expect(screen.getByLabelText('Adj')).toHaveValue('-5.25');
  });

  it('typing over a selection is judged on the result', async () => {
    render(<DecimalField label="Quantity (L)" defaultValue="1.234" />);
    const box = screen.getByLabelText('Quantity (L)') as HTMLInputElement;
    box.focus();
    box.setSelectionRange(2, 5);
    await userEvent.keyboard('9');
    expect(box).toHaveValue('1.9');
  });

  it('works with a form library: change events still arrive', async () => {
    const onChange = vi.fn();
    render(<DecimalField label="Quantity (L)" onChange={onChange} />);
    await userEvent.type(screen.getByLabelText('Quantity (L)'), '7');
    expect(onChange).toHaveBeenCalled();
  });
});
