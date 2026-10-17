import { useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { useGet } from '@/api/hooks';
import type { Tank } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { FormError } from '@/components/ui/FormDialog';
import { useToast } from '@/components/ui/Toast';
import { P } from '@/lib/permissions';

interface Row {
  dip_cm: string;
  litres: string;
}

/** Reads "dip,litres" lines from a pasted or imported file: commas, semicolons or tabs; a header line and blank lines are skipped. */
export function parseDipChartCsv(text: string): Row[] {
  const rows: Row[] = [];
  for (const line of text.split(/\r?\n/)) {
    const cells = line.split(/[,;\t]/).map((c) => c.trim().replace(/^"|"$/g, ''));
    if (cells.length < 2 || cells[0] === '' || cells[1] === '') continue;
    const dip = cells[0]!.replace(/,/g, '');
    const litres = cells[1]!.replace(/,/g, '');
    if (!/^-?\d+(\.\d+)?$/.test(dip) || !/^-?\d+(\.\d+)?$/.test(litres)) continue; // the header, or something that is not a number
    rows.push({ dip_cm: dip, litres });
  }
  return rows;
}

/** The oil company's table of dip (cm on the stick) against litres. Typed in, or imported from a CSV; the old chart stays on record. */
export function DipChartDialog({ tank, onClose }: { tank: Tank; onClose: () => void }) {
  const { can } = useAuth();
  const canManage = can(P.INVENTORY_MANAGE);
  const toast = useToast();
  const queryClient = useQueryClient();
  const current = useGet<Row[]>(['tanks', tank.id, 'dip-chart'], `/tanks/${tank.id}/dip-chart`);
  const [rows, setRows] = useState<Row[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (current.data && !loaded) {
      setRows(current.data.length ? current.data : [{ dip_cm: '', litres: '' }]);
      setLoaded(true);
    }
  }, [current.data, loaded]);

  const set = (i: number, key: keyof Row, value: string) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [key]: value } : r)));

  async function importFile(f: File | undefined) {
    if (!f) return;
    setError(null);
    const parsed = parseDipChartCsv(await f.text());
    if (parsed.length < 2) return setError('That file did not have two or more rows of "dip, litres".');
    setRows(parsed);
  }

  async function save() {
    setError(null);
    setBusy(true);
    try {
      const filled = rows.filter((r) => r.dip_cm.trim() !== '' || r.litres.trim() !== '');
      await api.put(`/tanks/${tank.id}/dip-chart`, { rows: filled });
      await queryClient.invalidateQueries({ queryKey: ['tanks'] });
      toast.success(`Dip chart saved for ${tank.code}.`);
      onClose();
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Dip chart - ${tank.code}`}
      description="The oil company's table: the dip stick reading in cm and the litres in the tank at that reading. With it the picture shows the true level. Saving a new chart keeps the old one on record."
    >
      <div className="flex flex-col gap-4">
        <FormError message={error} />
        {current.isLoading ? (
          <p className="text-sm text-muted">Loading the chart…</p>
        ) : (
          <table className="num w-full text-sm">
            <caption className="sr-only">Dip chart rows</caption>
            <thead>
              <tr className="text-left text-muted">
                <th scope="col" className="pb-1">Dip (cm)</th>
                <th scope="col" className="pb-1">Litres</th>
                <th scope="col" className="pb-1"><span className="sr-only">Remove</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="pr-2 pb-1">
                    <input
                      aria-label={`Row ${i + 1} dip in cm`}
                      inputMode="decimal"
                      disabled={!canManage}
                      value={r.dip_cm}
                      onChange={(e) => set(i, 'dip_cm', e.target.value)}
                      className="min-h-[40px] w-full rounded-md border border-line-strong bg-surface px-2"
                    />
                  </td>
                  <td className="pr-2 pb-1">
                    <input
                      aria-label={`Row ${i + 1} litres`}
                      inputMode="decimal"
                      disabled={!canManage}
                      value={r.litres}
                      onChange={(e) => set(i, 'litres', e.target.value)}
                      className="min-h-[40px] w-full rounded-md border border-line-strong bg-surface px-2"
                    />
                  </td>
                  <td className="pb-1">
                    {canManage && (
                      <button
                        type="button"
                        aria-label={`Remove row ${i + 1}`}
                        onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                        className="inline-flex size-10 items-center justify-center rounded-md hover:bg-surface-2"
                      >
                        <Trash2 className="size-4" aria-hidden />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {canManage ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setRows((rs) => [...rs, { dip_cm: '', litres: '' }])}>
              <Plus className="size-4" aria-hidden /> Add a row
            </Button>
            <Button onClick={() => file.current?.click()}>
              <Upload className="size-4" aria-hidden /> Import a CSV
            </Button>
            <input
              ref={file}
              type="file"
              accept=".csv,.txt,text/csv,text/plain"
              aria-label="CSV file of dip and litres"
              className="sr-only"
              onChange={(e) => void importFile(e.target.files?.[0])}
            />
          </div>
        ) : (
          <p className="text-sm text-muted">Only someone who may change tanks can edit the chart.</p>
        )}
        <div className="flex justify-end gap-3">
          <Button onClick={onClose}>Close</Button>
          {canManage && (
            <Button variant="primary" loading={busy} onClick={() => void save()}>
              Save chart
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
