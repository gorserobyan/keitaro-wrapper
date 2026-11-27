"""Thin async client for the Keitaro Admin API v1."""

from typing import Any

import httpx

from app.config import get_settings


class KeitaroError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class KeitaroClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 20.0):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise KeitaroError(502, f"Keitaro is unreachable: {exc}") from exc
        if resp.status_code >= 400:
            try:
                body = resp.json()
                message = body.get("error") or body.get("detail") or resp.text
            except ValueError:
                message = resp.text
            raise KeitaroError(resp.status_code, f"Keitaro {method} {path}: {message}")
        if not resp.content:
            return None
        return resp.json()

    # --- catalog (read only) ---
    async def list_offers(self) -> list[dict]:
        return await self._request("GET", "/offers")

    async def get_offer(self, offer_id: int) -> dict:
        return await self._request("GET", f"/offers/{offer_id}")

    async def list_domains(self) -> list[dict]:
        return await self._request("GET", "/domains")

    async def list_groups(self) -> list[dict]:
        return await self._request("GET", "/groups", params={"type": "campaigns"})

    async def list_traffic_sources(self) -> list[dict]:
        return await self._request("GET", "/traffic_sources")

    # --- campaigns ---
    async def list_campaigns(self) -> list[dict]:
        return await self._request("GET", "/campaigns")

    async def get_campaign(self, campaign_id: int) -> dict:
        return await self._request("GET", f"/campaigns/{campaign_id}")

    async def create_campaign(self, payload: dict) -> dict:
        return await self._request("POST", "/campaigns", json=payload)

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._request("DELETE", f"/campaigns/{campaign_id}")

    # --- streams ---
    async def list_streams(self, campaign_id: int) -> list[dict]:
        return await self._request("GET", f"/campaigns/{campaign_id}/streams")

    async def get_stream(self, stream_id: int) -> dict:
        return await self._request("GET", f"/streams/{stream_id}")

    async def create_stream(self, payload: dict) -> dict:
        return await self._request("POST", "/streams", json=payload)

    async def update_stream(self, stream_id: int, payload: dict) -> dict:
        return await self._request("PUT", f"/streams/{stream_id}", json=payload)


_client: KeitaroClient | None = None


def get_keitaro() -> KeitaroClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = KeitaroClient(s.keitaro_api_base, s.keitaro_api_key)
    return _client


async def close_keitaro() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
