# Configuration and Setup Guide

This guide covers every supported setting and provides two setup paths:

- **No AI:** the default; requires no model service or AI tooling.
- **Optional AI:** uses local Ollama for collection and/or preview rewriting.

All commands below run from the `CyberDailyNews` project directory in PowerShell.

## 1. Install the application

For a one-click Windows setup, double-click `Setup-CyberDailyNews.cmd`. It creates the
environment, installs the project, creates the ignored local configuration, initializes
the database, and opens the dashboard. It never installs Ollama or enables AI.

For manual or development installation:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m ccip.cli init-db
```

After installation, normal users can double-click `Start-CyberDailyNews.cmd`.
It creates the ignored local configuration when needed and opens the browser dashboard.
The remaining commands in this guide are available for administrators and troubleshooting;
routine configuration and operation can be completed in the dashboard.

The application requires Python 3.12 or newer. Configuration defaults to
`config/ccip.yml`; select another file by placing `--config path\to\file.yml` before
the command name.

Keep personal addresses and SMTP settings in `config/ccip.local.yml`. Files matching
`config/*.local.yml` are ignored by Git. Start by copying the tracked example, then edit
only the ignored copy:

```powershell
Copy-Item config\ccip.yml config\ccip.local.yml
```

```powershell
python -m ccip.cli --config config\ccip.local.yml preview --open
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

This path never calls an AI service. It uses deterministic cleanup, truncation,
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
     audience: senior executives and business leaders
     instructions: >-
       Use plain language. Focus on business impact, urgency, and the action or decision
       leaders need to understand. Avoid unnecessary technical detail.
   ```

3. Run collection:

   ```powershell
   python -m ccip.cli collect
   ```

With `fallback_to_rules: true`, collection continues with deterministic summaries if
Ollama is unavailable. Set it to `false` only when model failure should stop collection.

### Microsoft 365 Copilot for enterprise

Microsoft 365 Copilot is not the GitHub Copilot CLI. Its Chat API currently requires a
licensed work account, tenant application registration, delegated Microsoft Graph
permissions, and administrator consent. The API is also currently documented as preview.
The dashboard therefore explains these requirements but does not claim the provider is
enabled. Choose **No AI** or **Local Ollama** until an administrator configures and approves
the Microsoft 365 integration.

The dashboard provides a dedicated setup panel with direct links to Microsoft Entra and
the Microsoft documentation. An administrator supplies the Directory (tenant) ID and
Application (client) ID after registering and consenting to the application. These IDs
are stored only in the ignored local configuration. The dashboard continues to show the
integration as incomplete until administrator consent and API validation are available.

After valid IDs and administrator consent are available, enable the connection and use
**Test Microsoft sign-in**. The dashboard opens Microsoft's device sign-in page and shows
a one-time code. Microsoft handles the password, MFA, Conditional Access, and consent.
The delegated access token is used only to confirm sign-in and is then discarded; it is
never written to configuration or disk.

### Back up or restore local settings

Use **Download settings backup** in the dashboard to save the current local YAML. SMTP
passwords are always removed. Use **Restore settings** to select a YAML backup; the file
is validated before it replaces the ignored local configuration.

### Add an article manually

Use **Add an article to this email** inside the live review screen for a story found
outside configured feeds. Headline, summary, and an `http://` or `https://` hyperlink are
required. The article is added only to the current draft and checked against the other
stories in that email. Duplicate URLs and substantially similar headlines are rejected.

## 3. Configure the report

### Configure ranking and company watchlists

Ranking is deterministic and configurable. Source priority establishes the base score;
exploitation, ransomware, critical terms, and company watchlists add bonuses. Scores are
capped by `max_score`. Reports select the highest scores first and use publication time
to break ties.

```yaml
scoring:
  priority_multiplier: 1.2
  known_exploited_bonus: 2.0
  ransomware_bonus: 1.5
  critical_keyword_bonus: 1.0
  exploited_keywords: [exploited vulnerabilit, known exploited]
  ransomware_keywords: [ransomware]
  critical_keywords: [critical, remote code execution, zero-day]
  medium_threshold: 4.0
  high_threshold: 7.0
  critical_threshold: 9.0
  max_score: 10.0
  watchlist_keywords:
    - ExampleCorp
    - "Product X"
    - Example Partner
  watchlist_bonus: 2.0
```

Watchlist matching is case-insensitive and searches the source title, summary, category,
and source name. Enter one keyword per line in the dashboard. Put multi-word phrases in
quotes, such as `'Product X'`. The bonus is added once when any keyword matches.

Thresholds must increase in this order:
`medium_threshold < high_threshold < critical_threshold <= max_score`.

After changing scoring or watchlists, preview the effect on existing stored articles:

```powershell
python -m ccip.cli --config config\ccip.local.yml rescore
```

The default is read-only and reports how many records would change. Apply only after
reviewing the policy:

```powershell
python -m ccip.cli --config config\ccip.local.yml rescore --apply
```

Rescoring uses stored titles and summaries plus the current source priorities. It does
not collect feeds, call AI, alter article text, or send email.

In the dashboard, collection automatically applies rescoring after new articles are
stored. The single **Rescore articles** button also applies the current scoring policy;
there is no separate preview-rescore control in the user interface.

Collection uses deterministic rules so all feeds can be processed quickly. When Ollama
is selected, AI rewriting is deferred until preview or review and applies only to the
final, deduplicated report items (five by default). Previously stored article identities
are rejected before text processing. The dashboard reports the collection duration.
Collection runs as a background job: the page remains responsive, prevents overlapping
runs, and updates the green status area while fetching, rescoring, and completing.
The large CISA KEV catalog is cached locally for six hours by default. Set
`collection.kev_cache_hours` to `0` to disable caching or choose up to 168 hours.
Invalid responses are never cached. Use the dashboard's **News sources** card to include
or exclude individual feeds without editing YAML. Reopening the launcher reuses the
existing dashboard instead of starting another server.

Transient source failures are retried with exponential backoff. Sources whose newest
entry exceeds `stale_after_days` are marked stale in Collection Health. Retention removes
old stored articles and rejects expired feed entries before processing, preventing them
from being reintroduced by large catalogs.

The application opens to a dedicated analyst workspace showing the current email exactly
as it will be delivered. Analysts can collect news, then open **Review, edit & send** to
add an outside article, edit or reorder stories, remove items, approve delivery, or deny
the draft. Configuration stays on the separate **Setup & Administration** page, which
includes the setup checklist. Keyboard users
have a skip link and visible focus indicators; status changes use an ARIA live region.

Database schema versions are recorded automatically when the application starts. This
provides a safe migration boundary for future releases and refuses databases created by
a newer incompatible application version.

### Configure a daily schedule

Use the dashboard's **Daily schedule** card to enable collection and choose a local time.
Click **Save settings** to create or update the per-user Windows scheduled task. At that
time each day, Windows collects sources and automatically rescores stored articles. It
never sends email automatically; review and approval remain required.

The dashboard does not need to remain running. Disable the checkbox and save to remove
the task. The time uses the computer's local timezone and 24-hour `HH:MM` format.
Scheduled runs explicitly use the project directory, so relative database, template,
report, and cache paths remain reliable when Windows starts the task unattended.

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

These environment variables override the matching YAML values. Previewing and collection
never send mail.

## 6. Test and send email safely

The `send` command is a dry run unless delivery is explicitly confirmed. First prepare
the exact email as local HTML:

```powershell
python -m ccip.cli send --date 2026-07-20
```

The dry run uses the configured sender, recipients, subject, templates, and five-item
limit, but makes no SMTP connection. Choose a path or request AI rewriting if wanted:

```powershell
python -m ccip.cli send --date 2026-07-20 --output reports\send-test.html
python -m ccip.cli send --date 2026-07-20 --resummarize
```

After reviewing the output and configuring SMTP secrets, explicitly authorize delivery:

```powershell
python -m ccip.cli --config config\ccip.local.yml send --date 2026-07-20 --confirm-send
```

Confirmed delivery opens a local browser review application. Reviewers can edit titles
and summaries directly, include or exclude articles, drag cards to reorder them, request
a local-AI rewrite, and compare changes against the live email preview. **Save & Preview**
applies edits without sending. **Deny** stops before SMTP. **Approve & Send** requires the
Gmail app password and is the only browser action that permits delivery.

The application binds only to `127.0.0.1` on a temporary port and requires a random,
one-time session token. The app password is held in memory only for the approved send.
The review cannot approve an empty report.
Use `--bypass-review` only when intentionally skipping this human gate; it still requires
`--confirm-send` and still refuses an initially empty report.

After successful delivery, the date and recipient set are recorded locally. Another
dashboard send of the same report is blocked to prevent accidental duplicate delivery.

If `email.smtp.username` is configured and no password is present in YAML or
`CCIP_SMTP_PASSWORD`, the command securely prompts for the SMTP credential every time.
Input is hidden and is retained only for that process. For Gmail accounts with two-step
verification, enter an app password rather than the normal account password.

`--dry-run` may be supplied for clarity, but it is already the default. `--dry-run` and
`--confirm-send` are mutually exclusive. There is no implicit or scheduled delivery.

## 7. Configure intelligence sources

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

## 8. Configure application and database behavior

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

## 9. Complete setting reference

| Setting | Default/constraint | Purpose |
|---|---|---|
| `app.environment` | `development` | Environment label |
| `app.log_level` | `INFO` | Application logging level |
| `database.url` | `sqlite:///data/ccip.db` | SQLAlchemy connection URL |
| `database.echo` | `false` | SQL debug logging |
| `summarization.provider` | `rules`; `rules`, `ollama` | Collection summarizer |
| `summarization.model` | `llama3.2:3b` | Model identifier |
| `summarization.endpoint` | `http://127.0.0.1:11434` | Ollama API base URL |
| `summarization.timeout_seconds` | positive; shipped as `180` | Model request timeout |
| `summarization.fallback_to_rules` | `true` | Continue if collection AI fails |
| `summarization.audience` | executive audience | Intended reader for AI output |
| `summarization.instructions` | executive editorial guidance | Additional AI writing direction |
| `scoring.priority_multiplier` | `1.2`; nonnegative | Converts source priority into base score |
| `scoring.known_exploited_bonus` | `2.0`; nonnegative | Bonus for exploited keywords |
| `scoring.ransomware_bonus` | `1.5`; nonnegative | Bonus for ransomware evidence |
| `scoring.critical_keyword_bonus` | `1.0`; nonnegative | Bonus for critical keywords |
| `scoring.exploited_keywords` | exploited terms | Case-insensitive exploited indicators |
| `scoring.ransomware_keywords` | `ransomware` | Case-insensitive ransomware indicators |
| `scoring.critical_keywords` | critical/RCE/zero-day | High-impact indicators |
| `scoring.medium_threshold` | `4.0` | Minimum medium-severity score |
| `scoring.high_threshold` | `7.0` | Minimum high-severity score |
| `scoring.critical_threshold` | `9.0` | Minimum critical-severity score |
| `scoring.max_score` | `10.0`; positive | Score ceiling |
| `scoring.watchlist_keywords` | empty list | Company keywords or quoted phrases |
| `scoring.watchlist_bonus` | `1.0`; 0–10 | Bonus applied once when any keyword matches |
| `microsoft_365_copilot.tenant_id` | empty | Microsoft Entra directory identifier |
| `microsoft_365_copilot.client_id` | empty | Registered application identifier |
| `microsoft_365_copilot.enabled` | `false` | Reserved until consent/API validation succeeds |
| `schedule.enabled` | `false` | Enable daily collection and rescoring |
| `schedule.daily_time` | `08:00` | Local run time in 24-hour `HH:MM` format |
| `report.timezone` | `local` | Local computer time or an IANA zone such as `America/Chicago` |
| `collection.retention_days` | `365`; 30–3650 | Stored article retention and oldest accepted feed age |
| `collection.retry_attempts` | `2`; 0–5 | Retries after the initial source request |
| `collection.retry_backoff_seconds` | `0.5`; 0–30 | Initial exponential retry delay |
| `collection.stale_after_days` | `14`; 1–365 | Age that marks a source stale |
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

## 10. Troubleshooting

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
