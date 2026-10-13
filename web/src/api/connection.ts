// How this window is connected to the pump's data. Only a Client PC (window.pperp.mode === 'client') ever leaves 'local'.
//   local   - Single PC: the data is on this PC, nothing to show.
//   live    - Client PC, changes arrive the moment anyone saves.
//   polling - Client PC, the live stream is not available; the screens refresh every 20 seconds instead.
//   offline - Client PC cannot reach the Main PC: what is on screen can be read, nothing can be saved.
import { useSyncExternalStore } from 'react';

export type Link = 'local' | 'live' | 'polling' | 'offline';
export interface ConnectionState {
  link: Link;
  /** Epoch ms of the last answer from the Main PC. */
  lastOk: number | null;
}

export const isClient = (): boolean => window.pperp?.mode === 'client';

let state: ConnectionState = { link: isClient() ? 'polling' : 'local', lastOk: null };
const listeners = new Set<() => void>();

function set(next: Partial<ConnectionState>): void {
  const merged = { ...state, ...next };
  if (merged.link === state.link && merged.lastOk === state.lastOk) return;
  state = merged;
  listeners.forEach((l) => l());
}

export const connection = {
  get: () => state,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  /** Any good answer proves the Main PC is there. */
  answered() {
    if (!isClient()) return;
    set({ lastOk: Date.now(), link: state.link === 'offline' ? 'polling' : state.link });
  },
  unreachable() {
    if (isClient()) set({ link: 'offline' });
  },
  live() {
    if (isClient()) set({ link: 'live', lastOk: Date.now() });
  },
  polling() {
    if (isClient() && state.link !== 'offline') set({ link: 'polling' });
  },
  /** For tests. */
  reset() {
    state = { link: isClient() ? 'polling' : 'local', lastOk: null };
    listeners.forEach((l) => l());
  },
};

export const useConnection = (): ConnectionState => useSyncExternalStore(connection.subscribe, connection.get);
