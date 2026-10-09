import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type {
  Employee,
  Fuel,
  ReadingInput,
  Reconciliation,
  ReconcileInput,
  Tank,
  TankCreateInput,
  TankReading,
  TankStatusInput,
  TankTransaction,
  TransactionInput,
} from '@/api/types';

// Every key starts with 'tanks' so one invalidation refreshes every view of tank data.
export const keys = {
  all: ['tanks'] as const,
  list: ['tanks', 'list'] as const,
  one: (id: string) => ['tanks', 'one', id] as const,
  recent: ['tanks', 'recent'] as const,
  transactions: (id: string) => ['tanks', id, 'transactions'] as const,
  readings: (id: string) => ['tanks', id, 'readings'] as const,
  reconciliations: (id: string) => ['tanks', id, 'reconciliations'] as const,
};

export const RECENT_SHOWN = 8;

export const useTanks = () =>
  useQuery({ queryKey: keys.list, queryFn: () => api.get<Tank[]>('/tanks') });
export const useTank = (id: string) =>
  useQuery({ queryKey: keys.one(id), queryFn: () => api.get<Tank>(`/tanks/${id}`) });
export const useRecentTransactions = () =>
  useQuery({
    queryKey: keys.recent,
    queryFn: () => api.get<TankTransaction[]>(`/tanks/recent-transactions?limit=${RECENT_SHOWN}`),
  });
export const useTransactions = (id: string) =>
  useQuery({
    queryKey: keys.transactions(id),
    queryFn: () => api.get<TankTransaction[]>(`/tanks/${id}/transactions`),
  });
export const useReadings = (id: string) =>
  useQuery({
    queryKey: keys.readings(id),
    queryFn: () => api.get<TankReading[]>(`/tanks/${id}/readings`),
  });
export const useReconciliations = (id: string) =>
  useQuery({
    queryKey: keys.reconciliations(id),
    queryFn: () => api.get<Reconciliation[]>(`/tanks/${id}/reconciliations`),
  });

export const useFuels = (enabled: boolean) =>
  useQuery({
    queryKey: ['lookups', 'fuels'],
    queryFn: () => api.get<Fuel[]>('/lookups/fuels'),
    enabled,
  });
export const useEmployees = (enabled: boolean) =>
  useQuery({
    queryKey: ['lookups', 'employees'],
    queryFn: () => api.get<Employee[]>('/lookups/employees'),
    enabled,
  });

function useTankMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  });
}

export const useCreateTank = () =>
  useTankMutation((body: TankCreateInput) => api.post<Tank>('/tanks', body));
export const useSetStatus = (id: string) =>
  useTankMutation((body: TankStatusInput) => api.post<Tank>(`/tanks/${id}/status`, body));
export const useRecordTransaction = (id: string) =>
  useTankMutation((body: TransactionInput) =>
    api.post<TankTransaction>(`/tanks/${id}/transactions`, body),
  );
export const useRecordReading = (id: string) =>
  useTankMutation((body: ReadingInput) => api.post<TankReading>(`/tanks/${id}/readings`, body));
export const useReconcile = (id: string) =>
  useTankMutation((body: ReconcileInput) =>
    api.post<Reconciliation>(`/tanks/${id}/reconciliations`, body),
  );
