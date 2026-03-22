# Tripletex API Endpoint Reference

## POST /employee
Create an employee. Required: firstName, lastName. Optional: email, dateOfBirth, startDate (defaults to today), userType (STANDARD/EXTENDED/NO_ACCESS), department:{id}, phoneNumberMobile. The startDate field is required by Tripletex — always default to today if not provided.

## PUT /employee/{id}
Update an existing employee. Must GET the employee first to find their ID. Common updates: phoneNumberMobile, email.

## GET /employee
List or search employees. Use ?email=X&firstName=Y&lastName=Z to search. Returns {fullResultSize, values: [...]}.

## POST /customer
Create a customer or supplier. Fields: name (required), email, isCustomer (default true), isSupplier (default false), organizationNumber, phoneNumber. For suppliers, set isSupplier=true, isCustomer=false.

## PUT /customer/{id}
Update existing customer. Must GET first to find ID.

## POST /product
Create a product. Fields: name (required), priceExcludingVatCurrency, productNumber, vatPercentage.

## POST /project
Create a project. Fields: name (required), startDate (required), customer:{id}, projectManager:{id}. The projectManager must be an existing employee with active employment.

## POST /department
Create a department. Fields: name (required), departmentNumber (optional).

## POST /order
Create an order. Fields: customer:{id} (required), orderDate, deliveryDate, orderLines:[{description, count, product:{id}}]. At least one order line is required.

## POST /invoice
Create an invoice from an order. Fields: invoiceDate, invoiceDueDate, customer:{id}, orders:[{id}]. IMPORTANT: Requires company bank account to exist. Returns 422 "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer" if no bank account.

## PUT /invoice/{id}/:payment
Register or reverse a payment on an invoice. Uses query parameters (NOT JSON body): paymentDate, paidAmount, paidAmountCurrency, paymentTypeId (6=bank). For reversal, paidAmount is negative. Returns 404 if amount doesn't match the actual payment — try multiple amounts.

## POST /incomingInvoice
Create a supplier/vendor invoice. MUST use invoiceHeader wrapper: {invoiceHeader: {invoiceDate, invoiceNumber, vendorId, invoiceAmount, dueDate}, orderLines: [{amountInclVat, externalId, accountId}]}. CRITICAL: orderLines do NOT accept vatType or vatPercentage — VAT is derived from the account number.

## POST /travelExpense
Create a travel expense report. Fields: employee:{id} (required), title, departureDate, returnDate. Cost lines are added separately via POST /travelExpense/cost.

## POST /ledger/voucher
Create a journal voucher. Postings must use account:{id} (resolved via GET /ledger/account), NOT account:{number} or account:{name}. System-generated accounts reject number-based references.

## GET /ledger/account
Look up chart of accounts. Use ?number=NNNN to find by account number. Returns the account ID needed for voucher postings.

## DELETE /ledger/voucher/{id}
Delete a voucher by ID.

## POST /company/bankAccount
Create a company bank account. May return 405 Method Not Allowed on some proxies. Fallback: PUT /company/{id} with bankAccountNumber field.

## POST /activity
Create a project activity. Fields: name (required), number (optional).

## POST /timesheet/entry
Register time on a project. Fields: employee:{id}, project:{id}, activity:{id}, date, hours.
