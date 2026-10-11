import { api } from '@/api/client';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';

type S = components['schemas'];
export type Shift = S['ShiftOut'];
export type Assignment = S['AssignmentOut'];
export type MyShift = S['MyShiftOut'];

const K = 'shifts';
const post = <T>(path: string, body: unknown = {}) => api.post<T>(path, body);

export const useShifts = () => useGet<Shift[]>([K, 'list'], '/shifts');
export const useShift = (id: string) => useGet<Shift>([K, 'one', id], `/shifts/${id}`);
export const useAssignments = (id: string) =>
  useGet<Assignment[]>([K, 'assignments', id], `/shifts/${id}/assignments`);
export const useAssignOptions = () =>
  useGet<S['AssignOptions']>([K, 'assign-options'], '/shifts/assign-options');
export const useMyShift = () => useGet<MyShift | null>([K, 'mine'], '/shifts/mine');

// Shift changes also move sales, readings and stock, so refresh the neighbours too.
const inv = [K, 'tanks'];
export const useOpenShift = () => useWrite((b: S['OpenShiftIn']) => post<Shift>('/shifts', b), inv);
export const useCloseShift = (id: string) =>
  useWrite(() => post<Shift>(`/shifts/${id}/close`), inv);
export const useReopenShift = (id: string) =>
  useWrite((reason: string) => post<Shift>(`/shifts/${id}/reopen`, { reason }), inv);
export const useAssignNozzle = (shiftId: string) =>
  useWrite((b: S['AssignIn']) => post<Assignment>(`/shifts/${shiftId}/assignments`, b), inv);
export const useCompleteAssignment = () =>
  useWrite(
    (v: { id: string; body: S['CompleteIn'] }) =>
      post<Assignment>(`/shift-assignments/${v.id}/complete`, v.body),
    inv,
  );
export const useCancelAssignment = () =>
  useWrite(
    (v: { id: string; reason: string }) =>
      post<Assignment>(`/shift-assignments/${v.id}/cancel`, { reason: v.reason }),
    inv,
  );
