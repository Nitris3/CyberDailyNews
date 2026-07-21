"""Readiness checks for the preview Microsoft 365 Copilot Chat integration."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

COPILOT_DELEGATED_PERMISSIONS = (
    "Sites.Read.All",
    "Mail.Read",
    "People.Read.All",
    "OnlineMeetingTranscript.Read.All",
    "Chat.Read",
    "ChannelMessage.Read.All",
    "ExternalItem.Read.All",
)
OAuthFetcher = Callable[[str, bytes], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class CopilotReadiness:
    ready_for_sign_in: bool
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeviceSignIn:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class CopilotDeviceAuthenticator:
    """Microsoft device-code sign-in without retaining the resulting access token."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        *,
        fetcher: OAuthFetcher | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.fetcher = fetcher or _oauth_post

    def initiate(self) -> DeviceSignIn:
        document = self.fetcher(
            self._endpoint("devicecode"),
            urlencode({"client_id": self.client_id, "scope": self._scope()}).encode(),
        )
        try:
            return DeviceSignIn(
                device_code=str(document["device_code"]),
                user_code=str(document["user_code"]),
                verification_uri=str(document["verification_uri"]),
                expires_in=int(document["expires_in"]),
                interval=int(document.get("interval", 5)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"Microsoft sign-in could not start: {document}") from error

    def wait_for_sign_in(self, sign_in: DeviceSignIn) -> str:
        deadline = monotonic() + sign_in.expires_in
        interval = sign_in.interval
        while monotonic() < deadline:
            document = self.fetcher(
                self._endpoint("token"),
                urlencode(
                    {
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "client_id": self.client_id,
                        "device_code": sign_in.device_code,
                    }
                ).encode(),
            )
            if access_token := document.get("access_token"):
                return str(access_token)
            error = document.get("error")
            if error == "authorization_pending":
                sleep(interval)
                continue
            if error == "slow_down":
                interval += 5
                sleep(interval)
                continue
            raise RuntimeError(str(document.get("error_description") or error or document))
        raise RuntimeError("Microsoft sign-in timed out; please try again.")

    def _endpoint(self, operation: str) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/{operation}"

    @staticmethod
    def _scope() -> str:
        graph = "https://graph.microsoft.com/"
        permissions = " ".join(f"{graph}{name}" for name in COPILOT_DELEGATED_PERMISSIONS)
        return f"openid profile offline_access {permissions}"


def evaluate_copilot_readiness(
    tenant_id: str, client_id: str, *, enabled: bool
) -> CopilotReadiness:
    issues: list[str] = []
    if not _is_uuid(tenant_id):
        issues.append("Enter a valid Directory (tenant) ID.")
    if not _is_uuid(client_id):
        issues.append("Enter a valid Application (client) ID.")
    if not enabled:
        issues.append("Enable the connection after administrator consent is complete.")
    return CopilotReadiness(not issues, tuple(issues))


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


def _oauth_post(url: str, data: bytes) -> dict[str, Any]:
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310
        document = json.loads(response.read())
    if not isinstance(document, dict):
        raise RuntimeError("Microsoft identity returned an invalid response.")
    return document
