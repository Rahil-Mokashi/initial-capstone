import { expect, signIn, test } from './fixtures';

test.describe('employees', () => {
  test('add, change status with a reason, attach a document, record an exit', async ({
    launched,
  }) => {
    const { page } = launched;
    await signIn(page, 'manager1');
    await page.getByRole('link', { name: 'Employees' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Employees' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'EMP-0001' })).toBeVisible();

    // Add
    await page.getByRole('button', { name: /Add employee/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Add employee' });
    await expect(dialog.getByLabel(/Assigned outlet/)).toHaveValue('Main Outlet');
    await dialog.getByLabel('First name').fill('Anil');
    await dialog.getByLabel('Last name').fill('Shah');
    await dialog.getByLabel('Contact number').fill('+91 9876500000');
    await dialog.getByRole('button', { name: 'Save' }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole('row').filter({ hasText: 'Anil Shah' })).toBeVisible();

    // Quick status change needs a reason
    await page.getByLabel('Status of Anil Shah').selectOption('on_leave');
    await page.getByLabel('Reason for status change').fill('Family event');
    await page.getByRole('button', { name: 'Change status' }).click();
    await expect(page.getByLabel('Status of Anil Shah')).toHaveValue('on_leave');

    // Detail: the document path comes from the (test-stubbed) file dialog
    await page.getByRole('link', { name: 'Open Anil Shah' }).click();
    await expect(page.getByRole('heading', { name: 'Anil Shah' })).toBeVisible();
    await page.getByRole('button', { name: /Add document/ }).click();
    await page.getByLabel('Document type').fill('ID Proof');
    await page.getByRole('button', { name: 'Add document' }).last().click();
    await expect(page.getByText('C:\\docs\\id-proof.pdf')).toBeVisible();

    // Exit
    await page.getByRole('button', { name: 'Record exit' }).click();
    await page.getByLabel('Reason for exit').fill('Resigned');
    await page.getByRole('button', { name: 'Mark as exited' }).click();
    await expect(page.getByText(/^Left on /)).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Status' })).toHaveValue('terminated');
  });
});
