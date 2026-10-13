// Preload for the network setup window only. It wires the buttons to the main process; the page itself has no script
// and no bridge, so nothing it shows can reach Node.
import { ipcRenderer } from 'electron';

interface SetupState {
  mode: 'single' | 'client';
  client: { host: string; port: number; deviceName: string; fingerprint: string } | null;
  mainPcHere: boolean;
  defaultDeviceName: string;
}

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const num = (id: string): number => Number($<HTMLInputElement>(id).value.trim());

window.addEventListener('DOMContentLoaded', () => {
  const message = (text: string, bad = false): void => {
    const box = $('client-msg');
    box.textContent = text;
    box.className = bad ? 'msg bad' : 'msg';
  };
  const busy = async (fn: () => Promise<void>): Promise<void> => {
    document.querySelectorAll('button').forEach((b) => ((b as HTMLButtonElement).disabled = true));
    try {
      await fn();
    } catch (error) {
      message(String((error as Error).message ?? error).replace(/^Error invoking remote method '[^']+': (Error: )?/, ''), true);
    } finally {
      document.querySelectorAll('button').forEach((b) => ((b as HTMLButtonElement).disabled = false));
    }
  };

  let confirmed = '';
  const show = async (): Promise<SetupState> => {
    const state = (await ipcRenderer.invoke('lan:state')) as SetupState;
    $('current').textContent =
      state.mode === 'client' && state.client
        ? `This PC is a Client of the Main PC at ${state.client.host} (named "${state.client.deviceName}").`
        : state.mainPcHere
          ? 'This PC is set up as the Main PC. Its own window must be a Client: import a device file below.'
          : 'This PC works on its own (Single PC).';
    if (!$<HTMLInputElement>('device-name').value) $<HTMLInputElement>('device-name').value = state.defaultDeviceName;
    if (state.client && !$<HTMLInputElement>('host').value) $<HTMLInputElement>('host').value = state.client.host;
    $('test').hidden = state.mode !== 'client';
    return state;
  };
  void show();

  $('check').addEventListener('click', () =>
    busy(async () => {
      const host = $<HTMLInputElement>('host').value.trim();
      if (!host) return message('Type the Main PC address first.', true);
      const offer = (await ipcRenderer.invoke('lan:fetchCa', host, num('pairing-port'))) as { fingerprint: string; grouped: string };
      confirmed = offer.fingerprint;
      $('fingerprint').textContent = offer.grouped;
      $('confirm').hidden = false;
      message('');
    }),
  );

  $('pair').addEventListener('click', () =>
    busy(async () => {
      await ipcRenderer.invoke('lan:enrol', {
        host: $<HTMLInputElement>('host').value.trim(),
        port: num('port'),
        pairingPort: num('pairing-port'),
        code: $<HTMLInputElement>('code').value,
        deviceName: $<HTMLInputElement>('device-name').value,
        confirmedFingerprint: confirmed,
      });
      message('Paired. Opening the application...');
      await ipcRenderer.invoke('lan:finish');
    }),
  );

  $('test').addEventListener('click', () =>
    busy(async () => {
      const result = (await ipcRenderer.invoke('lan:test')) as { ok: boolean; message: string };
      message(result.message, !result.ok);
    }),
  );

  $('import').addEventListener('click', () =>
    busy(async () => {
      const done = (await ipcRenderer.invoke('lan:importFile')) as { ok: boolean; cancelled?: boolean; message?: string };
      if (done.cancelled) return;
      message(done.message ?? 'Imported. Opening the application...');
      if (done.ok) await ipcRenderer.invoke('lan:finish');
    }),
  );

  $('use-single').addEventListener('click', () =>
    busy(async () => {
      await ipcRenderer.invoke('lan:useSingle');
    }),
  );
});
