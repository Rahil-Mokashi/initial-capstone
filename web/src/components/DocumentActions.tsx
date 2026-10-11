import { FileSpreadsheet, FileText, Printer } from 'lucide-react';
import { useState } from 'react';
import { api } from '@/api/client';
import { friendlyMessage } from '@/api/errors';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { openPreview, saveFile } from '@/lib/documents';

export interface ExportFile {
  /** Button text, for example "PDF". */
  label: string;
  /** API path that returns the file, for example "/sales/ab12/receipt.pdf". */
  path: string;
  /** Suggested file name in the Save dialog. */
  filename: string;
}

/**
 * The standard "get this out of the app" row used by every receipt and report: print preview
 * (with Print and Save as PDF inside it) plus one button per exported file. The documents are
 * built by the same Python code as in the Qt app; this only fetches and hands them over.
 */
export function DocumentActions({
  getHtml,
  files = [],
  previewLabel = 'Print preview',
  disabled = false,
}: {
  /** Fetches the printable HTML. Omit when only files are offered. */
  getHtml?: () => Promise<string>;
  files?: ExportFile[];
  previewLabel?: string;
  disabled?: boolean;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  async function run(key: string, action: () => Promise<void>) {
    setBusy(key);
    try {
      await action();
    } catch (error) {
      toast.error(friendlyMessage(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Print and export">
      {getHtml && (
        <Button
          disabled={disabled}
          loading={busy === 'preview'}
          onClick={() =>
            void run('preview', async () => {
              const result = await openPreview(await getHtml());
              if (!result.ok) toast.error(result.error ?? 'Could not open the preview.');
            })
          }
        >
          <Printer className="size-4" aria-hidden /> {previewLabel}
        </Button>
      )}
      {files.map((f) => (
        <Button
          key={f.label}
          disabled={disabled}
          loading={busy === f.label}
          onClick={() =>
            void run(f.label, async () => {
              const result = await saveFile(f.filename, await api.download(f.path));
              if (result.ok)
                toast.success(result.path ? `Saved to ${result.path}` : `${f.label} ready.`);
              else if (result.error !== 'cancelled')
                toast.error(result.error ?? 'Could not save the file.');
            })
          }
        >
          {f.label === 'Excel' ? (
            <FileSpreadsheet className="size-4" aria-hidden />
          ) : (
            <FileText className="size-4" aria-hidden />
          )}{' '}
          {f.label === 'PDF'
            ? 'Export PDF'
            : f.label === 'Excel'
              ? 'Export Excel'
              : `Export ${f.label}`}
        </Button>
      ))}
    </div>
  );
}
