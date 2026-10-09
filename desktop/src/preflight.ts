// Windows cannot open a file whose full path is longer than 260 characters. The build records the
// longest path INSIDE the app (resources/path-budget.json); at startup we check that the folder the
// app was installed in leaves enough room, and say so plainly instead of crashing in the middle of
// a database migration.
export const MAX_FULL_PATH = 240; // 260 minus a safety margin

export interface PathCheck {
  ok: boolean;
  installDirLength: number;
  longestRelative: number;
  total: number;
}

export function checkInstallPath(
  installDir: string,
  longestRelative: number,
  limit = MAX_FULL_PATH,
): PathCheck {
  const total = installDir.replace(/[\\/]+$/, '').length + 1 + longestRelative;
  return { ok: total <= limit, installDirLength: installDir.length, longestRelative, total };
}

export function tooLongMessage(
  installDir: string,
  check: PathCheck,
  limit = MAX_FULL_PATH,
): string {
  const spare = Math.max(0, limit - check.longestRelative - 1);
  return [
    'The app is installed in a folder whose path is too long.',
    `Install folder: ${installDir} (${check.installDirLength} characters).`,
    `Windows can only open files up to 260 characters, and this app needs ${check.longestRelative} of them inside its own folder, so the install folder can be at most ${spare} characters long.`,
    'To fix it: uninstall, then install again into a shorter folder such as C:\\PPERP (the default is %LOCALAPPDATA%\\PPERP). Your data is not affected.',
  ].join('\n');
}
