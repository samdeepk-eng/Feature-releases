from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings

SLACK_SIGNATURE_VERSION = "v0"
SIGNATURE_TOLERANCE_SECONDS = 60 * 5

KEY_VALUE_PATTERN = re.compile(r"^\s*[\-*•]?\s*([^:\n]{2,40})\s*:\s*(.+?)\s*$")
URL_PATTERN = re.compile(r"<(https?://[^>|]+)(?:\|[^>]+)?>")
MRKDWN_DECORATION_PATTERN = re.compile(r"[*_`~]")
RELEASE_HINT_PATTERN = re.compile(r"\b(release|released|launch|version|changelog)\b", re.I)


class SlackSignatureError(ValueError):
    """Raised when a Slack request signature cannot be trusted."""


@dataclass(frozen=True)
class ReleaseAnnouncement:
    identifier: str
    title: str
    properties: dict[str, Any]


def verify_slack_signature(
    signing_secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    now: float | None = None,
) -> None:
    if not signing_secret:
        raise SlackSignatureError("Slack signing secret is not configured")
    if not timestamp or not signature:
        raise SlackSignatureError("Missing Slack signature headers")

    current_time = now if now is not None else time.time()
    try:
        request_time = int(timestamp)
    except ValueError as exc:
        raise SlackSignatureError("Invalid Slack request timestamp") from exc

    if abs(current_time - request_time) > SIGNATURE_TOLERANCE_SECONDS:
        raise SlackSignatureError("Slack request timestamp is outside the allowed window")

    base_string = b":".join(
        [
            SLACK_SIGNATURE_VERSION.encode("utf-8"),
            timestamp.encode("utf-8"),
            body,
        ]
    )
    digest = hmac.new(
        signing_secret.encode("utf-8"), base_string, hashlib.sha256
    ).hexdigest()
    expected = f"{SLACK_SIGNATURE_VERSION}={digest}"
    if not hmac.compare_digest(expected, signature):
        raise SlackSignatureError("Invalid Slack request signature")


def parse_release_announcement(
    event: dict[str, Any],
    settings: Settings,
) -> ReleaseAnnouncement | None:
    channel_id = event.get("channel")
    if channel_id != settings.slack_channel_id:
        return None

    if event.get("subtype") in {"bot_message", "message_deleted"}:
        return None

    text = normalize_slack_text(str(event.get("text") or "")).strip()
    if not text:
        return None

    fields = parse_key_value_fields(text)
    if not looks_like_release_announcement(text, fields):
        return None

    source_ts = str(event.get("ts") or event.get("event_ts") or "").strip()
    if not source_ts:
        return None

    summary = first_present(
        fields,
        ["summary", "release", "title", "name", "feature", "description"],
    )
    if not summary:
        summary = first_content_line(text)

    title = truncate(summary, 120)
    source_message_url = build_slack_permalink(
        settings.slack_workspace_domain, channel_id, source_ts
    )
    acceptance_criteria = extract_section(
        text,
        ["acceptance criteria", "criteria", "requirements"],
    )

    properties: dict[str, Any] = {
        "requestType": infer_request_type(text),
        "status": normalized_enum_value(
            fields.get("status"), allowed=STATUS_VALUES, default=settings.port_default_status
        ),
        "priority": normalized_enum_value(
            fields.get("priority"),
            allowed=PRIORITY_VALUES,
            default=settings.port_default_priority,
        ),
        "sourceChannelId": channel_id,
        "sourceMessageTs": source_ts,
        "rawMessage": text,
        "summary": title,
        "targetRepositoryUrl": settings.target_repository_url,
        "targetBranch": settings.target_branch,
        "cursorPrompt": build_cursor_prompt(title, text, settings),
    }

    optional_values = {
        "sourceChannel": settings.slack_channel_name,
        "sourceMessageUrl": source_message_url,
        "requesterName": fields.get("requester") or fields.get("owner"),
        "requesterEmail": fields.get("email") or fields.get("requester email"),
        "acceptanceCriteria": acceptance_criteria,
    }
    properties.update({key: value for key, value in optional_values.items() if value})

    return ReleaseAnnouncement(
        identifier=entity_identifier(channel_id, source_ts),
        title=title,
        properties=properties,
    )


def parse_key_value_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = KEY_VALUE_PATTERN.match(line)
        if not match:
            continue
        key = slug_key(match.group(1))
        value = match.group(2).strip()
        if key and value:
            fields[key] = value
    return fields


def looks_like_release_announcement(text: str, fields: dict[str, str]) -> bool:
    if any(key in fields for key in {"release", "version", "changelog"}):
        return True
    return bool(RELEASE_HINT_PATTERN.search(text))


def normalize_slack_text(text: str) -> str:
    text = URL_PATTERN.sub(r"\1", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return MRKDWN_DECORATION_PATTERN.sub("", text)


def build_slack_permalink(
    workspace_domain: str | None,
    channel_id: str,
    source_ts: str,
) -> str | None:
    if not workspace_domain:
        return None
    domain = workspace_domain.replace("https://", "").replace("http://", "").strip("/")
    if not domain:
        return None
    timestamp_path = source_ts.replace(".", "")
    return f"https://{domain}/archives/{channel_id}/p{timestamp_path}"


def entity_identifier(channel_id: str, source_ts: str) -> str:
    safe_ts = re.sub(r"[^0-9A-Za-z_-]+", "-", source_ts).strip("-")
    return f"slack-{channel_id}-{safe_ts}".lower()


def first_present(fields: dict[str, str], keys: list[str]) -> str | None:
    for key in keys:
        value = fields.get(key)
        if value:
            return value
    return None


def first_content_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip(" -")
        if stripped:
            return stripped
    return "Slack release announcement"


def truncate(value: str, max_length: int) -> str:
    value = value.strip()
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "..."


def slug_key(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


STATUS_VALUES = {
    "new",
    "triage",
    "ready_for_cursor",
    "in_progress",
    "done",
    "rejected",
}
PRIORITY_VALUES = {"low", "medium", "high", "urgent"}


def normalized_enum_value(
    value: str | None,
    *,
    allowed: set[str],
    default: str,
) -> str:
    candidate = slug_key(value or default).replace(" ", "_")
    if candidate in allowed:
        return candidate
    return default


def infer_request_type(text: str) -> str:
    return "feature" if re.search(r"\bfeature\b", text, re.I) else "use-case"


def extract_section(text: str, headings: list[str]) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        normalized = slug_key(line.rstrip(":"))
        if normalized not in headings:
            continue

        collected: list[str] = []
        for following in lines[index + 1 :]:
            if KEY_VALUE_PATTERN.match(following) and collected:
                break
            if following.strip():
                collected.append(following.rstrip())
        if collected:
            return "\n".join(collected).strip()
    return None


def build_cursor_prompt(title: str, text: str, settings: Settings) -> str:
    return "\n".join(
        [
            f"Implement the Slack release request: {title}",
            "",
            f"Target repository: {settings.target_repository_url}",
            f"Target branch: {settings.target_branch}",
            "",
            "Original Slack announcement:",
            text,
        ]
    )
