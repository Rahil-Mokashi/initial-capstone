import { api } from '@/api/client';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';

type S = components['schemas'];
export type UserRecord = S['UserRow'];
export type Role = S['RoleOut'];

export const useUsers = () => useGet<UserRecord[]>(['users', 'list'], '/users');
export const useRoles = () => useGet<Role[]>(['users', 'roles'], '/users/roles');

const post = <T>(path: string, body: unknown) => api.post<T>(path, body);
const inv = ['users'];

export const useCreateUser = () =>
  useWrite((body: S['UserCreateIn']) => post<UserRecord>('/users', body), inv);
export const useChangeRole = (id: string) =>
  useWrite((body: S['ChangeRoleIn']) => post<UserRecord>(`/users/${id}/role`, body), inv);
export const useSetActive = (id: string) =>
  useWrite((body: S['ActiveIn']) => post<UserRecord>(`/users/${id}/active`, body), inv);
export const useUnlock = (id: string) =>
  useWrite((reason: string) => post<UserRecord>(`/users/${id}/unlock`, { reason }), inv);
export const useResetPassword = (id: string) =>
  useWrite(
    (body: S['ResetPasswordIn']) => post<UserRecord>(`/users/${id}/reset-password`, body),
    inv,
  );
export const useResetCode = (id: string) =>
  useWrite((reason: string) => post<S['ResetCodeOut']>(`/users/${id}/reset-code`, { reason }), inv);
