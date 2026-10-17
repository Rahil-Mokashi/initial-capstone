// "Show numbers" on the tank pictures: remembered for each person, on this PC only. The pictures are the main view; the figures are one
// tap away unless this is switched on. A tiny shared store so every picture on the page changes together.
import { useSyncExternalStore } from 'react';

const key = (who: string) => `pperp.tanks.showNumbers.${who}`;
const listeners = new Set<() => void>();

function read(who: string): boolean {
  try {
    return window.localStorage.getItem(key(who)) === '1';
  } catch {
    return false;
  }
}

export function setShowNumbers(who: string, on: boolean): void {
  try {
    window.localStorage.setItem(key(who), on ? '1' : '0');
  } catch {
    /* storage can be unavailable; the switch then lasts until the page is reloaded */
    memory.set(who, on);
  }
  listeners.forEach((l) => l());
}

const memory = new Map<string, boolean>();

export function useShowNumbers(who: string): [boolean, (on: boolean) => void] {
  const value = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => memory.get(who) ?? read(who),
  );
  return [value, (on) => setShowNumbers(who, on)];
}
