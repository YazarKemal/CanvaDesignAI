import json

import pytest

from src.canva_client import API_BASE, CanvaAPIError, CanvaClient, CanvaJobTimeoutError


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0)


def test_upload_asset_returns_immediately_on_success():
    session = _FakeSession(
        [_FakeResponse(200, {"job": {"id": "job1", "status": "success", "asset": {"id": "asset1"}}})]
    )
    client = CanvaClient(access_token="tok", session=session)

    asset_id = client.upload_asset(b"bytes", name="Grand Opening Cafe")

    assert asset_id == "asset1"
    assert session.calls[0]["url"] == f"{API_BASE}/asset-uploads"
    assert session.calls[0]["headers"]["Content-Type"] == "application/octet-stream"


def test_upload_asset_polls_until_success():
    session = _FakeSession(
        [
            _FakeResponse(200, {"job": {"id": "job1", "status": "in_progress"}}),
            _FakeResponse(200, {"job": {"id": "job1", "status": "in_progress"}}),
            _FakeResponse(200, {"job": {"id": "job1", "status": "success", "asset": {"id": "asset1"}}}),
        ]
    )
    client = CanvaClient(access_token="tok", session=session)

    asset_id = client.upload_asset(b"bytes", name="Cafe", poll_interval=0)

    assert asset_id == "asset1"
    assert len(session.calls) == 3


def test_upload_asset_raises_on_job_failure():
    session = _FakeSession(
        [
            _FakeResponse(200, {"job": {"id": "job1", "status": "in_progress"}}),
            _FakeResponse(200, {"job": {"id": "job1", "status": "failed", "error": {"message": "bad image"}}}),
        ]
    )
    client = CanvaClient(access_token="tok", session=session)

    with pytest.raises(CanvaAPIError):
        client.upload_asset(b"bytes", name="Cafe", poll_interval=0)


def test_upload_asset_times_out(monkeypatch):
    session = _FakeSession([_FakeResponse(200, {"job": {"id": "job1", "status": "in_progress"}})] * 5)
    client = CanvaClient(access_token="tok", session=session)

    ticks = iter([0, 0.1, 10, 10])

    with pytest.raises(CanvaJobTimeoutError):
        client._poll_job(
            "/asset-uploads/job1",
            poll_interval=0,
            max_wait=1.0,
            sleep=lambda _s: None,
            clock=lambda: next(ticks),
        )


def test_create_design_returns_edit_url():
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                {
                    "design": {
                        "id": "design1",
                        "urls": {"edit_url": "https://canva.com/edit/design1", "view_url": "https://canva.com/view/design1"},
                    }
                },
            )
        ]
    )
    client = CanvaClient(access_token="tok", session=session)

    result = client.create_design(design_type="poster", asset_id="asset1", title="Grand Opening Cafe")

    assert result == {
        "id": "design1",
        "edit_url": "https://canva.com/edit/design1",
        "view_url": "https://canva.com/view/design1",
    }
    body = session.calls[0]["json"]
    assert body["design_type"] == {"type": "preset", "name": "poster"}
    assert body["asset_id"] == "asset1"


def test_request_raises_canva_api_error_on_failure():
    session = _FakeSession([_FakeResponse(400, {"error": "bad request"})])
    client = CanvaClient(access_token="tok", session=session)

    with pytest.raises(CanvaAPIError):
        client.create_design(design_type="poster")


def test_export_design_polls_and_returns_urls():
    session = _FakeSession(
        [
            _FakeResponse(200, {"job": {"id": "export1", "status": "in_progress"}}),
            _FakeResponse(200, {"job": {"id": "export1", "status": "success", "urls": ["https://files.canva.com/x.png"]}}),
        ]
    )
    client = CanvaClient(access_token="tok", session=session)

    urls = client.export_design("design1", format_type="png", poll_interval=0)

    assert urls == ["https://files.canva.com/x.png"]
