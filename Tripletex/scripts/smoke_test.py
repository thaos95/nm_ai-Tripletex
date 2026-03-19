import json
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

import httpx


DEFAULT_ENDPOINT = "https://tripletex-agent-538030928814.europe-north1.run.app/solve"
DEFAULT_BASE_URL = "https://kkpqfuj-amager.tripletex.dev/v2"


@dataclass
class TestCase:
    name: str
    prompt: str
    files: List[dict]


TEST_CASES = [
    TestCase("create_customer_no", "Opprett kunde Nordlys Test AS, nordlys.test@example.org", []),
    TestCase("update_customer_no", "Oppdater kunde Nordlys Test AS med telefon +47 48001234", []),
    TestCase(
        "create_employee_no",
        "Opprett en ansatt med navn Marte Solberg, marte.solberg.unique@example.org.",
        [],
    ),
    TestCase("update_employee_no", "Oppdater ansatt Marte Solberg med telefon +47 41234567", []),
    TestCase("create_product_no", "Opprett produkt Analysepakke 2500", []),
    TestCase("create_department_no", "Opprett avdeling Strategi 501", []),
    TestCase("create_project_no", "Opprett prosjekt Strategi 2026 for kunde Nordlys Test AS", []),
    TestCase("create_order_en", 'Create order for customer "Nordlys Test AS" with product "Analysepakke" 2500', []),
    TestCase("create_customer_es", "Crear cliente Cliente Verde SL, cliente.verde.unique@example.org", []),
    TestCase("create_customer_fr", "Creer client Client Bleu SARL, client.bleu.unique@example.org", []),
    TestCase("create_customer_de", "Erstellen Sie einen Kunden Blau GmbH, blau.gmbh.unique@example.org", []),
    TestCase(
        "create_project_oakwood",
        'Create the project "Analysis Oakwood" linked to the customer Oakwood Ltd (org no. 849612913). '
        "The project manager is Lucy Taylor (lucy.taylor@example.org).",
        [],
    ),
    TestCase("create_travel_expense_no", "Opprett reiseregning 2026-03-19 med belop 450", []),
    TestCase("delete_travel_expense_no", "Slett reiseregning 42", []),
    TestCase("delete_voucher_no", "Slett bilag 7", []),
    TestCase("create_invoice_en", 'Create invoice for customer "Nordlys Test AS" with product "Analysepakke" 2500', []),
]


def build_payload(prompt: str, files: List[dict], base_url: str, session_token: str) -> dict:
    return {
        "prompt": prompt,
        "files": files,
        "tripletex_credentials": {
            "base_url": base_url,
            "session_token": session_token,
        },
    }


def run_test_case(
    client: httpx.Client,
    endpoint: str,
    base_url: str,
    session_token: str,
    test_case: TestCase,
) -> bool:
    payload = build_payload(test_case.prompt, test_case.files, base_url, session_token)
    response = client.post(endpoint, json=payload)
    ok = response.status_code == 200 and response.json() == {"status": "completed"}
    if ok:
        print("PASS {0}".format(test_case.name))
        return True

    print("FAIL {0}".format(test_case.name))
    print("  status={0}".format(response.status_code))
    try:
        print("  body={0}".format(json.dumps(response.json(), ensure_ascii=True)))
    except Exception:
        print("  body={0}".format(response.text))
    return False


def main() -> int:
    session_token = os.getenv("TRIPLETEX_SESSION_TOKEN")
    if not session_token:
        print("Missing TRIPLETEX_SESSION_TOKEN")
        return 1

    endpoint = os.getenv("TRIPLETEX_SOLVE_URL", DEFAULT_ENDPOINT)
    base_url = os.getenv("TRIPLETEX_BASE_URL", DEFAULT_BASE_URL)
    only_name: Optional[str] = os.getenv("TRIPLETEX_TEST_NAME")

    selected_cases = [case for case in TEST_CASES if not only_name or case.name == only_name]
    if not selected_cases:
        print("No test cases matched TRIPLETEX_TEST_NAME={0}".format(only_name))
        return 1

    passed = 0
    with httpx.Client(timeout=60.0, trust_env=False) as client:
        for case in selected_cases:
            if run_test_case(client, endpoint, base_url, session_token, case):
                passed += 1

    print("{0}/{1} passed".format(passed, len(selected_cases)))
    return 0 if passed == len(selected_cases) else 1


if __name__ == "__main__":
    sys.exit(main())
