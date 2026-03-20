from typing import List, Optional

from app.clients.tripletex import TripletexClient, TripletexClientError
from app.error_handling import classify_tripletex_error
from app.schemas import ParsedTask, TaskType, ValidateResponse, ValidationCheck


PREFLIGHT_ENFORCED_TASKS = {
    TaskType.CREATE_INVOICE,
    TaskType.CREATE_ORDER,
    TaskType.CREATE_CREDIT_NOTE,
    TaskType.CREATE_PROJECT_BILLING,
    TaskType.CREATE_PAYROLL_VOUCHER,
}


SOLVE_BLOCKING_CODES = {
    "COMPANY_BANK_ACCOUNT_MISSING",
    "CUSTOMER_BANK_ACCOUNT_MISSING",
    "EMPLOYMENT_MISSING_FOR_PERIOD",
    "NOT_SUPPORTED_VIA_AVAILABLE_API",
}


def _operation_name(task: ParsedTask) -> str:
    mapping = {
        TaskType.CREATE_INVOICE: "Opprette faktura",
        TaskType.CREATE_ORDER: "Opprette ordre",
        TaskType.CREATE_CUSTOMER: "Opprette kunde",
        TaskType.CREATE_PAYROLL_VOUCHER: "Kjore lonn",
    }
    task_type = task.task_type
    if isinstance(task_type, str):
        return mapping.get(task_type, task_type)
    return mapping.get(task_type, task_type.value)


def _ok(name: str, message: str, endpoint: Optional[str] = None) -> ValidationCheck:
    return ValidationCheck(name=name, result="OK", code=None, message=message, suggested_action=None, endpoint=endpoint)


def _fail(name: str, code: str, message: str, suggested_action: Optional[str], endpoint: Optional[str]) -> ValidationCheck:
    return ValidationCheck(name=name, result="FAIL", code=code, message=message, suggested_action=suggested_action, endpoint=endpoint)


def _unknown(name: str, message: str, suggested_action: Optional[str] = None, endpoint: Optional[str] = None) -> ValidationCheck:
    return ValidationCheck(name=name, result="UNKNOWN", code=None, message=message, suggested_action=suggested_action, endpoint=endpoint)


def _resolve_customer(client: TripletexClient, task: ParsedTask):
    customer = task.related_entities.get("customer", {})
    if not customer:
        return None
    match_fields = {}
    if customer.get("email"):
        match_fields["email"] = customer["email"]
    elif customer.get("organizationNumber"):
        match_fields["organizationNumber"] = customer["organizationNumber"]
    elif customer.get("name"):
        match_fields["name"] = customer["name"]
    if not match_fields:
        return None
    return client.find_single("customer", match_fields, fields="id,name,email,organizationNumber,bankAccountNumber,*")


def _resolve_employee(client: TripletexClient, task: ParsedTask):
    employee = task.related_entities.get("employee", {})
    if not employee:
        return None
    match_fields = {}
    if employee.get("email"):
        match_fields["email"] = employee["email"]
    elif employee.get("first_name"):
        match_fields["first_name"] = employee["first_name"]
        if employee.get("last_name"):
            match_fields["last_name"] = employee["last_name"]
    if not match_fields:
        return None
    return client.find_single("employee", match_fields, fields="id,firstName,lastName,email,employments,*")


def validate_preflight(client: TripletexClient, task: ParsedTask) -> ValidateResponse:
    checks: List[ValidationCheck] = []
    can_continue = True

    try:
        if task.task_type in {TaskType.CREATE_INVOICE, TaskType.CREATE_ORDER, TaskType.CREATE_PROJECT_BILLING, TaskType.CREATE_CREDIT_NOTE}:
            customer = task.related_entities.get("customer", {})
            if customer:
                resolved_customer = _resolve_customer(client, task)
                if resolved_customer is None:
                    checks.append(_fail("customer_exists", "CUSTOMER_NOT_FOUND", "Kunden finnes ikke i Tripletex.", "POST /customer", "/customer"))
                    can_continue = False
                else:
                    checks.append(_ok("customer_exists", "Kunden finnes i Tripletex.", "/customer"))
                    bank_account = resolved_customer.get("bankAccountNumber") or resolved_customer.get("bankAccount")
                    if bank_account:
                        checks.append(_ok("customer_bank_account", "Kundens bankkonto er registrert.", "/customer"))
                    else:
                        checks.append(_fail("customer_bank_account", "CUSTOMER_BANK_ACCOUNT_MISSING", "Kunden finnes, men mangler bankkonto.", "PUT /customer/{id}", "/customer"))
                        can_continue = False

            needs_ledger_lookup = (
                task.task_type == TaskType.CREATE_INVOICE
                and not any(key.startswith("order_line_") for key in task.related_entities)
                and not task.related_entities.get("product", {}).get("id")
                and not task.related_entities.get("product", {}).get("name")
            )
            if needs_ledger_lookup:
                account_number = task.fields.get("accountNumber")
                if not account_number:
                    checks.append(_fail("ledger_account", "LEDGER_ACCOUNT_MISSING", "Hovedbokskonto mangler eller kan ikke bekreftes.", "GET /ledger/account for oppslag", "/ledger/account"))
                    can_continue = False
                else:
                    account = client.find_single("ledger/account", {"number": str(account_number)}, fields="id,number,name")
                    if account is None:
                        checks.append(_fail("ledger_account", "LEDGER_ACCOUNT_MISSING", "Oppgitt hovedbokskonto ble ikke funnet.", "GET /ledger/account for oppslag", "/ledger/account"))
                        can_continue = False
                    else:
                        checks.append(_ok("ledger_account", "Hovedbokskonto er bekreftet.", "/ledger/account"))

        if task.task_type == TaskType.CREATE_PAYROLL_VOUCHER:
            employee = _resolve_employee(client, task)
            if employee is None:
                checks.append(_unknown("employee", "Ansatt kan ikke bekreftes fra tilgjengelige data.", None, "/employee"))
                can_continue = False
            elif employee.get("employments"):
                checks.append(_ok("employment_for_period", "Ansatt har ansettelsesforhold registrert.", "/employee"))
            else:
                checks.append(_fail("employment_for_period", "EMPLOYMENT_MISSING_FOR_PERIOD", "Ansatt mangler gyldig ansettelsesforhold for perioden.", None, None))
                can_continue = False
    except TripletexClientError as exc:
        classified = classify_tripletex_error(str(exc))
        if classified.category.value == "validation_environment":
            checks.append(
                _fail(
                    "company_bank_account",
                    "COMPANY_BANK_ACCOUNT_MISSING",
                    "Selskapet mangler bankkonto. Dette ma normalt registreres i Tripletex UI.",
                    "NOT_SUPPORTED_VIA_AVAILABLE_API",
                    None,
                )
            )
        else:
            checks.append(_unknown("api_lookup", "Preflight-oppslag kunne ikke fullfores: {0}".format(str(exc)), None, None))
        can_continue = False

    if not checks:
        checks.append(_unknown("preconditions", "Ingen eksplisitte preflight-regler traff denne operasjonen.", None, None))

    if any(check.code == "CUSTOMER_NOT_FOUND" for check in checks):
        summary = "Kunde mangler og ma opprettes for operasjonen kan fortsette."
    elif any(check.code == "LEDGER_ACCOUNT_MISSING" for check in checks):
        summary = "Hovedbokskonto mangler eller kan ikke bekreftes."
    elif any(check.code == "CUSTOMER_BANK_ACCOUNT_MISSING" for check in checks):
        summary = "Kunden mangler bankkonto."
    elif any(check.code == "COMPANY_BANK_ACCOUNT_MISSING" for check in checks):
        summary = "Selskapet mangler bankkonto, og dette kan ikke loses via tilgjengelige API-endepunkter."
    elif any(check.code == "EMPLOYMENT_MISSING_FOR_PERIOD" for check in checks):
        summary = "Lonn kan ikke kjares uten gyldig ansettelsesforhold."
    elif any(check.result == "UNKNOWN" for check in checks):
        summary = "Minst en forutsetning kunne ikke bekreftes."
    else:
        summary = "Ingen preflight-avvik funnet."

    return ValidateResponse(
        status="OK" if can_continue and all(check.result != "FAIL" for check in checks) else "AVVIK",
        operation=_operation_name(task),
        checks=checks,
        summary=summary,
        can_continue=can_continue,
    )
