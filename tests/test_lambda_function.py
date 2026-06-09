from __future__ import annotations

import hashlib
import hmac
import json
import time

import lambda_function


SECRET = "test-secret"


def signed_event(payload: dict) -> dict:
    body = json.dumps(payload, separators=(",", ":"))
    timestamp = str(int(time.time()))
    signature = "v0=" + hmac.new(
        SECRET.encode(),
        b":".join([b"v0", timestamp.encode(), body.encode()]),
        hashlib.sha256,
    ).hexdigest()
    return {
        "headers": {
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
        "body": body,
        "isBase64Encoded": False,
    }


def test_console_lambda_handler_upserts_release(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C0B8VL89V0B")
    monkeypatch.setenv("PORT_CLIENT_ID", "client")
    monkeypatch.setenv("PORT_CLIENT_SECRET", "secret")
    monkeypatch.setattr(lambda_function, "post_json", lambda url, payload, token=None: calls.append((url, payload, token)) or {"accessToken": "token"})

    response = lambda_function.lambda_handler(
        signed_event(
            {
                "type": "event_callback",
                "event": {
                    "type": "message",
                    "channel": "C0B8VL89V0B",
                    "ts": "1710000000.000100",
                    "text": "Release: Console demo v1\nPriority: high",
                },
            }
        ),
        None,
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["entity_identifier"] == (
        "slack-c0b8vl89v0b-1710000000-000100"
    )
    assert len(calls) == 2
    assert calls[1][1]["properties"]["sourceChannelId"] == "C0B8VL89V0B"
