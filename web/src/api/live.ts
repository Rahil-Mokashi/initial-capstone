// Client PCs only: the Main PC says "something changed" the moment anybody saves, and every open screen refreshes.
// If that stream cannot be used, screens refresh every 20 seconds instead; if the Main PC cannot be reached at all,
// the window turns read-only (see client.ts) and keeps asking until it answers again.
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { apiBase, launchSecret } from './bridge';
import { connection, isClient } from './connection';
import { session } from './session';

export const POLL_MS = 20_000;
const RETRY_MS = 5_000;

/** Pulls complete server-sent events (blocks separated by a blank line) out of a growing text buffer. */
export function takeEvents(buffer: string): { events: string[]; rest: string } {
  const parts = buffer.split(/\r?\n\r?\n/);
  const rest = parts.pop() ?? '';
  return { events: parts, rest };
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function useLiveUpdates(): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!isClient()) return;
    let stopped = false;
    let controller: AbortController | null = null;
    let pending: number | undefined;
    const refresh = () => {
      window.clearTimeout(pending);
      pending = window.setTimeout(() => void queryClient.invalidateQueries(), 250);
    };

    async function stream(): Promise<void> {
      controller = new AbortController();
      const headers: Record<string, string> = { Accept: 'text/event-stream' };
      const secret = launchSecret();
      if (secret) headers['X-Launch-Secret'] = secret;
      if (session.token) headers.Authorization = `Bearer ${session.token}`;
      const res = await fetch(`${apiBase()}/api/events`, { headers, signal: controller.signal });
      if (res.status === 503) connection.unreachable();
      if (!res.ok || !res.body) throw new Error('no live stream');
      connection.live();
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return;
        connection.answered();
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = takeEvents(buffer);
        buffer = rest;
        if (events.some((e) => e.includes('"changed"'))) refresh();
      }
    }

    void (async () => {
      while (!stopped) {
        try {
          await stream();
        } catch (error) {
          if (stopped) return;
          if (error instanceof TypeError) connection.unreachable(); // the network itself failed
        }
        if (stopped) return;
        connection.polling();
        await sleep(RETRY_MS);
      }
    })();

    // Without the live stream the screens still catch up, and a PC that lost the Main PC keeps asking.
    const poll = window.setInterval(() => {
      const link = connection.get().link;
      if (link === 'offline') void fetch(`${apiBase()}/api/health`, { headers: { 'X-Launch-Secret': launchSecret() ?? '' } }).then((r) => r.ok && connection.answered()).catch(() => undefined);
      else if (link === 'polling') void queryClient.invalidateQueries();
    }, POLL_MS);

    return () => {
      stopped = true;
      controller?.abort();
      window.clearInterval(poll);
      window.clearTimeout(pending);
    };
  }, [queryClient]);
}
