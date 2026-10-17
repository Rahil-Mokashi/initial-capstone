import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const html = readFileSync(join(__dirname, 'setup.html'), 'utf8');
const section = (id: string) => html.slice(html.indexOf(`aria-labelledby="${id}"`), html.indexOf('</section>', html.indexOf(`aria-labelledby="${id}"`)));

describe('Network setup wording', () => {
  it('says plainly that a Client PC keeps no data of its own', () => {
    const client = section('h-client').replace(/<[^>]+>/g, '');
    expect(client).toMatch(/keeps no data of its own/);
    expect(client).not.toMatch(/keeps more data/);
  });
  it('keeps the technical steps for the guide: no PowerShell or script names on the Main PC part', () => {
    const main = section('h-main');
    expect(main).not.toMatch(/PowerShell|\.ps1|enrol-local|pperp_api/);
    expect(main).toMatch(/Network Setup Guide/);
  });
});
