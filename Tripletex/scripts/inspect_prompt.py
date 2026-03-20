import json
import sys

import httpx


DEFAULT_URL = "http://127.0.0.1:8000/inspect"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_prompt.py \"<prompt>\" [url]")
        return 1

    prompt = sys.argv[1]
    url = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_URL

    with httpx.Client(timeout=30.0, trust_env=False) as client:
        response = client.post(url, json={"prompt": prompt, "files": []})

    print("status={0}".format(response.status_code))
    try:
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(response.text)
        return 1
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
