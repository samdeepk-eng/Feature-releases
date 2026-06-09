from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from mangum import Mangum

from app.config import Settings
from app.port import PortClient
from app.slack import (
    ReleaseAnnouncement,
    SlackSignatureError,
    parse_release_announcement,
    verify_slack_signature,
)

LOGGER = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    port_client: PortClient | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    app = FastAPI(
        title="Feature Releases Slack-to-Port Service",
        summary="Creates Port slack_use_case entities from Slack release announcements.",
    )
    app.state.settings = resolved_settings
    app.state.port_client = port_client or PortClient(resolved_settings)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/slack/events")
    async def slack_events(
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        current_settings: Settings = request.app.state.settings
        try:
            current_settings.validate_runtime()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        raw_body = await request.body()
        try:
            verify_slack_signature(
                current_settings.slack_signing_secret,
                request.headers.get("X-Slack-Request-Timestamp"),
                request.headers.get("X-Slack-Signature"),
                raw_body,
            )
        except SlackSignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        if payload.get("type") != "event_callback":
            return {"ok": True, "ignored": "unsupported_payload_type"}

        event = normalized_message_event(payload.get("event") or {})
        if event.get("type") != "message":
            return {"ok": True, "ignored": "unsupported_event_type"}

        announcement = parse_release_announcement(event, current_settings)
        if not announcement:
            return {"ok": True, "ignored": "not_a_release_announcement"}

        background_tasks.add_task(
            upsert_announcement,
            request.app.state.port_client,
            announcement,
        )
        return {"ok": True, "entity_identifier": announcement.identifier}

    return app


def normalized_message_event(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("subtype") != "message_changed":
        return event

    message = dict(event.get("message") or {})
    message.setdefault("type", event.get("type"))
    message.setdefault("channel", event.get("channel"))
    message.setdefault("event_ts", event.get("event_ts"))
    return message


async def upsert_announcement(
    port_client: PortClient,
    announcement: ReleaseAnnouncement,
) -> None:
    try:
        await port_client.upsert_slack_use_case(announcement)
    except Exception:
        LOGGER.exception("Failed to upsert Port entity %s", announcement.identifier)


app = create_app()
handler = Mangum(app)
