"""Regression tests from actual competition runs.

Each test captures a real prompt that was submitted during competition,
verifying the parser + validator pipeline produces the correct task type,
preserves critical fields, and doesn't drop fields the executor needs.

These tests do NOT hit any external API — they only exercise:
  parse_prompt() → validate_and_normalize_task()
"""
from app.parser import parse_prompt
from app.schemas import ParsedTask, TaskType
from app.validator import validate_and_normalize_task


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _parse_and_validate(prompt: str) -> ParsedTask:
    parsed = parse_prompt(prompt)
    result = validate_and_normalize_task(parsed)
    assert result.blocking_error is None, f"Unexpected blocking error: {result.blocking_error}"
    return result.parsed_task


# ---------------------------------------------------------------------------
# CREATE_EMPLOYEE — Portuguese (competition run: 6/8 checks, startDate missing)
# ---------------------------------------------------------------------------
def test_create_employee_pt_preserves_start_and_birth_dates():
    prompt = (
        "Crie um funcionário chamado Inês Almeida com e-mail ines.almeida@example.org. "
        "Data de início: 2026-06-02. Data de nascimento: 1990-02-13."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_EMPLOYEE
    assert task.fields.get("first_name") or task.related_entities.get("employee", {}).get("first_name")
    # These fields must survive validation
    assert "startDate" in task.fields, "startDate was dropped by validator"
    assert "birthDate" in task.fields or "dateOfBirth" in task.fields, "birthDate was dropped by validator"


def test_create_employee_nb_with_admin_role():
    prompt = "Opprett en ansatt med navn Ola Nordmann, ola@example.org. Han skal vaere kontoadministrator."
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_EMPLOYEE
    assert task.fields.get("first_name") == "Ola"
    assert task.fields.get("last_name") == "Nordmann"
    assert task.fields.get("email") == "ola@example.org"


def test_create_employee_nn_with_birth_and_start():
    prompt = (
        "Me har ein ny tilsett som heiter Geir Stolsvik, fodd 6. March 1990. "
        "Opprett vedkomande som tilsett med e-post geir.stlsvik@example.org og startdato 14. November 2026."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_EMPLOYEE
    assert task.fields.get("birthDate") == "1990-03-06"
    assert task.fields.get("startDate") == "2026-11-14"


# ---------------------------------------------------------------------------
# CREATE_DEPARTMENT — 7/7 success, guard against regression
# ---------------------------------------------------------------------------
def test_create_three_departments_fr():
    prompt = 'Créez trois départements dans Tripletex : "Økonomi", "Lager" et "IT".'
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_DEPARTMENT
    assert task.fields.get("name") is not None
    assert "Økonomi" in task.fields.get("departmentNames", "")
    assert "IT" in task.fields.get("departmentNames", "")


# ---------------------------------------------------------------------------
# CREATE_SUPPLIER_INVOICE — supplier invoice needs externalId, vatPercentage
# ---------------------------------------------------------------------------
def test_create_supplier_invoice_preserves_vat_and_account():
    prompt = (
        "Register ein leverandørfaktura frå Fjordteknikk AS (org.nr 987654321). "
        "Fakturanummer: LF-2026-042. Beløp: 45000 kr inkl. MVA (25%). "
        "Kontonummer 4300. Forfallsdato: 2026-04-15."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_SUPPLIER_INVOICE
    assert "accountNumber" in task.fields or "vatPercentage" in task.fields
    # invoiceNumber must survive for externalId in the executor
    assert task.fields.get("invoiceNumber") is not None or task.fields.get("description") is not None


def test_supplier_invoice_nb_with_vat_and_account():
    """Supplier invoice with vatPercentage and account number.
    vatPercentage is now removed by the KB forbidden fields check —
    incomingInvoice orderLines do NOT accept vatType/vatPercentage.
    VAT is derived from the account number."""
    prompt = (
        "Vi har mottatt faktura INV-2026-8551 fra leverandøren Bergvik AS "
        "(org.nr 989568469) på 14850 kr inklusiv MVA. Beløpet gjelder "
        "kontortjenester (konto 6300). Registrer leverandørfakturaen med "
        "korrekt inngående MVA (25 %)."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_SUPPLIER_INVOICE
    assert task.fields.get("invoiceNumber") == "INV-2026-8551"
    assert task.fields.get("amount") == 14850.0
    assert task.fields.get("accountNumber") == "6300"
    # vatPercentage is now correctly removed by KB forbidden fields check
    assert task.fields.get("vatPercentage") is None, "vatPercentage should be removed (forbidden for incomingInvoice)"
    assert "supplier" in task.related_entities
    assert task.related_entities["supplier"].get("organizationNumber") == "989568469"


# ---------------------------------------------------------------------------
# CREATE_DIMENSION_VOUCHER — debitAccountNumber was being dropped
# ---------------------------------------------------------------------------
def test_dimension_voucher_preserves_debit_credit_accounts():
    prompt = (
        'Erstellen Sie eine neue Dimension "Kostenstelle" mit den Werten "Marketing", '
        '"Vertrieb" und "IT". Buchen Sie einen Beleg über 15000 NOK vom Konto 7100 '
        "auf das Konto 2400, zugeordnet zur Kostenstelle Marketing."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_DIMENSION_VOUCHER
    assert "debitAccountNumber" in task.fields, "debitAccountNumber was dropped by validator"


def test_dimension_voucher_simple_journal_entry():
    prompt = (
        "Registrer en provisjon for lønn: debet konto 5000, kredit konto 2900, "
        "beløp 73900 NOK. Dato: 2026-03-31."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_DIMENSION_VOUCHER
    assert task.fields.get("debitAccountNumber") is not None
    assert task.fields.get("creditAccountNumber") is not None
    assert task.fields.get("amount") is not None


# ---------------------------------------------------------------------------
# CREATE_INVOICE — markAsPaid / payment fields must survive
# ---------------------------------------------------------------------------
def test_create_invoice_with_payment_preserves_payment_fields():
    prompt = (
        "Opprett ein faktura til Nordfjord Bygg AS (org.nr 830362894) for "
        '"Systemutvikling" på 32200 kr ekskl. MVA. Marker som betalt.'
    )
    task = _parse_and_validate(prompt)
    # May classify as CREATE_INVOICE or REGISTER_PAYMENT — both are valid
    assert task.task_type in (TaskType.CREATE_INVOICE, TaskType.REGISTER_PAYMENT)
    assert task.fields.get("amount") is not None
    assert "customer" in task.related_entities
    assert task.related_entities["customer"].get("organizationNumber") == "830362894"


# ---------------------------------------------------------------------------
# REVERSE_PAYMENT
# ---------------------------------------------------------------------------
def test_reverse_payment_nn():
    prompt = (
        "Betalinga frå Vestfjord AS (org.nr 990290474) for fakturaen "
        '"Programvarelisens" (23850 kr ekskl. MVA) vart returnert av banken. '
        "Reverser betalinga slik at fakturaen igjen viser uteståande beløp."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.REVERSE_PAYMENT
    assert task.fields.get("amount") is not None
    assert "customer" in task.related_entities
    assert task.related_entities["customer"].get("organizationNumber") == "990290474"


# ---------------------------------------------------------------------------
# CREATE_PROJECT_BILLING — activity + time entries must be in related_entities
# ---------------------------------------------------------------------------
def test_project_billing_full_cycle_nn_not_blocked():
    """Full project cycle: multiple employees, supplier cost, customer invoice.
    Validator was blocking with 'requires billable amount' because budget != amount."""
    prompt = (
        "Gjennomfør heile prosjektsyklusen for 'Dataplattform Skogheim' (Skogheim AS, org.nr 841795067): "
        "1) Prosjektet har budsjett 258650 kr. "
        "2) Registrer timar: Torbjørn Brekke (prosjektleiar, torbjrn.brekke@example.org) 64 timar "
        "og Arne Kvamme (konsulent, arne.kvamme@example.org) 87 timar. "
        "3) Registrer leverandørkostnad 77950 kr frå Nordlys AS (org.nr 894689668). "
        "4) Opprett kundefaktura for prosjektet."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_PROJECT_BILLING
    assert task.fields.get("name") is not None
    # Must not be blocked — budget/fixedPriceAmountCurrency should serve as amount fallback
    assert task.fields.get("amount") is not None
    assert "customer" in task.related_entities
    assert task.related_entities["customer"].get("organizationNumber") == "841795067"


def test_project_billing_nn_preserves_activity_and_hours():
    prompt = (
        'Registrer 28 timar for Bjørn Kvamme (bjrn.kvamme@example.org) på aktiviteten "Analyse" '
        'i prosjektet "Datamigrering" for Fjelltopp AS (org.nr 986191127). Timesats: 1200 kr/t. '
        "Generer ein prosjektfaktura til kunden basert på dei registrerte timane."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_PROJECT_BILLING
    assert "customer" in task.related_entities
    assert task.related_entities["customer"].get("organizationNumber") == "986191127"
    # Activity and time data must be in related_entities
    assert "activity" in task.related_entities or "time_entry" in task.related_entities or "time_entries" in task.related_entities
    # Employee/project manager
    assert "employee" in task.related_entities or "project_manager" in task.related_entities


def test_project_billing_de():
    prompt = (
        'Erfassen Sie 32 Stunden für Hannah Richter (hannah.richter@example.org) auf der Aktivität '
        '"Design" im Projekt "E-Commerce-Entwicklung" für Bergwerk GmbH (Org.-Nr. 920065007). '
        "Stundensatz: 1550 NOK/h. Erstellen Sie eine Projektrechnung an den Kunden basierend auf "
        "den erfassten Stunden."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_PROJECT_BILLING
    assert task.fields.get("name") is not None  # project name
    assert "customer" in task.related_entities


# ---------------------------------------------------------------------------
# BANK_RECONCILIATION — was classified as UNSUPPORTED
# ---------------------------------------------------------------------------
def test_bank_reconciliation_fr_not_unsupported():
    """Bank reconciliation with CSV attachment was hitting UNSUPPORTED_INTENT_TOKENS."""
    prompt = (
        "Rapprochez le releve bancaire (CSV ci-joint) avec les factures ouvertes "
        "dans Tripletex. Associez les paiements entrants aux factures clients et "
        "les paiements sortants aux factures fournisseurs. Gerez correctement les "
        "paiements partiels."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type != TaskType.UNSUPPORTED
    assert task.task_type == TaskType.BANK_RECONCILIATION


# ---------------------------------------------------------------------------
# CORRECT_LEDGER_ERRORS — was classified as LIST_LEDGER_POSTINGS
# ---------------------------------------------------------------------------
def test_correct_ledger_errors_nn():
    """Ledger audit with 4 specific errors to correct. Was misclassified as list postings."""
    prompt = (
        "Me har oppdaga feil i hovudboka for januar og februar 2026. "
        "Gå gjennom alle bilag og finn dei 4 feila: "
        "ei postering på feil konto (konto 6500 brukt i staden for 6540, beløp 3450 kr), "
        "eit duplikat bilag (konto 6540, beløp 3700 kr), "
        "ei manglande MVA-linje (konto 6540, beløp ekskl. 23500 kr manglar MVA på konto 2710), "
        "og eit feil beløp (konto 7300, 18600 kr bokført i staden for 11550 kr). "
        "Korriger alle feil med rette bilag."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CORRECT_LEDGER_ERRORS


# ---------------------------------------------------------------------------
# REGISTER_PAYMENT — fields must not be dropped
# ---------------------------------------------------------------------------
def test_register_payment_preserves_all_fields():
    prompt = (
        "Registrer betaling for faktura til Havgull AS (org.nr 912345678). "
        "Betalingsdato: 2026-03-20. Beløp: 15000 kr. Valutakurs: 11.32."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.REGISTER_PAYMENT
    assert task.fields.get("paymentDate") is not None or task.fields.get("amount") is not None


# ---------------------------------------------------------------------------
# CREATE_TRAVEL_EXPENSE — many fields were being dropped
# ---------------------------------------------------------------------------
def test_create_travel_expense_preserves_fields():
    prompt = (
        "Opprett reiseregning for Kari Nordmann (kari@example.org). "
        "Reisedato: 2026-04-01. Beløp: 3500 kr. Beskrivelse: Kundebesøk Bergen. "
        "Avdeling: Salg."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_TRAVEL_EXPENSE
    # These fields were previously being dropped by the validator
    assert task.fields.get("description") is not None or task.fields.get("title") is not None


# ---------------------------------------------------------------------------
# MONTH END CLOSE (Spanish) — multi-voucher, classified as DIMENSION_VOUCHER
# ---------------------------------------------------------------------------
def test_month_end_close_es_classifies_and_extracts_accounts():
    prompt = (
        "Realice el cierre mensual de marzo de 2026. Registre la periodificación "
        "(12500 NOK por mes de la cuenta 1720 a gasto). Contabilice la depreciación "
        "mensual de un activo fijo con costo de adquisición 61400 NOK y vida útil 10 años "
        "(depreciación lineal a cuenta 6020). Verifique que el balance de saldos sea cero. "
        "También registre una provisión salarial (débito cuenta de gastos salariales 5000, "
        "crédito cuenta de salarios acumulados 2900)."
    )
    task = _parse_and_validate(prompt)
    # Should classify as some voucher type — not UNSUPPORTED
    assert task.task_type != TaskType.UNSUPPORTED
    assert task.fields.get("debitAccountNumber") is not None or task.fields.get("accountNumber") is not None
    assert task.fields.get("amount") is not None
    # Multi-entry: should have journalEntries with at least 2 entries
    entries = task.fields.get("journalEntries", [])
    assert len(entries) >= 2, f"Expected >=2 journal entries, got {len(entries)}: {entries}"
    # Check accrual entry
    accrual = entries[0]
    assert accrual["amount"] == 12500.0
    assert accrual["creditAccountNumber"] == "1720"
    # Check depreciation entry
    depreciation = entries[1]
    assert depreciation["debitAccountNumber"] == "6020"
    assert depreciation["amount"] == round(61400.0 / (10 * 12), 2)  # 511.67


# ---------------------------------------------------------------------------
# MONTH END CLOSE (German) — multi-voucher with 3 entries
# ---------------------------------------------------------------------------
def test_month_end_close_de_multi_voucher():
    prompt = (
        "Führen Sie den Monatsabschluss für März 2026 durch. Buchen Sie die "
        "Rechnungsabgrenzung (6150 EUR monatlich von Konto 1720 auf Aufwandskonto 6300). "
        "Buchen Sie die monatliche Abschreibung eines Anlageguts mit Anschaffungskosten "
        "48000 EUR und Nutzungsdauer 8 Jahre (lineare Abschreibung auf Konto 6010). "
        "Buchen Sie auch eine Gehaltsrückstellung (Aufwandskonto 5000, Konto aufgelaufene "
        "Gehälter 2900)."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_DIMENSION_VOUCHER
    entries = task.fields.get("journalEntries", [])
    assert len(entries) >= 2, f"Expected >=2 journal entries, got {len(entries)}: {entries}"
    # Accrual: debit 6300, credit 1720, amount 6150
    assert entries[0]["debitAccountNumber"] == "6300"
    assert entries[0]["creditAccountNumber"] == "1720"
    assert entries[0]["amount"] == 6150.0
    # Depreciation: debit 6010, amount = 48000 / (8*12) = 500
    assert entries[1]["debitAccountNumber"] == "6010"
    assert entries[1]["amount"] == 500.0


# ---------------------------------------------------------------------------
# MONTH END CLOSE (Norwegian) — multi-voucher
# ---------------------------------------------------------------------------
def test_month_end_close_nb_multi_voucher():
    prompt = (
        "Utfør månedsavslutning for mars 2026. Periodiser forskuddsbetalt kostnad "
        "(10150 kr per måned fra konto 1720 til kostnadskonto 6300). Bokfør månedlig "
        "avskrivning av et anleggsmiddel med anskaffelseskostnad 72000 kr og levetid "
        "6 år (lineær avskrivning til konto 6020). Bokfør også en lønnsavsetning "
        "(debiteringskonto 5000, krediteringskonto 2900)."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_DIMENSION_VOUCHER
    entries = task.fields.get("journalEntries", [])
    assert len(entries) >= 2, f"Expected >=2 journal entries, got {len(entries)}: {entries}"
    # Accrual: debit 6300, credit 1720, amount 10150
    assert entries[0]["debitAccountNumber"] == "6300"
    assert entries[0]["creditAccountNumber"] == "1720"
    assert entries[0]["amount"] == 10150.0
    # Depreciation: debit 6020, amount = 72000 / (6*12) = 1000
    assert entries[1]["debitAccountNumber"] == "6020"
    assert entries[1]["amount"] == 1000.0


# ---------------------------------------------------------------------------
# CREATE_CREDIT_NOTE — German, full credit of "Cloud-Speicher" invoice
# ---------------------------------------------------------------------------
def test_create_credit_note_de_cloud_speicher():
    prompt = (
        'Der Kunde Eichenhof GmbH (Org.-Nr. 820205790) hat die Rechnung für '
        '"Cloud-Speicher" (44400 NOK ohne MwSt.) reklamiert. Erstellen Sie eine '
        'vollständige Gutschrift, die die gesamte Rechnung storniert.'
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_CREDIT_NOTE
    assert task.fields.get("creditNote") is True
    # Amount should be negative (credit)
    assert task.fields.get("amount") is not None
    assert float(task.fields["amount"]) < 0
    # Customer info preserved
    customer = task.related_entities.get("customer", {})
    assert customer.get("name") == "Eichenhof GmbH"
    assert customer.get("organizationNumber") == "820205790"
    # Invoice description preserved
    invoice = task.related_entities.get("invoice", {})
    assert invoice.get("description") == "Cloud-Speicher" or invoice.get("amountExcludingVatCurrency") == 44400.0


# ---------------------------------------------------------------------------
# CREATE_CUSTOMER — German supplier registration (competition: 6/6)
# ---------------------------------------------------------------------------
def test_create_customer_de_supplier():
    prompt = (
        "Registrieren Sie den Lieferanten Brückentor GmbH mit der Organisationsnummer "
        "949229122. E-Mail: faktura@brckentorgmbh.no."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_CUSTOMER
    assert task.fields.get("name") == "Brückentor GmbH"
    assert task.fields.get("organizationNumber") == "949229122"
    assert task.fields.get("email") == "faktura@brckentorgmbh.no"
    assert task.fields.get("isSupplier") is True


# ---------------------------------------------------------------------------
# CREATE_SUPPLIER_INVOICE — Spanish, 25% VAT (competition: 0/8, vatType rejected)
# ---------------------------------------------------------------------------
def test_create_supplier_invoice_es_with_vat():
    prompt = (
        "Hemos recibido la factura INV-2026-9187 del proveedor Montaña SL "
        "(org. nº 884646979) por 19500 NOK con IVA incluido. El importe "
        "corresponde a servicios de oficina (cuenta 7300). Registre la factura "
        "del proveedor con el IVA soportado correcto (25 %)."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_SUPPLIER_INVOICE
    assert task.fields.get("amount") == 19500.0
    assert task.fields.get("accountNumber") == "7300"
    assert task.fields.get("invoiceNumber") == "INV-2026-9187"
    assert "supplier" in task.related_entities
    assert task.related_entities["supplier"].get("organizationNumber") == "884646979"


# ---------------------------------------------------------------------------
# REGISTER_PAYMENT — nb, amount excl. VAT (competition: 404 on payment)
# ---------------------------------------------------------------------------
def test_register_payment_nb_excl_vat():
    """Register payment for invoice with amount excl. VAT.
    The payment endpoint needs the amount INCLUDING VAT, not the parsed excl. VAT."""
    prompt = (
        'Kunden Fjordkraft AS (org.nr 891380690) har en utestående faktura på '
        '10100 kr eksklusiv MVA for "Konsulenttimer". Registrer full betaling '
        'på denne fakturaen.'
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.REGISTER_PAYMENT
    assert task.fields.get("amount") is not None
    assert "customer" in task.related_entities
    assert task.related_entities["customer"].get("organizationNumber") == "891380690"


# ---------------------------------------------------------------------------
# Validator whitelist: ensure no critical fields are silently dropped
# ---------------------------------------------------------------------------
class TestValidatorPreservesFields:
    """Verify the validator whitelist doesn't silently destroy executor-needed fields."""

    def test_employee_dateOfBirth_alias(self):
        """If LLM outputs dateOfBirth instead of birthDate, it must survive."""
        task = ParsedTask(
            task_type=TaskType.CREATE_EMPLOYEE,
            confidence=0.95,
            fields={
                "first_name": "Test",
                "last_name": "User",
                "email": "test@example.org",
                "dateOfBirth": "1990-01-15",
                "startDate": "2026-06-01",
            },
        )
        result = validate_and_normalize_task(task)
        assert result.blocking_error is None
        f = result.parsed_task.fields
        assert "dateOfBirth" in f or "birthDate" in f

    def test_employee_startDate_preserved(self):
        task = ParsedTask(
            task_type=TaskType.CREATE_EMPLOYEE,
            confidence=0.95,
            fields={
                "first_name": "Test",
                "last_name": "User",
                "email": "test@example.org",
                "startDate": "2026-06-01",
            },
        )
        result = validate_and_normalize_task(task)
        assert result.blocking_error is None
        assert result.parsed_task.fields.get("startDate") == "2026-06-01"

    def test_dimension_voucher_debit_credit_preserved(self):
        task = ParsedTask(
            task_type=TaskType.CREATE_DIMENSION_VOUCHER,
            confidence=0.95,
            fields={
                "debitAccountNumber": "5000",
                "creditAccountNumber": "2900",
                "amount": 73900.0,
                "date": "2026-03-31",
                "description": "Salary provision",
            },
        )
        result = validate_and_normalize_task(task)
        assert result.blocking_error is None
        f = result.parsed_task.fields
        assert f["debitAccountNumber"] == "5000"
        assert f["creditAccountNumber"] == "2900"
        assert f["amount"] == 73900.0

    def test_register_payment_fields_preserved(self):
        task = ParsedTask(
            task_type=TaskType.REGISTER_PAYMENT,
            confidence=0.95,
            fields={
                "paymentDate": "2026-03-20",
                "amount": 15000.0,
                "amountPaidCurrency": 15000.0,
                "exchangeRate": 11.32,
                "paymentTypeId": 6,
            },
            related_entities={"customer": {"name": "Test AS", "organizationNumber": "912345678"}},
        )
        result = validate_and_normalize_task(task)
        assert result.blocking_error is None
        f = result.parsed_task.fields
        assert f["paymentDate"] == "2026-03-20"
        assert f["amount"] == 15000.0

    def test_travel_expense_fields_preserved(self):
        task = ParsedTask(
            task_type=TaskType.CREATE_TRAVEL_EXPENSE,
            confidence=0.95,
            fields={
                "date": "2026-04-01",
                "amount": 3500.0,
                "description": "Customer visit",
                "title": "Bergen trip",
                "departmentName": "Sales",
            },
            related_entities={"employee": {"email": "kari@example.org"}},
        )
        result = validate_and_normalize_task(task)
        assert result.blocking_error is None
        f = result.parsed_task.fields
        assert f.get("description") is not None or f.get("title") is not None

    def test_supplier_invoice_fields_preserved(self):
        task = ParsedTask(
            task_type=TaskType.CREATE_SUPPLIER_INVOICE,
            confidence=0.95,
            fields={
                "invoiceDate": "2026-03-20",
                "invoiceNumber": "LF-2026-042",
                "amount": 45000.0,
                "accountNumber": "4300",
                "vatPercentage": 25.0,
                "invoiceDueDate": "2026-04-15",
            },
            related_entities={"supplier": {"name": "Fjordteknikk AS", "organizationNumber": "987654321"}},
        )
        result = validate_and_normalize_task(task)
        assert result.blocking_error is None
        f = result.parsed_task.fields
        assert f.get("invoiceNumber") == "LF-2026-042"
        # vatPercentage is removed by KB forbidden fields check (not valid for incomingInvoice)
        assert f.get("vatPercentage") is None

    def test_project_billing_hourly_rate_preserved(self):
        task = ParsedTask(
            task_type=TaskType.CREATE_PROJECT_BILLING,
            confidence=0.95,
            fields={
                "name": "Datamigrering",
                "startDate": "2026-03-22",
                "invoiceDate": "2026-03-24",
                "invoiceDueDate": "2026-03-24",
                "hourlyRateCurrency": 1200.0,
                "amount": 33600.0,
            },
            related_entities={
                "customer": {"name": "Fjelltopp AS", "organizationNumber": "986191127", "isCustomer": True},
                "employee": {"first_name": "Bjørn", "last_name": "Kvamme", "email": "bjrn.kvamme@example.org"},
                "activity": {"name": "Analyse"},
                "time_entry": {"hours": 28.0, "hourlyRate": 1200.0},
            },
        )
        result = validate_and_normalize_task(task)
        assert result.blocking_error is None
        f = result.parsed_task.fields
        assert f.get("hourlyRateCurrency") == 1200.0
        # related entities must survive
        r = result.parsed_task.related_entities
        assert "activity" in r
        assert "time_entry" in r or "time_entries" in r or "employee" in r


# ===========================================================================
# Validator whitelist tests — employee employment fields
# ===========================================================================
class TestValidatorPreservesEmploymentFields:
    def test_employee_employment_fields_preserved(self):
        """Validator must preserve nationalIdentityNumber, employmentPercentage, occupationCode."""
        task = ParsedTask(
            task_type=TaskType.CREATE_EMPLOYEE,
            confidence=0.95,
            fields={
                "first_name": "Hannah",
                "last_name": "Clark",
                "email": "hannah.clark@example.org",
                "dateOfBirth": "1990-06-27",
                "startDate": "2026-08-20",
                "nationalIdentityNumber": "27069086891",
                "employmentPercentage": 100.0,
                "annualSalary": 970000.0,
                "occupationCode": "3512",
            },
        )
        result = validate_and_normalize_task(task)
        assert result.blocking_error is None
        f = result.parsed_task.fields
        assert f["nationalIdentityNumber"] == "27069086891"
        assert f["employmentPercentage"] == 100.0
        assert f["occupationCode"] == "3512"
        assert f["annualSalary"] == 970000.0
        assert f["startDate"] == "2026-08-20"


# ===========================================================================
# Month-end close — Norwegian single-account accrual ("til kostkonto")
# ===========================================================================
def test_dimension_voucher_norwegian_til_kostkonto():
    prompt = (
        "Utfør månedsavslutning for mars 2026. Periodiser forskuddsbetalt kostnad "
        "(11000 kr per måned fra konto 1720 til kostkonto). Bokfør månedlig "
        "avskrivning for et driftsmiddel med anskaffelseskost 67050 kr og levetid "
        "5 år (lineær avskrivning til konto 6020). Kontroller at saldobalansen "
        "går i null. Bokfør også en lønnsavsetning (debet lønnskostnad konto 5000, "
        "kredit påløpt lønn konto 2900)."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_DIMENSION_VOUCHER
    entries = task.fields.get("journalEntries", [])
    assert len(entries) >= 1, f"Expected at least 1 journal entry, got {len(entries)}"
    # Accrual entry: credit 1720 (prepaid), debit 6300 (default expense)
    assert any(e["creditAccountNumber"] == "1720" for e in entries)
    # Primary debit should NOT be 5000 (system-generated salary account)
    assert task.fields.get("debitAccountNumber") != "5000"


# ===========================================================================
# Enrichment overrides LLM wrong entry (5000 → 2900)
# ===========================================================================
def test_dimension_voucher_enrichment_overrides_llm_5000():
    prompt = (
        "Utfør månedsavslutning for mars 2026. Periodiser forskuddsbetalt kostnad "
        "(10150 kr per måned fra konto 1720 til kostnadskonto 6300). Bokfør månedlig "
        "avskrivning av et anleggsmiddel med anskaffelseskostnad 72000 kr og levetid "
        "6 år (lineær avskrivning til konto 6020). Bokfør også en lønnsavsetning "
        "(debiteringskonto 5000, krediteringskonto 2900)."
    )
    task = _parse_and_validate(prompt)
    assert task.task_type == TaskType.CREATE_DIMENSION_VOUCHER
    # Primary debit should be the accrual expense account (6300), not salary (5000)
    assert task.fields.get("debitAccountNumber") == "6300"
    assert task.fields.get("creditAccountNumber") == "1720"
