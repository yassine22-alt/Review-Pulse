"""Opt-in recording of regulation responses, never request headers or credentials."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime


def record_calls(client, directory):
    if directory is None or getattr(client, "_response_recording", False):
        return client
    client._response_recording = True
    complete = client.complete

    def recorded(system, user, schema):
        response, error = None, None
        client.last = {}
        try:
            response = complete(system, user, schema)
            return response
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            directory.mkdir(parents=True, exist_ok=True)
            data = {"case": getattr(client, "case_id", None), "model": client.model,
                    "recorded_utc": datetime.now(UTC).isoformat(),
                    "response": response, "error_type": error,
                    "requested_fields": list(schema.get("properties", {})),
                    "text": getattr(client, "last", {}).get("text")}
            (directory / f"{uuid.uuid4().hex}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    client.complete = recorded
    return client
