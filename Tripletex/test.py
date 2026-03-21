import os
import time
from typing import Dict, List, Optional

import requests

BASE_API = os.environ["TRIPLETEX_BASE_URL"]
TOKEN = os.environ["TRIPLETEX_SESSION_TOKEN"]
SOLVE_URL = "http://127.0.0.1:8011/solve"

AUTH = ("0", TOKEN)

suffix = str(int(time.time()))
customer_name = f"Acme AS {suffix}"
customer_email = f"post{suffix}@acme.no"
employee_first = "Ola"
employee_last = f"Nordmann{suffix}"
employee_email = f"ola{suffix}@example.com"
project_name = f"Alpha Prosjekt {suffix}"


def call_solve(prompt: str, files: Optional[List[Dict]] = None) -> requests.Response:
    payload = {
        "prompt": prompt,
        "files": files or [],
        "tripletex_credentials": {
            "base_url": BASE_API,
            "session_token": TOKEN,
        },
    }
    return requests.post(SOLVE_URL, json=payload, timeout=120)


def get_names(endpoint: str) -> List[str]:
    r = requests.get(f"{BASE_API}/{endpoint}", auth=AUTH, timeout=30)
    r.raise_for_status()
    data = r.json()
    return [x.get("name") for x in data.get("values", []) if isinstance(x, dict)]


def verify_departments(expected: List[str]) -> bool:
    names = get_names("department")
    print("Departments now:", names)
    return all(name in names for name in expected)


def verify_customers(expected: List[str]) -> bool:
    names = get_names("customer")
    print("Customers now:", names)
    return all(name in names for name in expected)


def verify_employees(email: str) -> bool:
    r = requests.get(
        f"{BASE_API}/employee",
        params={"fields": "id,firstName,lastName,email", "count": 200},
        auth=AUTH,
        timeout=30,
    )
    r.raise_for_status()
    users = r.json().get("values", [])
    matches = [user for user in users if user.get("email") == email]
    print("Employees now:", [(u.get("firstName"), u.get("lastName"), u.get("email")) for u in matches])
    return bool(matches)


def verify_projects(name: str) -> bool:
    r = requests.get(
        f"{BASE_API}/project",
        params={"fields": "id,name", "count": 200},
        auth=AUTH,
        timeout=30,
    )
    r.raise_for_status()
    projects = r.json().get("values", [])
    matches = [proj for proj in projects if proj.get("name") == name]
    print("Projects now:", [p.get("name") for p in matches])
    return bool(matches)


TESTS: List[Dict] = [
    {
        "name": "create_department_basic",
        "prompt": "Opprett tre avdelinger: Kundeservice, InnkjÃ¸p og Regnskap.",
        "verify": lambda: verify_departments(["Kundeservice", "InnkjÃ¸p", "Regnskap"]),
    },
    {
        "name": "create_customer_basic",
        "prompt": f"Opprett en kunde som heter {customer_name} med e-post {customer_email}.",
        "verify": lambda: verify_customers([customer_name]),
    },
    {
        "name": "create_employee_basic",
        "prompt": f"Opprett en ansatt som heter {employee_first} {employee_last} med e-post {employee_email}.",
        "verify": lambda: verify_employees(employee_email),
    },
    {
        "name": "create_project_basic",
        "prompt": f"Opprett et prosjekt som heter {project_name} for kunden {customer_name}.",
        "verify": lambda: verify_projects(project_name),
    },
]


def run_test(test: Dict) -> bool:
    print(f"\n=== RUNNING {test['name']} ===")
    response = call_solve(test["prompt"])
    print("Solve status:", response.status_code)
    print("Solve body:", response.text)

    if response.status_code != 200:
        print("FAIL: /solve did not return 200")
        return False

    try:
        ok = test["verify"]()
    except Exception as exc:
        print("FAIL: verification crashed:", exc)
        return False

    if ok:
        print("PASS")
        return True

    print("FAIL: verification did not match expected result")
    return False


def main() -> None:
    passed = 0
    for test in TESTS:
        if run_test(test):
            passed += 1
    print(f"\nPassed {passed}/{len(TESTS)} tests")


if __name__ == "__main__":
    main()
