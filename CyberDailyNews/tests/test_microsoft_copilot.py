from ccip.microsoft_copilot import (
    COPILOT_DELEGATED_PERMISSIONS,
    CopilotDeviceAuthenticator,
    evaluate_copilot_readiness,
)


def test_copilot_readiness_requires_valid_ids_and_activation() -> None:
    readiness = evaluate_copilot_readiness("bad", "", enabled=False)

    assert readiness.ready_for_sign_in is False
    assert len(readiness.issues) == 3


def test_copilot_readiness_accepts_enabled_uuid_configuration() -> None:
    readiness = evaluate_copilot_readiness(
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        enabled=True,
    )

    assert readiness.ready_for_sign_in is True
    assert readiness.issues == ()
    assert "Mail.Read" in COPILOT_DELEGATED_PERMISSIONS


def test_device_sign_in_uses_delegated_scopes_and_returns_ephemeral_token() -> None:
    requests: list[tuple[str, bytes]] = []
    responses = [
        {
            "device_code": "device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://microsoft.com/devicelogin",
            "expires_in": 900,
            "interval": 1,
        },
        {"access_token": "temporary-token"},
    ]

    def fetcher(url: str, data: bytes):  # type: ignore[no-untyped-def]
        requests.append((url, data))
        return responses.pop(0)

    authenticator = CopilotDeviceAuthenticator(
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        fetcher=fetcher,
    )
    sign_in = authenticator.initiate()

    assert sign_in.user_code == "ABCD-EFGH"
    assert authenticator.wait_for_sign_in(sign_in) == "temporary-token"
    assert b"Mail.Read" in requests[0][1]
    assert requests[1][0].endswith("/token")
