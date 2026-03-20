from datetime import date

from fastapi.testclient import TestClient

from app.main import app


TODAY_ISO = date.today().isoformat()


def _inspect(prompt: str) -> dict:
    client = TestClient(app)
    response = client.post("/inspect", json={"prompt": prompt, "files": []})
    assert response.status_code == 200
    return response.json()


def test_inspect_hard_prompt_pack_invoice_nb() -> None:
    body = _inspect(
        "Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) på 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring."
    )
    assert body["parsed_task"]["task_type"] == "create_invoice"
    assert body["parsed_task"]["fields"]["invoiceDate"] == TODAY_ISO
    assert "sendByEmail" not in body["parsed_task"]["fields"]
    assert body["parsed_task"]["related_entities"]["customer"]["organizationNumber"] == "845762686"
    assert body["parsed_task"]["related_entities"]["invoice"]["description"] == "Skylagring"
    assert [step["name"] for step in body["plan"]] == [
        "resolve-invoice-customer",
        "create-order",
        "create-invoice",
    ]


def test_inspect_hard_prompt_pack_invoice_fr() -> None:
    body = _inspect(
        "Créez et envoyez une facture au client Etoile SARL (nº org. 995085488) de 7250 NOK hors TVA. La facture concerne Rapport d'analyse."
    )
    assert body["parsed_task"]["task_type"] == "create_invoice"
    assert "sendByEmail" not in body["parsed_task"]["fields"]
    assert body["parsed_task"]["related_entities"]["customer"]["organizationNumber"] == "995085488"
    assert body["parsed_task"]["related_entities"]["invoice"]["description"] == "Rapport d'analyse"


def test_inspect_hard_prompt_pack_payment_en() -> None:
    body = _inspect(
        'The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.'
    )
    assert body["parsed_task"]["task_type"] == "create_invoice"
    assert body["parsed_task"]["fields"]["markAsPaid"] is True
    assert body["parsed_task"]["fields"]["paymentDate"] == TODAY_ISO
    assert body["parsed_task"]["related_entities"]["invoice"]["description"] == "System Development"


def test_inspect_hard_prompt_pack_payment_pt() -> None:
    body = _inspect(
        'O cliente Floresta Lda (org. nº 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.'
    )
    assert body["parsed_task"]["task_type"] == "create_invoice"
    assert body["parsed_task"]["fields"]["markAsPaid"] is True
    assert body["parsed_task"]["related_entities"]["customer"]["organizationNumber"] == "916058896"


def test_inspect_hard_prompt_pack_credit_note_nn() -> None:
    body = _inspect(
        'Kunden Fossekraft AS (org.nr 918737227) har reklamert på fakturaen for "Konsulenttimar" (16200 kr ekskl. MVA). Opprett ei fullstendig kreditnota som reverserer heile fakturaen.'
    )
    assert body["parsed_task"]["task_type"] == "create_credit_note"
    assert body["parsed_task"]["fields"]["creditNote"] is True
    assert body["parsed_task"]["related_entities"]["invoice"]["description"] == "Konsulenttimar"


def test_inspect_hard_prompt_pack_project_es() -> None:
    body = _inspect(
        'Crea el proyecto "Implementación Dorada" vinculado al cliente Dorada SL (org. nº 831075392). El director del proyecto es Isabel Rodríguez (isabel.rodriguez@example.org).'
    )
    assert body["parsed_task"]["task_type"] == "create_project"
    assert body["parsed_task"]["fields"]["name"] == "Implementación Dorada"
    assert body["parsed_task"]["related_entities"]["customer"]["organizationNumber"] == "831075392"
    assert body["parsed_task"]["related_entities"]["project_manager"]["email"] == "isabel.rodriguez@example.org"


def test_inspect_hard_prompt_pack_project_pt() -> None:
    body = _inspect(
        'Crie o projeto "Implementação Rio" vinculado ao cliente Rio Azul Lda (org. nº 827937223). O gerente de projeto é Gonçalo Oliveira (goncalo.oliveira@example.org).'
    )
    assert body["parsed_task"]["task_type"] == "create_project"
    assert body["parsed_task"]["fields"]["name"] == "Implementação Rio"
    assert body["parsed_task"]["related_entities"]["customer"]["organizationNumber"] == "827937223"
    assert body["parsed_task"]["related_entities"]["project_manager"]["email"] == "goncalo.oliveira@example.org"


def test_inspect_hard_prompt_pack_project_billing_fixed_price_nb() -> None:
    body = _inspect(
        'Sett fastpris 203000 kr på prosjektet "Digital transformasjon" for Stormberg AS (org.nr 834028719). Prosjektleder er Hilde Hansen (hilde.hansen@example.org). Fakturer kunden for 75 % av fastprisen som en delbetaling.'
    )
    assert body["parsed_task"]["task_type"] == "create_project_billing"
    assert body["parsed_task"]["fields"]["name"] == "Digital transformasjon"
    assert body["parsed_task"]["fields"]["amount"] == 152250.0
    assert body["parsed_task"]["related_entities"]["customer"]["organizationNumber"] == "834028719"
    assert body["parsed_task"]["related_entities"]["invoice"]["amountExcludingVatCurrency"] == 152250.0


def test_inspect_hard_prompt_pack_project_billing_hours_nn() -> None:
    body = _inspect(
        'Registrer 28 timar for Bjørn Kvamme (bjrn.kvamme@example.org) på aktiviteten "Analyse" i prosjektet "Datamigrering" for Fjelltopp AS (org.nr 986191127). Timesats: 1200 kr/t. Generer ein prosjektfaktura til kunden basert på dei registrerte timane.'
    )
    assert body["parsed_task"]["task_type"] == "create_project_billing"
    assert body["parsed_task"]["fields"]["name"] == "Datamigrering"
    assert body["parsed_task"]["fields"]["amount"] == 33600.0
    assert body["parsed_task"]["related_entities"]["activity"]["name"] == "Analyse"
    assert body["parsed_task"]["related_entities"]["time_entries"]["hours"] == 28.0


def test_inspect_hard_prompt_pack_project_billing_de() -> None:
    body = _inspect(
        'Erfassen Sie 32 Stunden für Hannah Richter (hannah.richter@example.org) auf der Aktivität "Design" im Projekt "E-Commerce-Entwicklung" für Bergwerk GmbH (Org.-Nr. 920065007). Stundensatz: 1550 NOK/h. Erstellen Sie eine Projektrechnung an den Kunden basierend auf den erfassten Stunden.'
    )
    assert body["parsed_task"]["task_type"] == "create_project_billing"
    assert body["parsed_task"]["fields"]["name"] == "E-Commerce-Entwicklung"
    assert body["parsed_task"]["fields"]["amount"] == 49600.0
    assert body["parsed_task"]["related_entities"]["activity"]["name"] == "Design"
    assert [step["name"] for step in body["plan"]][-3:] == [
        "create-billing-project",
        "create-billing-order",
        "create-billing-invoice",
    ]


def test_inspect_hard_prompt_pack_travel_expense_nn() -> None:
    body = _inspect(
        'Registrer ei reiserekning for Svein Berge (svein.berge@example.org) for "Kundebesøk Trondheim". Reisa varte 5 dagar med diett (dagssats 800 kr). Utlegg: flybillett 2850 kr og taxi 200 kr.'
    )
    assert body["parsed_task"]["task_type"] == "create_travel_expense"
    assert body["parsed_task"]["fields"]["amount"] == 7050.0


def test_inspect_hard_prompt_pack_update_travel_expense_nb() -> None:
    body = _inspect("Oppdater reiseregning 42 med beløp 950 og dato 2026-03-19.")
    assert body["parsed_task"]["task_type"] == "update_travel_expense"
    assert body["parsed_task"]["fields"]["travel_expense_id"] == 42
    assert body["parsed_task"]["fields"]["amount"] == 950.0


def test_inspect_hard_prompt_pack_dimension_voucher_pt() -> None:
    body = _inspect(
        'Crie uma dimensão contabilística personalizada "Marked" com os valores "Bedrift" e "Privat". Em seguida, lance um documento na conta 6590 por 16750 NOK, vinculado ao valor de dimensão "Bedrift".'
    )
    assert body["parsed_task"]["task_type"] == "create_dimension_voucher"
    assert body["parsed_task"]["fields"]["dimensionName"] == "Marked"
    assert body["parsed_task"]["fields"]["accountNumber"] == "6590"
    assert body["parsed_task"]["fields"]["amount"] == 16750.0


def test_inspect_hard_prompt_pack_payroll_voucher_en() -> None:
    body = _inspect(
        "Run payroll for James Williams (james.williams@example.org) for this month. The base salary is 34950 NOK. Add a one-time bonus of 15450 NOK on top of the base salary. If the salary API is unavailable, you can use manual vouchers on salary accounts (5000-series) to record the payroll expense."
    )
    assert body["parsed_task"]["task_type"] == "create_payroll_voucher"
    assert body["parsed_task"]["fields"]["amount"] == 50400.0
    assert body["parsed_task"]["related_entities"]["employee"]["email"] == "james.williams@example.org"
