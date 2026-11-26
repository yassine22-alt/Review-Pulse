"""The hosted model is offered only when configured, is off for every project until the reviewer allows it, and the
setting survives a restart."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402


class Hosted:
    model, provider, external = "big-model", "groq", True


def test_health_reports_the_hosted_model_and_consent_is_per_project(tmp_path):
    with TestClient(create_app(tmp_path, llm=lambda: None, fallback=lambda: Hosted(), auth=False)) as c:
        h = c.get("/api/health").json()
        assert h["hosted"]["available"] and h["hosted"]["external"] and h["hosted"]["model"] == "big-model"
        assert "Groq" in (h["hosted"]["data_note"] or "")
        pid = c.post("/api/projects", json={"name": "t"}).json()["id"]
        assert c.get(f"/api/projects/{pid}").json()["external_consent"] is False       # off by default
        assert c.patch(f"/api/projects/{pid}", json={"external_consent": True}).json()["external_consent"] is True
    with TestClient(create_app(tmp_path, llm=lambda: None, fallback=lambda: Hosted(), auth=False)) as c2:   # a restart
        assert c2.get(f"/api/projects/{pid}").json()["external_consent"] is True


def test_without_a_hosted_model_nothing_is_offered(tmp_path):
    with TestClient(create_app(tmp_path, llm=lambda: None, fallback=lambda: None, auth=False)) as c:
        assert c.get("/api/health").json()["hosted"]["available"] is False
