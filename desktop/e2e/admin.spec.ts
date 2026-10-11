import { existsSync, mkdtempSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, signIn, test } from './fixtures';

test('company profile, backups (make, check, copy off the drive) and the audit trail', async ({
  launched,
}) => {
  const { page } = launched;
  await signIn(page, 'admin1');

  // Company profile
  await page.getByRole('link', { name: 'Company Profile' }).click();
  await expect(page.getByText(/No business name is set/)).toBeVisible();
  await page.getByLabel(/Business name/).fill('Sai Fuels');
  await page.getByLabel(/GST number/).fill('bad');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(/15 alphanumeric characters/)).toBeVisible();
  await page.getByLabel(/GST number/).fill('27aapfu0939f1zv');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Company profile saved.')).toBeVisible();
  await expect(page.getByText(/No business name is set/)).toBeHidden();
  await expect(page.getByLabel(/GST number/)).toHaveValue('27AAPFU0939F1ZV');

  // Backups: make one, check integrity, copy it to a folder
  await page.getByRole('link', { name: 'Backups' }).click();
  await expect(page.getByText(/No off-device backup has been made/)).toBeVisible();
  await page.getByRole('button', { name: 'Back Up Now' }).click();
  await expect(page.getByRole('cell', { name: /^petrol_pump_\d+_\d+_\d+_manual\.db$/ })).toBeVisible();
  await page.getByRole('button', { name: 'Check Integrity' }).click();
  await expect(page.getByRole('dialog', { name: 'Database is healthy' })).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'OK' }).click();

  const usb = mkdtempSync(join(tmpdir(), 'pperp-usb-'));
  await page.getByRole('button', { name: /Copy petrol_pump_.*_manual\.db to USB/ }).click();
  await page.getByRole('dialog').getByLabel('Destination folder').fill(usb);
  await page.getByRole('dialog').getByRole('button', { name: 'Copy' }).click();
  await expect(page.getByText(/copied and verified/)).toBeVisible();
  expect(readdirSync(usb).filter((f) => f.endsWith('.db'))).toHaveLength(1);
  expect(existsSync(usb)).toBe(true);

  // Audit log: the profile change and the backup are there; the trail verifies
  await page.getByRole('link', { name: 'Audit Log' }).click();
  await expect(page.getByRole('cell', { name: 'settings_updated' }).first()).toBeVisible();
  await expect(page.getByRole('cell', { name: 'backup_created' }).first()).toBeVisible();
  await page.getByLabel('Event contains').fill('backup');
  await page.getByRole('button', { name: 'Filter' }).click();
  await expect(page.getByRole('cell', { name: 'settings_updated' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Verify Trail' }).click();
  await expect(page.getByRole('dialog', { name: 'Audit trail verified' })).toBeVisible();
});
