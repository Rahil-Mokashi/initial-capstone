/* eslint-disable @typescript-eslint/no-require-imports -- electron-builder loads this hook with require() */
// electron-builder afterPack hook. Runs on the unpacked app folder, before the installer is made.
//  - Path budget: Windows cannot open files whose full path exceeds 260 characters. Measure the longest
//    path RELATIVE to the install root, record it for the startup preflight, and FAIL the build if it
//    exceeds the budget.
const { readdirSync, statSync, writeFileSync } = require('node:fs');
const { join } = require('node:path');

// Budget for the longest relative path. Install folder + this must stay under 240 (260 minus 20 spare),
// so 130 allows an install folder of up to 110 characters. The default (%LOCALAPPDATA%\PPERP) is about
// 35 and even a very deep per-user profile rarely exceeds 70.
const RELATIVE_BUDGET = 130;

function longestRelative(root) {
  let best = { length: 0, path: '' };
  (function walk(dir, rel) {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      const relative = rel ? rel + '\\' + name : name;
      if (statSync(full).isDirectory()) walk(full, relative);
      else if (relative.length > best.length) best = { length: relative.length, path: relative };
    }
  })(root, '');
  return best;
}

exports.default = async function afterPack(context) {
  const root = context.appOutDir;
  // The record file lives at resources\path-budget.json; make sure it is counted in the measurement.
  const record = join(root, 'resources', 'path-budget.json');
  writeFileSync(record, '{}');
  const best = longestRelative(root);
  writeFileSync(record, JSON.stringify({ longestRelative: best.length, example: best.path }));
  console.log(
    '  - path budget: longest relative path ' +
      best.length +
      ' (budget ' +
      RELATIVE_BUDGET +
      '): ' +
      best.path,
  );
  if (best.length > RELATIVE_BUDGET) {
    throw new Error(
      'Path budget exceeded: ' + best.length + ' > ' + RELATIVE_BUDGET + ' for ' + best.path,
    );
  }
};
