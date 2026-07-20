"""Thin client for the Canva Connect API (asset upload + design creation).

Canva has no public "generate image from a prompt" endpoint, so this client
only covers what the Connect API actually offers:
  - upload an image you already have as an asset (`upload_asset`)
  - create a design from that asset (`create_design`)
  - export a design to a downloadable file (`export_design`)

Auth is a bearer access token obtained via Canva's OAuth2 (authorization
code + PKCE) flow — that interactive browser/redirect flow is out of scope
here, so this client expects a already-issued access token (see
CANVA_ACCESS_TOKEN in .env.example) and can refresh it given a refresh
token + client credentials.

NOTE: Canva's docs site blocked automated fetches while building this, so
endpoint paths/fields below are written from documentation knowledge and
should be spot-checked against api reference at canva.dev/docs/connect
before depending on this in production.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import requests

API_BASE = "https://api.canva.com/rest/v1"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"

DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_MAX_WAIT = 60.0


class CanvaAPIError(RuntimeError):
    pass


class CanvaJobTimeoutError(CanvaAPIError):
    pass


class CanvaClient:
    def __init__(self, *, access_token: str, session: requests.Session | None = None):
        self.access_token = access_token
        self.session = session or requests.Session()

    def _headers(self, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", **extra}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(method, f"{API_BASE}{path}", **kwargs)
        if not response.ok:
            raise CanvaAPIError(f"Canva API {method} {path} failed ({response.status_code}): {response.text}")
        return response.json()

    def _poll_job(
        self,
        path: str,
        *,
        job_key: str = "job",
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_wait: float = DEFAULT_MAX_WAIT,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> dict[str, Any]:
        deadline = clock() + max_wait
        while True:
            data = self._request("GET", path, headers=self._headers())
            job = data[job_key]
            if job["status"] == "success":
                return job
            if job["status"] == "failed":
                raise CanvaAPIError(f"Canva job failed: {job.get('error')}")
            if clock() >= deadline:
                raise CanvaJobTimeoutError(f"Canva job at {path} did not complete within {max_wait}s")
            sleep(poll_interval)

    def upload_asset(
        self,
        image_bytes: bytes,
        *,
        name: str,
        tags: list[str] | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_wait: float = DEFAULT_MAX_WAIT,
    ) -> str:
        """Upload raw image bytes as a Canva asset. Returns the asset ID."""
        name_b64 = base64.b64encode(name.encode("utf-8")).decode("ascii")
        metadata = {"name_base64": name_b64}
        if tags:
            metadata["tags"] = tags

        create = self._request(
            "POST",
            "/asset-uploads",
            data=image_bytes,
            headers=self._headers(
                **{
                    "Content-Type": "application/octet-stream",
                    "Asset-Upload-Metadata": _json_header(metadata),
                }
            ),
        )
        job = create["job"]
        if job["status"] == "success":
            return job["asset"]["id"]

        job = self._poll_job(
            f"/asset-uploads/{job['id']}", poll_interval=poll_interval, max_wait=max_wait
        )
        return job["asset"]["id"]

    def create_design(
        self,
        *,
        design_type: str,
        asset_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, str]:
        """Create a design (preset type, e.g. 'poster') from an uploaded asset.

        Returns {"id": design_id, "edit_url": ..., "view_url": ...}.
        """
        body: dict[str, Any] = {"design_type": {"type": "preset", "name": design_type}}
        if asset_id:
            body["asset_id"] = asset_id
        if title:
            body["title"] = title

        data = self._request("POST", "/designs", json=body, headers=self._headers())
        design = data["design"]
        return {
            "id": design["id"],
            "edit_url": design["urls"]["edit_url"],
            "view_url": design["urls"].get("view_url", ""),
        }

    def export_design(
        self,
        design_id: str,
        *,
        format_type: str = "png",
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_wait: float = DEFAULT_MAX_WAIT,
    ) -> list[str]:
        """Export a design and return the list of downloadable file URLs."""
        create = self._request(
            "POST",
            "/exports",
            json={"design_id": design_id, "format": {"type": format_type}},
            headers=self._headers(),
        )
        job = create["job"]
        if job["status"] != "success":
            job = self._poll_job("/exports/" + job["id"], poll_interval=poll_interval, max_wait=max_wait)
        return job["urls"]


def _json_header(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, separators=(",", ":"))


def refresh_access_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    session: requests.Session | None = None,
) -> dict[str, str]:
    """Exchange a refresh token for a new access token.

    Returns {"access_token": ..., "refresh_token": ..., "expires_in": ...}.
    """
    session = session or requests.Session()
    response = session.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    if not response.ok:
        raise CanvaAPIError(f"Canva token refresh failed ({response.status_code}): {response.text}")
    return response.json()
