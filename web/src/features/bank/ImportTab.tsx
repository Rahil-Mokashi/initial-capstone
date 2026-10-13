import { useEffect, useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';
import { Button } from '@/components/ui/Button';
import { SelectField, TextField } from '@/components/ui/Field';
import { FormError } from '@/components/ui/FormDialog';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { formatDate, formatMoney } from '@/lib/format';

type S = components['schemas'];
type Mapping = S['BankMappingIn'];

export const DATE_FORMATS = [
  { value: '', label: 'Work it out (common formats)' },
  { value: '%d/%m/%Y', label: '31/12/2026' },
  { value: '%d-%m-%Y', label: '31-12-2026' },
  { value: '%d-%b-%Y', label: '31-Dec-2026' },
  { value: '%Y-%m-%d', label: '2026-12-31' },
];

/** First guess of which column is which, from the words banks use. The person can change every one. */
export function guessMapping(headers: string[], headerRow: number): Mapping {
  const find = (...words: string[]) =>
    headers.find((h) => words.some((w) => h.toLowerCase().includes(w))) ?? null;
  return {
    date_col: find('txn date', 'transaction date', 'date', 'value dt') ?? '',
    description_col: find('narration', 'description', 'particulars', 'details', 'remarks') ?? '',
    debit_col: find('withdrawal', 'debit', 'dr amount', 'paid out'),
    credit_col: find('deposit', 'credit', 'cr amount', 'paid in'),
    balance_col: find('balance'),
    reference_col: find('utr', 'reference', 'ref no', 'chq'),
    header_row: headerRow,
    date_format: null,
    amount_col: null,
    type_col: null,
    delimiter: null,
    sheet: null,
  };
}

// FileReader works everywhere (including the unit-test DOM); Blob.arrayBuffer is not in every environment.
function readBytes(file: File): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
}

async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await readBytes(file));
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000)
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

function ColumnSelect({
  label,
  headers,
  value,
  onChange,
  optional,
}: {
  label: string;
  headers: string[];
  value: string | null | undefined;
  onChange: (v: string | null) => void;
  optional?: boolean;
}) {
  return (
    <SelectField
      label={label}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">{optional ? '(none)' : 'Choose the column'}</option>
      {headers.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
    </SelectField>
  );
}

export function ImportTab() {
  const toast = useToast();
  const accounts = useGet<S['BankAccountOut'][]>(['bank', 'accounts'], '/bank/accounts');
  const [accountId, setAccountId] = useState('');
  const [file, setFile] = useState<{ name: string; data: string } | null>(null);
  const [headerRow, setHeaderRow] = useState(0);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [preview, setPreview] = useState<S['BankPreviewOut'] | null>(null);
  const [skip, setSkip] = useState(false);
  const [profileName, setProfileName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const account = accountId || accounts.data?.[0]?.id || '';
  const profiles = useGet<S['BankProfileOut'][]>(
    ['bank', 'profiles', account],
    `/bank/accounts/${account}/profiles`,
    account !== '',
  );

  const readHeaders = useWrite(
    (b: S['BankHeadersIn']) =>
      api.post<S['BankHeadersOut']>(`/bank/accounts/${account}/headers`, b),
    [],
  );
  const doPreview = useWrite(
    (b: S['BankFileIn']) => api.post<S['BankPreviewOut']>(`/bank/accounts/${account}/preview`, b),
    [],
  );
  const doImport = useWrite(
    (b: S['BankFileIn']) => api.post<S['BankImportOut']>(`/bank/accounts/${account}/import`, b),
    ['bank', 'checks'],
  );
  const saveProfile = useWrite(
    (v: { name: string; m: Mapping }) =>
      api.put(`/bank/accounts/${account}/profiles/${encodeURIComponent(v.name)}`, v.m),
    ['bank'],
  );

  useEffect(() => {
    if (!file) return;
    setError(null);
    readHeaders
      .mutateAsync({ filename: file.name, content_base64: file.data, header_row: headerRow })
      .then((h) => {
        setHeaders(h.headers);
        setMapping((m) =>
          m && m.header_row === headerRow ? m : guessMapping(h.headers, headerRow),
        );
        setPreview(null);
      })
      .catch((e) => setError(friendlyMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-read only when the file or the header line changes
  }, [file, headerRow, account]);

  async function choose(f: File | undefined) {
    if (!f) return;
    setPreview(null);
    setFile({ name: f.name, data: await toBase64(f) });
  }
  const body = (): S['BankFileIn'] => ({
    filename: file!.name,
    content_base64: file!.data,
    mapping: mapping!,
    skip_unreadable: skip,
  });
  const upd = (patch: Partial<Mapping>) => mapping && setMapping({ ...mapping, ...patch });
  const style = mapping?.amount_col ? (mapping.type_col ? 'drcr' : 'signed') : 'separate';

  return (
    <section aria-labelledby="imp" className="flex flex-col gap-4">
      <h2 id="imp" className="text-base font-bold">
        Import a bank statement
      </h2>
      <p className="text-sm text-muted">
        CSV or Excel (.xlsx) from net banking. PDF statements cannot be read yet. Nothing is stored
        until you press Import; a line that is already there is never added twice.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <SelectField
          label="Bank account"
          value={account}
          onChange={(e) => {
            setAccountId(e.target.value);
            setPreview(null);
          }}
        >
          {(accounts.data ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </SelectField>
        <label className="flex flex-col gap-1 text-sm font-semibold">
          Statement file
          <input
            type="file"
            accept=".csv,.xlsx,.txt"
            className="min-h-[44px] rounded-md border border-line-strong px-3 py-2 font-normal"
            onChange={(e) => void choose(e.target.files?.[0])}
          />
        </label>
        {(profiles.data ?? []).length > 0 && (
          <SelectField
            label="Saved column layout"
            value=""
            onChange={(e) => {
              const p = profiles.data?.find((x) => x.name === e.target.value);
              if (p) {
                setMapping(p.mapping as unknown as Mapping);
                setHeaderRow((p.mapping as { header_row?: number }).header_row ?? 0);
                setProfileName(p.name);
              }
            }}
          >
            <option value="">Use a saved layout…</option>
            {profiles.data!.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </SelectField>
        )}
      </div>
      <FormError message={error} />
      {file && mapping && headers.length > 0 && (
        <fieldset className="flex flex-col gap-3 rounded-lg border border-line p-4">
          <legend className="px-1 text-sm font-bold">Which column is which</legend>
          <div className="grid gap-3 md:grid-cols-3">
            <TextField
              label="Header line (0 = first line)"
              type="number"
              value={String(headerRow)}
              onChange={(e) => setHeaderRow(Math.max(0, Number(e.target.value) || 0))}
            />
            <ColumnSelect
              label="Date"
              headers={headers}
              value={mapping.date_col}
              onChange={(v) => upd({ date_col: v ?? '' })}
            />
            <ColumnSelect
              label="Details"
              headers={headers}
              value={mapping.description_col}
              onChange={(v) => upd({ description_col: v ?? '' })}
            />
            <SelectField
              label="Money is in"
              value={style}
              onChange={(e) => {
                const v = e.target.value;
                upd(
                  v === 'separate'
                    ? { amount_col: null, type_col: null }
                    : v === 'signed'
                      ? { debit_col: null, credit_col: null, type_col: null }
                      : { debit_col: null, credit_col: null },
                );
              }}
            >
              <option value="separate">Separate money-out and money-in columns</option>
              <option value="signed">One amount column (minus = money out)</option>
              <option value="drcr">One amount column plus a Dr/Cr column</option>
            </SelectField>
            {style === 'separate' ? (
              <>
                <ColumnSelect
                  label="Money out (withdrawal)"
                  headers={headers}
                  value={mapping.debit_col}
                  onChange={(v) => upd({ debit_col: v })}
                  optional
                />
                <ColumnSelect
                  label="Money in (deposit)"
                  headers={headers}
                  value={mapping.credit_col}
                  onChange={(v) => upd({ credit_col: v })}
                  optional
                />
              </>
            ) : (
              <>
                <ColumnSelect
                  label="Amount"
                  headers={headers}
                  value={mapping.amount_col}
                  onChange={(v) => upd({ amount_col: v })}
                />
                {style === 'drcr' && (
                  <ColumnSelect
                    label="Dr / Cr"
                    headers={headers}
                    value={mapping.type_col}
                    onChange={(v) => upd({ type_col: v })}
                  />
                )}
              </>
            )}
            <ColumnSelect
              label="Balance"
              headers={headers}
              value={mapping.balance_col}
              onChange={(v) => upd({ balance_col: v })}
              optional
            />
            <ColumnSelect
              label="Reference (UTR / RRN)"
              headers={headers}
              value={mapping.reference_col}
              onChange={(v) => upd({ reference_col: v })}
              optional
            />
            <SelectField
              label="Date looks like"
              value={mapping.date_format ?? ''}
              onChange={(e) => upd({ date_format: e.target.value || null })}
            >
              {DATE_FORMATS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </SelectField>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <Button
              variant="primary"
              loading={doPreview.isPending}
              onClick={() =>
                doPreview
                  .mutateAsync(body())
                  .then(setPreview)
                  .catch((e) => setError(friendlyMessage(e)))
              }
            >
              Preview (stores nothing)
            </Button>
            <TextField
              label="Save this layout as"
              optional
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
            />
            <Button
              disabled={!profileName.trim()}
              onClick={() =>
                saveProfile
                  .mutateAsync({ name: profileName.trim(), m: mapping })
                  .then(() => toast.success('Layout saved for this bank.'))
              }
            >
              Save layout
            </Button>
          </div>
        </fieldset>
      )}
      {preview && (
        <div className="flex flex-col gap-3" aria-label="Import preview">
          <p className="text-sm">
            <strong>{preview.row_count}</strong> line(s) read: <strong>{preview.new_rows}</strong>{' '}
            new, <strong>{preview.duplicate_rows}</strong> already imported.
            {preview.date_from &&
              ` ${formatDate(preview.date_from)} to ${formatDate(preview.date_to!)}.`}
            {preview.opening_balance != null &&
              ` Opening balance ${formatMoney(preview.opening_balance)}, closing ${formatMoney(preview.closing_balance!)}.`}
          </p>
          {preview.same_file_before && (
            <StatusBadge tone="warn">This exact file was imported before</StatusBadge>
          )}
          {preview.breaks.length > 0 && (
            <p
              role="alert"
              className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
            >
              Rows are missing: the running balance jumps at line{' '}
              {preview.breaks.map((b) => `${b.line} (by ${formatMoney(String(b.gap))})`).join(', ')}
              .
            </p>
          )}
          {preview.problems.length > 0 && (
            <div
              role="alert"
              className="rounded-md border border-danger bg-danger-bg p-3 text-sm text-danger-fg"
            >
              <p className="font-medium">{preview.problems.length} line(s) cannot be read:</p>
              <ul>
                {preview.problems.slice(0, 8).map((p, i) => (
                  <li key={i}>
                    line {String(p.line)}: {String(p.message)}
                  </li>
                ))}
              </ul>
              <label className="mt-2 flex items-center gap-2">
                <input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} />{' '}
                Import the rest and skip these lines (they will be noted)
              </label>
            </div>
          )}
          <table className="w-full border-collapse text-sm" aria-label="First lines of the file">
            <tbody>
              {preview.sample.map((r) => (
                <tr key={r.id}>
                  <td className="border border-line px-3 py-1">{formatDate(r.txn_date)}</td>
                  <td className="border border-line px-3 py-1">{r.description}</td>
                  <td className="num border border-line px-3 py-1 text-right">
                    {Number(r.credit) > 0
                      ? `+${formatMoney(r.credit)}`
                      : `-${formatMoney(r.debit)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div>
            <Button
              variant="primary"
              loading={doImport.isPending}
              disabled={preview.new_rows === 0 || (preview.problems.length > 0 && !skip)}
              onClick={() =>
                doImport
                  .mutateAsync(body())
                  .then((r) => {
                    toast.success(`${r.new_rows} new line(s) imported.`);
                    setPreview(null);
                    setFile(null);
                  })
                  .catch((e) => setError(friendlyMessage(e)))
              }
            >
              Import {preview.new_rows} new line(s)
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
