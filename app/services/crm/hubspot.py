"""HubSpot adapter (CRM v3 API, private-app access token; works against a developer sandbox).

One request per push: `POST /crm/v3/objects/contacts/batch/upsert` with `idProperty=email`, so
HubSpot itself creates or updates the contact. That makes a retry after a crash harmless and
keeps the "upsert keyed by email" contract of `CrmClient`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.models import Lead, LeadScore

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.hubapi.com"
UPSERT_PATH = "/crm/v3/objects/contacts/batch/upsert"
TIMEOUT_SECONDS = 10.0


class HubSpotError(Exception):
    """A HubSpot call failed. The job runner retries it with backoff."""


class HubSpotAuthError(HubSpotError):
    """401/403: the token is wrong, expired or missing the crm.objects.contacts.write scope."""


class HubSpotRateLimited(HubSpotError):
    """429: HubSpot asked us to slow down. Retried by the job backoff."""


class HubSpotCrm:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        score_property: str = "",
        segment_property: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError("HubSpot needs CRM_API_TOKEN (a private app access token)")
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._score_property = score_property
        self._segment_property = segment_property
        self._transport = transport

    def build_properties(self, lead: Lead, score: LeadScore, segment: str) -> dict[str, str]:
        """Standard contact properties, plus the score/segment if custom properties are named.
        HubSpot rejects properties that do not exist in the portal, so the custom ones are
        opt-in (HUBSPOT_SCORE_PROPERTY / HUBSPOT_SEGMENT_PROPERTY)."""
        props: dict[str, str] = {"email": lead.email}
        optional = {
            "firstname": lead.first_name,
            "lastname": lead.last_name,
            "jobtitle": lead.job_title,
            "company": lead.company.name or lead.company.domain,
            "website": lead.company.domain,
        }
        props.update({k: v for k, v in optional.items() if v})
        if self._score_property:
            props[self._score_property] = str(score.score)
        if self._segment_property:
            props[self._segment_property] = segment
        return props

    async def upsert_lead(self, lead: Lead, score: LeadScore, segment: str) -> str:
        body = {
            "inputs": [
                {
                    "idProperty": "email",
                    "id": lead.email,
                    "properties": self.build_properties(lead, score, segment),
                }
            ]
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        # A client per call: each push runs in its own short-lived event loop.
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=TIMEOUT_SECONDS,
            transport=self._transport,
        ) as client:
            try:
                response = await client.post(UPSERT_PATH, json=body, headers=headers)
            except httpx.HTTPError as exc:
                raise HubSpotError(f"HubSpot request failed: {exc}") from exc
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> str:
        if response.status_code in (401, 403):
            raise HubSpotAuthError(f"HubSpot rejected the token ({response.status_code})")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "?")
            raise HubSpotRateLimited(f"HubSpot rate limit hit (Retry-After: {retry_after}s)")
        if response.status_code >= 400:
            raise HubSpotError(
                f"HubSpot returned {response.status_code}: {_error_message(response)}"
            )
        try:
            results: list[dict[str, Any]] = response.json()["results"]
            return str(results[0]["id"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise HubSpotError("HubSpot response did not contain a contact id") from exc


def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
        return str(data.get("message") or data)[:500]
    except ValueError:
        return response.text[:500]
