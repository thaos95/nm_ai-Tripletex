from datetime import date

import app.parser as parser_module
from app.schemas import ParsedTask
from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task


TODAY_ISO = date.today().isoformat()


def test_parse_create_employee_prompt() -> None:
    parsed = parse_prompt(
        "Opprett en ansatt med navn Ola Nordmann, ola@example.org. Han skal vaere kontoadministrator."
    )

    assert parsed.task_type == TaskType.CREATE_EMPLOYEE
    assert parsed.fields["first_name"] == "Ola"
    assert parsed.fields["last_name"] == "Nordmann"
    assert parsed.fields["email"] == "ola@example.org"
    assert parsed.fields["employee_type"] == "ACCOUNT_MANAGER"


def test_parse_update_customer_prompt() -> None:
    parsed = parse_prompt("Oppdater kunde Acme AS med telefon +47 12345678")
    assert parsed.task_type == TaskType.UPDATE_CUSTOMER
    assert parsed.match_fields["name"] == "Acme AS"
    assert parsed.fields["phoneNumber"] == "+4712345678"


def test_parse_update_employee_prompt_uses_email_for_matching() -> None:
    parsed = parse_prompt("Oppdater ansatt Marte Solberg med e-post marte@example.org og telefon +47 41234567")
    assert parsed.task_type == TaskType.UPDATE_EMPLOYEE
    assert parsed.match_fields["first_name"] == "Marte"
    assert parsed.match_fields["last_name"] == "Solberg"
    assert parsed.match_fields["email"] == "marte@example.org"
    assert parsed.fields["phoneNumberMobile"] == "+4741234567"


def test_parse_create_invoice_prompt() -> None:
    parsed = parse_prompt('Create invoice for customer "Acme AS" with product "Consulting" 1500')
    assert parsed.task_type == TaskType.CREATE_INVOICE
    assert parsed.related_entities["customer"]["name"] == "Acme AS"
    assert parsed.related_entities["product"]["name"] == "Consulting"
    assert parsed.related_entities["product"]["priceExcludingVatCurrency"] == 1500.0


def test_parse_delete_travel_expense_prompt() -> None:
    parsed = parse_prompt("Slett reiseregning 42")
    assert parsed.task_type == TaskType.DELETE_TRAVEL_EXPENSE
    assert parsed.fields["travel_expense_id"] == 42


def test_parse_update_travel_expense_prompt() -> None:
    parsed = parse_prompt("Oppdater reiseregning 42 med beløp 950 og dato 2026-03-19")
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.UPDATE_TRAVEL_EXPENSE
    assert validated.parsed_task.fields["travel_expense_id"] == 42
    assert validated.parsed_task.fields["amount"] == 950.0
    assert validated.parsed_task.fields["date"] == "2026-03-19"


def test_parse_create_project_with_customer_and_org_number() -> None:
    parsed = parse_prompt(
        'Create the project "Analysis Oakwood" linked to the customer Oakwood Ltd (org no. 849612913). The project manager is Lucy Taylor (lucy.taylor@example.org).'
    )
    assert parsed.task_type == TaskType.CREATE_PROJECT
    assert parsed.fields["name"] == "Analysis Oakwood"
    assert parsed.related_entities["customer"]["name"] == "Oakwood Ltd"
    assert parsed.related_entities["customer"]["organizationNumber"] == "849612913"
    assert parsed.related_entities["project_manager"]["first_name"] == "Lucy"
    assert parsed.related_entities["project_manager"]["last_name"] == "Taylor"
    assert parsed.related_entities["project_manager"]["email"] == "lucy.taylor@example.org"
    assert "phone" not in parsed.fields


def test_parse_norwegian_project_with_customer_and_manager() -> None:
    parsed = parse_prompt(
        'Opprett prosjektet "Implementering Tindra" knyttet til kunden Tindra AS (org.nr 886715536). Prosjektleder er Jonas Haugen (jonas.haugen@example.org).'
    )
    assert parsed.task_type == TaskType.CREATE_PROJECT
    assert parsed.fields["name"] == "Implementering Tindra"
    assert parsed.related_entities["customer"]["name"] == "Tindra AS"
    assert parsed.related_entities["customer"]["organizationNumber"] == "886715536"
    assert parsed.related_entities["project_manager"]["first_name"] == "Jonas"
    assert parsed.related_entities["project_manager"]["last_name"] == "Haugen"
    assert parsed.related_entities["project_manager"]["email"] == "jonas.haugen@example.org"


def test_parse_list_employees_prompt() -> None:
    parsed = parse_prompt("Hent ansatte")
    assert parsed.task_type == TaskType.LIST_EMPLOYEES
    assert parsed.fields["fields"] == "id,firstName,lastName,email"


def test_parse_search_customers_prompt() -> None:
    parsed = parse_prompt("Finn alle kunder med orgnr 849612913")
    assert parsed.task_type == TaskType.SEARCH_CUSTOMERS
    assert parsed.match_fields["organizationNumber"] == "849612913"


def test_validator_drops_invalid_customer_org_number() -> None:
    parsed = parse_prompt("Creer client Client Bleu 12345 SARL, client.bleu@example.org")
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_CUSTOMER
    assert "organizationNumber" not in validated.parsed_task.fields


def test_parse_supplier_customer_with_address() -> None:
    parsed = parse_prompt(
        "Registrer leverandøren Dalheim AS med organisasjonsnummer 892196753. Adressa er Parkveien 45, 5003 Bergen. E-post: faktura@dalheim.no."
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_CUSTOMER
    assert validated.parsed_task.fields["isSupplier"] is True
    assert validated.parsed_task.fields["organizationNumber"] == "892196753"
    assert validated.parsed_task.related_entities["customer_address"]["addressStreet"] == "Parkveien 45"
    assert validated.parsed_task.related_entities["customer_address"]["postalCode"] == "5003"
    assert validated.parsed_task.related_entities["customer_address"]["city"] == "Bergen"


def test_parse_supplier_invoice_prompt_is_unsupported() -> None:
    parsed = parse_prompt(
        "We have received invoice INV-2026-9601 from the supplier Oakwood Ltd (org no. 967247049) for 79750 NOK including VAT. The amount relates to office services (account 6540). Register the supplier invoice with the correct input VAT (25%)."
    )
    assert parsed.task_type == TaskType.CREATE_SUPPLIER_INVOICE
    assert parsed.related_entities["supplier"]["organizationNumber"] == "967247049"
    assert parsed.fields["invoiceNumber"] == "INV-2026-9601"
    assert parsed.fields["amount"] == 79750.0
    assert parsed.fields["accountNumber"] == "6540"
    assert parsed.fields["vatPercentage"] == 25.0


def test_parse_german_supplier_invoice_prompt_is_unsupported() -> None:
    parsed = parse_prompt(
        "Wir haben die Rechnung INV-2026-8810 vom Lieferanten Sonnental GmbH (Org.-Nr. 988926221) über 8050 NOK einschließlich MwSt. erhalten. Der Betrag betrifft Bürodienstleistungen (Konto 6860). Erfassen Sie die Lieferantenrechnung mit der korrekten Vorsteuer (25 %)."
    )
    assert parsed.task_type == TaskType.CREATE_SUPPLIER_INVOICE
    assert parsed.related_entities["supplier"]["organizationNumber"] == "988926221"


def test_parse_supplier_invoice_fast_path_skips_llm(monkeypatch) -> None:
    def fail_llm(prompt: str) -> ParsedTask:
        raise AssertionError("LLM should not be called for high-confidence supplier invoice prompts")

    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", fail_llm)
    parsed = parse_prompt(
        "We have received invoice INV-2026-9601 from the supplier Oakwood Ltd (org no. 967247049) for 79750 NOK including VAT. The amount relates to office services (account 6540). Register the supplier invoice with the correct input VAT (25%)."
    )
    assert parsed.task_type == TaskType.CREATE_SUPPLIER_INVOICE


def test_parse_employee_with_birth_and_start_dates() -> None:
    parsed = parse_prompt(
        "Me har ein ny tilsett som heiter Arne Berge, fødd 21. December 2000. Opprett vedkomande som tilsett med e-post arne.berge@example.org og startdato 14. April 2026."
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_EMPLOYEE
    assert validated.parsed_task.fields["birthDate"] == "2000-12-21"
    assert validated.parsed_task.fields["startDate"] == "2026-04-14"


def test_parse_product_with_number_and_vat() -> None:
    parsed = parse_prompt(
        'Opprett produktet "Analyserapport" med produktnummer 1908. Prisen er 18050 kr eksklusiv MVA, og standard MVA-sats på 25 % skal nyttast.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_PRODUCT
    assert validated.parsed_task.fields["productNumber"] == "1908"
    assert validated.parsed_task.fields["vatPercentage"] == 25.0


def test_parse_invoice_with_description_and_dates() -> None:
    parsed = parse_prompt(
        'Créez et envoyez une facture au client Étoile SARL (nº org. 995085488) de 7250 NOK hors TVA. La facture concerne Rapport d\'analyse.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert "sendByEmail" not in validated.parsed_task.fields
    assert validated.parsed_task.fields["orderDate"] == TODAY_ISO
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Rapport d'analyse"


def test_parse_spanish_invoice_uses_description_phrase() -> None:
    parsed = parse_prompt(
        'Crea y envía una factura al cliente Montaña SL (org. nº 831306742) por 48600 NOK sin IVA. La factura es por Licencia de software.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "831306742"
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Licencia de software"
    assert validated.parsed_task.related_entities["order"]["description"] == "Licencia de software"


def test_parse_payment_prompt_maps_to_invoice_flow() -> None:
    parsed = parse_prompt(
        'The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert validated.parsed_task.fields["markAsPaid"] is True
    assert validated.parsed_task.fields["paymentDate"] == TODAY_ISO
    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "830362894"
    assert validated.parsed_task.related_entities["invoice"]["description"] == "System Development"


def test_parse_portuguese_payment_prompt_maps_to_invoice_flow() -> None:
    parsed = parse_prompt(
        'O cliente Floresta Lda (org. nº 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert validated.parsed_task.fields["markAsPaid"] is True
    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "916058896"
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Desenvolvimento de sistemas"


def test_parse_nynorsk_invoice_description_without_quotes() -> None:
    parsed = parse_prompt(
        "Opprett og send ein faktura til kunden Strandvik AS (org.nr 993504815) på 1800 kr eksklusiv MVA. Fakturaen gjeld Opplæring."
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Opplæring"
    assert validated.parsed_task.related_entities["order"]["description"] == "Opplæring"


def test_parse_multi_department_prompt() -> None:
    parsed = parse_prompt('Erstellen Sie drei Abteilungen in Tripletex: "Utvikling", "Innkjøp" und "Økonomi".')
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_DEPARTMENT
    assert validated.parsed_task.fields["departmentNames"] == "Utvikling||Innkjøp||Økonomi"
def test_parse_payment_reversal_prompt_keeps_invoice_unpaid() -> None:
    parsed = parse_prompt(
        'Betalinga frÃ¥ Strandvik AS (org.nr 859256333) for fakturaen "Nettverksteneste" (41550 kr ekskl. MVA) vart returnert av banken. Reverser betalinga slik at fakturaen igjen viser utestÃ¥ande belÃ¸p.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert "markAsPaid" not in validated.parsed_task.fields
    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "859256333"
    assert validated.parsed_task.related_entities["order"]["description"] == "Nettverksteneste"


def test_parse_multiline_order_invoice_prompt_collects_all_order_lines() -> None:
    parsed = parse_prompt(
        'Erstellen Sie einen Auftrag fÃ¼r den Kunden Waldstein GmbH (Org.-Nr. 899060113) mit den Produkten Netzwerkdienst (5411) zu 29200 NOK und Schulung (7883) zu 10350 NOK. Wandeln Sie den Auftrag in eine Rechnung um und registrieren Sie die vollstÃ¤ndige Zahlung.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "899060113"
    assert validated.parsed_task.related_entities["order_line_1"]["description"] == "Netzwerkdienst"
    assert validated.parsed_task.related_entities["order_line_2"]["description"] == "Schulung"
    assert validated.parsed_task.fields["amount"] == 39550.0
    assert validated.parsed_task.fields["amountPaidCurrency"] == 39550.0
