import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { connection } from '@/api/connection';
import { useLiveUpdates } from '@/api/live';
import { session } from '@/api/session';

function Probe() {
  useLiveUpdates();
  return null;
}

function stream(chunks: string[], keepOpen = true) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
        if (!keepOpen) controller.close();
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );
}

beforeEach(() => {
  session.set('tok');
  (window as unknown as { pperp: unknown }).pperp = { mode: 'client', apiBase: '', launchSecret: 's', files: {}, print: {} };
  connection.reset();
});
afterEach(() => {
  delete (window as unknown as { pperp?: unknown }).pperp;
  connection.reset();
  vi.unstubAllGlobals();
});

describe('live updates on a Client PC', () => {
  it('refreshes every open screen when the Main PC says something changed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => stream(['retry: 3000\ndata: {"type":"hello"}\n\n', 'data: {"type":"changed","area":"tanks"}\n\n'])));
    const client = new QueryClient();
    const refresh = vi.spyOn(client, 'invalidateQueries');
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(connection.get().link).toBe('live'));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]! as [string, RequestInit];
    expect(url).toBe('/api/events');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok'); // the stream needs a signed-in person
  });

  it('shows read-only when the network itself fails, and does nothing on a Single PC', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Probe />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(connection.get().link).toBe('offline'));
  });

  it('does not open a stream at all on a Single PC', async () => {
    delete (window as unknown as { pperp?: unknown }).pperp;
    connection.reset();
    const spy = vi.fn();
    vi.stubGlobal('fetch', spy);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Probe />
      </QueryClientProvider>,
    );
    await new Promise((r) => setTimeout(r, 50));
    expect(spy).not.toHaveBeenCalled();
    expect(connection.get().link).toBe('local');
  });
});
