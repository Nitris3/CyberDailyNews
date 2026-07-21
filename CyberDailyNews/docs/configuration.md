# Configuration and Setup Guide

This guide covers every supported setting and provides two setup paths:

- **No AI:** the default; requires no model service or AI tooling.
- **Optional AI:** uses local Ollama for collection and/or preview rewriting.

All commands below run from the `CyberDailyNews` project directory in PowerShell.

## 1. Install the application

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m ccip.cli init-db
```

The application requires Python 3.12 or newer. Configuration defaults to
`config/ccip.yml`; select another file by placing `--config path\to\file.yml` before
the command name.

```powershell
python -m ccip.cli --config config\ccip.yml preview --open
```

## 2. Choose the summarization mode

### Option A: no AI

Keep this setting in `config/ccip.yml`:

```yaml
summarization:
  provider: rules
```

Then collect and preview normally:

```powershell
python -m ccip.cli collect
python -m ccip.cli preview --open
```

This path never calls Ollama or Copilot. It uses deterministic cleanup, truncation,
priority scoring, and severity rules.

### Option B: Ollama only for an AI preview

1. Install Ollama for Windows from <https://ollama.com/download/windows>.
2. Pull the configured model:

   ```powershell
   ollama pull llama3.2:3b
   ```

3. Keep `provider: rules`; the preview flag is the explicit opt-in.
4. Generate an AI-rewritten preview:

   ```powershell
   python -m ccip.cli preview --resummarize --open
   ```

`--resummarize` rewrites both display titles and summaries in memory. It does not
modify stored articles and never sends email.

### Option C: Ollama during collection

1. Complete the Ollama installation steps above.
2. Change the provider:

   ```yaml
   summarization:
     provider: ollama
     model: llama3.2:3b
     endpoint: http://127.0.0.1:11434
     timeout_seconds: 180
     fallback_to_rules: true
   ```

3. Run collection:

   ```powershell
   python -m ccip.cli collect
   ```

With `fallback_to_rules: true`, collection continues with deterministic summaries if
Ollama is unavailable. Set it to `false` only when model failure should stop collection.

### Option D: Copilot CLI during collection

Set `provider: copilot`, choose a supported model name, and set `copilot_binary` if the
signed-in executable is not named `copilot`:

```yaml
summarization:
  provider: copilot
  model: your-model-name
  copilot_binary: copilot
  timeout_seconds: 180
  fallback_to_rules: true
```

Copilot is supported for collection. The preview-specific `--resummarize` flag always
uses Ollama so that preview rewriting remains local.

## 3. Configure the report

Edit the `email` section:

```yaml
email:
  sender: cyber-intelligence@example.com
  recipients:
    - security-team@example.com
  subject: "Daily Cyber Intelligence - {{ report_date }}"
  template_directory: templates/email
  html_template: daily_news.html.j2
  text_template: daily_news.txt.j2
  max_items: 5
```

- `sender`: From address used by email composition.
- `recipients`: one or more destination addresses; the list cannot be empty.
- `subject`: Jinja subject template; `report_date` is available.
- `template_directory`: directory containing both report templates.
- `html_template`: HTML email template filename.
- `text_template`: plain-text fallback template filename.
- `max_items`: maximum report entries, from 1 through 200.

Customize branding and layout in `templates/email/daily_news.html.j2`. Keep inline CSS
for email-client compatibility. Customize the fallback in
`templates/email/daily_news.txt.j2`.

## 4. Test the email appearance without sending

Preview today using deterministic stored copy:

```powershell
python -m ccip.cli preview --open
```

Preview a specific date:

```powershell
python -m ccip.cli preview --date 2026-07-20 --open
```

Choose the output file:

```powershell
python -m ccip.cli preview --output reports\test-email.html --open
```

Add `--resummarize` only when an Ollama rewrite is wanted. The preview command writes
HTML locally; it does not invoke SMTP.

## 5. Configure SMTP

```yaml
email:
  smtp:
    host: smtp.example.com
    port: 587
    username: null
    password: null
    start_tls: true
    timeout_seconds: 30
```

- `host`: SMTP hostname; required.
- `port`: integer from 1 through 65535.
- `username`: optional login name.
- `password`: optional password. Do not commit a real password to YAML.
- `start_tls`: upgrades the SMTP connection with STARTTLS when `true`.
- `timeout_seconds`: positive connection and operation timeout.

Set secrets for the current PowerShell session instead:

```powershell
$env:CCIP_SMTP_HOST = "smtp.example.com"
$env:CCIP_SMTP_USERNAME = "service-account@example.com"
$env:CCIP_SMTP_PASSWORD = "replace-with-secret"
```

These environment variables override the matching YAML values. SMTP composition and
delivery are implemented, but the current CLI does not yet expose a `send` command;
previewing and collection never send mail.

## 6. Configure intelligence sources

The main file references `config/sources.yml`:

```yaml
source_files:
  - sources.yml
```

Paths are relative to the main configuration file. Sources can also be placed directly
under a `sources:` list in the main file. Referenced and inline sources are merged.

Each source supports:

```yaml
- name: Example Feed
  kind: rss
  url: https://example.com/feed.xml
  category: Security News
  priority: 3
  enabled: true
```

- `name`: unique display name.
- `kind`: `rss`, `api`, or `web`. Current collectors implement RSS and the CISA KEV API;
  generic `web` collection is reserved but not implemented.
- `url`: unique feed/API URL.
- `category`: report grouping label.
- `priority`: integer from 1 (supplemental) through 5 (most authoritative/actionable).
- `enabled`: set `false` to retain a source without collecting it.

Duplicate names and duplicate URLs are rejected.

## 7. Configure application and database behavior

```yaml
app:
  environment: development
  log_level: INFO

database:
  url: sqlite:///data/ccip.db
  echo: false
```

- `app.environment`: free-form environment label such as `development` or `production`.
- `app.log_level`: logging level such as `DEBUG`, `INFO`, `WARNING`, or `ERROR`.
- `database.url`: SQLAlchemy database URL. The shipped setup uses local SQLite.
- `database.echo`: emits SQL statements when `true`; mainly useful for debugging.

## 8. Complete setting reference

| Setting | Default/constraint | Purpose |
|---|---|---|
| `app.environment` | `development` | Environment label |
| `app.log_level` | `INFO` | Application logging level |
| `database.url` | `sqlite:///data/ccip.db` | SQLAlchemy connection URL |
| `database.echo` | `false` | SQL debug logging |
| `summarization.provider` | `rules`; `rules`, `ollama`, `copilot` | Collection summarizer |
| `summarization.model` | `llama3.2:3b` | Model identifier |
| `summarization.endpoint` | `http://127.0.0.1:11434` | Ollama API base URL |
| `summarization.timeout_seconds` | positive; shipped as `180` | Model request timeout |
| `summarization.fallback_to_rules` | `true` | Continue if collection AI fails |
| `summarization.copilot_binary` | `copilot` | Copilot executable path/name |
| `email.sender` | required | From address |
| `email.recipients` | at least one | Destination addresses |
| `email.subject` | dated default template | Email subject template |
| `email.template_directory` | `templates/email` | Template directory |
| `email.html_template` | `daily_news.html.j2` | HTML template |
| `email.text_template` | `daily_news.txt.j2` | Plain-text template |
| `email.max_items` | schema default `25`; shipped as `5`; 1–200 | Report item limit |
| `email.smtp.host` | required | SMTP host |
| `email.smtp.port` | `587`; 1–65535 | SMTP port |
| `email.smtp.username` | `null` | Optional SMTP username |
| `email.smtp.password` | `null` | Optional SMTP password |
| `email.smtp.start_tls` | `true` | Enable STARTTLS |
| `email.smtp.timeout_seconds` | `30`; positive | SMTP timeout |
| `source_files` | empty list | Additional source registries |
| `sources` | empty list | Inline source definitions |

Configuration is strict: unknown keys, invalid values, missing required email/SMTP
fields, and duplicate source names or URLs fail immediately with a validation error.

## 9. Troubleshooting

### Ollama preview times out

Confirm the API and model:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
ollama list
```

Start Ollama, pull the configured model if missing, and increase
`summarization.timeout_seconds` for slow cold starts.

### Preview contains no items

Run collection first, then preview a date for which articles were stored:

```powershell
python -m ccip.cli collect
python -m ccip.cli preview --date 2026-07-20 --open
```

### A source fails

Check the URL, temporarily set `enabled: false`, and rerun collection. Some publishers
block automated requests even when their feed URL works in a browser.

### Validate changes

```powershell
python -m pytest
python -m ruff check .
python -m mypy src
```
