# Tripletex API Error Patterns and Resolutions

## 422 "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer"
Invoice requires company bank account. Resolution: Auto-create bank account via POST /company/bankAccount or PUT /company/{id} with bankAccountNumber, then retry invoice creation.

## 422 "vatType: Feltet eksisterer ikke i objektet"
The vatType field is not valid on incomingInvoice orderLines. Resolution: Remove vatType from the orderLines. VAT is derived automatically from the account number.

## 422 "invoiceDate: Feltet eksisterer ikke i objektet" on incomingInvoice
Using flat payload structure instead of invoiceHeader wrapper. Resolution: Wrap invoiceDate, vendorId, invoiceNumber, invoiceAmount, dueDate inside an invoiceHeader object.

## 422 "Systemgenererte posteringer kan ikke endres"
Voucher postings using account number/name references for system accounts. Resolution: Resolve account IDs via GET /ledger/account?number=NNNN and use {id: accountId} in postings.

## 404 on PUT /invoice/{id}/:payment
Payment amount doesn't match. Resolution: Try multiple amounts — invoice total (incl. VAT), amountExcludingVat, amountOutstanding, and derived payment (total - outstanding). Also ensure company bank account exists.

## 405 Method Not Allowed on POST /company/bankAccount
The proxy doesn't support this endpoint. Resolution: Try PUT /company/{id} with bankAccountNumber field as fallback. First GET /company to find the company ID.

## 405 Method Not Allowed on GET /incomingInvoice
The proxy may not support listing incoming invoices. Resolution: Handle gracefully with try/except and proceed without supplier invoice matching.

## 422 "Validering feilet" on project creation without projectManager
Project requires a project manager. Resolution: Resolve employee by email/name, or fall back to any existing employee in the system.

## 422 "Project billing requires billable amount"
Validator blocking because amount field is missing. Resolution: Use budget or fixedPriceAmountCurrency or budgetAmount as fallback for amount.

## 400 on supplier creation with organizationNumber format error
Organization number must be exactly 9 digits. Resolution: Strip all non-digit characters and validate length before sending.

## 422 duplicate customer/supplier
Customer or supplier already exists with that organization number. Resolution: Search first with GET /customer?organizationNumber=X, use existing ID if found.

## 404 on employee search
No employee found matching search criteria. Resolution: Create the employee if sufficient information (firstName, lastName, email) is available.

## General retry strategy
On first attempt failure, re-parse with higher LLM thinking level. Use error context from KB gotchas to guide the retry. Remove forbidden fields from payload before retrying.
