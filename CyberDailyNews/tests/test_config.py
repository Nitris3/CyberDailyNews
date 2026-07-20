from pathlib import Path

import pytest
from pydantic import ValidationError

from ccip.config import load_settings


def test_load_settings_reads_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
email:
  sender: reports@example.com
  recipients: [analyst@example.com]
  smtp: {host: smtp.example.com}
sources:
  - name: Example
    kind: rss
    url: https://example.com/feed
    category: News
""",
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.email.smtp.host == "smtp.example.com"
    assert settings.sources[0].priority == 3


def test_load_settings_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        "email:\n  sender: x@example.com\n  recipients: [y@example.com]\n"
        "  smtp: {host: localhost, graph_tenant: forbidden}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_settings(path)

