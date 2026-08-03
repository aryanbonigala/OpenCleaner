"""Health response contract: machine-parseable `stage` field.

Closes the /health gap noted in docs/VERSION_API_CONTRACT_AUDIT.md — `stage` was
only embedded inside the free-text `version` string, with no distinct field.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

HEALTH_KEYS = {"status", "component", "version", "api_version", "stage", "scan_in_progress"}


def test_health_includes_stage_and_existing_fields():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert HEALTH_KEYS <= body.keys()
    assert isinstance(body["stage"], str)
    assert body["stage"]
