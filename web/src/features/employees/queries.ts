import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/schema';

type S = components['schemas'];
export type EmployeeRecord = S['EmployeeFull'];
export type EmployeeDocument = S['DocumentOut'];
export type EmployeeStatus = S['StatusIn']['status'];

export const EMPLOYEE_STATUSES: EmployeeStatus[] = [
  'active',
  'on_leave',
  'suspended',
  'terminated',
];

// Everything employee-related starts with 'employees'; one invalidation refreshes every view.
const all = ['employees'] as const;

export const useEmployeeList = () =>
  useQuery({ queryKey: [...all, 'list'], queryFn: () => api.get<EmployeeRecord[]>('/employees') });

export const useEmployee = (id: string) =>
  useQuery({
    queryKey: [...all, 'one', id],
    queryFn: () => api.get<EmployeeRecord>(`/employees/${id}`),
  });

export const useDocuments = (id: string) =>
  useQuery({
    queryKey: [...all, id, 'documents'],
    queryFn: () => api.get<EmployeeDocument[]>(`/employees/${id}/documents`),
  });

function useEmployeeMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: all });
      // The reading dialog on the Tanks screen lists employees too.
      await queryClient.invalidateQueries({ queryKey: ['lookups', 'employees'] });
    },
  });
}

export const useCreateEmployee = () =>
  useEmployeeMutation((body: S['EmployeeCreateIn']) =>
    api.post<EmployeeRecord>('/employees', body),
  );
export const useUpdateEmployee = (id: string) =>
  useEmployeeMutation((body: S['EmployeeUpdateIn']) =>
    api.patch<EmployeeRecord>(`/employees/${id}`, body),
  );
export const useChangeStatus = () =>
  useEmployeeMutation((v: { id: string; status: EmployeeStatus; reason: string }) =>
    api.post<EmployeeRecord>(`/employees/${v.id}/status`, { status: v.status, reason: v.reason }),
  );
export const useRecordExit = (id: string) =>
  useEmployeeMutation((reason: string) =>
    api.post<EmployeeRecord>(`/employees/${id}/exit`, { reason }),
  );
export const useAddDocument = (id: string) =>
  useEmployeeMutation((body: S['DocumentIn']) =>
    api.post<EmployeeDocument>(`/employees/${id}/documents`, body),
  );
export const useRemoveDocument = () =>
  useEmployeeMutation((v: { documentId: string; reason: string }) =>
    api.post<EmployeeDocument>(`/employees/documents/${v.documentId}/remove`, { reason: v.reason }),
  );

export const useEmployeeShortages = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: [...all, id, 'shortages'],
    queryFn: () => api.get<components['schemas']['EmployeeShortageOut'][]>(`/employees/${id}/shortages`),
    enabled,
  });
