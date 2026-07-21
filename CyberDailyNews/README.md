# CCIP Cyber-Intelligence Automation

Python 3.12 service for collecting, processing, storing, rendering, and delivering a
daily cyber-intelligence report.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

Configuration is read from `config/ccip.yml`. Keep SMTP credentials out of source
control and provide them with `CCIP_SMTP_USERNAME` and `CCIP_SMTP_PASSWORD`.
The curated feed registry is maintained separately in `config/sources.yml` and is
referenced by the main configuration through `source_files`.

See the [complete configuration and setup guide](docs/configuration.md) for step-by-step
AI and non-AI installation paths, every supported setting, previews, sources, SMTP, and
troubleshooting.

## Email template

The complete end-user HTML template is `templates/email/daily_news.html.j2`. Edit that
file directly to add organization branding, header, footer, and email-safe inline styles.
Its opening comment documents every available Jinja value. The plain-text fallback is
next to it at `templates/email/daily_news.txt.j2`.

Render a report without sending email:

```powershell
& ".\.venv\Scripts\python.exe" -m ccip.cli preview --date 2026-07-20
```

Add `--open` to display the rendered email in your default browser. This only writes
the local HTML preview; it never connects to SMTP or sends a message:

```powershell
& ".\.venv\Scripts\python.exe" -m ccip.cli preview --date 2026-07-20 --open
```

Local AI is optional. Normal collection and preview use deterministic rules and do not
require Ollama. Add `--resummarize` to explicitly use the configured local Ollama model
to simplify both headlines and summaries in a preview (stored source records are unchanged):

```powershell
& ".\.venv\Scripts\python.exe" -m ccip.cli preview --date 2026-07-20 --resummarize --open
```

To also use Ollama during collection, explicitly change `summarization.provider` in
`config/ccip.yml` from `rules` to `ollama`.

## Generative summaries

`summarization.provider` supports `ollama`, `copilot`, or `rules`. Ollama uses the local
endpoint configured in `ccip.yml`. Copilot invokes an installed and signed-in Copilot CLI
non-interactively and grants it no file, shell, or URL tools. When configured,
`fallback_to_rules` keeps collection operational if the model is unavailable.

The HTML establishes the render contract and email-safe structure. The
`report.report_date` and `report.items` data contract is stable.

## Architecture

- `domain.py`: immutable collector and report models
- `interfaces.py`: collector, processor, and email-delivery ports
- `db.py` / `repository.py`: SQLAlchemy persistence and transaction boundary
- `rendering.py`: strict, auto-escaped Jinja rendering
- `delivery.py`: multipart email composition and SMTP adapter
- `config.py`: strict YAML validation and environment secret overrides

Microsoft Graph is intentionally not used. Additional delivery mechanisms implement
the `EmailDelivery` protocol without changing the reporting pipeline.
