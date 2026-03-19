from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx


class TripletexClientError(RuntimeError):
    pass


@dataclass
class TripletexClient:
    base_url: str
    session_token: str
    verify_tls: bool = True
    transport: Optional[httpx.BaseTransport] = None
    operations: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url.rstrip("/"),
            auth=("0", self.session_token),
            timeout=20.0,
            verify=self.verify_tls,
            transport=self.transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        self.operations.append(
            {
                "method": method,
                "path": path,
                "params": kwargs.get("params"),
                "json": kwargs.get("json"),
                "status_code": response.status_code,
            }
        )
        if response.is_error:
            raise TripletexClientError(
                "Tripletex API error {0} on {1} {2}: {3}".format(
                    response.status_code, method, path, response.text
                )
            )
        if not response.content:
            return {}
        return response.json()

    def list_resource(self, resource: str, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/" + resource.strip("/"), params=params)

    def create_resource(self, resource: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/" + resource.strip("/"), json=payload)

    def update_resource(self, resource: str, resource_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", "/{0}/{1}".format(resource.strip("/"), resource_id), json=payload)

    def delete_resource(self, resource: str, resource_id: int) -> Dict[str, Any]:
        return self._request("DELETE", "/{0}/{1}".format(resource.strip("/"), resource_id))

    def _match_value(self, candidate: Dict[str, Any], field: str) -> Optional[str]:
        value = candidate.get(field)
        if value is not None:
            return str(value).strip().lower()
        nested_map = {
            "first_name": "firstName",
            "last_name": "lastName",
            "mobilePhoneNumber": "mobilePhoneNumber",
            "phoneNumberMobile": "phoneNumberMobile",
            "phoneNumber": "phoneNumber",
        }
        nested = nested_map.get(field)
        if nested and candidate.get(nested) is not None:
            return str(candidate.get(nested)).strip().lower()
        return None

    def find_single(self, resource: str, match_fields: Dict[str, Any], fields: str = "*") -> Optional[Dict[str, Any]]:
        if not match_fields:
            return None

        query_params = {"fields": fields, "count": 100}
        for key in ("name", "email", "first_name", "last_name"):
            if key in match_fields:
                param_name = "firstName" if key == "first_name" else "lastName" if key == "last_name" else key
                query_params[param_name] = match_fields[key]

        response = self.list_resource(resource, **query_params)
        values = response.get("values", [])
        if not values:
            return None

        normalized_match = dict((key, str(value).strip().lower()) for key, value in match_fields.items())
        exact_matches = []
        for candidate in values:
            if all(self._match_value(candidate, key) == value for key, value in normalized_match.items()):
                exact_matches.append(candidate)

        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(values) == 1:
            return values[0]
        return None

    def find_by_id(self, resource: str, resource_id: int, fields: str = "*") -> Optional[Dict[str, Any]]:
        response = self._request("GET", "/{0}/{1}".format(resource.strip("/"), resource_id), params={"fields": fields})
        if "value" in response and isinstance(response["value"], dict):
            return response["value"]
        if response:
            return response
        return None
