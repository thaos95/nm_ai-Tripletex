from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional

import httpx

LOGGER = logging.getLogger(__name__)

ALLOWED_RESOURCES = {
    "employee",
    "customer",
    "product",
    "project",
    "invoice",
    "order",
    "department",
    "ledger",
    "travelExpense",
    "supplier",
    "supplierInvoice",
    "voucher",
    "bank",
    "currency",
    "company",
    "token",
    "subscription",
    "contact",
    "balanceSheet",
    "resultbudget",
    "salary",
}


class TripletexClientError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: Optional[int] = None,
        method: Optional[str] = None,
        path: Optional[str] = None,
        response_text: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        if message:
            super().__init__(message)
        elif status_code and method and path:
            text = response_text or ""
            super().__init__(f"Tripletex API error {status_code} on {method} {path}: {text}")
        else:
            super().__init__(message or "Tripletex client error")
        self.status_code = status_code
        self.method = method
        self.path = path
        self.response_text = response_text


@dataclass
class TripletexClient:
    base_url: str
    session_token: str
    verify_tls: bool = True
    timeout: float = 20.0
    transport: Optional[httpx.BaseTransport] = None
    operations: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url.rstrip("/"),
            auth=("0", self.session_token),
            timeout=self.timeout,
            verify=self.verify_tls,
            transport=self.transport,
            headers={"Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params or {})

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", path, json=payload)

    def put(self, path: str, payload: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("PUT", path, json=payload or {}, params=params or {})

    def delete(self, path: str) -> Dict[str, Any]:
        return self._request("DELETE", path)

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        normalized_path = self._normalize_path(path)
        self._ensure_allowed(normalized_path)

        print("TRIPLETEX REQUEST:", method, normalized_path, kwargs.get("json"))
        try:
            response = self._client.request(method, normalized_path, **kwargs)
        except httpx.HTTPError as exc:
            raise TripletexClientError(message=str(exc)) from exc
        self.operations.append(
            {
                "method": method,
                "path": normalized_path,
                "params": kwargs.get("params"),
                "json": kwargs.get("json"),
                "status_code": response.status_code,
            }
        )
        LOGGER.info(
            "Tripletex request method=%s path=%s status=%s payload=%s",
            method,
            normalized_path,
            response.status_code,
            kwargs.get("json"),
        )
        if response.is_error:
            raise TripletexClientError(
                status_code=response.status_code,
                method=method,
                path=normalized_path,
                response_text=response.text,
            )
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError:
            return {"text": response.text}
        return self._normalize_response(data)

    def _normalize_path(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        return normalized

    def _ensure_allowed(self, path: str) -> None:
        stripped = path.lstrip("/")
        first_segment = stripped.split("/", 1)[0].split(":", 1)[0]
        if first_segment not in ALLOWED_RESOURCES:
            raise TripletexClientError(message=f"Endpoint '{first_segment}' is not allowed")

    def _normalize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if "values" in data:
            return data
        if "value" in data:
            return {"value": data["value"]}
        return data
