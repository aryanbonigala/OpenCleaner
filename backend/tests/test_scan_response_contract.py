"""Scan response contract: api_version on ScanResult, timing/status on ScanSummary.

Closes the v0.1.1 APIContractLock gap noted in docs/VERSION_API_CONTRACT_AUDIT.md —
no code existed to surface api_version on the scan response, or per-scan
duration/status on ScanSummary.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.version import API_VERSION

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLEANER_DATA_DIR", str(tmp_path))
    assert get_settings().database_path == tmp_path / "opencleaner.db"
    yield tmp_path


def test_scan_response_includes_api_version_and_existing_fields(monkeypatch):
    monkeypatch.setenv("OPENCLEANER_USE_MOCK", "1")
    with TestClient(app) as client:
        resp = client.post("/api/scan")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["api_version"] == API_VERSION
    summary = body["summary"]
    for field in ("scan_id", "scan_schema_version", "platform", "mode", "items_count", "buckets", "generated_at"):
        assert field in summary


def test_scan_summary_status_is_success_when_no_scanner_warnings(monkeypatch):
    monkeypatch.setenv("OPENCLEANER_USE_MOCK", "1")
    with TestClient(app) as client:
        resp = client.post("/api/scan")
    summary = resp.json()["summary"]

    assert summary["scanner_warnings"] == []
    assert summary["status"] == "success"


def test_scan_summary_status_is_partial_success_when_all_scanner_groups_disabled(monkeypatch):
    # No OPENCLEANER_USE_MOCK: real-scanner path runs, finds zero toggles enabled,
    # records a warning, then falls back to the mock dataset (no live scanner calls).
    with TestClient(app) as client:
        patch = client.put(
            "/api/settings",
            json={
                "scanner_toggles": {
                    "performance": False,
                    "startup": False,
                    "tasks": False,
                    "files": False,
                    "browser": False,
                }
            },
        )
        assert patch.status_code == 200, patch.text
        resp = client.post("/api/scan")
    summary = resp.json()["summary"]

    assert summary["scanner_warnings"] != []
    assert summary["status"] == "partial_success"


def test_scan_summary_timing_fields_are_present_and_duration_non_negative(monkeypatch):
    monkeypatch.setenv("OPENCLEANER_USE_MOCK", "1")
    with TestClient(app) as client:
        resp = client.post("/api/scan")
    summary = resp.json()["summary"]

    assert summary["started_at"]
    assert summary["finished_at"]
    assert isinstance(summary["duration_ms"], int)
    assert summary["duration_ms"] >= 0


def test_latest_scan_round_trips_contract_fields(monkeypatch):
    monkeypatch.setenv("OPENCLEANER_USE_MOCK", "1")
    with TestClient(app) as client:
        posted = client.post("/api/scan")
        latest = client.get("/api/scan/latest")

    assert latest.json()["api_version"] == API_VERSION
    posted_summary = posted.json()["summary"]
    latest_summary = latest.json()["summary"]
    for field in ("started_at", "finished_at", "duration_ms", "status"):
        assert latest_summary[field] == posted_summary[field]
