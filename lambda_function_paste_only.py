import base64
import hashlib
import hmac
import json
import re
import time
import urllib.request


# DEMO-ONLY CONFIG:
# Fill these values in the Lambda console, then paste/deploy the whole file.
# Do not use this hardcoded-secret style for a long-lived production service.
CONFIG = {
    "SLACK_SIGNING_SECRET": "paste-slack-signing-secret-here",
    "SLACK_CHANNEL_ID": "C0B8VL89V0B",
    "SLACK_CHANNEL_NAME": "test-channel",
    "SLACK_WORKSPACE_DOMAIN": "",
    "PORT_BASE_URL": "https://api.getport.io",
    "PORT_CLIENT_ID": "paste-port-client-id-here",
    "PORT_CLIENT_SECRET": "paste-port-client-secret-here",
    "PORT_BLUEPRINT_IDENTIFIER": "slack_use_case",
    "TARGET_REPOSITORY_URL": "https://github.com/samdeepk-eng/Feature-releases.git",
    "TARGET_BRANCH": "main",
}


RELEASE_HINT = re.compile(r"\b(release|released|launch|version|changelog)\b", re.I)
KV = re.compile(r"^\s*[\-*]?\s*([^:\n]{2,40})\s*:\s*(.+?)\s*$")
PLACEHOLDER = "paste-"


def lambda_handler(event, context):
    missing = missing_config()
    if missing:
        return response(500, {"error": "missing demo config", "fields": missing})

    body = event.get("body") or ""
    raw_body = base64.b64decode(body) if event.get("isBase64Encoded") else body.encode()
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    try:
        verify_slack_signature(
            CONFIG["SLACK_SIGNING_SECRET"],
            headers.get("x-slack-request-timestamp"),
            headers.get("x-slack-signature"),
            raw_body,
        )
    except Exception as exc:
        return response(401, {"error": str(exc)})

    payload = json.loads(raw_body)
    if payload.get("type") == "url_verification":
        return response(200, {"challenge": payload.get("challenge")})

    event_payload = payload.get("event") or {}
    announcement = parse_announcement(event_payload)
    if not announcement:
        return response(200, {"ok": True, "ignored": True})

    upsert_port_entity(announcement)
    return response(200, {"ok": True, "entity_identifier": announcement["identifier"]})


def missing_config():
    required = ["SLACK_SIGNING_SECRET", "PORT_CLIENT_ID", "PORT_CLIENT_SECRET"]
    return [
        key
        for key in required
        if not CONFIG.get(key) or str(CONFIG[key]).startswith(PLACEHOLDER)
    ]


def verify_slack_signature(secret, timestamp, signature, raw_body):
    if not timestamp or not signature:
        raise ValueError("missing Slack signature headers")
    if abs(time.time() - int(timestamp)) > 60 * 5:
        raise ValueError("stale Slack request")

    base = b":".join([b"v0", timestamp.encode(), raw_body])
    digest = hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    if not hmac.compare_digest(expected, signature):
        raise ValueError("invalid Slack signature")


def parse_announcement(event_payload):
    channel_id = event_payload.get("channel")
    if channel_id != CONFIG["SLACK_CHANNEL_ID"]:
        return None
    if event_payload.get("type") != "message":
        return None
    if event_payload.get("subtype") in {"bot_message", "message_deleted"}:
        return None

    text = normalize_slack_text(event_payload.get("text") or "").strip()
    if not text or not RELEASE_HINT.search(text):
        return None

    fields = parse_fields(text)
    ts = event_payload.get("ts") or event_payload.get("event_ts")
    if not ts:
        return None

    summary = (
        fields.get("release")
        or fields.get("summary")
        or fields.get("title")
        or first_line(text)
    )
    properties = {
        "requestType": "feature" if re.search(r"\bfeature\b", text, re.I) else "use-case",
        "status": normalize_choice(fields.get("status"), "ready_for_cursor"),
        "priority": normalize_choice(fields.get("priority"), "medium"),
        "sourceChannel": CONFIG["SLACK_CHANNEL_NAME"],
        "sourceChannelId": channel_id,
        "sourceMessageTs": ts,
        "rawMessage": text,
        "summary": summary[:120],
        "targetRepositoryUrl": CONFIG["TARGET_REPOSITORY_URL"],
        "targetBranch": CONFIG["TARGET_BRANCH"],
        "cursorPrompt": cursor_prompt(summary, text),
    }
    source_url = slack_permalink(channel_id, ts)
    if source_url:
        properties["sourceMessageUrl"] = source_url
    if fields.get("owner"):
        properties["requesterName"] = fields["owner"]

    return {
        "identifier": f"slack-{channel_id}-{re.sub(r'[^0-9a-zA-Z_-]+', '-', ts)}".lower(),
        "title": summary[:120],
        "properties": {k: v for k, v in properties.items() if v},
    }


def normalize_slack_text(text):
    text = re.sub(r"<(https?://[^>|]+)(?:\|[^>]+)?>", r"\1", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def parse_fields(text):
    fields = {}
    for line in text.splitlines():
        match = KV.match(line)
        if match:
            key = re.sub(r"[^a-z0-9]+", " ", match.group(1).lower()).strip()
            fields[key] = match.group(2).strip()
    return fields


def first_line(text):
    return next((line.strip(" -") for line in text.splitlines() if line.strip()), "Release")


def normalize_choice(value, default):
    if not value:
        return default
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def slack_permalink(channel_id, ts):
    domain = CONFIG["SLACK_WORKSPACE_DOMAIN"].replace("https://", "").strip("/")
    return f"https://{domain}/archives/{channel_id}/p{ts.replace('.', '')}" if domain else None


def cursor_prompt(summary, text):
    return "\n".join(
        [
            f"Implement the Slack release request: {summary}",
            "",
            "Target repository: " + CONFIG["TARGET_REPOSITORY_URL"],
            "Target branch: " + CONFIG["TARGET_BRANCH"],
            "",
            "Original Slack announcement:",
            text,
        ]
    )


def upsert_port_entity(entity):
    base_url = CONFIG["PORT_BASE_URL"].rstrip("/")
    token_payload = post_json(
        f"{base_url}/v1/auth/access_token",
        {
            "clientId": CONFIG["PORT_CLIENT_ID"],
            "clientSecret": CONFIG["PORT_CLIENT_SECRET"],
        },
    )
    token = token_payload["accessToken"]
    blueprint = CONFIG["PORT_BLUEPRINT_IDENTIFIER"]
    post_json(
        f"{base_url}/v1/blueprints/{blueprint}/entities?upsert=true&merge=true",
        entity,
        token,
    )


def post_json(url, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as result:
        return json.loads(result.read() or b"{}")


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
