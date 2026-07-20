# CCIP Cyber-Intelligence Automation

Python 3.12 service for collecting, processing, storing, rendering, and delivering the
CSAA Daily Cyber News report.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

Configuration is read from `config/ccip.yml`. Keep SMTP credentials out of source
control and provide them with `CCIP_SMTP_USERNAME` and `CCIP_SMTP_PASSWORD`.

The HTML currently establishes the render contract and email-safe structure. Replace
the presentation markup in `templates/daily_news.html.j2` with the supplied CSAA Daily
Cyber News template; the `report.report_date` and `report.items` data contract is stable.

## Architecture

- `domain.py`: immutable collector and report models
- `interfaces.py`: collector, processor, and email-delivery ports
- `db.py` / `repository.py`: SQLAlchemy persistence and transaction boundary
- `rendering.py`: strict, auto-escaped Jinja rendering
- `delivery.py`: multipart email composition and SMTP adapter
- `config.py`: strict YAML validation and environment secret overrides

Microsoft Graph is intentionally not used. Additional delivery mechanisms implement
the `EmailDelivery` protocol without changing the reporting pipeline.

