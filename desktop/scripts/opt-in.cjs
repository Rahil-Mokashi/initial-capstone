/* eslint-disable @typescript-eslint/no-require-imports -- plain Node launcher */
// Runs one of the OPT-IN Playwright suites (the ones that are skipped in a normal `npm run e2e`).
//   npm run test:packaged            installed-app tests (smoke, run-as-node fuse, inspector fuse, offline rules)
//   npm run test:packaged -- --install   install the freshly built installer first (silent, default folder)
//   npm run test:deep-path           installs the built installer into a deliberately deep folder, checks the
//                                    "path too long" message, then uninstalls it again
//   npm run test:screenshots         regenerates the screenshots in docs/
//   npm run test:print-spike         sends one receipt to the SYSTEM DEFAULT printer (touches a real printer!)
// ELECTRON_RUN_AS_NODE is removed first: some terminals set it and Electron would then behave as plain Node.
const { spawnSync } = require('node:child_process');
const { existsSync, rmSync } = require('node:fs');
const { join, resolve } = require('node:path');

const desktop = resolve(__dirname, '..');
const installer = join(desktop, 'release', 'Petrol Pump ERP Setup 2.0.3.exe');
const defaultExe = join(process.env.LOCALAPPDATA ?? '', 'PPERP', 'Petrol Pump ERP.exe');
const [, , which, ...flags] = process.argv;

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

function run(command, args, extraEnv = {}) {
  return (
    spawnSync(command, args, {
      cwd: desktop,
      stdio: 'inherit',
      shell: true,
      env: { ...env, ...extraEnv },
    }).status ?? 1
  );
}
function install(dir) {
  if (!existsSync(installer)) {
    console.error('No installer found. Build it first: npm run dist');
    process.exit(2);
  }
  const args = ['/S'];
  if (dir) args.push('/D=' + dir);
  const status = spawnSync(installer, args, { stdio: 'inherit' }).status;
  if (status !== 0) process.exit(status ?? 1);
}
function playwright(spec, extraEnv) {
  return run('npx', ['playwright', 'test', spec], extraEnv);
}

switch (which) {
  case 'packaged': {
    if (flags.includes('--install')) install(null);
    const exe = process.env.PPERP_PACKAGED_EXE || defaultExe;
    if (!existsSync(exe)) {
      console.error(
        'The installed app was not found at ' +
          exe +
          '. Install it first (use --install) or set PPERP_PACKAGED_EXE.',
      );
      process.exit(2);
    }
    process.exit(playwright('e2e/packaged.spec.ts', { PPERP_PACKAGED_EXE: exe }));
    break;
  }
  case 'deep-path': {
    // 12 x "deepfolder_" = 132 characters plus the temp folder: the install folder is well over 134 characters,
    // so install folder + the app's longest inner path is above the 240-character limit.
    const deep = join(process.env.TEMP ?? 'C:\\Temp', 'deepfolder_'.repeat(12) + 'x');
    install(deep);
    const status = playwright('e2e/deep-path.spec.ts', {
      PPERP_DEEP_EXE: join(deep, 'Petrol Pump ERP.exe'),
    });
    spawnSync('taskkill', ['/IM', 'Petrol Pump ERP.exe', '/F'], { stdio: 'ignore' });
    spawnSync(join(deep, 'Uninstall Petrol Pump ERP.exe'), ['/S'], { stdio: 'ignore' });
    rmSync(deep, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 });
    process.exit(status);
    break;
  }
  case 'screenshots':
    process.exit(playwright('e2e/screenshots.spec.ts', { SCREENSHOTS: '1' }));
    break;
  case 'print-spike':
    console.warn('This sends one receipt to the Windows default printer.');
    process.exit(playwright('e2e/printing.spec.ts', { PRINT_SPIKE: '1' }));
    break;
  default:
    console.error('Usage: node scripts/opt-in.cjs packaged|deep-path|screenshots|print-spike');
    process.exit(2);
}
