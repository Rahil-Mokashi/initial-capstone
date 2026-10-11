import { api } from '@/api/client';
import { useGet, useWrite } from '@/api/hooks';
import type { components } from '@/api/schema';

type S = components['schemas'];
export type Supplier = S['SupplierOut'];
export type PurchaseOrder = S['PurchaseOrderOut'];
export type Delivery = S['DeliveryOut'];
export type Invoice = S['InvoiceOut'];
export type Payment = S['PaymentOut'];

const K = 'procurement';
const inv = [K];
const post = <T>(path: string, body: unknown = {}) => api.post<T>(path, body);

export const useSuppliers = () => useGet<Supplier[]>([K, 'suppliers'], '/suppliers');
export const useOrders = () => useGet<PurchaseOrder[]>([K, 'orders'], '/purchase-orders');
export const useOrder = (id: string) =>
  useGet<PurchaseOrder>([K, 'order', id], `/purchase-orders/${id}`);
export const useDeliveries = (poId: string) =>
  useGet<Delivery[]>([K, 'deliveries', poId], `/purchase-orders/${poId}/deliveries`);
export const useDelivery = (id: string) =>
  useGet<Delivery>([K, 'delivery', id], `/deliveries/${id}`);
export const useInvoices = () => useGet<Invoice[]>([K, 'invoices'], '/invoices');
export const useInvoice = (id: string) => useGet<Invoice>([K, 'invoice', id], `/invoices/${id}`);
export const usePayments = (id: string) =>
  useGet<Payment[]>([K, 'payments', id], `/invoices/${id}/payments`);
export const useOrderOptions = () =>
  useGet<S['OrderOptions']>([K, 'order-options'], '/procurement/order-options');
export const useArrivalOptions = () =>
  useGet<S['ArrivalOptions']>([K, 'arrival-options'], '/procurement/arrival-options');

export const useCreateSupplier = () =>
  useWrite((b: S['SupplierIn']) => post<Supplier>('/suppliers', b), inv);
export const useSupplierStatus = () =>
  useWrite(
    (v: { id: string; status: 'active' | 'inactive'; reason: string }) =>
      post<Supplier>(`/suppliers/${v.id}/status`, { status: v.status, reason: v.reason }),
    inv,
  );
export const useCreateOrder = () =>
  useWrite((b: S['PurchaseOrderIn']) => post<PurchaseOrder>('/purchase-orders', b), inv);
export const useCancelOrder = (id: string) =>
  useWrite(
    (reason: string) => post<PurchaseOrder>(`/purchase-orders/${id}/cancel`, { reason }),
    inv,
  );
export const useRecordArrival = (poId: string) =>
  useWrite((b: S['ArrivalIn']) => post<Delivery>(`/purchase-orders/${poId}/deliveries`, b), inv);

export const useDeliveryStep = (id: string) =>
  useWrite(
    (step: {
      path: 'verify-documents' | 'verify-quality' | 'pre-dip' | 'post-dip' | 'reject';
      body?: unknown;
    }) => post<Delivery>(`/deliveries/${id}/${step.path}`, step.body ?? {}),
    // A post-dip changes tank stock too.
    [K, 'tanks'],
  );

export const useCreateInvoice = () =>
  useWrite((b: S['InvoiceIn']) => post<Invoice>('/invoices', b), inv);
export const useRecordPayment = (id: string) =>
  useWrite((b: S['PaymentIn']) => post<Payment>(`/invoices/${id}/payments`, b), inv);
