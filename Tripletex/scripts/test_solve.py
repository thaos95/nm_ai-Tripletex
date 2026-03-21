import json
from typing import List

import httpx

from app.attachment_parser import parse_attachments
from app.clients.tripletex import TripletexClient
from app.executor import execute_plan
from app.planner import create_plan
from app.schemas import SolveRequest, TripletexCredentials


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": {"id": 1}})

    return httpx.MockTransport(handler)


def run_local_scenario(prompt: str, files: List[dict]) -> None:
    request = SolveRequest(
        prompt=prompt,
        files=[],
        tripletex_credentials=TripletexCredentials(
            base_url="https://example.tripletex.dev/v2",
            session_token="dummy-token",
        ),
    )
    attachments = parse_attachments(request.files)
    plan = create_plan(request, attachments=attachments)

    client = TripletexClient(
        base_url=str(request.tripletex_credentials.base_url),
        session_token=request.tripletex_credentials.session_token,
        transport=_mock_transport(),
    )
    try:
        print("Plan steps:")
        for step in plan.steps:
            print(json.dumps(step.model_dump(), indent=2, ensure_ascii=False))

        result = execute_plan(client, plan)
        print("Executor result:", result)
    finally:
        client.close()

    print("Planned API operations:")
    for op in client.operations:
        print(json.dumps(op, indent=2, ensure_ascii=False))


def main() -> None:
    prompt = "Opprett tre avdelinger: Kundeservice, Innkjøp og Regnskap."
    run_local_scenario(prompt, files=[])


if __name__ == "__main__":
    main()
