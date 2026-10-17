import type { Page, Route } from '@playwright/test';
import { expect, signIn, test } from './fixtures';

// Huge figures must stay inside their boxes at the two screen sizes the pump uses, in light and in dark.
// The numbers are swapped into the REAL responses on the way in, so every other part of the page is genuine.
const BIG_MONEY = '9999999.99'; // ₹99,99,999.99
const BIG_LITRES = '99999.999'; // 99,999.999 L

async function patch(route: Route, change: (body: Record<string, unknown>) => void) {
  const response = await route.fetch();
  const body = (await response.json()) as Record<string, unknown>;
  change(body);
  await route.fulfill({ response, json: body });
}

async function useBigFigures(page: Page) {
  await page.route('**/api/dashboard/summary', (route) =>
    patch(route, (b) => {
      b.sales_today_count = 99999;
      b.sales_today_amount = BIG_MONEY;
    }),
  );
  await page.route('**/api/digest**', (route) =>
    patch(route, (b) => {
      b.total_sale = BIG_MONEY;
      b.litres_sold = BIG_LITRES;
      b.credit_sales = BIG_MONEY;
      b.credit_outstanding = BIG_MONEY;
    }),
  );
  await page.route('**/api/credit/accounts', async (route) => {
    const response = await route.fetch();
    const rows = (await response.json()) as Array<Record<string, unknown>>;
    for (const r of rows) r.outstanding = BIG_MONEY;
    await route.fulfill({ response, json: rows });
  });
}

/** Cards whose content is wider than the card, plus anything that makes the whole page scroll sideways. */
async function overflowing(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const found: string[] = [];
    const root = document.documentElement;
    if (root.scrollWidth > window.innerWidth + 1) found.push(`page is ${root.scrollWidth}px wide in a ${window.innerWidth}px window`);
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('main section, main li, main article, main [class*="rounded-lg"], main [class*="rounded-md"]'))) {
      if (el.scrollWidth > el.clientWidth + 1) found.push(`${el.tagName.toLowerCase()} "${(el.textContent ?? '').trim().slice(0, 40)}" ${el.scrollWidth} > ${el.clientWidth}`);
    }
    return found;
  });
}

for (const size of [
  { width: 1024, height: 700 }, // a small window, as a worst case
  { width: 1366, height: 768 },
  { width: 1920, height: 1080 },
]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`Today and More keep big figures inside their boxes at ${size.width}x${size.height} in ${theme}`, async ({ launched }) => {
      const { app, page } = launched;
      await app.evaluate(({ BrowserWindow }, [w, h]) => BrowserWindow.getAllWindows()[0]!.setContentSize(w!, h!), [size.width, size.height]);
      await useBigFigures(page);
      await signIn(page, 'owner1', undefined, { home: true });
      await expect(page.getByRole('heading', { level: 1, name: /Good (morning|afternoon|evening)/ })).toBeVisible();
      await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);

      await expect(page.getByText('₹99,99,999.99').first()).toBeVisible();
      expect(await overflowing(page)).toEqual([]);
      await page.screenshot({ path: `test-results/today-${size.width}-${theme}.png`, fullPage: true });

      await page.getByRole('link', { name: /^More:/ }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'More' })).toBeVisible();
      await expect(page.getByText('99,999.999').first()).toBeVisible();
      expect(await overflowing(page)).toEqual([]);
      await page.screenshot({ path: `test-results/more-${size.width}-${theme}.png`, fullPage: true });
    });
  }
}
