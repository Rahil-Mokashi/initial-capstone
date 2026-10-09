import { BrowserWindow, Menu, app, ipcMain, session } from 'electron';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { dirname } from 'node:path';
import { readFileSync } from 'node:fs';
import { checkInstallPath, tooLongMessage } from './preflight';
import { listPrinters, printToPdf, printToPrinter, type PrintOptions } from './print';
import { isAllowedNavigation, isAllowedRequest, type Policy } from './security';
import { startSidecar, stopSidecar, waitUntilHealthy, type RunningSidecar } from './sidecar';

// E2E hooks are inert unless the test harness sets this.
const E2E = process.env.PPERP_E2E === '1';

if (process.env.PPERP_USER_DATA) app.setPath('userData', process.env.PPERP_USER_DATA);

const errorPage = join(__dirname, 'error.html');
const policy: Policy = { allowedOrigins: [], allowedFileUrls: [pathToFileURL(errorPage).href] };

let sidecar: RunningSidecar | null = null;
let mainWindow: BrowserWindow | null = null;
let errorWindow: BrowserWindow | null = null;
let quitting = false;

/** URLs the request blocker refused. Exposed only to the test harness. */
const blocked: string[] = [];
if (E2E) {
  (globalThis as Record<string, unknown>).__pperp = {
    blocked,
    policy,
    getOrigin: () => sidecar?.origin,
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

function createMainWindow(running: RunningSidecar): BrowserWindow {
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

async function launch(): Promise<void> {
  const pathProblem = installPathProblem();
  if (pathProblem) {
    showError(pathProblem);
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

async function restart(): Promise<void> {
  if (sidecar) await stopSidecar(sidecar, 3000).catch(() => undefined);
  sidecar = null;
  await launch();
}

function registerIpc(): void {
  ipcMain.handle('shell:restart', () => restart());
  ipcMain.handle('shell:quit', () => app.quit());
  ipcMain.handle('print:toPdf', (_e, html: string, options: PrintOptions = {}) =>
    printToPdf(String(html), options, policy),
  );
  ipcMain.handle('print:toPrinter', (_e, html: string, options: PrintOptions = {}) =>
    printToPrinter(String(html), options, policy),
  );
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
    void done.finally(() => app.exit(0));
  });

  app.on('window-all-closed', () => app.quit());

  void app.whenReady().then(async () => {
    if (app.isPackaged) Menu.setApplicationMenu(null);
    installOfflineGuards();
    registerIpc();
    await launch();
  });
}
