from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    slack_signing_secret: str
    slack_channel_id: str = "C067Z2CJ0H0"
    slack_channel_name: str | None = None
    slack_workspace_domain: str | None = None
    port_base_url: str = "https://api.getport.io"
    port_client_id: str = ""
    port_client_secret: str = ""
    port_blueprint_identifier: str = "slack_use_case"
    port_default_status: str = "ready_for_cursor"
    port_default_priority: str = "medium"
    target_repository_url: str = "https://github.com/samdeepk-eng/Feature-releases.git"
    target_branch: str = "main"
    request_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            slack_signing_secret=os.getenv("SLACK_SIGNING_SECRET", ""),
            slack_channel_id=os.getenv("SLACK_CHANNEL_ID", cls.slack_channel_id),
            slack_channel_name=os.getenv("SLACK_CHANNEL_NAME"),
            slack_workspace_domain=os.getenv("SLACK_WORKSPACE_DOMAIN"),
            port_base_url=os.getenv("PORT_BASE_URL", cls.port_base_url).rstrip("/"),
            port_client_id=os.getenv("PORT_CLIENT_ID", ""),
            port_client_secret=os.getenv("PORT_CLIENT_SECRET", ""),
            port_blueprint_identifier=os.getenv(
                "PORT_BLUEPRINT_IDENTIFIER", cls.port_blueprint_identifier
            ),
            port_default_status=os.getenv(
                "PORT_DEFAULT_STATUS", cls.port_default_status
            ),
            port_default_priority=os.getenv(
                "PORT_DEFAULT_PRIORITY", cls.port_default_priority
            ),
            target_repository_url=os.getenv(
                "TARGET_REPOSITORY_URL", cls.target_repository_url
            ),
            target_branch=os.getenv("TARGET_BRANCH", cls.target_branch),
            request_timeout_seconds=float(
                os.getenv("REQUEST_TIMEOUT_SECONDS", str(cls.request_timeout_seconds))
            ),
        )

    def validate_runtime(self) -> None:
        missing = [
            name
            for name, value in {
                "SLACK_SIGNING_SECRET": self.slack_signing_secret,
                "PORT_CLIENT_ID": self.port_client_id,
                "PORT_CLIENT_SECRET": self.port_client_secret,
            }.items()
            if not value
        ]
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing required environment variables: {joined}")
