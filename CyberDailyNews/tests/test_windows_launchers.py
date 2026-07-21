from pathlib import Path


def test_first_time_setup_remains_no_ai_and_uses_local_config() -> None:
    root = Path(__file__).parents[1]
    setup = (root / "Setup-CyberDailyNews.cmd").read_text(encoding="utf-8")

    assert "pip install -e ." in setup
    assert "config\\ccip.local.yml" in setup
    assert "init-db" in setup
    assert "ollama" not in setup.lower()


def test_normal_launcher_directs_unconfigured_users_to_setup() -> None:
    root = Path(__file__).parents[1]
    launcher = (root / "Start-CyberDailyNews.cmd").read_text(encoding="utf-8")

    assert "Setup-CyberDailyNews.cmd" in launcher
