# Prompt Inventory

Denne oversikten er bygd fra filer som faktisk ligger i repoet. Jeg fant ingen egen logg over historiske submits, saa dette er den naermeste komplette lokale oversikten over JSON-oppgaver og promptene som brukes ved submit/inspect.

## 1. JSON-filer i repoet

Disse filene inneholder faktiske request-bodies med `prompt`-felt:

- `Tripletex/fixtures/sample_request.json`
  - `Opprett en ansatt med navn Ola Nordmann, ola@example.org. Han skal vaere kontoadministrator.`
- `Tripletex/fixtures/sample_order_request.json`
  - `Create order for customer "Acme AS" with product "Consulting" 1500`
- `Tripletex/fixtures/sample_invoice_request.json`
  - `Create invoice for customer "Acme AS" with product "Consulting" 1500`
- `Tripletex/temp_customer.json`
  - `Opprett kunde Test Kunde AS, testkunde@example.org`
- `Tripletex/temp_order.json`
  - `Create order for customer "Test Kunde AS" with product "Konsulenttime" 1500`
- `Tripletex/temp_department.json`
  - `Opprett avdeling Marked`

## 2. Eksplisitte prompt-oppgaver i tester

Disse promptene ligger som eksplisitte strenger i testene og er de mest konkrete "oppgavene" i repoet.

### Fra `tests/test_app.py`

- `Opprett en ansatt med navn Ola Nordmann, ola@example.org. Han skal vaere kontoadministrator.`
- `Erfassen Sie 32 Stunden für Hannah Richter (hannah.richter@example.org) auf der Aktivität "Design" im Projekt "E-Commerce-Entwicklung" für Bergwerk GmbH (Org.-Nr. 920065007). Stundensatz: 1550 NOK/h. Erstellen Sie eine Projektrechnung an den Kunden basierend auf den erfassten Stunden.`
- `Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) på 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.`
- `Oppdater reiseregning 42 med beløp 950 og dato 2026-03-19`
- `Oppdater kunde Acme AS med telefon +47 12345678`
- `Hent ansatte`
- `Finn alle kunder med orgnr 849612913`
- `Oppdater ansatt Marte Solberg med telefon +47 41234567`
- `Create invoice for customer "Acme AS" with product "Consulting" 1500`
- `Slett reiseregning 42`
- `Opprett reiseregning 2026-03-19 med belop 450`
- `Slett bilag 7`
- `Opprett kunde Acme AS`
- `Opprett kunde Acme AS, acme@example.org`
- `Registrer leverandøren Dalheim AS med organisasjonsnummer 892196753. Adressa er Parkveien 45, 5003 Bergen. E-post: faktura@dalheim.no.`
- `Wir haben einen neuen Mitarbeiter namens Leonie Becker, geboren am 17. January 1996. Bitte legen Sie ihn als Mitarbeiter mit der E-Mail leonie.becker@example.org und dem Startdatum 12. January 2026 an.`
- `Me har ein ny tilsett som heiter Geir Stolsvik, fodd 6. March 1990. Opprett vedkomande som tilsett med e-post geir.stlsvik@example.org og startdato 14. November 2026.`
- `Opprett produktet "Havregryn" med produktnummer 3113. Prisen er 29250 kr eksklusiv MVA, og MVA-sats for næringsmiddel på 15 % skal nyttast.`
- `Créez et envoyez une facture au client Étoile SARL (nº org. 995085488) de 7250 NOK hors TVA. La facture concerne Rapport d'analyse.`
- `Crea y envía una factura al cliente Montaña SL (org. nº 831306742) por 48600 NOK sin IVA. La factura es por Licencia de software.`
- `The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.`
- `O cliente Floresta Lda (org. nº 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.`
- `Opprett og send ein faktura til kunden Strandvik AS (org.nr 993504815) på 1800 kr eksklusiv MVA. Fakturaen gjeld Opplæring.`
- `Erstellen Sie drei Abteilungen in Tripletex: "Utvikling", "Innkjøp" und "Økonomi".`
- `Betalinga frå Strandvik AS (org.nr 859256333) for fakturaen "Nettverksteneste" (41550 kr ekskl. MVA) vart returnert av banken. Reverser betalinga slik at fakturaen igjen viser uteståande beløp.`
- `Erstellen Sie einen Auftrag für den Kunden Waldstein GmbH (Org.-Nr. 899060113) mit den Produkten Netzwerkdienst (5411) zu 29200 NOK und Schulung (7883) zu 10350 NOK. Wandeln Sie den Auftrag in eine Rechnung um und registrieren Sie die vollständige Zahlung.`

### Fra `tests/test_inspect_hard_prompt_pack.py`

- `Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) på 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.`
- `Créez et envoyez une facture au client Etoile SARL (nº org. 995085488) de 7250 NOK hors TVA. La facture concerne Rapport d'analyse.`
- `The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.`
- `O cliente Floresta Lda (org. nº 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.`
- `Kunden Fossekraft AS (org.nr 918737227) har reklamert på fakturaen for "Konsulenttimar" (16200 kr ekskl. MVA). Opprett ei fullstendig kreditnota som reverserer heile fakturaen.`
- `Crea el proyecto "Implementación Dorada" vinculado al cliente Dorada SL (org. nº 831075392). El director del proyecto es Isabel Rodríguez (isabel.rodriguez@example.org).`
- `Crie o projeto "Implementação Rio" vinculado ao cliente Rio Azul Lda (org. nº 827937223). O gerente de projeto é Gonçalo Oliveira (goncalo.oliveira@example.org).`
- `Sett fastpris 203000 kr på prosjektet "Digital transformasjon" for Stormberg AS (org.nr 834028719). Prosjektleder er Hilde Hansen (hilde.hansen@example.org). Fakturer kunden for 75 % av fastprisen som en delbetaling.`
- `Registrer 28 timar for Bjørn Kvamme (bjrn.kvamme@example.org) på aktiviteten "Analyse" i prosjektet "Datamigrering" for Fjelltopp AS (org.nr 986191127). Timesats: 1200 kr/t. Generer ein prosjektfaktura til kunden basert på dei registrerte timane.`
- `Erfassen Sie 32 Stunden für Hannah Richter (hannah.richter@example.org) auf der Aktivität "Design" im Projekt "E-Commerce-Entwicklung" für Bergwerk GmbH (Org.-Nr. 920065007). Stundensatz: 1550 NOK/h. Erstellen Sie eine Projektrechnung an den Kunden basierend auf den erfassten Stunden.`
- `Registrer ei reiserekning for Svein Berge (svein.berge@example.org) for "Kundebesøk Trondheim". Reisa varte 5 dagar med diett (dagssats 800 kr). Utlegg: flybillett 2850 kr og taxi 200 kr.`
- `Oppdater reiseregning 42 med beløp 950 og dato 2026-03-19.`
- `Crie uma dimensão contabilística personalizada "Marked" com os valores "Bedrift" e "Privat". Em seguida, lance um documento na conta 6590 por 16750 NOK, vinculado ao valor de dimensão "Bedrift".`
- `Run payroll for James Williams (james.williams@example.org) for this month. The base salary is 34950 NOK. Add a one-time bonus of 15450 NOK on top of the base salary. If the salary API is unavailable, you can use manual vouchers on salary accounts (5000-series) to record the payroll expense.`

### Fra `tests/test_hidden_prompt_corpus.py`

- `Registe o fornecedor Solmar Lda com numero de organizacao 978911226. E-mail: faktura@solmarlda.no.`
- `Me har ein ny tilsett som heiter Gunnhild Eide, fodd 21. June 1997. Opprett vedkomande som tilsett med e-post gunnhild.eide@example.org og startdato 28. June 2026.`
- `Opprett produktet "Konsulenttimar" med produktnummer 3923. Prisen er 26400 kr eksklusiv MVA, og standard MVA-sats pa 25 % skal nyttast.`
- `Opprett tre avdelingar i Tripletex: "Okonomi", "Administrasjon" og "Innkjop".`
- `Crea el proyecto "Implementacion Dorada" vinculado al cliente Dorada SL (org. no 831075392). El director del proyecto es Isabel Rodriguez (isabel.rodriguez@example.org).`
- `Crie o projeto "Integracao Porto" vinculado ao cliente Porto Alegre Lda (org. no 872798277). O gerente de projeto e Andre Oliveira (andre.oliveira@example.org).`
- `Crie o projeto "Implementacao Rio" vinculado ao cliente Rio Azul Lda (org. no 827937223). O gerente de projeto e Goncalo Oliveira (goncalo.oliveira@example.org).`
- `Erstellen Sie das Produkt "Datenberatung" mit der Produktnummer 7855. Der Preis betragt 41550 NOK ohne MwSt., mit dem Standardsatz von 25 %.`
- `Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) pa 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.`
- `O cliente Floresta Lda (org. no 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.`

### Fra `tests/test_tier2_workflow_matrix.py`

- `Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) pa 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.`
- `The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.`
- `O cliente Floresta Lda (org. no 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.`
- `Crea el proyecto "Implementacion Dorada" vinculado al cliente Dorada SL (org. no 831075392). El director del proyecto es Isabel Rodriguez (isabel.rodriguez@example.org).`
- `Crie o projeto "Implementacao Rio" vinculado ao cliente Rio Azul Lda (org. no 827937223). O gerente de projeto e Goncalo Oliveira (goncalo.oliveira@example.org).`

## 3. Stor generert promptmatrise

`tests/test_large_prompt_matrix.py` genererer ikkje bare noen faa prompts. Den lager **294 prompt-cases** totalt.

Regnestykket er:

- 6 datasett med ulike navn, firma, organisasjonsnummer, belop osv.
- 49 sprakmaler totalt
- 6 x 49 = 294 genererte prompts

### Oppgavetyper i den genererte matrisen

- `supplier` -> create_customer
- `employee` -> create_employee
- `product` -> create_product
- `project` -> create_project
- `invoice` -> create_invoice
- `credit_note` -> create_credit_note
- `travel_expense` -> create_travel_expense
- `department` -> create_department

### Sprakdekning per oppgavetype

- `supplier`: nb, nn, en, pt, de, fr
- `employee`: nb, nn, en, de
- `product`: nb, nn, en, es, pt, de
- `project`: nb, nn, en, es, pt, de, fr
- `invoice`: nb, nn, en, es, fr
- `credit_note`: nb, nn, en, es, pt, de, fr
- `travel_expense`: nb, nn, en, es, pt, de, fr
- `department`: nb, nn, en, es, pt, de, fr

### Datasettverdier som kombineres inn i promptene

Det brukes 6 sett med virksomheter/personer, blant annet:

- `Nordlys Leveranse AS` / `Nordlys AS` / `Ola Hansen` / org `912345670`
- `Fjord Partner AS` / `Kari Lie` / org `923456781`
- `Berg Data AS` / `Arne Berge` / org `934567892`
- `Vest Regnskap AS` / `Nora Dahl` / org `945678903`
- `Aasen Konsult AS` / `Mina Larsen` / org `956789014`
- `Solberg Partner AS` / `Even Moen` / org `967890125`

### Basemaler som utvides til hundrevis av prompts

- Leverandor:
  - `Registrer leverandoren {supplier} med organisasjonsnummer {org}. E-post: {email}.`
  - `Create supplier {supplier} with organization number {org}. Email: {email}.`
  - `Registe o fornecedor {supplier} com numero de organizacao {org}. E-mail: {email}.`
- Ansatt:
  - `Opprett en ansatt som heter {first} {last} med e-post {email}.`
  - `Create employee {first} {last} with email {email}.`
  - `Erstellen Sie den Mitarbeiter {first} {last} mit E-Mail {email}.`
- Produkt:
  - `Opprett produktet "{product}" for {amount} kr.`
  - `Create product "{product}" for {amount} NOK.`
  - `Crie o produto "{product}" por {amount} NOK.`
- Prosjekt:
  - `Opprett prosjektet "{project}" knyttet til kunden {customer} (org.nr {org}). Prosjektleder er {first} {last} ({email}).`
  - `Create the project "{project}" linked to customer {customer} (org no. {org}). The project manager is {first} {last} ({email}).`
  - `Crie o projeto "{project}" vinculado ao cliente {customer} (org. n {org}). O gerente de projeto e {first} {last} ({email}).`
- Faktura:
  - `Opprett og send en faktura til kunden {customer} (org.nr {org}) pa {amount} kr eksklusiv MVA. Fakturaen gjelder {desc}.`
  - `Create and send an invoice to customer {customer} (org no. {org}) for {amount} NOK excluding VAT. The invoice is for {desc}.`
  - `Crea y envia una factura al cliente {customer} (org. n {org}) por {amount} NOK sin IVA. La factura es por {desc}.`
- Kreditnota:
  - `Opprett en full kreditnota for kunden {customer} (org.nr {org}) for "{desc}" pa {amount} kr.`
  - `Create a full credit note for customer {customer} (org no. {org}) for "{desc}" {amount} NOK.`
  - `Erstellen Sie eine vollstandige Gutschrift fur den Kunden {customer} (Org.-Nr. {org}) fur "{desc}" uber {amount} NOK.`
- Reiseregning:
  - `Registrer en reiseregning for {first} {last} ({email}). Reisen varte {days} dager med diett (dagssats {rate} kr). Utlegg: hotell {expense} kr.`
  - `Register a travel expense for {first} {last} ({email}). The trip lasted {days} days with per diem ({rate} NOK per day). Expenses: hotel {expense} NOK.`
  - `Registe uma despesa de viagem para {first} {last} ({email}). A viagem durou {days} dias com dieta ({rate} NOK por dia). Despesas: hotel {expense} NOK.`
- Avdeling:
  - `Opprett avdelingen "{department}".`
  - `Create department "{department}".`
  - `Erstellen Sie die Abteilung "{department}".`

## 4. Hva dette faktisk sier om "oppgavene du har fått"

Lokalt i repoet ser oppgavene ut til a falle i disse hovedklassene:

- Opprette eller oppdatere ansatte
- Opprette eller oppdatere kunder og leverandorer
- Opprette produkter
- Opprette prosjekter og knytte prosjektleder/kunde
- Opprette ordre og faktura
- Registrere betaling eller reversere betaling
- Opprette kreditnota
- Opprette og oppdatere reiseregninger
- Opprette avdelinger
- Opprette dimensjonsbilag
- Kjore lonn / payroll-voucher
- Slette reiseregning eller bilag
- Hente ansatte eller soke etter kunder

## 5. Begrensning

Jeg fant ingen fil som viser en faktisk kronologisk historikk over dine submits med eksakt respons fra konkurranse-endepunktet. Rapporten over er derfor en komplett lokal inventarliste over prompts som ligger i kodebasen, ikke en sikker "server-logg" over alt du har sendt inn.
