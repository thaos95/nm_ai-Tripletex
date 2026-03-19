import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import httpx


DEFAULT_ENDPOINT = "https://tripletex-agent-538030928814.europe-north1.run.app/solve"
DEFAULT_BASE_URL = "https://kkpqfuj-amager.tripletex.dev/v2"


@dataclass
class TestCase:
    name: str
    prompt: str
    files: List[dict]


def build_test_cases() -> List[TestCase]:
    suffix = os.getenv("TRIPLETEX_TEST_SUFFIX") or datetime.utcnow().strftime("%m%d%H%M%S")
    customer_name = "Nordlys Test {0} AS".format(suffix)
    customer_email = "nordlys.{0}@example.org".format(suffix)
    employee_full_name = "Marte Solberg {0}".format(suffix)
    employee_email = "marte.solberg.{0}@example.org".format(suffix)
    product_name = "Analysepakke {0}".format(suffix)
    department_number = str(int(suffix[-4:]))
    project_name = "Strategi {0}".format(suffix)
    customer_es = "Cliente Verde {0} SL".format(suffix)
    customer_fr = "Client Bleu {0} SARL".format(suffix)
    customer_de = "Blau {0} GmbH".format(suffix)

    return [
        TestCase("create_customer_no", "Opprett kunde {0}, {1}".format(customer_name, customer_email), []),
        TestCase("update_customer_no", "Oppdater kunde {0} med telefon +47 48001234".format(customer_name), []),
        TestCase(
            "create_employee_no",
            "Opprett en ansatt med navn {0}, {1}.".format(employee_full_name, employee_email),
            [],
        ),
        TestCase(
            "update_employee_no",
            "Oppdater ansatt {0} med e-post {1} og telefon +47 41234567".format(employee_full_name, employee_email),
            [],
        ),
        TestCase("create_product_no", "Opprett produkt {0} 2500".format(product_name), []),
        TestCase("create_department_no", "Opprett avdeling Strategi {0}".format(department_number), []),
        TestCase("create_project_no", "Opprett prosjekt {0} for kunde {1}".format(project_name, customer_name), []),
        TestCase(
            "create_order_en",
            'Create order for customer "{0}" with product "{1}" 2500'.format(customer_name, product_name),
            [],
        ),
        TestCase("create_customer_es", "Crear cliente {0}, cliente.verde.{1}@example.org".format(customer_es, suffix), []),
        TestCase("create_customer_fr", "Creer client {0}, client.bleu.{1}@example.org".format(customer_fr, suffix), []),
        TestCase("create_customer_de", "Erstellen Sie einen Kunden {0}, blau.{1}@example.org".format(customer_de, suffix), []),
        TestCase(
            "create_project_oakwood",
            'Create the project "Analysis Oakwood" linked to the customer Oakwood Ltd (org no. 849612913). '
            "The project manager is Lucy Taylor (lucy.taylor@example.org).",
            [],
        ),
        TestCase("create_travel_expense_no", "Opprett reiseregning 2026-03-19 med belop 450", []),
        TestCase("delete_travel_expense_no", "Slett reiseregning 42", []),
        TestCase("delete_voucher_no", "Slett bilag 7", []),
        TestCase(
            "create_invoice_en",
            'Create invoice for customer "{0}" with product "{1}" 2500'.format(customer_name, product_name),
            [],
        ),
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

    test_cases = build_test_cases()
    selected_cases = [case for case in test_cases if not only_name or case.name == only_name]
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
