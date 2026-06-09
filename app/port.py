from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import Settings
from app.slack import ReleaseAnnouncement


class PortClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token: str | None = None
        self._expires_at = 0.0

    async def upsert_slack_use_case(self, announcement: ReleaseAnnouncement) -> None:
        token = await self._get_access_token()
        entity = {
            "identifier": announcement.identifier,
            "title": announcement.title,
            "properties": announcement.properties,
        }
        endpoint = (
            f"{self.settings.port_base_url}/v1/blueprints/"
            f"{self.settings.port_blueprint_identifier}/entities"
        )
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds
        ) as client:
            response = await client.post(
                endpoint,
                params={"upsert": "true", "merge": "true"},
                headers={"Authorization": f"Bearer {token}"},
                json=entity,
            )
            response.raise_for_status()

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at:
            return self._access_token

        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds
        ) as client:
            response = await client.post(
                f"{self.settings.port_base_url}/v1/auth/access_token",
                json={
                    "clientId": self.settings.port_client_id,
                    "clientSecret": self.settings.port_client_secret,
                },
            )
            response.raise_for_status()

        payload: dict[str, Any] = response.json()
        access_token = payload.get("accessToken")
        if not access_token:
            raise RuntimeError("Port authentication response did not include accessToken")

        expires_in = int(payload.get("expiresIn") or payload.get("expires_in") or 900)
        self._access_token = access_token
        self._expires_at = time.time() + max(expires_in - 60, 0)
        return access_token
