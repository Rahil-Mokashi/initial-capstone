/* eslint-disable @typescript-eslint/no-require-imports -- plain Node launcher */
// Starts Electron on print-test/main.cjs, forwarding the arguments. It removes ELECTRON_RUN_AS_NODE first
// (some terminals set it, and then Electron would behave as plain Node and print nothing).
//   npm run print-test -- --list
//   npm run print-test -- --printer "Your Printer Name" --doc both
const { spawn } = require('node:child_process');
const { join } = require('node:path');

const electron = require('electron'); // path to the electron executable
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electron, [join(__dirname, 'main.cjs'), ...process.argv.slice(2)], {
  env,
  stdio: 'inherit',
});
child.on('exit', (code) => process.exit(code ?? 1));
