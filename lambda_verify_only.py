import base64
import json


def lambda_handler(event, context):
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}

    challenge = payload.get("challenge")
    if challenge:
        return {
            "statusCode": 200,
            "headers": {"content-type": "text/plain"},
            "body": challenge,
        }

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"ok": True}),
    }
