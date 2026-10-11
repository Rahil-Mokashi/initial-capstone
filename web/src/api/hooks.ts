import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { api } from './client';

/** GET a path; `key` starts with the feature name so one invalidation refreshes everything in it. */
export const useGet = <T>(key: QueryKey, path: string, enabled = true, refetchMs?: number) =>
  useQuery({
    queryKey: key,
    queryFn: () => api.get<T>(path),
    enabled,
    refetchInterval: refetchMs,
  });

/**
 * A write that, on success, refreshes every query whose key starts with one of `invalidate`.
 * `send` does the actual call (POST/PATCH...), so each hook states its endpoint in one line.
 */
export function useWrite<TVars, TResult = unknown>(
  send: (vars: TVars) => Promise<TResult>,
  invalidate: string[],
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSuccess: async () => {
      await Promise.all(invalidate.map((k) => queryClient.invalidateQueries({ queryKey: [k] })));
    },
  });
}
