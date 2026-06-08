from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.slack import (
    SlackSignatureError,
    parse_release_announcement,
    verify_slack_signature,
)


SECRET = "test-signing-secret"


class FakePortClient:
    def __init__(self) -> None:
        self.announcements = []

    async def upsert_slack_use_case(self, announcement):
        self.announcements.append(announcement)


def signed_headers(body: bytes, timestamp: str | None = None) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    base = b":".join([b"v0", timestamp.encode("utf-8"), body])
    signature = "v0=" + hmac.new(
        SECRET.encode("utf-8"), base, hashlib.sha256
    ).hexdigest()
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }


def body(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def settings() -> Settings:
    return Settings(
        slack_signing_secret=SECRET,
        slack_channel_id="C067Z2CJ0H0",
        slack_channel_name="feature-releases",
        slack_workspace_domain="example.slack.com",
        port_client_id="port-client-id",
        port_client_secret="port-client-secret",
    )


def test_verifies_valid_slack_signature() -> None:
    payload = b'{"type":"event_callback"}'
    timestamp = str(int(time.time()))

    verify_slack_signature(
        SECRET,
        timestamp,
        signed_headers(payload, timestamp)["X-Slack-Signature"],
        payload,
    )


def test_rejects_stale_slack_signature() -> None:
    payload = b"{}"
    timestamp = str(int(time.time()) - 600)

    with pytest.raises(SlackSignatureError):
        verify_slack_signature(
            SECRET,
            timestamp,
            signed_headers(payload, timestamp)["X-Slack-Signature"],
            payload,
        )


def test_url_verification_returns_challenge_without_port_upsert() -> None:
    fake_port = FakePortClient()
    client = TestClient(create_app(settings(), fake_port))
    request_body = body({"type": "url_verification", "challenge": "challenge-token"})

    response = client.post(
        "/slack/events",
        content=request_body,
        headers=signed_headers(request_body),
    )

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-token"}
    assert fake_port.announcements == []


def test_rejects_invalid_signature() -> None:
    client = TestClient(create_app(settings(), FakePortClient()))
    request_body = body({"type": "event_callback", "event": {"type": "message"}})

    response = client.post(
        "/slack/events",
        content=request_body,
        headers={
            "X-Slack-Request-Timestamp": str(int(time.time())),
            "X-Slack-Signature": "v0=invalid",
        },
    )

    assert response.status_code == 401


def test_ignores_messages_outside_configured_channel() -> None:
    fake_port = FakePortClient()
    client = TestClient(create_app(settings(), fake_port))
    request_body = body(
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "channel": "COTHER",
                "ts": "1710000000.000100",
                "text": "Release: Billing history v1.0.0",
            },
        }
    )

    response = client.post(
        "/slack/events",
        content=request_body,
        headers=signed_headers(request_body),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "ignored": "not_a_release_announcement"}
    assert fake_port.announcements == []


def test_release_announcement_creates_port_entity() -> None:
    fake_port = FakePortClient()
    client = TestClient(create_app(settings(), fake_port))
    request_body = body(
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "channel": "C067Z2CJ0H0",
                "user": "U123",
                "ts": "1710000000.000100",
                "text": "\n".join(
                    [
                        "*Release*: Feature flags v1.2.0",
                        "Priority: high",
                        "Status: triage",
                        "Owner: Ada Lovelace",
                        "Acceptance Criteria:",
                        "- Feature flag state is visible",
                        "- Rollout metrics are linked",
                    ]
                ),
            },
        }
    )

    response = client.post(
        "/slack/events",
        content=request_body,
        headers=signed_headers(request_body),
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "entity_identifier": "slack-c067z2cj0h0-1710000000-000100",
    }
    assert len(fake_port.announcements) == 1
    announcement = fake_port.announcements[0]
    assert announcement.title == "Feature flags v1.2.0"
    assert announcement.properties["requestType"] == "feature"
    assert announcement.properties["status"] == "triage"
    assert announcement.properties["priority"] == "high"
    assert announcement.properties["sourceChannelId"] == "C067Z2CJ0H0"
    assert announcement.properties["sourceMessageTs"] == "1710000000.000100"
    assert announcement.properties["sourceMessageUrl"] == (
        "https://example.slack.com/archives/C067Z2CJ0H0/p1710000000000100"
    )
    assert announcement.properties["targetRepositoryUrl"] == (
        "https://github.com/samdeepk-eng/Feature-releases.git"
    )
    assert "Feature flag state is visible" in announcement.properties["acceptanceCriteria"]


def test_parser_ignores_non_release_messages() -> None:
    announcement = parse_release_announcement(
        {
            "type": "message",
            "channel": "C067Z2CJ0H0",
            "ts": "1710000000.000100",
            "text": "Can someone review the dashboard?",
        },
        settings(),
    )

    assert announcement is None
