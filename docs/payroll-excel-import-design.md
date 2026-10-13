# Payroll Excel import: design only (deferred, U-02)

The separate accounts person keeps salaries in Excel today. The real files have not been seen, so nothing is imported
yet and no layout is guessed. When the files arrive, the import follows the bank statement import exactly:

1. **Read** the .xlsx (`app/services/bank_parsing.read_table` already reads CSV and XLSX with a header line anywhere).
2. **Column mapping step**: the person points at the header line and says which column is employee code/name, monthly
   salary, advance given, advance recovered, deductions. A layout can be saved per file type (like `BankImportProfile`).
3. **Preview, store nothing**: rows read, employees not found by code/name, amounts that cannot be read, totals.
4. **Import** only into new records (`SalarySetup`, `EmployeeAdvance`); never overwrite a payroll run. Duplicates are
   skipped by a row hash. Every import is audit-logged.
5. **Tally**: after import the payroll checks (advances given = recovered + outstanding, register totals) show whether
   the Excel history agrees with what the app computes.
Open: U-02 (the files), how the historical advances should be opened (as of which date).
