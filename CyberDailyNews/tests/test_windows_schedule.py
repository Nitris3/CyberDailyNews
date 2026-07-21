from pathlib import Path
from subprocess import CompletedProcess

import ccip.windows_schedule as schedule


def test_configure_windows_task_creates_daily_task(monkeypatch: object) -> None:
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(arguments)
        return CompletedProcess(arguments, 0, "SUCCESS", "")

    monkeypatch.setattr(schedule.sys, "platform", "win32")  # type: ignore[attr-defined]
    monkeypatch.setattr(schedule.subprocess, "run", fake_run)  # type: ignore[attr-defined]

    message = schedule.configure_windows_task(
        Path("C:/app/config.local.yml"), "07:30", enabled=True
    )

    assert "/Create" in calls[0]
    assert "07:30" in calls[0]
    assert "scheduled for 07:30" in message


def test_configure_windows_task_deletes_disabled_task(monkeypatch: object) -> None:
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(arguments)
        return CompletedProcess(arguments, 0, "SUCCESS", "")

    monkeypatch.setattr(schedule.sys, "platform", "win32")  # type: ignore[attr-defined]
    monkeypatch.setattr(schedule.subprocess, "run", fake_run)  # type: ignore[attr-defined]

    schedule.configure_windows_task(Path("C:/app/config.local.yml"), "07:30", enabled=False)

    assert "/Delete" in calls[0]
