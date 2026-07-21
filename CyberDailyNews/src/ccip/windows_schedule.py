"""Install and remove the per-user Windows collection task."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TASK_NAME = "Cyber Daily News Collection"


def configure_windows_task(config_path: Path, daily_time: str, *, enabled: bool) -> str:
    if sys.platform != "win32":
        return "Automatic task setup is available on Windows only."
    if not enabled:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode not in {0, 1}:
            raise RuntimeError((result.stderr or result.stdout).strip())
        return "Daily Windows task disabled."
    python = Path(sys.executable).with_name("python.exe")
    command = f'"{python}" -m ccip.cli --config "{config_path}" scheduled-run'
    result = subprocess.run(
        [
            "schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", daily_time,
            "/TN", TASK_NAME, "/TR", command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return f"Daily Windows task scheduled for {daily_time}."
