from pathlib import Path

import yaml

from ccip.config import load_settings
from ccip.dashboard import (
    dashboard_config_backup,
    render_dashboard,
    restore_dashboard_config,
    save_dashboard_config,
)


def test_dashboard_saves_local_non_secret_settings(tmp_path: Path) -> None:
    path = tmp_path / "ccip.local.yml"
    source = Path(__file__).parents[1] / "config" / "ccip.yml"
    path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    sources = Path(__file__).parents[1] / "config" / "sources.yml"
    (tmp_path / "sources.yml").write_text(sources.read_text(encoding="utf-8"), encoding="utf-8")
    form = {
        "provider": ["rules"], "audience": ["Executives"], "instructions": ["Be brief"],
        "priority_multiplier": ["1.2"], "known_exploited_bonus": ["2"],
        "ransomware_bonus": ["1.5"], "critical_keyword_bonus": ["1"],
        "medium_threshold": ["4"], "high_threshold": ["7"],
        "critical_threshold": ["9"], "max_score": ["10"],
        "watchlist_keywords": ["ExampleCorp\n'Product X'"], "watchlist_bonus": ["2"],
        "sender": ["sender@example.com"], "recipients": ["one@example.com, two@example.com"],
        "subject": ["News"], "max_items": ["5"], "smtp_host": ["smtp.example.com"],
        "smtp_port": ["587"], "smtp_username": ["sender@example.com"], "start_tls": ["yes"],
        "m365_tenant_id": ["tenant-id"], "m365_client_id": ["client-id"],
        "m365_enabled": ["yes"],
        "report_timezone": ["America/Chicago"],
    }

    save_dashboard_config(path, form)

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["scoring"]["watchlist_keywords"] == ["ExampleCorp", "'Product X'"]
    assert document["email"]["smtp"]["password"] is None
    assert document["microsoft_365_copilot"]["enabled"] is True
    assert document["report"]["timezone"] == "America/Chicago"


def test_dashboard_polling_disables_collection_while_background_job_runs() -> None:
    settings = load_settings(Path(__file__).parents[1] / "config" / "ccip.yml")

    page = render_dashboard(settings, "test-token").decode()

    assert "/status?token=test-token" in page
    assert 'button[value="collect"]' in page
    assert "b.disabled=s.busy" in page
    assert "News sources" in page
    assert 'name="enabled_source"' in page
    assert "Daily workflow" in page
    assert "1. Collect news" in page
    assert "2. Preview email" in page
    assert "3. Review & Send" in page
    assert "Getting started" in page
    assert "Skip to main content" in page


def test_dashboard_backup_removes_password_and_restore_validates(tmp_path: Path) -> None:
    path = tmp_path / "ccip.local.yml"
    source = Path(__file__).parents[1] / "config" / "ccip.yml"
    content = source.read_text(encoding="utf-8").replace("password: null", "password: secret")
    path.write_text(content, encoding="utf-8")
    sources = Path(__file__).parents[1] / "config" / "sources.yml"
    (tmp_path / "sources.yml").write_text(sources.read_text(encoding="utf-8"), encoding="utf-8")

    backup = dashboard_config_backup(path)
    assert b"secret" not in backup

    restored = yaml.safe_load(backup)
    restored["email"]["subject"] = "Restored Daily"
    restore_dashboard_config(path, yaml.safe_dump(restored))

    assert load_settings(path).email.subject.startswith("Restored Daily")


def test_dashboard_warns_when_todays_report_was_already_sent() -> None:
    settings = load_settings(Path(__file__).parents[1] / "config" / "ccip.yml")

    page = render_dashboard(
        settings,
        "token",
        delivery_status={
            "already_sent": True,
            "smtp_ready": True,
            "credential_required": True,
            "attempts": [],
        },
    ).decode()

    assert "Email delivery" in page
    assert "already sent" in page
    assert "credential will be requested" in page
