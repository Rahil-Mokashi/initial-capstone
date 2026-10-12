// Light / dark / follow-the-system, remembered on this terminal (the Qt app keeps the same choice in QSettings).
export type Theme = 'system' | 'light' | 'dark';
const KEY = 'pperp.theme';

export function getTheme(): Theme {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch {
    return 'system';
  }
}

export function applyTheme(theme: Theme): void {
  if (theme === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', theme);
}

export function setTheme(theme: Theme): void {
  applyTheme(theme);
  try {
    window.localStorage.setItem(KEY, theme);
  } catch {
    // Private mode or blocked storage: the choice just lasts until the window closes.
  }
}

/** True when dark is in effect right now (explicit choice, or the system's when following it). */
export function isDark(theme: Theme = getTheme()): boolean {
  return (
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  );
}
