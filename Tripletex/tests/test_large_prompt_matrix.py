import pytest

import app.parser as parser_module

from app.parser import parse_prompt
from app.schemas import TaskType


DATASETS = [
    {
        "supplier": "Nordlys Leveranse AS",
        "customer": "Nordlys AS",
        "first": "Ola",
        "last": "Hansen",
        "email": "ola.hansen@example.org",
        "org": "912345670",
        "product": "Analysepakke",
        "project": "Systemloft",
        "desc": "Radgivning",
        "amount": 12500,
        "days": 3,
        "rate": 850,
        "expense": 2200,
        "department": "Okonomi",
    },
    {
        "supplier": "Fjord Partner AS",
        "customer": "Fjord Partner AS",
        "first": "Kari",
        "last": "Lie",
        "email": "kari.lie@example.org",
        "org": "923456781",
        "product": "Driftstjeneste",
        "project": "Skyflyt",
        "desc": "Programvarelisens",
        "amount": 16400,
        "days": 4,
        "rate": 900,
        "expense": 3100,
        "department": "Salg",
    },
    {
        "supplier": "Berg Data AS",
        "customer": "Berg Data AS",
        "first": "Arne",
        "last": "Berge",
        "email": "arne.berge@example.org",
        "org": "934567892",
        "product": "Konsulentpakke",
        "project": "Dataloft",
        "desc": "Implementering",
        "amount": 20750,
        "days": 5,
        "rate": 780,
        "expense": 2850,
        "department": "Drift",
    },
    {
        "supplier": "Vest Regnskap AS",
        "customer": "Vest Regnskap AS",
        "first": "Nora",
        "last": "Dahl",
        "email": "nora.dahl@example.org",
        "org": "945678903",
        "product": "Rapportering",
        "project": "Fakturaflyt",
        "desc": "Analyse",
        "amount": 9800,
        "days": 2,
        "rate": 950,
        "expense": 1800,
        "department": "Administrasjon",
    },
    {
        "supplier": "Aasen Konsult AS",
        "customer": "Aasen Konsult AS",
        "first": "Mina",
        "last": "Larsen",
        "email": "mina.larsen@example.org",
        "org": "956789014",
        "product": "Supportavtale",
        "project": "ERP-skifte",
        "desc": "Opplaering",
        "amount": 24300,
        "days": 6,
        "rate": 800,
        "expense": 3400,
        "department": "Innkjop",
    },
    {
        "supplier": "Solberg Partner AS",
        "customer": "Solberg Partner AS",
        "first": "Even",
        "last": "Moen",
        "email": "even.moen@example.org",
        "org": "967890125",
        "product": "Integrasjon",
        "project": "Portalprosjekt",
        "desc": "Vedlikehold",
        "amount": 18850,
        "days": 7,
        "rate": 870,
        "expense": 2600,
        "department": "Logistikk",
    },
]


LANGUAGE_FAMILIES = {
    "supplier": {
        "nb": "Registrer leverandoren {supplier} med organisasjonsnummer {org}. E-post: {email}.",
        "nn": "Registrer leverandoren {supplier} med organisasjonsnummer {org}. E-post: {email}.",
        "en": "Create supplier {supplier} with organization number {org}. Email: {email}.",
        "pt": "Registe o fornecedor {supplier} com numero de organizacao {org}. E-mail: {email}.",
        "de": "Erstellen Sie den Lieferanten {supplier} mit Organisationsnummer {org}. E-Mail: {email}.",
        "fr": "Creez le fournisseur {supplier} avec numero d'organisation {org}. E-mail: {email}.",
    },
    "employee": {
        "nb": "Opprett en ansatt som heter {first} {last} med e-post {email}.",
        "nn": "Opprett ein tilsett som heiter {first} {last} med e-post {email}.",
        "en": "Create employee {first} {last} with email {email}.",
        "de": "Erstellen Sie den Mitarbeiter {first} {last} mit E-Mail {email}.",
    },
    "product": {
        "nb": 'Opprett produktet "{product}" for {amount} kr.',
        "nn": 'Opprett produktet "{product}" for {amount} kr.',
        "en": 'Create product "{product}" for {amount} NOK.',
        "es": 'Crea el producto "{product}" por {amount} NOK.',
        "pt": 'Crie o produto "{product}" por {amount} NOK.',
        "de": 'Erstellen Sie das Produkt "{product}" fur {amount} NOK.',
    },
    "project": {
        "nb": 'Opprett prosjektet "{project}" knyttet til kunden {customer} (org.nr {org}). Prosjektleder er {first} {last} ({email}).',
        "nn": 'Opprett prosjektet "{project}" knytt til kunden {customer} (org.nr {org}). Prosjektleiar er {first} {last} ({email}).',
        "en": 'Create the project "{project}" linked to customer {customer} (org no. {org}). The project manager is {first} {last} ({email}).',
        "es": 'Crea el proyecto "{project}" vinculado al cliente {customer} (org. n {org}). El director del proyecto es {first} {last} ({email}).',
        "pt": 'Crie o projeto "{project}" vinculado ao cliente {customer} (org. n {org}). O gerente de projeto e {first} {last} ({email}).',
        "de": 'Erstellen Sie das Projekt "{project}" fur den Kunden {customer} (Org.-Nr. {org}). Der Projektleiter ist {first} {last} ({email}).',
        "fr": 'Creez le projet "{project}" lie au client {customer} (n org. {org}). Le chef de projet est {first} {last} ({email}).',
    },
    "invoice": {
        "nb": "Opprett og send en faktura til kunden {customer} (org.nr {org}) pa {amount} kr eksklusiv MVA. Fakturaen gjelder {desc}.",
        "nn": "Opprett og send ei faktura til kunden {customer} (org.nr {org}) pa {amount} kr eksklusiv MVA. Fakturaen gjeld {desc}.",
        "en": "Create and send an invoice to customer {customer} (org no. {org}) for {amount} NOK excluding VAT. The invoice is for {desc}.",
        "es": "Crea y envia una factura al cliente {customer} (org. n {org}) por {amount} NOK sin IVA. La factura es por {desc}.",
        "fr": "Creez et envoyez une facture au client {customer} (n org. {org}) de {amount} NOK hors TVA. La facture concerne {desc}.",
    },
    "credit_note": {
        "nb": 'Opprett en full kreditnota for kunden {customer} (org.nr {org}) for "{desc}" pa {amount} kr.',
        "nn": 'Opprett ei full kreditnota for kunden {customer} (org.nr {org}) for "{desc}" pa {amount} kr.',
        "en": 'Create a full credit note for customer {customer} (org no. {org}) for "{desc}" {amount} NOK.',
        "es": 'Crea una nota de credito completa para el cliente {customer} (org. n {org}) por "{desc}" {amount} NOK.',
        "pt": 'Crie uma nota de credito completa para o cliente {customer} (org. n {org}) por "{desc}" {amount} NOK.',
        "de": 'Erstellen Sie eine vollstandige Gutschrift fur den Kunden {customer} (Org.-Nr. {org}) fur "{desc}" uber {amount} NOK.',
        "fr": 'Creez un avoir complet pour le client {customer} (n org. {org}) pour "{desc}" de {amount} NOK.',
    },
    "travel_expense": {
        "nb": 'Registrer en reiseregning for {first} {last} ({email}). Reisen varte {days} dager med diett (dagssats {rate} kr). Utlegg: hotell {expense} kr.',
        "nn": 'Registrer ei reiserekning for {first} {last} ({email}). Reisa varte {days} dagar med diett (dagssats {rate} kr). Utlegg: hotell {expense} kr.',
        "en": 'Register a travel expense for {first} {last} ({email}). The trip lasted {days} days with per diem ({rate} NOK per day). Expenses: hotel {expense} NOK.',
        "es": 'Crea un expense report para {first} {last} ({email}). El viaje duro {days} dias con dieta ({rate} NOK por dia). Gastos: hotel {expense} NOK.',
        "pt": 'Registe uma despesa de viagem para {first} {last} ({email}). A viagem durou {days} dias com dieta ({rate} NOK por dia). Despesas: hotel {expense} NOK.',
        "de": 'Registrieren Sie Spesen fur {first} {last} ({email}). Die Reise dauerte {days} Tage mit Tagessatz {rate} NOK. Ausgaben: Hotel {expense} NOK.',
        "fr": 'Creez un expense report pour {first} {last} ({email}). Le voyage a dure {days} jours avec indemnite de {rate} NOK. Depenses: hotel {expense} NOK.',
    },
    "department": {
        "nb": 'Opprett avdelingen "{department}".',
        "nn": 'Opprett avdelinga "{department}".',
        "en": 'Create department "{department}".',
        "es": 'Crea el departamento "{department}".',
        "pt": 'Crie o departamento "{department}".',
        "de": 'Erstellen Sie die Abteilung "{department}".',
        "fr": 'Creez le departement "{department}".',
    },
}


EXPECTED_TASKS = {
    "supplier": TaskType.CREATE_CUSTOMER,
    "employee": TaskType.CREATE_EMPLOYEE,
    "product": TaskType.CREATE_PRODUCT,
    "project": TaskType.CREATE_PROJECT,
    "invoice": TaskType.CREATE_INVOICE,
    "credit_note": TaskType.CREATE_CREDIT_NOTE,
    "travel_expense": TaskType.CREATE_TRAVEL_EXPENSE,
    "department": TaskType.CREATE_DEPARTMENT,
}


CASES = []
for family, templates in LANGUAGE_FAMILIES.items():
    for language, template in templates.items():
        for index, dataset in enumerate(DATASETS):
            prompt = template.format(**dataset)
            case_id = f"{family}-{language}-{index + 1}"
            CASES.append((case_id, prompt, EXPECTED_TASKS[family]))


@pytest.mark.parametrize("case_id,prompt,expected_task", CASES, ids=[case[0] for case in CASES])
def test_large_prompt_matrix(monkeypatch, case_id: str, prompt: str, expected_task: TaskType) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(prompt)

    assert parsed.task_type == expected_task, case_id
