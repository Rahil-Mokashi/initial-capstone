import { api } from '@/api/client';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';

type S = components['schemas'];
export type Sale = S['SaleOut'];
export type SalePage = S['SalePage'];
export type Customer = S['CustomerOut'];
export type FuelRevenue = S['FuelRevenue'];
export type SaleOptions = S['SaleOptions'];

export const PAGE_SIZE = 50;
const K = 'sales';
const post = <T>(path: string, body: unknown = {}) => api.post<T>(path, body);

export const useSalesPage = (page: number) =>
  useGet<SalePage>([K, 'page', page], `/sales?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`);
export const useTodayByFuel = () => useGet<FuelRevenue[]>([K, 'today'], '/sales/today-by-fuel');
export const useSaleOptions = () => useGet<SaleOptions>([K, 'options'], '/sales/options');
export const useCustomers = () => useGet<Customer[]>([K, 'customers'], '/customers');

// A sale moves tank stock and credit balances, so refresh those lists too.
const inv = [K, 'tanks', 'credit'];
export const useCreateSale = () => useWrite((b: S['SaleIn']) => post<Sale>('/sales', b), inv);
export const useCreateMySale = () =>
  useWrite((b: S['SelfSaleIn']) => post<Sale>('/sales/mine', b), inv);
export const useCancelSale = () =>
  useWrite(
    (v: { id: string; reason: string }) =>
      post<Sale>(`/sales/${v.id}/cancel`, { reason: v.reason }),
    inv,
  );
export const usePaymentAction = () =>
  useWrite(
    (v: { id: string; action: 'mark-failed' | 'refund'; reason: string }) =>
      post(`/payments/${v.id}/${v.action}`, { reason: v.reason }),
    inv,
  );
export const useCreateCustomer = () =>
  useWrite((b: S['CustomerIn']) => post<Customer>('/customers', b), [K, 'credit']);
export const useCustomerStatus = () =>
  useWrite(
    (v: { id: string; status: 'active' | 'inactive'; reason: string }) =>
      post<Customer>(`/customers/${v.id}/status`, { status: v.status, reason: v.reason }),
    [K, 'credit'],
  );
export const getReceiptHtml = async (id: string) =>
  (await api.get<S['ReceiptOut']>(`/sales/${id}/receipt`)).html;
