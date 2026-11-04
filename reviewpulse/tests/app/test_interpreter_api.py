"""The application exposes the same reviewed interpreter workflow as the CLI."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from reviewpulse.interpreter.api import interpreter_router
from reviewpulse.interpreter.schema import Program


def test_http_context_draft_review_approve_and_check():
    source = "1 Requirement.\n"
    program = Program.model_validate(
        {
            "id": "api",
            "document": "fixture",
            "title": "API rule",
            "requirement": {"node": "literal", "value": True},
            "sources": [{"clause": "1", "start": 0, "end": 1, "quote": "1"}],
        }
    )

    class Client:
        model = "test"

        def complete(self, system, user, schema):
            return (
                {"issues": [], "limitations": []} if "Independently audit" in system else program.model_dump()
            )

    app = FastAPI()
    app.include_router(interpreter_router(lambda: Client()))
    with TestClient(app) as client:
        context = client.post(
            "/api/interpreter/context", json={"document": "fixture", "text": source, "target": "1"}
        )
        assert context.status_code == 200
        inputs = {"bindings": {}}
        payload = {"context": context.json(), "inputs": inputs}
        draft = client.post("/api/interpreter/draft", json=payload)
        assert draft.status_code == 200
        payload["program"] = draft.json()["program"]
        preview = client.post(
            "/api/interpreter/check", json={"program": payload["program"], "inputs": inputs}
        )
        assert preview.status_code == 422
        report = client.post("/api/interpreter/review", json=payload)
        assert report.status_code == 200
        approved = client.post(
            "/api/interpreter/approve", json={**payload, "report": report.json(), "reviewer": "Tester"}
        )
        assert approved.status_code == 200
        checked = client.post("/api/interpreter/check", json={"program": approved.json(), "inputs": inputs})
        assert checked.status_code == 200 and checked.json()["outcome"] == "SATISFIED"
        assert (
            client.post(
                "/api/interpreter/context", json={"document": "fixture", "text": source, "target": "absent"}
            ).status_code
            == 422
        )


def test_http_missing_model_is_reported():
    app = FastAPI()
    app.include_router(interpreter_router(lambda: None))
    with TestClient(app) as client:
        context = client.post(
            "/api/interpreter/context", json={"document": "fixture", "text": "1 Rule.", "target": "1"}
        ).json()
        response = client.post(
            "/api/interpreter/draft", json={"context": context, "inputs": {"bindings": {}}}
        )
        assert response.status_code == 503
