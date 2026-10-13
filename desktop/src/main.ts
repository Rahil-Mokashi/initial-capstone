import { BrowserWindow, Menu, app, dialog, ipcMain, safeStorage, session } from 'electron';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { hostname } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { dirname } from 'node:path';
import { readFileSync } from 'node:fs';
import { checkInstallPath, tooLongMessage } from './preflight';
import { listPrinters, printToPdf, printToPrinter, type PrintOptions } from './print';
import { isAllowedNavigation, isAllowedRequest, type Policy } from './security';
import {
  type DeviceBundle,
  type RunningProxy,
  type SecretBox,
  describeClient,
  enrol,
  fetchAuthority,
  forgetBundle,
  groupFingerprint,
  loadBundle,
  parseBundle,
  saveBundle,
  startProxy,
  testConnection,
} from './lan-client';
import { newSecret, startSidecar, stopSidecar, waitUntilHealthy, type RunningSidecar } from './sidecar';

// E2E hooks are inert unless the test harness sets this.
const E2E = process.env.PPERP_E2E === '1';

if (process.env.PPERP_USER_DATA) app.setPath('userData', process.env.PPERP_USER_DATA);

const errorPage = join(__dirname, 'error.html');
const previewPage = join(__dirname, 'preview.html');
const setupPage = join(__dirname, 'setup.html');
const policy: Policy = {
  allowedOrigins: [],
  allowedFileUrls: [
    pathToFileURL(errorPage).href,
    pathToFileURL(previewPage).href,
    pathToFileURL(setupPage).href,
  ],
};
/** The document each open preview window shows, keyed by that window's webContents id. */
const previews = new Map<number, { html: string; pageSize: PrintOptions['pageSize'] }>();

let sidecar: RunningSidecar | null = null;
/** Client PC mode: the loopback proxy that carries the device certificate to the Main PC. */
let proxy: RunningProxy | null = null;
let setupWindow: BrowserWindow | null = null;
let mainWindow: BrowserWindow | null = null;
let errorWindow: BrowserWindow | null = null;
let quitting = false;

/** URLs the request blocker refused. Exposed only to the test harness. */
const blocked: string[] = [];
if (E2E) {
  (globalThis as Record<string, unknown>).__pperp = {
    blocked,
    policy,
    getOrigin: () => sidecar?.origin ?? proxy?.origin,
    getProxyStatus: () => proxy?.status(),
    getSidecarPid: () => sidecar?.child.pid,
  };
}

function installOfflineGuards(): void {
  const ses = session.defaultSession;
  // Second layer of offline enforcement (the CSP is the first): cancel anything that is
  // not the local API or the app's own files, whatever asked for it.
  ses.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, callback) => {
    const allowed = isAllowedRequest(details.url, policy);
    if (!allowed) blocked.push(details.url);
    callback({ cancel: !allowed });
  });
  ses.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  ses.setPermissionCheckHandler(() => false);

  app.on('web-contents-created', (_event, contents) => {
    contents.on('will-attach-webview', (e) => e.preventDefault());
    contents.on('will-navigate', (e, url) => {
      if (!isAllowedNavigation(url, policy)) e.preventDefault();
    });
    contents.on('will-redirect', (e, url) => {
      if (!isAllowedNavigation(url, policy)) e.preventDefault();
    });
    contents.setWindowOpenHandler(() => ({ action: 'deny' }));
  });
}

function sidecarConfig() {
  const extraEnv: NodeJS.ProcessEnv = {};
  if (app.isPackaged) {
    return {
      executable: join(process.resourcesPath, 'api', 'pperp-api.exe'),
      webDir: join(process.resourcesPath, 'web'),
      extraEnv,
    };
  }
  const repoRoot = resolve(app.getAppPath(), '..');
  return {
    cwd: repoRoot,
    python: process.env.PPERP_PYTHON,
    webDir: process.env.PPERP_WEB_DIR ?? join(repoRoot, 'web', 'dist'),
    extraEnv,
  };
}

const secretBox: SecretBox = {
  available: () => safeStorage.isEncryptionAvailable(),
  encrypt: (text) => safeStorage.encryptString(text),
  decrypt: (data) => safeStorage.decryptString(data),
};

/** True when this PC was installed as the Main PC (lan.json says so, or is unreadable): Single PC mode must not run here. */
function mainPcHere(): boolean {
  const dir =
    process.env.PPERP_LAN_DIR ??
    join(process.env.ProgramData ?? 'C:\\ProgramData', 'PetrolPumpERP', 'lan');
  const file = join(dir, 'lan.json');
  if (!existsSync(file)) return false;
  try {
    return (JSON.parse(readFileSync(file, 'utf8')) as { mode?: string }).mode === 'main';
  } catch {
    return true;
  }
}

function createMainWindow(
  running: { origin: string; secret: string },
  mode: 'single' | 'client' = 'single',
): BrowserWindow {
  const win = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    title: 'Petrol Pump ERP',
    backgroundColor: '#14201b',
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: false,
      spellcheck: false,
      additionalArguments: [
        `--pperp-api-base=${running.origin}`,
        `--pperp-secret=${running.secret}`,
        `--pperp-mode=${mode}`,
      ],
    },
  });
  win.once('ready-to-show', () => win.show());
  win.on('closed', () => {
    mainWindow = null;
  });
  void win.loadURL(`${running.origin}/`);
  return win;
}

function showError(message: string): void {
  // Open the error window BEFORE closing the main one: with no window left Electron would
  // quit the whole app and the user would see it simply vanish.
  const previous = mainWindow;
  mainWindow = null;
  if (!errorWindow) {
    errorWindow = new BrowserWindow({
      width: 640,
      height: 460,
      title: 'Petrol Pump ERP',
      resizable: false,
      backgroundColor: '#f4f2ed',
      webPreferences: {
        preload: join(__dirname, 'preload-error.js'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });
    errorWindow.on('closed', () => {
      errorWindow = null;
    });
  }
  void errorWindow.loadFile(errorPage, { query: { message: message.slice(0, 1500) } });
  previous?.destroy();
}

/** Packaged builds only: refuse, with a clear message, to start from a path that is too long. */
function installPathProblem(): string | null {
  if (!app.isPackaged) return null;
  try {
    const record = JSON.parse(
      readFileSync(join(process.resourcesPath, 'path-budget.json'), 'utf8'),
    ) as {
      longestRelative: number;
    };
    const installDir = dirname(process.execPath);
    const check = checkInstallPath(installDir, record.longestRelative);
    return check.ok ? null : tooLongMessage(installDir, check);
  } catch {
    return null; // no record (older build): do not block startup
  }
}

async function launchClient(bundle: DeviceBundle): Promise<void> {
  try {
    const running = await startProxy(bundle, newSecret());
    proxy = running;
    policy.allowedOrigins = [running.origin];
    const previousError = errorWindow;
    mainWindow = createMainWindow(running, 'client');
    previousError?.destroy();
  } catch (error) {
    if (proxy) await proxy.close().catch(() => undefined);
    proxy = null;
    showError(error instanceof Error ? error.message : String(error));
  }
}

async function launch(): Promise<void> {
  const pathProblem = installPathProblem();
  if (pathProblem) {
    showError(pathProblem);
    return;
  }
  const dir = app.getPath('userData');
  if (describeClient(dir)) {
    try {
      const bundle = loadBundle(dir, secretBox);
      if (bundle) return await launchClient(bundle);
    } catch {
      showError(
        "This PC's saved connection to the Main PC could not be read. Open Network setup and pair this PC again.",
      );
      openSetup();
      return;
    }
  }
  if (mainPcHere()) {
    openSetup(); // this PC IS the Main PC: its own window has to be a Client
    return;
  }
  try {
    const running = await startSidecar(sidecarConfig());
    sidecar = running;
    policy.allowedOrigins = [running.origin];
    await waitUntilHealthy(running);
    const previousError = errorWindow;
    mainWindow = createMainWindow(running);
    previousError?.destroy(); // only once the new window exists, so the app never has zero windows
    // If the service dies while the app is open, say so clearly instead of leaving a dead window.
    void running.exited.then((code) => {
      if (!quitting && sidecar === running) {
        showError(
          `The application service stopped unexpectedly (exit code ${code}).\n${running.stderrTail()}`,
        );
      }
    });
  } catch (error) {
    if (sidecar) await stopSidecar(sidecar, 1000).catch(() => undefined);
    sidecar = null;
    showError(error instanceof Error ? error.message : String(error));
  }
}

async function stopBackends(): Promise<void> {
  if (sidecar) await stopSidecar(sidecar, 3000).catch(() => undefined);
  sidecar = null;
  if (proxy) await proxy.close().catch(() => undefined);
  proxy = null;
}

async function restart(): Promise<void> {
  await stopBackends();
  await launch();
}

function openSetup(): void {
  if (setupWindow) {
    setupWindow.focus();
    return;
  }
  setupWindow = new BrowserWindow({
    width: 820,
    height: 760,
    title: 'Network setup - Petrol Pump ERP',
    backgroundColor: '#f4f2ed',
    webPreferences: {
      preload: join(__dirname, 'preload-setup.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  setupWindow.setMenuBarVisibility(false);
  setupWindow.on('closed', () => {
    setupWindow = null;
  });
  void setupWindow.loadFile(setupPage);
}

const HOST_OK = /^(?:\d{1,3}(?:\.\d{1,3}){3}|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)$/;
function checkTarget(host: unknown, ...ports: unknown[]): string {
  if (typeof host !== 'string' || !HOST_OK.test(host.trim()))
    throw new Error('Type the Main PC address like 192.168.1.10.');
  for (const p of ports)
    if (!Number.isInteger(p) || (p as number) < 1024 || (p as number) > 65535)
      throw new Error('A port is a number from 1024 to 65535.');
  return host.trim();
}

function registerSetupIpc(): void {
  // Only the setup window may use these: the application window never can.
  const guard = (event: Electron.IpcMainInvokeEvent): void => {
    if (!setupWindow || event.sender.id !== setupWindow.webContents.id) throw new Error('Not allowed.');
  };
  ipcMain.handle('shell:networkSetup', (event) => {
    if (!mainWindow || event.sender.id !== mainWindow.webContents.id) throw new Error('Not allowed.');
    openSetup();
  });
  ipcMain.handle('lan:state', (event) => {
    guard(event);
    const client = describeClient(app.getPath('userData'));
    return { mode: client ? 'client' : 'single', client, mainPcHere: mainPcHere(), defaultDeviceName: hostname() };
  });
  ipcMain.handle('lan:fetchCa', async (event, host: unknown, pairingPort: unknown) => {
    guard(event);
    const offer = await fetchAuthority(checkTarget(host, pairingPort), pairingPort as number);
    return { fingerprint: offer.fingerprint, grouped: groupFingerprint(offer.fingerprint) };
  });
  ipcMain.handle('lan:enrol', async (event, a: Record<string, unknown>) => {
    guard(event);
    const host = checkTarget(a.host, a.port, a.pairingPort);
    const name = String(a.deviceName ?? '').trim();
    if (!name || name.length > 80) throw new Error('Give this PC a name (up to 80 letters).');
    const bundle = await enrol({
      host,
      port: a.port as number,
      pairingPort: a.pairingPort as number,
      code: String(a.code ?? ''),
      deviceName: name,
      confirmedFingerprint: String(a.confirmedFingerprint ?? ''),
    });
    saveBundle(app.getPath('userData'), bundle, secretBox);
    return { ok: true };
  });
  ipcMain.handle('lan:test', async (event) => {
    guard(event);
    const bundle = loadBundle(app.getPath('userData'), secretBox);
    return bundle ? testConnection(bundle) : { ok: false, message: 'This PC is not paired yet.' };
  });
  ipcMain.handle('lan:importFile', async (event) => {
    guard(event);
    const picked =
      E2E && process.env.PPERP_E2E_DEVICE_FILE
        ? process.env.PPERP_E2E_DEVICE_FILE
        : (
            await dialog.showOpenDialog(setupWindow!, {
              properties: ['openFile'],
              filters: [{ name: 'Device file', extensions: ['json'] }],
            })
          ).filePaths[0];
    if (!picked) return { ok: false, cancelled: true };
    const bundle = parseBundle(readFileSync(picked, 'utf8'));
    const test = await testConnection(bundle);
    if (!test.ok) return { ok: false, message: test.message };
    saveBundle(app.getPath('userData'), bundle, secretBox);
    return { ok: true, message: "Imported. Delete the device file now: it holds this PC's private key." };
  });
  ipcMain.handle('lan:useSingle', async (event) => {
    guard(event);
    if (mainPcHere())
      throw new Error('This PC is the Main PC, so it cannot run on its own. Import a device file instead.');
    forgetBundle(app.getPath('userData'));
    await finishSetup();
  });
  ipcMain.handle('lan:finish', async (event) => {
    guard(event);
    await finishSetup();
  });
}

async function finishSetup(): Promise<void> {
  const window = setupWindow;
  await restart();
  window?.destroy();
}

function registerIpc(): void {
  registerSetupIpc();
  ipcMain.handle('shell:restart', () => restart());
  ipcMain.handle('shell:quit', () => app.quit());
  ipcMain.handle('files:pick', async (event) => {
    // Test harness only: a fixed answer instead of a native dialog nobody can click in an automated run.
    if (E2E && process.env.PPERP_E2E_PICK_PATH) return process.env.PPERP_E2E_PICK_PATH;
    const win = BrowserWindow.fromWebContents(event.sender) ?? undefined;
    const result = await (win
      ? dialog.showOpenDialog(win, { properties: ['openFile'] })
      : dialog.showOpenDialog({ properties: ['openFile'] }));
    return result.canceled || result.filePaths.length === 0 ? null : (result.filePaths[0] ?? null);
  });
  ipcMain.handle('files:pickFolder', async (event) => {
    if (E2E && process.env.PPERP_E2E_PICK_FOLDER) return process.env.PPERP_E2E_PICK_FOLDER;
    const win = BrowserWindow.fromWebContents(event.sender) ?? undefined;
    const options = { properties: ['openDirectory', 'createDirectory'] as Array<'openDirectory' | 'createDirectory'> };
    const result = await (win ? dialog.showOpenDialog(win, options) : dialog.showOpenDialog(options));
    return result.canceled || result.filePaths.length === 0 ? null : (result.filePaths[0] ?? null);
  });
  ipcMain.handle('print:toPdf', (_e, html: string, options: PrintOptions = {}) =>
    printToPdf(String(html), options, policy),
  );
  ipcMain.handle('print:toPrinter', (_e, html: string, options: PrintOptions = {}) =>
    printToPrinter(String(html), options, policy),
  );
  ipcMain.handle('print:preview', (_e, html: string, options: PrintOptions = {}) => {
    const win = new BrowserWindow({
      width: 900,
      height: 760,
      title: 'Print preview',
      parent: mainWindow ?? undefined,
      modal: false,
      backgroundColor: '#e8e6df',
      webPreferences: {
        preload: join(__dirname, 'preload-preview.js'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });
    win.setMenuBarVisibility(false);
    const id = win.webContents.id;
    previews.set(id, { html: String(html), pageSize: options.pageSize ?? 'A4' });
    win.on('closed', () => previews.delete(id));
    void win.loadFile(previewPage);
    return { ok: true };
  });
  ipcMain.handle('preview:init', (event) => previews.get(event.sender.id) ?? { html: '', pageSize: 'A4' });
  ipcMain.handle('files:save', async (event, suggestedName: string, base64: string) => {
    const name = String(suggestedName).replace(/[\\/:*?"<>|]/g, '_') || 'export';
    const data = Buffer.from(String(base64), 'base64');
    // Test harness only: a fixed folder instead of a native dialog nobody can click in an automated run.
    if (E2E && process.env.PPERP_E2E_SAVE_DIR) {
      mkdirSync(process.env.PPERP_E2E_SAVE_DIR, { recursive: true });
      const target = join(process.env.PPERP_E2E_SAVE_DIR, name);
      writeFileSync(target, data);
      return { ok: true, path: target };
    }
    // The page never chooses the path: the person does, in the Windows Save dialog.
    const win = BrowserWindow.fromWebContents(event.sender) ?? undefined;
    const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : '';
    const options = {
      defaultPath: join(app.getPath('documents'), name),
      filters: ext ? [{ name: ext.toUpperCase(), extensions: [ext] }] : [],
    };
    const choice = await (win ? dialog.showSaveDialog(win, options) : dialog.showSaveDialog(options));
    if (choice.canceled || !choice.filePath) return { ok: false, error: 'cancelled' };
    writeFileSync(choice.filePath, data);
    return { ok: true, path: choice.filePath };
  });
  ipcMain.handle('print:list', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    return win ? listPrinters(win) : [];
  });
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const win = mainWindow ?? errorWindow;
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.on('before-quit', (event) => {
    if (quitting) return;
    quitting = true;
    event.preventDefault();
    // Graceful first so SQLite checkpoints its WAL; force-kill only after a timeout.
    const done = sidecar ? stopSidecar(sidecar) : Promise.resolve('already-stopped' as const);
    void done
      .finally(() => (proxy ? proxy.close().catch(() => undefined) : undefined))
      .finally(() => app.exit(0));
  });

  app.on('window-all-closed', () => app.quit());

  void app.whenReady().then(async () => {
    if (app.isPackaged) Menu.setApplicationMenu(null);
    installOfflineGuards();
    registerIpc();
    await launch();
  });
}
