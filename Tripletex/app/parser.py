import re
import unicodedata
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from app.llm_parser import parse_prompt_with_llm
from app.schemas import ParsedTask, TaskType


EMAIL_RE = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+")
PHONE_RE = re.compile(
    r"((?:\+\d{1,3}\s?)?(?:\d[\s-]?){8,15}\d)"
)
NUMBER_RE = re.compile(r"(\d+(?:[.,]\d{1,2})?)")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
QUOTED_RE = re.compile(r"['\"]([^'\"]+)['\"]")

CREATE_WORDS = [
    "opprett",
    "registrer",
    "lag",
    "create",
    "crea",
    "crear",
    "criar",
    "crie",
    "cree",
    "erstellen",
    "creer",
    "créez",
    "creez",
    "envia",
    "envía",
    "registre",
    "registrieren",
    "anlegen",
    "legen sie",
]
UPDATE_WORDS = ["oppdater", "endre", "set", "update", "actualizar", "aktualisieren", "mettre"]
DELETE_WORDS = ["slett", "fjern", "delete", "remove", "borrar", "excluir", "loschen", "supprimer"]
READ_WORDS = ["hent", "list", "liste", "finn", "find", "show", "vis", "search", "sok", "søk", "buscar", "chercher"]

ENTITY_KEYWORDS = {
    "employee": ["ansatt", "employee", "empleado", "funcionario", "mitarbeiter", "employe", "tilsett", "tilsatt"],
    "customer": ["kunde", "customer", "cliente", "kund", "client"],
    "product": ["produkt", "product", "producto", "produto"],
    "project": ["prosjekt", "project", "proyecto", "projeto", "projekt", "projet"],
    "department": ["avdeling", "department", "departamento", "abteilung", "departement"],
    "invoice": ["faktura", "invoice", "factura", "fatura", "rechnung", "facture"],
    "order": ["ordre", "order", "pedido", "bestellung", "commande"],
    "travel_expense": ["reiseregning", "travel expense", "expense report", "viagem", "spesen"],
    "voucher": ["bilag", "voucher", "comprobante", "buchung"],
    "ledger_account": ["kontoplan", "ledger account", "chart of accounts", "konti"],
    "ledger_posting": ["hovedboksposteringer", "ledger posting", "postering", "postings", "hovedbok"],
}

ROLE_MAP = {
    "kontoadministrator": "ACCOUNT_MANAGER",
    "account administrator": "ACCOUNT_MANAGER",
    "account manager": "ACCOUNT_MANAGER",
}

MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

SEND_INVOICE_TOKENS = [
    "send",
    "sende",
    "senda",
    "envoy",
    "envoyer",
    "envia",
    "envía",
    "senden",
    "versenden",
]

PAYMENT_TOKENS = [
    "register full payment",
    "full payment",
    "payment on this invoice",
    "paid in full",
    "settle this invoice",
    "registe o pagamento",
    "registar o pagamento",
    "pagamento total",
    "pagamento completo",
    "pagamento",
    "registre le paiement",
    "paiement total",
    "paiement complet",
    "registrer full betaling",
    "registrer betaling",
    "betaling",
    "registre el pago",
    "pago completo",
    "pago total",
    "zahlung",
    "vollstandige zahlung",
    "vollstÃ¤ndige zahlung",
    "bezahlen",
]


def _today_iso() -> str:
    return date.today().isoformat()


def _language_hint(prompt: str) -> str:
    lowered = _normalized_text(prompt)
    if any(word in lowered for word in ["opprett", "ansatt", "kunde", "reiseregning", "avdeling"]):
        return "nb"
    if any(word in lowered for word in ["create", "employee", "customer", "travel expense"]):
        return "en"
    if any(word in lowered for word in ["crear", "cliente", "factura"]):
        return "es"
    if any(word in lowered for word in ["criar", "cliente", "fatura"]):
        return "pt"
    if any(word in lowered for word in ["erstellen", "kunde", "rechnung"]):
        return "de"
    if any(word in lowered for word in ["creer", "client", "facture"]):
        return "fr"
    return "unknown"


def _contains_any(text: str, options: List[str]) -> bool:
    return any(option in text for option in options)


def _contains_send_invoice_intent(text: str) -> bool:
    return _contains_any(text, SEND_INVOICE_TOKENS)


def _contains_payment_intent(text: str) -> bool:
    return _contains_any(text, PAYMENT_TOKENS)


def _normalized_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def _repair_mojibake(text: str) -> str:
    repaired = text
    for _ in range(3):
        if "Ã" not in repaired and "Â" not in repaired:
            break
        try:
            candidate = repaired.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if not candidate or candidate == repaired:
            break
        repaired = candidate
    return repaired


def _detect_action(lowered: str) -> Optional[str]:
    if _contains_any(lowered, CREATE_WORDS):
        return "create"
    if _contains_any(lowered, UPDATE_WORDS):
        return "update"
    if _contains_any(lowered, DELETE_WORDS):
        return "delete"
    if _contains_any(lowered, READ_WORDS):
        return "read"
    return None


def _detect_entity(lowered: str) -> Optional[str]:
    priority = [
        "invoice",
        "order",
        "travel_expense",
        "voucher",
        "ledger_posting",
        "ledger_account",
        "employee",
        "customer",
        "product",
        "project",
        "department",
    ]
    for entity in priority:
        keywords = ENTITY_KEYWORDS[entity]
        if _contains_any(lowered, keywords):
            return entity
    return None


def _first_match(regex: re.Pattern, text: str) -> Optional[str]:
    match = regex.search(text)
    if match:
        return match.group(1) if match.lastindex else match.group(0)
    return None


def _clean_name(value: str) -> str:
    for marker in [" (org no", " (org.nr", " med ", " with ", " som ", " for ", " linked to ", " knyttet til ", ",", "."]:
        if marker in value:
            value = value.split(marker, 1)[0]
    return value.strip(" .,:;")


def _extract_named_entity(prompt: str, keywords: List[str]) -> Optional[str]:
    keyword_pattern = "|".join(re.escape(keyword) for keyword in keywords)

    quoted_pattern = re.compile(r"(?:{0})[^\n\"']*['\"]([^'\"]+)['\"]".format(keyword_pattern), re.IGNORECASE)
    quoted_match = quoted_pattern.search(prompt)
    if quoted_match:
        return _clean_name(quoted_match.group(1))

    plain_pattern = re.compile(
        r"(?:{0})(?:\s+(?:med|named|name|kalt|called|for))?\s+([A-ZÆØÅÉÜÖÄ][^,\.\n]+)".format(keyword_pattern),
        re.IGNORECASE,
    )
    plain_match = plain_pattern.search(prompt)
    if plain_match:
        return _clean_name(plain_match.group(1))

    return None


def _extract_project_manager_name(prompt: str) -> Optional[str]:
    alt_match = re.search(
        r"(?:director del proyecto|gerente de projeto)\s+(?:(?:es|e|é)\s+)?([A-Z][\w.\-]+(?:\s+[A-Z][\w.\-]+)+)",
        prompt,
        re.IGNORECASE,
    )
    if alt_match:
        return _clean_name(alt_match.group(1))
    match = re.search(
        r"(?:project manager|prosjektleder)\s+(?:is\s+)?([A-ZÆØÅ][\wÆØÅæøå.\-]+(?:\s+[A-ZÆØÅ][\wÆØÅæøå.\-]+)+)",
        prompt,
        re.IGNORECASE,
    )
    if match:
        return _clean_name(match.group(1))
    return None


def _split_person_name(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not name:
        return None, None
    parts = name.split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def _extract_project_manager_name_v2(prompt: str) -> Optional[str]:
    alt_pattern = r"(?:director del proyecto|gerente de projeto)\s+(?:(?:es|e|é)\s+)?([A-Z][\w.\-]+(?:\s+[A-Z][\w.\-]+)+)"
    alt_match = re.search(alt_pattern, prompt, re.IGNORECASE)
    if alt_match:
        return _clean_name(alt_match.group(1))
    pattern = r"(?:project manager|prosjektleder)\s+(?:(?:is|er)\s+)?([A-Z][\w.\-]+(?:\s+[A-Z][\w.\-]+)+)"
    match = re.search(pattern, prompt, re.IGNORECASE)
    if match:
        return _clean_name(match.group(1))
    return _extract_project_manager_name(prompt)


def _extract_project_manager_name_safe(prompt: str) -> Optional[str]:
    patterns = [
        r"(?:director del proyecto|gerente de projeto)\s+(?:is\s+|es\s+|er\s+|e\s+)?([^(\n.]+)",
        r"(?:project manager|prosjektleder)\s+(?:is\s+|er\s+)?([^(\n.]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            candidate = _clean_name(match.group(1))
            if candidate:
                return candidate
    return _extract_project_manager_name_v2(prompt)


def _extract_project_customer_name(prompt: str) -> Optional[str]:
    alt_match = re.search(r"(?:vinculado al cliente|vinculado ao cliente)\s+([A-Z][^,(.\n]+)", prompt, re.IGNORECASE)
    if alt_match:
        return _clean_name(alt_match.group(1))
    french_match = re.search(r"(?:au client)\s+([^,(.\n][^,(.\n]+)", prompt, re.IGNORECASE)
    if french_match:
        return _clean_name(french_match.group(1))
    patterns = [
        r"(?:linked to the customer|for kunde|for kunden|knyttet til kunden|knyttet til kunde)\s+([A-ZÆØÅÉÜÖÄ][^,(.\n]+)",
        r"(?:customer|kunde|kunden|client|cliente)\s+([A-ZÆØÅÉÜÖÄ][^,(.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return _clean_name(match.group(1))
    return _extract_named_entity(prompt, ["kunde", "kunden", "customer", "cliente", "client"])


def _extract_amount(prompt: str) -> Optional[float]:
    currency_match = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*(?:nok|kr)\b", prompt, re.IGNORECASE)
    amount = currency_match.group(1) if currency_match else _first_match(NUMBER_RE, prompt)
    if amount is None:
        return None
    return float(amount.replace(",", "."))


def _extract_common_fields(prompt: str) -> Dict[str, object]:
    fields = {}
    email = _first_match(EMAIL_RE, prompt)
    date = _first_match(DATE_RE, prompt)
    phone_match = None
    if any(keyword in prompt.lower() for keyword in ["telefon", "phone", "mobil", "mobile"]):
        phone_match = PHONE_RE.search(prompt)
    if email:
        fields["email"] = email
    if phone_match:
        fields["phone"] = phone_match.group(1).replace(" ", "")
    if date:
        fields["date"] = date
    return fields


def _extract_numeric_id(prompt: str) -> Optional[int]:
    amount = _extract_amount(prompt)
    if amount is None:
        return None
    if amount.is_integer():
        return int(amount)
    return None


def _extract_invoice_entities(prompt: str) -> Dict[str, Dict[str, object]]:
    related_entities = {}
    customer_name = _extract_project_customer_name(prompt)
    product_name = _extract_named_entity(prompt, ["produkt", "product", "producto", "produto"])
    if customer_name:
        related_entities["customer"] = {"name": customer_name, "isCustomer": True}
        org_number = _extract_org_number(prompt)
        if org_number:
            related_entities["customer"]["organizationNumber"] = org_number
    if product_name:
        related_entities["product"] = {"name": product_name}
    return related_entities


def _extract_org_number(prompt: str) -> Optional[str]:
    match = re.search(
        r"(?:organization number|organisasjonsnummer|org(?:anization)?\.?\s*(?:no\.?|n\S?\.?)|org[\.\-\s]*nr\.?|numero de organizacao|numero de organizac?ao|numero d'organisation|numero dorganisation|num[eé]ro d'organisation|num[eé]ro dorganisation|n\S?\s*org\.?)\s*(\d{9})",
        prompt,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def _extract_textual_dates(prompt: str) -> List[str]:
    matches = re.findall(r"(\d{1,2})\.\s*([A-Za-z]+)\s+(\d{4})", prompt)
    dates: List[str] = []
    for day, month_name, year in matches:
        month = MONTH_MAP.get(month_name.lower())
        if not month:
            continue
        try:
            parsed = datetime(int(year), month, int(day))
        except ValueError:
            continue
        dates.append(parsed.strftime("%Y-%m-%d"))
    return dates


def _extract_address_fields(prompt: str) -> Dict[str, str]:
    patterns = [
        r"(?:addressen er|adressa er|o endere[cç]o [ée]|l'adresse est|adresse ist|address is)\s+([^,.\n]+),\s*(\d{4})\s+([A-Za-zÆØÅæøåÉéÜüÖöÄä\- ]+)",
        r"(?:adresse|address)\s*:\s*([^,.\n]+),\s*(\d{4})\s+([A-Za-zÆØÅæøåÉéÜüÖöÄä\- ]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return {
                "addressStreet": match.group(1).strip(),
                "postalCode": match.group(2).strip(),
                "city": match.group(3).strip(" ."),
                "country": "NO",
            }
    return {}


def _extract_employee_name(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    patterns = [
        r"(?:navn|named|called|chamado|namens|heiter|heter)\s+([A-ZÆØÅ][\wÆØÅæøå.\-]+(?:\s+[A-ZÆØÅ][\wÆØÅæøå.\-]+)+)",
        r"(?:employee|ansatt|funcion[aá]rio|mitarbeiter|tilsett|employ[ée])(?:\s+med\s+navn)?\s+([A-ZÆØÅ][\wÆØÅæøå.\-]+(?:\s+[A-ZÆØÅ][\wÆØÅæøå.\-]+)+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return _split_person_name(_clean_name(match.group(1)))
    return None, None


def _extract_employee_number(prompt: str) -> Optional[str]:
    match = re.search(
        r"(?:employee|ansatt|tilsett|mitarbeiter|funcion[aá]rio)[^@\n]*?\b(\d{8,12})\b",
        prompt,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    standalone = re.findall(r"\b\d{8,12}\b", prompt)
    return standalone[0] if standalone else None


def _extract_customer_name(prompt: str) -> Optional[str]:
    customer_name = _extract_project_customer_name(prompt)
    if customer_name:
        return customer_name
    supplier_patterns = [
        r"(?:leverand[^\s]*|supplier|vendor|fornecedor|fournisseur|lieferanten?)\s+([A-ZÆØÅÉÜÖÄ][^,.\n]+)",
    ]
    for pattern in supplier_patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return _clean_name(match.group(1))
    return None


def _extract_product_number(prompt: str) -> Optional[str]:
    match = re.search(r"(?:produktnummer|product number|n[uú]mero de producto|numero do produto)\s+(\d+)", prompt, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _extract_vat_percentage(prompt: str) -> Optional[float]:
    match = re.search(r"(\d{1,2}(?:[.,]\d+)?)\s*%", prompt)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _extract_department_names(prompt: str) -> List[str]:
    names = [name.strip() for name in QUOTED_RE.findall(prompt) if name.strip()]
    if names:
        return names
    name = _extract_named_entity(prompt, ["avdeling", "department", "departamento", "abteilung"])
    return [name] if name else []


def _extract_invoice_description(prompt: str) -> Optional[str]:
    quoted = QUOTED_RE.findall(prompt)
    if quoted:
        return quoted[-1].strip()
    nynorsk_match = re.search(r"(?:gjeld)\s+([A-ZÃ†Ã˜Ã…Ã‰][^.\n]+)", prompt, re.IGNORECASE)
    if nynorsk_match:
        return _clean_name(nynorsk_match.group(1))
    patterns = [
        r"(?:concerne|gjelder|betrifft|for)\s+([A-ZÆØÅÉ][^.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return _clean_name(match.group(1))
    return None


def _extract_invoice_description_fallback(prompt: str) -> Optional[str]:
    patterns = [
        r"(?:factura\s+es\s+por|invoice\s+is\s+for|facture\s+est\s+pour)\s+([A-Z][^.\n]+)",
        r"(?:gjeld)\s+([A-Z][^.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return _clean_name(match.group(1))
    return None


def parse_prompt_rule_based(prompt: str) -> ParsedTask:
    lowered = _normalized_text(prompt)
    action = _detect_action(lowered)
    entity = _detect_entity(lowered)
    fields = _extract_common_fields(prompt)
    related_entities = {}
    match_fields = {}
    notes = []

    supplier_detected = any(
        token in lowered for token in ["leverand", "supplier", "vendor", "fornecedor", "fournisseur", "lieferant"]
    )
    payment_detected = any(
        token in lowered
        for token in [
            "register full payment",
            "full payment",
            "registe",
            "registe o pagamento",
            "registre el pago",
            "registrer full betaling",
            "betaling",
            "pago completo",
            "pagamento total",
            "pagamento completo",
            "pagamento",
            "registre le paiement",
            "zahlung",
            "vollstandige zahlung",
            "vollständige zahlung",
            "payment on this invoice",
        ]
    )
    payment_detected = _contains_payment_intent(lowered)
    invoice_context_detected = any(token in lowered for token in ["invoice", "facture", "faktura", "fatura", "rechnung"])
    if supplier_detected:
        entity = "customer"
        action = "create"
    if "tilsett" in lowered or "tilsatt" in lowered:
        entity = "employee"
    if not supplier_detected and payment_detected and invoice_context_detected:
        entity = "invoice"
        action = "create"
    if not supplier_detected and invoice_context_detected and (
        any(token in lowered for token in ["create", "creez", "creer", "opprett", "lag", "registrer"])
        or _contains_send_invoice_intent(lowered)
        or payment_detected
    ):
        entity = "invoice"
        action = "create"
    if "project" in lowered or "prosjekt" in lowered or "projeto" in lowered or "proyecto" in lowered:
        entity = "project"

    if entity == "employee" and action == "create":
        first_name, last_name = _extract_employee_name(prompt)
        if first_name:
            fields["first_name"] = first_name
        if last_name:
            fields["last_name"] = last_name
        textual_dates = _extract_textual_dates(prompt)
        if textual_dates:
            fields["birthDate"] = textual_dates[0]
        if len(textual_dates) > 1:
            fields["startDate"] = textual_dates[1]
        for token, role in ROLE_MAP.items():
            if token in lowered:
                fields["employee_type"] = role
        return ParsedTask(
            task_type=TaskType.CREATE_EMPLOYEE,
            confidence=0.9,
            language_hint=_language_hint(prompt),
            fields=fields,
            notes=notes,
        )

    if entity == "employee" and action == "update":
        first_name, last_name = _extract_employee_name(prompt)
        if first_name:
            match_fields["first_name"] = first_name
        if last_name:
            match_fields["last_name"] = last_name
        employee_number = _extract_employee_number(prompt)
        if employee_number:
            match_fields["employeeNumber"] = employee_number
        if "email" in fields:
            match_fields["email"] = fields.pop("email")
        if "phone" in fields:
            fields["phoneNumberMobile"] = fields.pop("phone")
        return ParsedTask(
            task_type=TaskType.UPDATE_EMPLOYEE,
            confidence=0.84,
            language_hint=_language_hint(prompt),
            fields=fields,
            match_fields=match_fields,
        )

    if entity == "employee" and action == "read":
        fields["fields"] = "id,firstName,lastName,email"
        fields["count"] = 100
        return ParsedTask(
            task_type=TaskType.LIST_EMPLOYEES,
            confidence=0.82,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "customer" and action == "create":
        customer_name = _extract_customer_name(prompt)
        fields["name"] = customer_name or "Unknown Customer"
        fields["isCustomer"] = True
        org_number = _extract_org_number(prompt)
        if org_number:
            fields["organizationNumber"] = org_number
            match_fields["organizationNumber"] = org_number
        if supplier_detected:
            fields["isSupplier"] = True
            fields["isCustomer"] = False
        address_fields = _extract_address_fields(prompt)
        if address_fields:
            related_entities["customer_address"] = address_fields
        return ParsedTask(
            task_type=TaskType.CREATE_CUSTOMER,
            confidence=0.86,
            language_hint=_language_hint(prompt),
            fields=fields,
            match_fields=match_fields,
            related_entities=related_entities,
        )

    if entity == "customer" and action == "update":
        customer_name = _extract_project_customer_name(prompt)
        if customer_name:
            match_fields["name"] = customer_name
        if "phone" in fields:
            fields["phoneNumber"] = fields.pop("phone")
        return ParsedTask(
            task_type=TaskType.UPDATE_CUSTOMER,
            confidence=0.82,
            language_hint=_language_hint(prompt),
            fields=fields,
            match_fields=match_fields,
        )

    if entity == "customer" and action == "read":
        customer_name = _extract_project_customer_name(prompt)
        if customer_name:
            match_fields["name"] = customer_name
        org_number = _extract_org_number(prompt)
        if org_number:
            match_fields["organizationNumber"] = org_number
        fields["fields"] = "id,name,email,organizationNumber"
        fields["count"] = 100
        return ParsedTask(
            task_type=TaskType.SEARCH_CUSTOMERS,
            confidence=0.8,
            language_hint=_language_hint(prompt),
            fields=fields,
            match_fields=match_fields,
        )

    if entity == "product" and action == "create":
        product_name = _extract_named_entity(prompt, ["produkt", "product", "producto", "produto"])
        fields["name"] = product_name or "Unknown Product"
        amount = _extract_amount(prompt)
        if amount is not None:
            fields["priceExcludingVatCurrency"] = amount
        product_number = _extract_product_number(prompt)
        if product_number:
            fields["productNumber"] = product_number
            match_fields["productNumber"] = product_number
        vat_percentage = _extract_vat_percentage(prompt)
        if vat_percentage is not None:
            fields["vatPercentage"] = vat_percentage
        return ParsedTask(
            task_type=TaskType.CREATE_PRODUCT,
            confidence=0.82,
            language_hint=_language_hint(prompt),
            fields=fields,
            match_fields=match_fields,
        )

    if entity == "project" and action == "create":
        project_name = _extract_named_entity(prompt, ["prosjekt", "project", "proyecto", "projeto", "projekt"])
        fields["name"] = project_name or "Unknown Project"
        fields["startDate"] = fields.get("date") or _today_iso()
        customer_name = _extract_project_customer_name(prompt)
        if customer_name:
            related_entities["customer"] = {"name": customer_name, "isCustomer": True}
            org_number = _extract_org_number(prompt)
            if org_number:
                related_entities["customer"]["organizationNumber"] = org_number
        manager_name = _extract_project_manager_name_safe(prompt)
        if manager_name:
            manager_first_name, manager_last_name = _split_person_name(manager_name)
            related_entities["project_manager"] = {}
            if manager_first_name:
                related_entities["project_manager"]["first_name"] = manager_first_name
            if manager_last_name:
                related_entities["project_manager"]["last_name"] = manager_last_name
            if "email" in fields:
                related_entities["project_manager"]["email"] = fields["email"]
        return ParsedTask(
            task_type=TaskType.CREATE_PROJECT,
            confidence=0.81,
            language_hint=_language_hint(prompt),
            fields=fields,
            related_entities=related_entities,
        )

    if entity == "department" and action == "create":
        department_names = _extract_department_names(prompt)
        fields["name"] = department_names[0] if department_names else "Unknown Department"
        if len(department_names) > 1:
            fields["departmentNames"] = "||".join(department_names)
        number = _extract_amount(prompt)
        if number is not None and number.is_integer():
            fields["departmentNumber"] = str(int(number))
        return ParsedTask(
            task_type=TaskType.CREATE_DEPARTMENT,
            confidence=0.8,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "travel_expense" and action == "delete":
        identifier = _extract_amount(prompt)
        if identifier is not None:
            fields["travel_expense_id"] = int(identifier)
        return ParsedTask(
            task_type=TaskType.DELETE_TRAVEL_EXPENSE,
            confidence=0.8,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "travel_expense" and action == "create":
        amount = _extract_amount(prompt)
        if amount is not None:
            fields["amount"] = amount
        if "date" in fields:
            fields["expenseDate"] = fields.pop("date")
        if "kilometer" in lowered or "km" in lowered:
            fields["distance"] = int(amount) if amount is not None else 0
        return ParsedTask(
            task_type=TaskType.CREATE_TRAVEL_EXPENSE,
            confidence=0.72,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "voucher" and action == "delete":
        identifier = _extract_amount(prompt)
        if identifier is not None:
            fields["voucher_id"] = int(identifier)
        return ParsedTask(
            task_type=TaskType.DELETE_VOUCHER,
            confidence=0.75,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "ledger_account" and action == "read":
        fields["fields"] = "id,number,name"
        fields["count"] = 100
        return ParsedTask(
            task_type=TaskType.LIST_LEDGER_ACCOUNTS,
            confidence=0.76,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "ledger_posting" and action == "read":
        fields["fields"] = "id,date,amount,description"
        fields["count"] = 100
        month_match = re.search(r"(?:for|i)\s+(januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember|january)", lowered)
        if month_match:
            fields["period_hint"] = month_match.group(1)
        return ParsedTask(
            task_type=TaskType.LIST_LEDGER_POSTINGS,
            confidence=0.72,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "order" and action == "create":
        fields["orderDate"] = fields.get("date") or _today_iso()
        fields["deliveryDate"] = fields.get("date") or fields["orderDate"]
        related_entities = _extract_invoice_entities(prompt)
        amount = _extract_amount(prompt)
        if amount is not None and "product" in related_entities:
            related_entities["product"]["priceExcludingVatCurrency"] = amount
        description = _extract_invoice_description(prompt)
        if not description:
            description = _extract_invoice_description_fallback(prompt)
        if description:
            related_entities.setdefault("order", {})["description"] = description
        return ParsedTask(
            task_type=TaskType.CREATE_ORDER,
            confidence=0.74,
            language_hint=_language_hint(prompt),
            fields=fields,
            related_entities=related_entities,
        )

    if entity == "invoice" and action == "create":
        fields["invoiceDate"] = fields.get("date") or _today_iso()
        fields["invoiceDueDate"] = fields.get("date") or _today_iso()
        fields["orderDate"] = fields["invoiceDate"]
        fields["deliveryDate"] = fields["invoiceDate"]
        related_entities = _extract_invoice_entities(prompt)
        amount = _extract_amount(prompt)
        if amount is not None:
            fields["amount"] = amount
            if "product" in related_entities:
                related_entities["product"]["priceExcludingVatCurrency"] = amount
            else:
                related_entities.setdefault("invoice", {})["amountExcludingVatCurrency"] = amount
        description = _extract_invoice_description(prompt)
        if not description:
            description = _extract_invoice_description_fallback(prompt)
        if description:
            related_entities.setdefault("invoice", {})["description"] = description
            related_entities.setdefault("order", {})["description"] = description
        if _contains_send_invoice_intent(lowered):
            fields["sendByEmail"] = True
        if payment_detected:
            fields["markAsPaid"] = True
            fields["paymentDate"] = fields["invoiceDate"]
            if amount is not None:
                fields["amountPaidCurrency"] = amount
        return ParsedTask(
            task_type=TaskType.CREATE_INVOICE,
            confidence=0.79,
            language_hint=_language_hint(prompt),
            fields=fields,
            related_entities=related_entities,
        )

    return ParsedTask(
        task_type=TaskType.UNSUPPORTED,
        confidence=0.1,
        language_hint=_language_hint(prompt),
        fields=fields,
        notes=["No supported workflow matched prompt."],
    )


def parse_prompt(prompt: str) -> ParsedTask:
    prompt = _repair_mojibake(prompt)
    llm_parsed = parse_prompt_with_llm(prompt)
    rule_based = parse_prompt_rule_based(prompt)
    if llm_parsed is not None and llm_parsed.task_type != TaskType.UNSUPPORTED:
        if llm_parsed.task_type == rule_based.task_type:
            for key, value in rule_based.fields.items():
                if key not in llm_parsed.fields:
                    llm_parsed.fields[key] = value
            for key, value in rule_based.match_fields.items():
                if key not in llm_parsed.match_fields:
                    llm_parsed.match_fields[key] = value
            for key, value in rule_based.related_entities.items():
                if key not in llm_parsed.related_entities:
                    llm_parsed.related_entities[key] = value
                else:
                    for nested_key, nested_value in value.items():
                        if nested_key not in llm_parsed.related_entities[key]:
                            llm_parsed.related_entities[key][nested_key] = nested_value
            return llm_parsed

        llm_detail_score = len(llm_parsed.fields) + len(llm_parsed.match_fields) + sum(
            len(value) for value in llm_parsed.related_entities.values()
        )
        rule_detail_score = len(rule_based.fields) + len(rule_based.match_fields) + sum(
            len(value) for value in rule_based.related_entities.values()
        )
        if (
            rule_based.task_type != TaskType.UNSUPPORTED
            and rule_detail_score > llm_detail_score
            and rule_based.confidence >= llm_parsed.confidence - 0.1
        ):
            return rule_based
        return llm_parsed
    return rule_based
