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
    "opprette",
    "registrer",
    "lag",
    "lage",
    "legg til",
    "sett opp",
    "opprett gjerne",
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
    "registe",
    "registrieren",
    "anlegen",
    "legen sie",
    "add",
    "ajouter",
]
UPDATE_WORDS = ["oppdater", "endre", "set", "update", "actualizar", "aktualisieren", "mettre", "edit", "change"]
DELETE_WORDS = ["slett", "fjern", "delete", "remove", "borrar", "excluir", "loschen", "supprimer", "ta bort"]
READ_WORDS = ["hent", "list", "liste", "finn", "find", "show", "vis", "search", "sok", "søk", "buscar", "chercher", "vis meg"]

ENTITY_KEYWORDS = {
    "employee": ["ansatt", "employee", "empleado", "funcionario", "mitarbeiter", "employe", "tilsett", "tilsatt"],
    "customer": ["kunde", "customer", "cliente", "kund", "client"],
    "product": ["produkt", "product", "producto", "produto", "produit"],
    "project": ["prosjekt", "project", "proyecto", "projeto", "projekt", "projet"],
    "department": ["avdeling", "department", "departamento", "abteilung", "departement"],
    "invoice": ["faktura", "invoice", "factura", "fatura", "rechnung", "facture"],
    "order": ["ordre", "order", "pedido", "bestellung", "commande"],
    "travel_expense": ["reiseregning", "reiserekning", "travel expense", "expense report", "viagem", "spesen"],
    "voucher": ["bilag", "voucher", "comprobante", "buchung"],
    "ledger_account": ["kontoplan", "ledger account", "chart of accounts", "konti"],
    "ledger_posting": ["hovedboksposteringer", "ledger posting", "postering", "postings", "hovedbok"],
}

SEMANTIC_REPLACEMENTS = {
    "kan du ": "",
    "kunne du ": "",
    "vil du ": "",
    "please ": "",
    "kindly ": "",
    "vennligst ": "",
    "gjerne ": "",
    "om mulig ": "",
    "i tripletex": " ",
    "in tripletex": " ",
    "legg til": "opprett",
    "sett opp": "opprett",
    "ta bort": "slett",
    "vis meg": "vis",
    "i tillegg": "deretter",
    "og sa": "deretter",
    "og så": "deretter",
    "samt": "deretter",
    "as well as": "and then",
    "afterwards": "after that",
    "e depois": "em seguida",
    "und dann": "deretter",
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

PAYMENT_REVERSAL_TOKENS = [
    "reverse payment",
    "reverser betaling",
    "reverser betalinga",
    "reverser betalingen",
    "returned by the bank",
    "returnert av banken",
    "returned payment",
    "reverse the payment",
    "utestaande belop",
    "utestaende belop",
    "outstanding amount",
    "zuruckgebucht",
    "zuruck gebucht",
    "zurückgebucht",
    "stornieren sie die zahlung",
    "cancel the payment",
    "annuler le paiement",
]

SUPPLIER_INVOICE_TOKENS = [
    "supplier invoice",
    "vendor invoice",
    "leverandorfaktura",
    "leverandorfakturaen",
    "lieferantenrechnung",
    "lieferant enrechnung",
    "received invoice",
    "mottatt faktura",
    "inngaende faktura",
    "incoming invoice",
    "input vat",
    "inngaende mva",
    "vorsteuer",
    "einschliesslich mwst",
    "einschlie lich mwst",
]


INTENT_THRESHOLDS = {
    "supplier_customer": 6,
    "travel_expense": 8,
    "credit_note": 8,
    "project_billing": 8,
    "dimension_voucher": 8,
    "payroll_voucher": 8,
}


def _today_iso() -> str:
    return date.today().isoformat()


def _language_hint(prompt: str) -> str:
    lowered = _normalized_text(prompt)
    if any(word in lowered for word in ["opprett", "ansatt", "kunde", "reiseregning", "reiserekning", "avdeling"]):
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


def _contains_action_keyword(text: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in text
    return re.search(r"\b{0}\b".format(re.escape(keyword)), text) is not None


def _contains_send_invoice_intent(text: str) -> bool:
    return _contains_any(text, SEND_INVOICE_TOKENS)


def _contains_payment_intent(text: str) -> bool:
    return _contains_any(text, PAYMENT_TOKENS)


def _contains_payment_reversal_intent(text: str) -> bool:
    return _contains_any(text, PAYMENT_REVERSAL_TOKENS)


def _contains_supplier_invoice_intent(text: str) -> bool:
    return _contains_any(text, SUPPLIER_INVOICE_TOKENS)


def _normalized_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    lowered = re.sub(r"[^\w@.+\-]+", " ", lowered)
    for source, target in SEMANTIC_REPLACEMENTS.items():
        lowered = lowered.replace(source, target)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


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
    if any(_contains_action_keyword(lowered, word) for word in CREATE_WORDS):
        return "create"
    if any(_contains_action_keyword(lowered, word) for word in UPDATE_WORDS):
        return "update"
    if any(_contains_action_keyword(lowered, word) for word in DELETE_WORDS):
        return "delete"
    if any(_contains_action_keyword(lowered, word) for word in READ_WORDS):
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
    for marker in [
        " (org no",
        " (org.nr",
        " med ",
        " with ",
        " som ",
        " for ",
        " linked to ",
        " knyttet til ",
        " avec le numéro",
        " avec le numero",
        " con número",
        " con numero",
        ",",
        ".",
    ]:
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
    german_match = re.search(r"(?:f[uü]r)\s+([A-ZÃ†Ã˜Ã…Ã‰ÃœÃ–Ã„][^,(.\n]+)\s+\((?:Org|org)", prompt, re.IGNORECASE)
    if german_match:
        return _clean_name(german_match.group(1))
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


def _extract_travel_expense_id(prompt: str) -> Optional[int]:
    match = re.search(
        r"(?:reiseregning|reiserekning|travel expense|expense report|despesa de viagem)[^\d\n]*?(\d+)",
        prompt,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


def _extract_labeled_amount(prompt: str) -> Optional[float]:
    match = re.search(
        r"(?:bel[øo]p|amount|sum|belop)[^\d\n]*?(\d+(?:[.,]\d{1,2})?)\s*(?:nok|kr)?",
        prompt,
        re.IGNORECASE,
    )
    if match:
        return float(match.group(1).replace(",", "."))
    return _extract_amount(prompt)


def _extract_invoice_customer_name(prompt: str) -> Optional[str]:
    patterns = [
        r"(?:kunden|kunde|customer|client|cliente)\s+([A-ZÃ†Ã˜Ã…Ã‰ÃœÃ–Ã„][^,(.\n]+)",
        r"(?:betalinga\s+fr[åa]|betaling\s+fr[åa]|payment\s+from|zahlung\s+von)\s+([A-ZÃ†Ã˜Ã…Ã‰ÃœÃ–Ã„][^,(.\n]+)",
        r"(?:for)\s+([A-ZÃ†Ã˜Ã…Ã‰ÃœÃ–Ã„][^,(.\n]+)\s+\((?:Org|org)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return _clean_name(match.group(1))
    return _extract_project_customer_name(prompt)


def _extract_invoice_entities(prompt: str) -> Dict[str, Dict[str, object]]:
    related_entities = {}
    customer_name = _extract_invoice_customer_name(prompt)
    product_name = _extract_named_entity(prompt, ["produkt", "product", "producto", "produto"])
    customer_email = _first_match(EMAIL_RE, prompt)
    if customer_name:
        related_entities["customer"] = {"name": customer_name, "isCustomer": True}
        org_number = _extract_org_number(prompt)
        if org_number:
            related_entities["customer"]["organizationNumber"] = org_number
        if customer_email:
            related_entities["customer"]["email"] = customer_email
    if product_name:
        related_entities["product"] = {"name": product_name}
    return related_entities


def _extract_supplier_name(prompt: str) -> Optional[str]:
    patterns = [
        r"(?:supplier|vendor|leverand[^\s]*|fornecedor|fournisseur|lieferanten?)\s+([A-ZÆØÅÉÜÖÄ][^,(.\n]+)",
        r"(?:from|vom)\s+(?:the\s+)?(?:supplier|vendor|leverand[^\s]*|fornecedor|fournisseur|lieferanten?)\s+([A-ZÆØÅÉÜÖÄ][^,(.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return _clean_name(match.group(1))
    return None


def _extract_supplier_invoice_number(prompt: str) -> Optional[str]:
    match = re.search(r"\bINV-[A-Z0-9-]+\b", prompt, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    match = re.search(r"\b(?:invoice|faktura|rechnung)[- ]+[A-Z0-9-]+\b", prompt, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return None


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


def _extract_project_customer_name_safe(prompt: str) -> Optional[str]:
    german_project_billing_match = re.search(
        r'im\s+projekt\s+[\'"][^\'"]+[\'"]\s+f[uü]r\s+([A-ZÆØÅÉÜÖÄ][^,(.\n]+)\s+\((?:Org|org)',
        prompt,
        re.IGNORECASE,
    )
    if german_project_billing_match:
        return _clean_name(german_project_billing_match.group(1))
    return _extract_project_customer_name(prompt)


def _extract_employee_name_safe(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    first_name, last_name = _extract_employee_name(prompt)
    if first_name:
        return first_name, last_name
    german_match = re.search(
        r'(?:f[uü]r)\s+([A-ZÆØÅÉÜÖÄ][\wÆØÅæøåÉéÜüÖöÄä.\-]+(?:\s+[A-ZÆØÅÉÜÖÄ][\wÆØÅæøåÉéÜüÖöÄä.\-]+)+)\s+\(',
        prompt,
        re.IGNORECASE,
    )
    if german_match:
        return _split_person_name(_clean_name(german_match.group(1)))
    return None, None


def _extract_activity_name(prompt: str) -> Optional[str]:
    quoted_match = re.search(
        r'(?:aktivitet|activity|aktivitat|aktivit[aä]t)\s+["\']([^"\']+)["\']',
        prompt,
        re.IGNORECASE,
    )
    if quoted_match:
        return _clean_name(quoted_match.group(1))
    return _extract_named_entity(prompt, ["aktivitet", "activity", "aktivitat"])


def _extract_project_customer_name_billing_safe(prompt: str) -> Optional[str]:
    normalized_prompt = _normalized_text(prompt)
    match = re.search(r'im\s+projekt\s+[\'"][^\'"]+[\'"]\s+fur\s+([^,(.\n]+)\s+\((?:org)', normalized_prompt)
    if match:
        return _clean_name(match.group(1))
    portuguese_match = re.search(
        r'(?:no projeto|do projeto)\s+[\'"][^\'"]+[\'"]\s+para\s+([^,(.\n]+)\s+\((?:org)',
        normalized_prompt,
    )
    if portuguese_match:
        return _clean_name(portuguese_match.group(1))
    spanish_match = re.search(
        r'(?:del proyecto|en el proyecto)\s+[\'"][^\'"]+[\'"]\s+para\s+([^,(.\n]+)\s+\((?:org)',
        normalized_prompt,
    )
    if spanish_match:
        return _clean_name(spanish_match.group(1))
    return _extract_project_customer_name(prompt)


def _extract_employee_name_billing_safe(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    first_name, last_name = _extract_employee_name(prompt)
    if first_name:
        return first_name, last_name
    normalized_prompt = _normalized_text(prompt)
    match = re.search(r'(?:fur)\s+([a-z][^(\n]+)\s+\(', normalized_prompt)
    if not match:
        return None, None
    candidate = _clean_name(match.group(1)).title()
    return _split_person_name(candidate)


def _extract_activity_name_safe(prompt: str) -> Optional[str]:
    match = re.search(r'(?:aktivitet|activity|aktivitat|aktivit.t)\s+["\']([^"\']+)["\']', prompt, re.IGNORECASE)
    if match:
        return _clean_name(match.group(1))
    return _extract_activity_name(prompt)


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


def _extract_account_number(prompt: str) -> Optional[str]:
    match = re.search(r"(?:account|konto|conta)\s+(\d{4})", prompt, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _extract_percentage(prompt: str) -> Optional[float]:
    match = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*%", prompt)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _extract_hours(prompt: str) -> Optional[float]:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:timar|timer|stunden|hours|hrs|h|horas)\b", prompt, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _extract_daily_rate(prompt: str) -> Optional[float]:
    match = re.search(r"(?:dagssats|daily rate)\s*(?:pa|på|of|:)?\s*(\d+(?:[.,]\d+)?)\s*(?:nok|kr)\b", prompt, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _extract_day_count(prompt: str) -> Optional[int]:
    match = re.search(r"(\d+)\s*(?:dagar|dager|days)\b", prompt, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _extract_currency_amounts(prompt: str) -> List[float]:
    return [float(value.replace(",", ".")) for value in re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:nok|kr)\b", prompt, re.IGNORECASE)]


def _extract_dimension_name(prompt: str) -> Optional[str]:
    quoted_values = [value.strip() for value in QUOTED_RE.findall(prompt) if value.strip()]
    if quoted_values:
        return quoted_values[0]
    patterns = [
        r"(?:custom accounting dimension|accounting dimension|dimensjon(?:en)?|dimens[aã]o contabil[íi]stica)\s+['\"]([^'\"]+)['\"]",
        r"(?:custom accounting dimension|accounting dimension|dimensjon(?:en)?|dimens[aã]o contabil[íi]stica)\s+([A-Z][^,.\\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return _clean_name(match.group(1))
    return None


def _extract_dimension_value_names(prompt: str) -> List[str]:
    quoted_values = [value.strip() for value in QUOTED_RE.findall(prompt) if value.strip()]
    if len(quoted_values) >= 2:
        seen = set()
        values: List[str] = []
        for value in quoted_values[1:]:
            if value not in seen:
                seen.add(value)
                values.append(value)
        return values
    return []


def _extract_selected_dimension_value(prompt: str, value_names: List[str]) -> Optional[str]:
    for value_name in value_names:
        if re.search(r"\b{0}\b".format(re.escape(value_name)), prompt, re.IGNORECASE):
            return value_name
    return value_names[0] if value_names else None


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


def _extract_order_line_specs(prompt: str) -> List[Dict[str, object]]:
    specs: List[Dict[str, object]] = []
    patterns = [
        re.compile(
            r'([A-ZÃ†Ã˜Ã…Ã‰ÃœÃ–Ã„][\wÃ†Ã˜Ã…Ã¦Ã¸Ã¥Ã‰Ã©ÃœÃ¼Ã–Ã¶Ã„Ã¤ .\-]+?)\s*\((\d{3,})\)\s*(?:zu|for|por|a|til|à)\s*(\d+(?:[.,]\d+)?)\s*(?:nok|kr)\b',
            re.IGNORECASE,
        ),
        re.compile(
            r'["\']([^"\']+)["\']\s*\((\d{3,})\)\s*(?:zu|for|por|a|til|à)\s*(\d+(?:[.,]\d+)?)\s*(?:nok|kr)\b',
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        for match in pattern.finditer(prompt):
            name = _clean_name(match.group(1))
            name = re.sub(
                r"^(?:mit den produkten|mit dem produkt|med produktene|med produktet|with the products|with product)\s+",
                "",
                name,
                flags=re.IGNORECASE,
            )
            name = re.sub(r"^(?:und|and|og|e)\s+", "", name, flags=re.IGNORECASE)
            product_number = match.group(2)
            amount = float(match.group(3).replace(",", "."))
            if not name:
                continue
            specs.append(
                {
                    "name": name,
                    "description": name,
                    "productNumber": product_number,
                    "priceExcludingVatCurrency": amount,
                }
            )
        if specs:
            break
    return specs


def _score_intents(lowered: str) -> Dict[str, int]:
    scores: Dict[str, int] = {}

    def add(intent: str, value: int) -> None:
        scores[intent] = scores.get(intent, 0) + value

    if any(token in lowered for token in ["leverand", "supplier", "vendor", "fornecedor", "fournisseur", "lieferant", "proveedor"]):
        add("supplier_customer", 6)
    if "tilsett" in lowered or "tilsatt" in lowered:
        add("employee", 3)
    if any(
        token in lowered
        for token in [
            "reiseregning",
            "reiserekning",
            "travel expense",
            "expense report",
            "despesa de viagem",
            "relatorio de despesas",
            "relatório de despesas",
        ]
    ):
        add("travel_expense", 8)
    if any(token in lowered for token in ["kreditnota", "credit note", "credit memo", "nota de credito", "avoir", "gutschrift"]):
        add("credit_note", 9)
    if any(token in lowered for token in ["payroll", "salary api", "payroll expense"]) and any(
        token in lowered for token in ["salary", "bonus", "lonn", "lønn"]
    ):
        add("payroll_voucher", 9)
    if any(token in lowered for token in ["custom accounting dimension", "accounting dimension", "dimensjon", "dimensao contabilistica", "dimensão contabilística"]) and any(
        token in lowered for token in ["voucher", "bilag", "document", "dokument", "lance um documento", "post a document", "bokfor"]
    ):
        add("dimension_voucher", 9)
    if any(token in lowered for token in ["project", "prosjekt", "projeto", "proyecto", "projekt"]):
        add("project", 3)
    if any(
        token in lowered
        for token in [
            "fastpris",
            "fixed price",
            "delbetaling",
            "fakturer kunden",
            "bill the customer",
            "timesats",
            "hourly rate",
            "timar",
            "timer",
            "stunden",
            "stundensatz",
            "based on the registered hours",
            "basert pa dei registrerte timane",
            "basert på dei registrerte timane",
            "basierend auf den erfassten stunden",
            "fature o cliente",
            "gere uma fatura de projeto",
            "gerar uma fatura de projeto",
            "genere una factura de proyecto",
        ]
    ):
        add("project_billing", 8)
    if _contains_payment_intent(lowered):
        add("payment_invoice", 7)
    if any(token in lowered for token in ["invoice", "facture", "faktura", "fatura", "rechnung"]):
        add("invoice", 4)
    if any(token in lowered for token in ["customer", "kunde", "cliente", "client"]):
        add("customer", 2)
    project_context = any(
        token in lowered for token in ["project", "prosjekt", "projeto", "proyecto", "projekt", "projet"]
    )
    strict_project_billing_trigger = any(
        token in lowered
        for token in [
            "fastpris",
            "fixed price",
            "delbetaling",
            "fakturer kunden",
            "bill the customer",
            "based on the registered hours",
            "basert pa dei registrerte timane",
            "basert pÃ¥ dei registrerte timane",
            "basierend auf den erfassten stunden",
            "fature o cliente",
            "gere uma fatura de projeto",
            "gerar uma fatura de projeto",
            "genere una factura de proyecto",
        ]
    )
    strict_project_billing_rate_signal = any(token in lowered for token in ["timesats", "hourly rate", "stundensatz"])
    strict_project_billing_hours_signal = any(
        re.search(pattern, lowered)
        for pattern in [r"\b\d+(?:[.,]\d+)?\s*timar\b", r"\b\d+(?:[.,]\d+)?\s*timer\b", r"\b\d+(?:[.,]\d+)?\s*stunden\b"]
    )
    if scores.get("project_billing") and not (
        (project_context and strict_project_billing_trigger)
        or (strict_project_billing_rate_signal and strict_project_billing_hours_signal)
    ):
        scores.pop("project_billing", None)
    return scores


def _classify_intent(lowered: str) -> Optional[str]:
    scores = _score_intents(lowered)
    for intent in [
        "supplier_customer",
        "travel_expense",
        "credit_note",
        "project_billing",
        "dimension_voucher",
        "payroll_voucher",
    ]:
        if scores.get(intent, 0) >= INTENT_THRESHOLDS[intent]:
            return intent
    return None


def parse_prompt_rule_based(prompt: str) -> ParsedTask:
    lowered = _normalized_text(prompt)
    action = _detect_action(lowered)
    entity = _detect_entity(lowered)
    classified_intent = _classify_intent(lowered)
    fields = _extract_common_fields(prompt)
    related_entities = {}
    match_fields = {}
    notes = []

    supplier_detected = any(
        token in lowered for token in ["leverand", "supplier", "vendor", "fornecedor", "fournisseur", "lieferant", "proveedor"]
    )
    supplier_invoice_detected = supplier_detected and (
        _contains_supplier_invoice_intent(lowered)
        or ("invoice" in lowered and any(token in lowered for token in ["including vat", "input vat", "office services", "account "]))
        or ("faktura" in lowered and any(token in lowered for token in ["inkludert mva", "inngaende mva", "konto "]))
        or ("rechnung" in lowered and any(token in lowered for token in ["erhalten", "mwst", "vorsteuer", "konto "]))
        or ("facture" in lowered and any(token in lowered for token in ["tva deductible", "tva déductible", "facture fournisseur", "compte "]))
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
    payment_reversal_detected = _contains_payment_reversal_intent(lowered)
    invoice_context_detected = any(token in lowered for token in ["invoice", "facture", "faktura", "fatura", "rechnung"])
    if supplier_invoice_detected:
        supplier_name = _extract_supplier_name(prompt)
        if supplier_name:
            related_entities["supplier"] = {"name": supplier_name}
            org_number = _extract_org_number(prompt)
            if org_number:
                related_entities["supplier"]["organizationNumber"] = org_number
        invoice_number = _extract_supplier_invoice_number(prompt)
        if invoice_number:
            fields["invoiceNumber"] = invoice_number
        amount = _extract_amount(prompt)
        if amount is not None:
            fields["amount"] = amount
        account_number = _extract_account_number(prompt)
        if account_number:
            fields["accountNumber"] = account_number
        vat_match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", prompt)
        if vat_match:
            fields["vatPercentage"] = float(vat_match.group(1).replace(",", "."))
        fields["invoiceDate"] = fields.get("date") or _today_iso()
        return ParsedTask(
            task_type=TaskType.CREATE_SUPPLIER_INVOICE,
            confidence=0.95,
            language_hint=_language_hint(prompt),
            fields=fields,
            related_entities=related_entities,
        )
    if supplier_detected:
        entity = "customer"
        action = "create"
    if any(token in lowered for token in ["avdeling", "department", "departamento", "abteilung", "departement"]):
        entity = "department"
    if "tilsett" in lowered or "tilsatt" in lowered:
        entity = "employee"
    if (
        "reiseregning" in lowered
        or "reiserekning" in lowered
        or "travel expense" in lowered
        or "expense report" in lowered
        or "nota de gastos de viaje" in lowered
        or "despesa de viagem" in lowered
        or "relatorio de despesas" in lowered
        or "relatório de despesas" in lowered
    ):
        entity = "travel_expense"
    if "hovedboksposteringer" in lowered or "ledger posting" in lowered or "postings" in lowered:
        entity = "ledger_posting"
    if "kontoplan" in lowered or "ledger account" in lowered or "chart of accounts" in lowered:
        entity = "ledger_account"
    if not supplier_detected and payment_reversal_detected and invoice_context_detected:
        payment_fields = dict(fields)
        payment_fields["invoiceDate"] = payment_fields.get("date") or _today_iso()
        payment_fields["invoiceDueDate"] = payment_fields["invoiceDate"]
        payment_fields["orderDate"] = payment_fields["invoiceDate"]
        payment_fields["deliveryDate"] = payment_fields["invoiceDate"]
        payment_fields["paymentDate"] = payment_fields["invoiceDate"]
        related_entities = _extract_invoice_entities(prompt)
        description = _extract_invoice_description(prompt)
        if not description:
            description = _extract_invoice_description_fallback(prompt)
        if description:
            related_entities.setdefault("invoice", {})["description"] = description
            related_entities.setdefault("order", {})["description"] = description
        amount = _extract_amount(prompt)
        if amount is not None:
            payment_fields["amount"] = amount
            related_entities.setdefault("invoice", {})["amountExcludingVatCurrency"] = amount
        return ParsedTask(
            task_type=TaskType.REVERSE_PAYMENT,
            confidence=0.8,
            language_hint=_language_hint(prompt),
            fields=payment_fields,
            related_entities=related_entities,
            notes=["Reverses an existing invoice payment."],
        )
    if not supplier_detected and (payment_detected or payment_reversal_detected) and invoice_context_detected:
        entity = "invoice"
        action = "create"
    if not supplier_detected and invoice_context_detected and (
        any(token in lowered for token in ["create", "creez", "creer", "opprett", "lag", "registrer"])
        or _contains_send_invoice_intent(lowered)
        or payment_detected
        or payment_reversal_detected
    ):
        entity = "invoice"
        action = "create"
    if (
        "project" in lowered
        or "prosjekt" in lowered
        or "projeto" in lowered
        or "proyecto" in lowered
        or "projekt" in lowered
        or "projet" in lowered
    ):
        entity = "project"
    if "despesa de viagem" in lowered or "relatorio de despesas" in lowered or "relatório de despesas" in lowered:
        action = "create"

    credit_note_detected = any(
        token in lowered
        for token in ["kreditnota", "credit note", "credit memo", "nota de credito", "nota de credito", "avoir", "gutschrift"]
    )
    project_billing_detected = (
        entity == "project"
        and any(
            token in lowered
            for token in [
                "fastpris",
                "fixed price",
                "partial payment",
                "delbetaling",
                "fakturer kunden",
                "bill the customer",
                "fatur",
                "invoice customer",
                "prosjektfaktura",
                "project invoice",
                "timesats",
                "hourly rate",
                "timar",
                "timer",
                "based on the registered hours",
                "basert pa dei registrerte timane",
                "basert på dei registrerte timane",
            ]
        )
    )
    if entity == "project" and any(
        token in lowered
        for token in [
            "projektfaktura",
            "stunden",
            "stundensatz",
            "basierend auf den erfassten stunden",
            "fature o cliente",
        ]
    ):
        project_billing_detected = True
    if entity == "project" and any(
        token in lowered
        for token in [
            "gere uma fatura de projeto",
            "gerar uma fatura de projeto",
            "genere una factura de proyecto",
        ]
    ):
        project_billing_detected = True
    if project_billing_detected:
        project_context = any(
            token in lowered for token in ["project", "prosjekt", "projeto", "proyecto", "projekt", "projet"]
        )
        billing_phrase = any(
            token in lowered
            for token in [
                "fastpris",
                "fixed price",
                "delbetaling",
                "fakturer kunden",
                "bill the customer",
                "fature o cliente",
                "based on the registered hours",
                "basert pa dei registrerte timane",
                "basert pÃ¥ dei registrerte timane",
                "basierend auf den erfassten stunden",
            ]
        )
        if any(
            token in lowered
            for token in [
                "gere uma fatura de projeto",
                "gerar uma fatura de projeto",
                "genere una factura de proyecto",
            ]
        ):
            billing_phrase = True
        rate_signal = any(token in lowered for token in ["timesats", "hourly rate", "stundensatz"])
        hours_signal = any(
            re.search(pattern, lowered)
            for pattern in [r"\b\d+(?:[.,]\d+)?\s*timar\b", r"\b\d+(?:[.,]\d+)?\s*timer\b", r"\b\d+(?:[.,]\d+)?\s*stunden\b"]
        )
        if not ((project_context and billing_phrase) or (rate_signal and hours_signal)):
            project_billing_detected = False
    dimension_voucher_detected = (
        any(token in lowered for token in ["custom accounting dimension", "accounting dimension", "dimension comptable", "dimensjon", "dimensao contabilistica", "dimensao contabilistica", "dimensao contabilistica"])
        and any(token in lowered for token in ["voucher", "bilag", "document", "dokument", "piece", "pièce", "lance um documento", "post a document", "comptabilisez", "bokfor"])
    )
    payroll_detected = any(
        token in lowered
        for token in ["run payroll", "payroll", "paie", "salaire", "salario", "salário", "lonn", "salary", "bonus", "prime", "bónus", "payroll expense", "salary api"]
    )

    if classified_intent == "supplier_customer":
        entity = "customer"
        action = "create"
    if classified_intent == "travel_expense":
        entity = "travel_expense"
        action = action if action in {"create", "update", "delete"} else "create"
    if classified_intent == "credit_note":
        credit_note_detected = True
        entity = "invoice"
        action = "create"
    if classified_intent == "project_billing":
        project_billing_detected = True
        entity = "project"
        action = "create"
    if classified_intent == "dimension_voucher":
        dimension_voucher_detected = True
    if classified_intent == "payroll_voucher":
        payroll_detected = True

    if credit_note_detected:
        entity = "invoice"
        action = "create"

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

    if project_billing_detected:
        project_name = _extract_named_entity(prompt, ["prosjekt", "project", "proyecto", "projeto", "projekt"])
        fields["name"] = project_name or "Unknown Project"
        fields["startDate"] = fields.get("date") or _today_iso()
        fields["invoiceDate"] = fields.get("date") or _today_iso()
        fields["invoiceDueDate"] = fields["invoiceDate"]
        fields["orderDate"] = fields["invoiceDate"]
        fields["deliveryDate"] = fields["invoiceDate"]
        fixed_price_amount = _extract_amount(prompt)
        billing_percentage = _extract_percentage(prompt)
        hours = _extract_hours(prompt)
        if hours is None:
            hours_match = re.search(r"(\d+(?:[.,]\d+)?)\s*horas\b", prompt, re.IGNORECASE)
            if hours_match:
                hours = float(hours_match.group(1).replace(",", "."))
        currency_amounts = _extract_currency_amounts(prompt)
        if fixed_price_amount is not None:
            fields["fixedPriceAmountCurrency"] = fixed_price_amount
        if billing_percentage is not None:
            fields["billingPercentage"] = billing_percentage
            if fixed_price_amount is not None:
                fields["amount"] = round(fixed_price_amount * billing_percentage / 100.0, 2)
        customer_name = _extract_project_customer_name_billing_safe(prompt)
        if customer_name:
            related_entities["customer"] = {"name": customer_name, "isCustomer": True}
            org_number = _extract_org_number(prompt)
            if org_number:
                related_entities["customer"]["organizationNumber"] = org_number
                match_fields["customerOrganizationNumber"] = org_number
        if project_name:
            related_entities["project"] = {"name": project_name}
        manager_name = _extract_project_manager_name_safe(prompt)
        if not manager_name:
            employee_first_name, employee_last_name = _extract_employee_name_billing_safe(prompt)
            if employee_first_name:
                related_entities["employee"] = {}
                related_entities["employee"]["first_name"] = employee_first_name
                if employee_last_name:
                    related_entities["employee"]["last_name"] = employee_last_name
                if "email" in fields:
                    related_entities["employee"]["email"] = fields["email"]
        if manager_name:
            manager_first_name, manager_last_name = _split_person_name(manager_name)
            related_entities["project_manager"] = {}
            if manager_first_name:
                related_entities["project_manager"]["first_name"] = manager_first_name
            if manager_last_name:
                related_entities["project_manager"]["last_name"] = manager_last_name
            if "email" in fields:
                related_entities["project_manager"]["email"] = fields["email"]
        activity_name = _extract_activity_name_safe(prompt)
        if activity_name:
            related_entities["activity"] = {"name": activity_name}
        if hours is not None:
            related_entities["time_entries"] = {"hours": hours}
        if fields.get("amount") is None and hours is not None and len(currency_amounts) >= 1:
            rate_amount = currency_amounts[-1]
            fields["hourlyRateCurrency"] = rate_amount
            fields["amount"] = round(hours * rate_amount, 2)
        if fields.get("hourlyRateCurrency") is None:
            rate_match = re.search(r"(?:taxa horaria|taxa horária)[^\d\n]*?(\d+(?:[.,]\d+)?)\s*(?:nok|kr)\s*/?\s*h\b", prompt, re.IGNORECASE)
            if rate_match:
                fields["hourlyRateCurrency"] = float(rate_match.group(1).replace(",", "."))
                if hours is not None and fields.get("amount") is None:
                    fields["amount"] = round(hours * float(fields["hourlyRateCurrency"]), 2)
        if fields.get("amount") is not None:
            billing_description = activity_name or (
                "Partial billing {0}% of fixed price".format(int(billing_percentage or 100))
                if billing_percentage is not None
                else "Project billing"
            )
            related_entities["invoice"] = {
                "description": billing_description,
                "amountExcludingVatCurrency": fields["amount"],
            }
            related_entities["order"] = {"description": related_entities["invoice"]["description"]}
        return ParsedTask(
            task_type=TaskType.CREATE_PROJECT_BILLING,
            confidence=0.8,
            language_hint=_language_hint(prompt),
            fields=fields,
            match_fields=match_fields,
            related_entities=related_entities,
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
        identifier = _extract_travel_expense_id(prompt)
        if identifier is not None:
            fields["travel_expense_id"] = int(identifier)
        return ParsedTask(
            task_type=TaskType.DELETE_TRAVEL_EXPENSE,
            confidence=0.8,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "travel_expense" and action == "update":
        identifier = _extract_travel_expense_id(prompt)
        if identifier is not None:
            fields["travel_expense_id"] = int(identifier)
        amount = _extract_labeled_amount(prompt)
        if amount is not None:
            fields["amount"] = amount
        if "date" in fields:
            fields["expenseDate"] = fields.pop("date")
        if "kilometer" in lowered or "km" in lowered:
            fields["distance"] = int(amount) if amount is not None else 0
        return ParsedTask(
            task_type=TaskType.UPDATE_TRAVEL_EXPENSE,
            confidence=0.74,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "travel_expense" and action == "create":
        amount = _extract_amount(prompt)
        day_count = _extract_day_count(prompt)
        daily_rate = _extract_daily_rate(prompt)
        if day_count is None:
            fallback_day_match = re.search(r"(\d+)\s*(?:tage|tag|jours|dias|d[ií]as)\b", prompt, re.IGNORECASE)
            if fallback_day_match:
                day_count = int(fallback_day_match.group(1))
        if daily_rate is None:
            fallback_rate_match = re.search(
                r"(?:dagsats|dagssats|tagessatz|tarifa diaria|tasa diaria|taux journalier)[^\d\n]*?(\d+(?:[.,]\d+)?)\s*(?:nok|kr)\b",
                prompt,
                re.IGNORECASE,
            )
            if fallback_rate_match:
                daily_rate = float(fallback_rate_match.group(1).replace(",", "."))
        expense_amounts = _extract_currency_amounts(prompt)
        if day_count is not None and daily_rate is not None:
            amount = float(day_count * daily_rate)
            if expense_amounts:
                # Drop the daily rate if it appears in the generic amount list before summing expenses.
                remaining_expenses = []
                dropped_rate = False
                for expense in expense_amounts:
                    if not dropped_rate and abs(expense - daily_rate) < 0.001:
                        dropped_rate = True
                        continue
                    remaining_expenses.append(expense)
                amount += sum(remaining_expenses)
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

    if dimension_voucher_detected:
        fields["date"] = fields.get("date") or _today_iso()
        dimension_name = _extract_dimension_name(prompt)
        if dimension_name:
            fields["dimensionName"] = dimension_name
        dimension_values = _extract_dimension_value_names(prompt)
        if dimension_values:
            fields["dimensionValues"] = "||".join(dimension_values)
            selected_value = _extract_selected_dimension_value(prompt, dimension_values)
            if selected_value:
                fields["selectedDimensionValue"] = selected_value
        account_number = _extract_account_number(prompt)
        if account_number:
            fields["accountNumber"] = account_number
        amount = _extract_amount(prompt)
        if amount is not None:
            fields["amount"] = amount
        return ParsedTask(
            task_type=TaskType.CREATE_DIMENSION_VOUCHER,
            confidence=0.74,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if payroll_detected:
        fields["date"] = fields.get("date") or _today_iso()
        amounts = [float(value.replace(",", ".")) for value in re.findall(r"(\d+(?:[.,]\d{1,2})?)\s*(?:nok|kr)\b", prompt, re.IGNORECASE)]
        if amounts:
            fields["baseSalaryCurrency"] = amounts[0]
        if len(amounts) > 1:
            fields["bonusCurrency"] = amounts[1]
        if amounts:
            fields["amount"] = sum(amounts[:2]) if len(amounts) > 1 else amounts[0]
        if "email" in fields:
            related_entities["employee"] = {"email": fields["email"]}
        return ParsedTask(
            task_type=TaskType.CREATE_PAYROLL_VOUCHER,
            confidence=0.7,
            language_hint=_language_hint(prompt),
            fields=fields,
            related_entities=related_entities,
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
        order_line_specs = _extract_order_line_specs(prompt)
        if order_line_specs:
            for index, spec in enumerate(order_line_specs, start=1):
                related_entities["order_line_{0}".format(index)] = spec
            fields["amount"] = round(sum(float(spec["priceExcludingVatCurrency"]) for spec in order_line_specs), 2)
        amount = fields.get("amount") if fields.get("amount") is not None else _extract_amount(prompt)
        if amount is not None and "product" in related_entities:
            related_entities["product"]["priceExcludingVatCurrency"] = amount
        description = _extract_invoice_description(prompt)
        if not description:
            description = _extract_invoice_description_fallback(prompt)
        if description:
            related_entities.setdefault("order", {})["description"] = description
        elif order_line_specs:
            related_entities.setdefault("order", {})["description"] = str(order_line_specs[0]["description"])
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
        order_line_specs = _extract_order_line_specs(prompt)
        if order_line_specs:
            for index, spec in enumerate(order_line_specs, start=1):
                related_entities["order_line_{0}".format(index)] = spec
            amount = round(sum(float(spec["priceExcludingVatCurrency"]) for spec in order_line_specs), 2)
        else:
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
        elif order_line_specs:
            combined_description = ", ".join(str(spec["description"]) for spec in order_line_specs)
            related_entities.setdefault("invoice", {})["description"] = combined_description
            related_entities.setdefault("order", {})["description"] = combined_description
        if payment_detected and not payment_reversal_detected:
            fields["markAsPaid"] = True
            fields["paymentDate"] = fields["invoiceDate"]
            if amount is not None:
                fields["amountPaidCurrency"] = amount
        if credit_note_detected:
            fields["creditNote"] = True
            if amount is not None:
                fields["amount"] = -abs(amount)
                related_entities.setdefault("invoice", {})["amountExcludingVatCurrency"] = fields["amount"]
            related_entities.setdefault("invoice", {})["description"] = (
                related_entities.get("invoice", {}).get("description")
                or related_entities.get("order", {}).get("description")
                or "Credit note"
            )
            related_entities.setdefault("order", {})["description"] = related_entities["invoice"]["description"]
            return ParsedTask(
                task_type=TaskType.CREATE_CREDIT_NOTE,
                confidence=0.78,
                language_hint=_language_hint(prompt),
                fields=fields,
                match_fields=match_fields,
                related_entities=related_entities,
            )
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
    rule_based = parse_prompt_rule_based(prompt)
    if rule_based.task_type == TaskType.UNSUPPORTED and rule_based.confidence >= 0.9:
        return rule_based
    if rule_based.task_type == TaskType.CREATE_SUPPLIER_INVOICE and rule_based.confidence >= 0.9:
        return rule_based
    if rule_based.task_type in {
        TaskType.CREATE_EMPLOYEE,
        TaskType.UPDATE_EMPLOYEE,
        TaskType.LIST_EMPLOYEES,
        TaskType.CREATE_CUSTOMER,
        TaskType.UPDATE_CUSTOMER,
        TaskType.SEARCH_CUSTOMERS,
        TaskType.CREATE_PRODUCT,
        TaskType.CREATE_DEPARTMENT,
        TaskType.DELETE_TRAVEL_EXPENSE,
        TaskType.UPDATE_TRAVEL_EXPENSE,
        TaskType.LIST_LEDGER_ACCOUNTS,
        TaskType.LIST_LEDGER_POSTINGS,
    } and rule_based.confidence >= 0.84:
        return rule_based
    if rule_based.task_type == TaskType.CREATE_DEPARTMENT and (
        rule_based.fields.get("departmentNames") or rule_based.fields.get("name")
    ):
        return rule_based
    if rule_based.task_type == TaskType.CREATE_INVOICE and (
        rule_based.fields.get("markAsPaid") or any(key.startswith("order_line_") for key in rule_based.related_entities)
    ):
        return rule_based
    if rule_based.task_type == TaskType.CREATE_PROJECT_BILLING and rule_based.confidence >= 0.78:
        return rule_based
    if rule_based.task_type == TaskType.CREATE_PAYROLL_VOUCHER and rule_based.confidence >= 0.7:
        return rule_based
    if rule_based.task_type == TaskType.REVERSE_PAYMENT and rule_based.confidence >= 0.75:
        return rule_based

    llm_parsed = parse_prompt_with_llm(prompt)
    specialized_rule_tasks = {
        TaskType.CREATE_TRAVEL_EXPENSE,
        TaskType.CREATE_CREDIT_NOTE,
        TaskType.CREATE_PROJECT_BILLING,
        TaskType.CREATE_DIMENSION_VOUCHER,
        TaskType.CREATE_PAYROLL_VOUCHER,
    }
    if llm_parsed is not None and llm_parsed.task_type != TaskType.UNSUPPORTED:
        if rule_based.task_type != TaskType.UNSUPPORTED and rule_based.confidence >= 0.78 and llm_parsed.task_type != rule_based.task_type:
            return rule_based
        if (
            rule_based.task_type in specialized_rule_tasks
            and llm_parsed.task_type != rule_based.task_type
            and rule_based.confidence >= 0.7
        ):
            return rule_based
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
