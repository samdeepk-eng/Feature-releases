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

The repo includes a plain CloudFormation template at `template.yaml`. It creates:

- The Lambda function
- The Lambda execution role
- The CloudWatch Logs log group
- A public Lambda Function URL
- The Lambda environment variables

Because the app has Python dependencies, CloudFormation needs a Lambda zip file
in S3. No SAM or GitHub Actions deployment is required.

### 1. Build the Lambda zip

Build the package for the same Python runtime and architecture as your Lambda
function. For a Python 3.14, `x86_64` Lambda:

```bash
LAMBDA_PYTHON_VERSION=3.14 LAMBDA_ARCHITECTURE=x86_64 ./scripts/build-lambda-zip.sh
```

This creates `lambda.zip`.

If you choose `arm64` in CloudFormation, build with:

```bash
LAMBDA_PYTHON_VERSION=3.14 LAMBDA_ARCHITECTURE=arm64 ./scripts/build-lambda-zip.sh
```

### 2. Upload the zip to S3

Use an existing S3 bucket or create a small deployment-artifacts bucket. Upload
`lambda.zip`, then note the bucket and object key.

Example AWS CLI upload:

```bash
aws s3 cp lambda.zip s3://<your-bucket>/feature-releases-slack-port/lambda.zip
```

If you prefer the AWS Console, upload `lambda.zip` through the S3 UI.

### 3. Create the CloudFormation stack

In the AWS CloudFormation console:

1. Choose **Create stack**.
2. Choose **Upload a template file**.
3. Upload `template.yaml`.
4. Fill in the required parameters.

Important parameters for the test channel demo:

```env
CodeS3Bucket=<your-bucket>
CodeS3Key=feature-releases-slack-port/lambda.zip
LambdaRuntime=python3.14
LambdaArchitecture=x86_64
SlackSigningSecret=<from Slack app>
SlackChannelId=C0B8VL89V0B
SlackChannelName=<test-channel-name>
PortClientId=<from Port>
PortClientSecret=<from Port>
PortBlueprintIdentifier=slack_use_case
TargetRepositoryUrl=https://github.com/samdeepk-eng/Feature-releases.git
TargetBranch=main
```

Use the defaults for `ServiceName`, `EnvironmentName`, memory, timeout, and
architecture unless you have a reason to change them.

### 4. Configure Slack

After the stack is created, open the CloudFormation **Outputs** tab and copy the
`SlackEventSubscriptionUrl` value into Slack Event Subscriptions. It will look
like:

```text
https://<lambda-function-url>/slack/events
```

For the live demo, post a release-looking message in channel `C0B8VL89V0B`.
When moving to the production feature releases channel, update the stack with
`SlackChannelId=C067Z2CJ0H0` and invite the Slack app to that channel.

The base install is intentionally Lambda-focused. For local server or Docker
runtime installs, use the `server` extra:

```bash
python -m pip install ".[server]"
```
