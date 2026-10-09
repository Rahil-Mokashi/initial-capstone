// Friendly aliases over the GENERATED schema (npm run api:types). Never hand-write
// response shapes here: if the backend changes, regenerating makes tsc fail.
import type { components } from './schema';

type S = components['schemas'];

export type User = S['UserOut'];
export type LoginResult = S['LoginOut'];
export type Tank = S['TankOut'];
export type TankTransaction = S['TransactionOut'];
export type TankReading = S['ReadingOut'];
export type Reconciliation = S['ReconciliationOut'];
export type Fuel = S['FuelOut'];
export type Employee = S['EmployeeOut'];

export type TankCreateInput = S['TankCreateIn'];
export type TankStatusInput = S['TankStatusIn'];
export type ReadingInput = S['ReadingIn'];
export type TransactionInput = S['TransactionIn'];
export type ReconcileInput = S['ReconcileIn'];

export type TankStatus = S['TankStatus'];
export type TransactionType = TransactionInput['transaction_type'];
