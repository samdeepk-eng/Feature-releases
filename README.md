# Feature Releases Slack-to-Port Service

This repository contains a small FastAPI service that receives Slack Events API
callbacks for release announcement posts and creates or updates Port
`slack_use_case` entities.

The service is configured for:

- Slack channel ID: `C067Z2CJ0H0`
- Target repository: `https://github.com/samdeepk-eng/Feature-releases.git`
- Port blueprint: `slack_use_case`

## What it does

`POST /slack/events`:

1. Verifies the Slack request signature using `SLACK_SIGNING_SECRET`.
2. Handles Slack URL verification challenges.
3. Accepts message events only from `C067Z2CJ0H0`.
4. Parses release announcement text for fields such as `Release`, `Summary`,
   `Priority`, `Status`, `Owner`, and `Acceptance Criteria`.
5. Upserts a Port `slack_use_case` entity using the Slack channel and message
   timestamp as the stable identifier.

The Port entity uses the current `slack_use_case` blueprint fields, including:

- `requestType`
- `status`
- `priority`
- `sourceChannelId`
- `sourceMessageTs`
- `sourceMessageUrl`
- `requesterName`
- `rawMessage`
- `summary`
- `acceptanceCriteria`
- `targetRepositoryUrl`
- `targetBranch`
- `cursorPrompt`

## Example Slack announcement

```text
Release: Feature flags v1.2.0
Priority: high
Status: triage
Owner: Ada Lovelace
Acceptance Criteria:
- Feature flag state is visible
- Rollout metrics are linked
```

Messages that do not look like release announcements are acknowledged and
ignored.

## Configuration

Copy `.env.example` and provide real values:

```bash
cp .env.example .env
```

Required:

- `SLACK_SIGNING_SECRET`
- `PORT_CLIENT_ID`
- `PORT_CLIENT_SECRET`

Useful optional values:

- `SLACK_WORKSPACE_DOMAIN` builds Slack permalinks like
  `https://example.slack.com/archives/C067Z2CJ0H0/p...`.
- `SLACK_CHANNEL_NAME` populates the Port `sourceChannel` property.
- `PORT_DEFAULT_STATUS` defaults to `ready_for_cursor`.
- `PORT_DEFAULT_PRIORITY` defaults to `medium`.

### Testing with the test Slack channel

To test before listening to the production feature releases channel, deploy the
service with:

```env
SLACK_CHANNEL_ID=C0B8VL89V0B
SLACK_CHANNEL_NAME=<test-channel-name>
```

Invite the Slack app to that channel, then post a release-looking message using
the example format above. Switch `SLACK_CHANNEL_ID` back to `C067Z2CJ0H0` before
using the service for the production feature releases channel.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest
```

## Slack app setup

1. Create or open a Slack app.
2. Enable **Event Subscriptions**.
3. Set the request URL to your deployed service:

   ```text
   https://<your-domain>/slack/events
   ```

4. Subscribe to message events for the target channel, such as
   `message.channels` for public channels.
5. Install the app into the workspace and invite it to channel `C067Z2CJ0H0`.
6. Configure `SLACK_SIGNING_SECRET` from the Slack app **Basic Information**
   page.

## Docker

Build and run:

```bash
docker build -t feature-releases-slack-port .
docker run --env-file .env -p 8000:8000 feature-releases-slack-port
```

Health check:

```bash
curl http://localhost:8000/healthz
```

## AWS Lambda Function URL deployment

For a low-cost demo deployment on AWS, run this FastAPI app on Lambda using the
included Mangum handler.

Lambda settings:

- Runtime: Python 3.12
- Handler: `app.main.handler`
- Timeout: 15 seconds
- Function URL auth type: `NONE`

Minimum environment variables for the test channel demo:

```env
SLACK_SIGNING_SECRET=<from Slack app>
SLACK_CHANNEL_ID=C0B8VL89V0B
SLACK_CHANNEL_NAME=<test-channel-name>
PORT_CLIENT_ID=<from Port>
PORT_CLIENT_SECRET=<from Port>
PORT_BLUEPRINT_IDENTIFIER=slack_use_case
TARGET_REPOSITORY_URL=https://github.com/samdeepk-eng/Feature-releases.git
TARGET_BRANCH=main
```

After creating the Function URL, configure Slack Event Subscriptions to call:

```text
https://<lambda-function-url>/slack/events
```

For a zip-based deployment, install dependencies into a build directory, copy
the app code, zip it, and update the Lambda function:

```bash
rm -rf build lambda.zip
python3 -m pip install --target build .
cp -R app build/app
(cd build && zip -r ../lambda.zip .)
aws lambda update-function-code \
  --function-name <function-name> \
  --zip-file fileb://lambda.zip
```

For the live demo, post a release-looking message in channel `C0B8VL89V0B`.
When moving to the production feature releases channel, set
`SLACK_CHANNEL_ID=C067Z2CJ0H0` and invite the Slack app to that channel.
