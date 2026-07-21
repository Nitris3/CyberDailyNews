# ruff: noqa: E501, E701, E702
"""Local browser dashboard for configuring and operating CCIP."""

from __future__ import annotations

import html
import json
import secrets
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from typing import BinaryIO

import yaml

from ccip.collection_status import load_collection_status, record_rescore_seconds
from ccip.config import Settings, load_settings
from ccip.db import Database, build_engine
from ccip.microsoft_copilot import (
    COPILOT_DELEGATED_PERMISSIONS,
    CopilotDeviceAuthenticator,
    DeviceSignIn,
    evaluate_copilot_readiness,
)
from ccip.repository import DeliveryRepository
from ccip.summarization import check_ollama
from ccip.windows_schedule import configure_windows_task


def _form_value(form: dict[str, list[str]], name: str, default: str = "") -> str:
    return form.get(name, [default])[0].strip()


def _acquire_instance_lock(path: Path) -> BinaryIO | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except (ImportError, OSError):
        handle.close()
        return None
    return handle


def save_dashboard_config(path: Path, form: dict[str, list[str]]) -> None:
    """Persist non-secret dashboard settings only to an ignored local config."""
    if not path.name.endswith(".local.yml"):
        raise ValueError("Dashboard changes require a config/*.local.yml file")
    current = load_settings(path)
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    summary = document.setdefault("summarization", {})
    summary["provider"] = _form_value(form, "provider", "rules")
    summary["audience"] = _form_value(form, "audience")
    summary["instructions"] = _form_value(form, "instructions")
    scoring = document.setdefault("scoring", {})
    for name in (
        "priority_multiplier", "known_exploited_bonus", "ransomware_bonus",
        "critical_keyword_bonus", "medium_threshold", "high_threshold",
        "critical_threshold", "max_score",
    ):
        scoring[name] = float(_form_value(form, name))
    scoring["watchlist_keywords"] = [
        line.strip()
        for line in _form_value(form, "watchlist_keywords").splitlines()
        if line.strip().strip("'\"")
    ]
    scoring["watchlist_bonus"] = float(_form_value(form, "watchlist_bonus"))
    email = document.setdefault("email", {})
    email["sender"] = _form_value(form, "sender")
    email["recipients"] = [
        value.strip() for value in _form_value(form, "recipients").split(",") if value.strip()
    ]
    email["subject"] = _form_value(form, "subject")
    email["max_items"] = int(_form_value(form, "max_items"))
    smtp = email.setdefault("smtp", {})
    smtp["host"] = _form_value(form, "smtp_host")
    smtp["port"] = int(_form_value(form, "smtp_port"))
    smtp["username"] = _form_value(form, "smtp_username") or None
    smtp["password"] = None
    smtp["start_tls"] = form.get("start_tls") == ["yes"]
    microsoft = document.setdefault("microsoft_365_copilot", {})
    microsoft["tenant_id"] = _form_value(form, "m365_tenant_id")
    microsoft["client_id"] = _form_value(form, "m365_client_id")
    microsoft["enabled"] = (
        form.get("m365_enabled") == ["yes"]
        and bool(microsoft["tenant_id"])
        and bool(microsoft["client_id"])
    )
    schedule = document.setdefault("schedule", {})
    schedule["enabled"] = form.get("schedule_enabled") == ["yes"]
    schedule["daily_time"] = _form_value(form, "daily_time", "08:00")
    report = document.setdefault("report", {})
    report["timezone"] = _form_value(form, "report_timezone", "local")
    if "source_controls_present" in form:
        enabled_sources = set(form.get("enabled_source", []))
        collection = document.setdefault("collection", {})
        collection["disabled_sources"] = [
            source.name for source in current.sources if source.name not in enabled_sources
        ]
    collection = document.setdefault("collection", {})
    collection["retention_days"] = int(_form_value(form, "retention_days", "365"))
    collection["retry_attempts"] = int(_form_value(form, "retry_attempts", "2"))
    collection["retry_backoff_seconds"] = float(
        _form_value(form, "retry_backoff_seconds", "0.5")
    )
    collection["stale_after_days"] = int(_form_value(form, "stale_after_days", "14"))
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    load_settings(path)


def dashboard_config_backup(path: Path) -> bytes:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ValueError("configuration root must be a YAML mapping")
    smtp = document.setdefault("email", {}).setdefault("smtp", {})
    smtp["password"] = None
    return yaml.safe_dump(document, sort_keys=False).encode()


def restore_dashboard_config(path: Path, content: str) -> None:
    if not path.name.endswith(".local.yml"):
        raise ValueError("Dashboard changes require a config/*.local.yml file")
    document = yaml.safe_load(content) or {}
    if not isinstance(document, dict):
        raise ValueError("backup must contain a YAML mapping")
    smtp = document.setdefault("email", {}).setdefault("smtp", {})
    smtp["password"] = None
    temporary = path.with_name(f"{path.stem}.restore.yml")
    temporary.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    try:
        load_settings(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _watchlist_text(settings: Settings) -> str:
    return "\n".join(settings.scoring.watchlist_keywords)


def _health_panel(status: dict[str, object] | None) -> str:
    if not status:
        return '<section class="card health"><h2>Collection health</h2><p>No collection run recorded yet.</p></section>'
    raw_sources = status.get("sources")
    sources = raw_sources if isinstance(raw_sources, list) else []
    failed = [s for s in sources if isinstance(s, dict) and s.get("status") == "failed"]
    stale = [s for s in sources if isinstance(s, dict) and s.get("status") == "stale"]
    warning = ""
    if sources and len(failed) >= max(1, len(sources) // 2):
        warning = '<div class="warning">Warning: most configured sources failed.</div>'
    elif failed:
        warning = f'<div class="warning">{len(failed)} source(s) failed.</div>'
    if stale:
        warning += f'<div class="warning">{len(stale)} source(s) may be stale.</div>'
    rows = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_status = str(source.get("status", "unknown"))
        rows.append(
            f'<tr><td>{html.escape(str(source.get("name", "Unknown")))}</td>'
            f'<td class="{html.escape(source_status)}">{html.escape(source_status.title())}</td>'
            f'<td>{html.escape(str(source.get("item_count", 0)))}</td>'
            f'<td>{html.escape(str(source.get("error") or ""))}</td></tr>'
        )
    return (
        '<section class="card health"><h2>Collection health</h2>'
        f'{warning}<p><strong>Last run:</strong> {html.escape(str(status.get("completed_at", "Unknown")))}<br>'
        f'Collection {html.escape(str(status.get("total_seconds", "?")))}s · '
        f'Rescore {html.escape(str(status.get("rescore_seconds") or "not recorded"))}s · '
        f'New articles {html.escape(str(status.get("stored", 0)))}</p>'
        '<details><summary>Show source details</summary><div class="table-wrap"><table><thead>'
        '<tr><th>Source</th><th>Status</th><th>Items</th><th>Details</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></details></section>'
    )


def _delivery_status(settings: Settings) -> dict[str, object]:
    database = Database(build_engine(settings.database.url, echo=settings.database.echo))
    database.create_schema()
    with database.session() as session:
        repository = DeliveryRepository(session)
        attempts = repository.recent_attempts()
        already_sent = repository.was_sent(date.today(), settings.email.recipients)
    smtp_ready = bool(
        settings.email.sender and settings.email.recipients and settings.email.smtp.host
    )
    return {
        "already_sent": already_sent,
        "smtp_ready": smtp_ready,
        "credential_required": bool(
            settings.email.smtp.username and settings.email.smtp.password is None
        ),
        "attempts": attempts,
    }


def _delivery_panel(status: dict[str, object] | None) -> str:
    if not status:
        return ""
    duplicate = (
        '<div class="warning">Today\'s report was already sent to these recipients.</div>'
        if status.get("already_sent")
        else ""
    )
    readiness = "Ready" if status.get("smtp_ready") else "Configuration incomplete"
    credential = (
        "A credential will be requested after approval."
        if status.get("credential_required")
        else "No interactive SMTP credential is currently required."
    )
    rows = []
    attempts = status.get("attempts")
    if isinstance(attempts, list):
        for attempt in attempts:
            rows.append(
                f"<tr><td>{html.escape(str(attempt.attempted_at))}</td>"
                f"<td>{html.escape(attempt.status.title())}</td>"
                f"<td>{html.escape(str(attempt.report_date))}</td>"
                f"<td>{attempt.item_count}</td>"
                f"<td>{html.escape(attempt.recipients)}</td>"
                f"<td>{html.escape(attempt.detail or '')}</td></tr>"
            )
    history = (
        '<details><summary>Recent delivery activity</summary><div class="table-wrap"><table>'
        '<thead><tr><th>Time</th><th>Status</th><th>Report</th><th>Items</th>'
        f'<th>Recipients</th><th>Details</th></tr></thead><tbody>{"".join(rows)}</tbody>'
        '</table></div></details>'
        if rows
        else "<p>No delivery attempts recorded yet.</p>"
    )
    return (
        '<section class="card health"><h2>Email delivery</h2>'
        f'{duplicate}<p><strong>SMTP:</strong> {readiness}<br>{html.escape(credential)}</p>'
        f"{history}</section>"
    )


def _setup_checklist(settings: Settings) -> str:
    email_ready = bool(
        settings.email.sender
        and settings.email.recipients
        and settings.email.smtp.host
        and "example.com" not in settings.email.sender
    )
    enabled_sources = len(settings.sources) - len(settings.collection.disabled_sources)
    items = (
        (email_ready, "Email sender, recipients, and SMTP configured"),
        (enabled_sources > 0, f"News sources enabled ({enabled_sources})"),
        (settings.email.max_items <= 5, "Email limited to five or fewer articles"),
        (True, "AI is optional; rules-only mode is supported"),
    )
    complete = sum(ready for ready, _ in items)
    rows = "".join(
        f'<li><span aria-hidden="true">{"✓" if ready else "○"}</span> '
        f'{html.escape(label)}</li>'
        for ready, label in items
    )
    return (
        '<section class="card checklist" aria-labelledby="setup-title">'
        f'<h2 id="setup-title">Getting started ({complete}/{len(items)})</h2>'
        f'<ul>{rows}</ul></section>'
    )


def render_dashboard(
    settings: Settings,
    token: str,
    message: str = "",
    popup: str = "",
    collection_status: dict[str, object] | None = None,
    delivery_status: dict[str, object] | None = None,
) -> bytes:
    def checked(value: bool) -> str:
        return " checked" if value else ""
    options = "".join(
        f'<option value="{name}"{(" selected" if settings.summarization.provider == name else "")}>{label}</option>'
        for name, label in (("rules", "No AI"), ("ollama", "Local Ollama"))
    )
    s = settings.scoring
    microsoft = settings.microsoft_365_copilot
    copilot_readiness = evaluate_copilot_readiness(
        microsoft.tenant_id, microsoft.client_id, enabled=microsoft.enabled
    )
    disabled_sources = set(settings.collection.disabled_sources)
    source_controls = "".join(
        f'<label><input style="width:auto" type="checkbox" name="enabled_source" '
        f'value="{html.escape(source.name, quote=True)}"'
        f'{checked(source.name not in disabled_sources)}> {html.escape(source.name)}</label>'
        for source in settings.sources
    )
    microsoft_status = (
        "Ready for interactive work-account sign-in testing."
        if copilot_readiness.ready_for_sign_in
        else " ".join(copilot_readiness.issues)
    )
    permission_text = ", ".join(COPILOT_DELEGATED_PERMISSIONS)
    notice_style = "" if message else ' style="display:none"'
    notice = (
        f'<div class="notice" id="status" role="status" aria-live="polite"'
        f'{notice_style}>{html.escape(message)}</div>'
    )
    health_panel = _health_panel(collection_status)
    delivery_panel = _delivery_panel(delivery_status)
    setup_checklist = _setup_checklist(settings)
    popup_script = f"<script>alert({popup!r})</script>" if popup else ""
    status_url = json.dumps(f"/status?token={token}")
    status_script = f"""<script>
    let wasBusy=false;async function refreshStatus(){{try{{const r=await fetch({status_url});if(!r.ok)return;
    const s=await r.json();const n=document.getElementById('status');
    if(s.message){{n.textContent=s.message;n.style.display='block';}}
    const b=document.querySelector('button[value="collect"]');if(b)b.disabled=s.busy;
    if(wasBusy&&!s.busy){{location.reload();return;}}wasBusy=s.busy;
    }}catch(_error){{}}}}
    setInterval(refreshStatus,1000);refreshStatus();
    </script>"""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Cyber Daily News</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#eef2f7;color:#172033;font:15px Arial}}header{{background:#142b4a;color:white;padding:24px 5vw}}h1{{margin:0 0 6px}}main{{max-width:1200px;margin:auto;padding:22px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}}.card{{background:white;padding:20px;border-radius:10px;box-shadow:0 2px 9px #0001}}label{{display:block;font-weight:bold;margin:12px 0 4px}}input,select,textarea{{width:100%;padding:9px;border:1px solid #adb9c9;border-radius:5px;font:inherit}}textarea{{resize:vertical}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}button{{border:0;border-radius:5px;padding:11px 15px;font-weight:bold;cursor:pointer;background:#075da8;color:white}}button.secondary{{background:#52647a}}button.good{{background:#087443}}button.warn{{background:#9a6700}}.actions{{display:flex;flex-wrap:wrap;gap:9px}}.notice{{background:#dff7e9;color:#14532d;padding:12px;border-radius:6px;margin-bottom:16px}}small{{color:#52647a}}@media(max-width:600px){{.row{{grid-template-columns:1fr}}}}
    </style><style>.skip-link{{position:absolute;left:-9999px}}.skip-link:focus{{left:12px;top:12px;background:white;padding:10px;z-index:10}}:focus-visible{{outline:3px solid #ffbf47;outline-offset:2px}}.workflow{{margin-bottom:16px}}.settings>summary{{background:#fff;padding:16px;border-radius:10px;margin-bottom:16px}}.checklist li{{margin:6px 0}}</style></head><body><a class="skip-link" href="#main">Skip to main content</a>{popup_script}{status_script}<header><h1>Cyber Daily News</h1><div>Configuration, ranking, preview, and reviewed delivery</div></header><main id="main">{notice}{setup_checklist}<form method="post"><input type="hidden" name="token" value="{token}"><section class="card workflow" aria-labelledby="workflow-title"><h2 id="workflow-title">Daily workflow</h2><div class="actions"><button name="action" value="collect">1. Collect news</button><button name="action" value="preview">2. Preview email</button><button name="action" value="review-send" class="good">3. Review & Send</button></div></section>{health_panel}{delivery_panel}<details class="settings"><summary>Settings and administration</summary><div class="grid">
    <section class="card"><h2>AI preference</h2><label>Provider</label><select name="provider">{options}</select>
    <small>No AI is always supported. Microsoft 365 Copilot setup is managed in its own panel below.</small>
    <label>Audience</label><input name="audience" value="{html.escape(settings.summarization.audience, quote=True)}">
    <label>Editorial guidance</label><textarea name="instructions" rows="5">{html.escape(settings.summarization.instructions)}</textarea>
    <div class="actions"><button name="action" value="ollama-check" class="secondary">Check Ollama</button></div></section>
    <section class="card"><h2>Microsoft 365 Copilot (preview)</h2><p><strong>Status:</strong> {html.escape(microsoft_status)}</p>
    <p>This connection requires a Microsoft 365 Copilot add-on license and an Entra public-client application approved by your administrator.</p>
    <ol><li>Open App registrations in Entra and create a single-tenant application.</li><li>Enable public client flows under Authentication.</li><li>Add the Copilot Chat API delegated permissions and grant administrator consent.</li><li>Paste the IDs below, enable the connection, and save.</li></ol>
    <label>Directory (tenant) ID</label><input name="m365_tenant_id" value="{html.escape(microsoft.tenant_id, quote=True)}" placeholder="00000000-0000-0000-0000-000000000000">
    <label>Application (client) ID</label><input name="m365_client_id" value="{html.escape(microsoft.client_id, quote=True)}" placeholder="00000000-0000-0000-0000-000000000000">
    <label><input style="width:auto" type="checkbox" name="m365_enabled" value="yes"{checked(microsoft.enabled)}> Enable after administrator consent</label>
    <p><strong>Required delegated permissions:</strong> {html.escape(permission_text)}</p>
    <div class="actions"><button name="action" value="m365-sign-in" class="secondary">Test Microsoft sign-in</button></div>
    <p><a href="https://m365.cloud.microsoft/chat" target="_blank">Test my work-account Copilot sign-in</a></p>
    <p><a href="https://entra.microsoft.com/" target="_blank">Open Microsoft Entra admin center</a> · <a href="https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/api/ai-services/chat/overview" target="_blank">Microsoft setup documentation</a></p></section>
    <section class="card"><h2>Scoring</h2><div class="row">
    <label>Priority multiplier<input name="priority_multiplier" type="number" step=".1" value="{s.priority_multiplier}"></label>
    <label>Exploited bonus<input name="known_exploited_bonus" type="number" step=".1" value="{s.known_exploited_bonus}"></label>
    <label>Ransomware bonus<input name="ransomware_bonus" type="number" step=".1" value="{s.ransomware_bonus}"></label>
    <label>Critical-term bonus<input name="critical_keyword_bonus" type="number" step=".1" value="{s.critical_keyword_bonus}"></label>
    <label>Medium threshold<input name="medium_threshold" type="number" step=".1" value="{s.medium_threshold}"></label>
    <label>High threshold<input name="high_threshold" type="number" step=".1" value="{s.high_threshold}"></label>
    <label>Critical threshold<input name="critical_threshold" type="number" step=".1" value="{s.critical_threshold}"></label>
    <label>Maximum score<input name="max_score" type="number" step=".1" value="{s.max_score}"></label></div></section>
    <section class="card"><h2>Company watchlist</h2><small>One keyword per line. Put phrases in quotes, for example 'Product X'.</small>
    <textarea name="watchlist_keywords" rows="10" placeholder="Vendor name&#10;'Product X'">{html.escape(_watchlist_text(settings))}</textarea>
    <label>Watchlist match bonus</label><input name="watchlist_bonus" type="number" step=".1" min="0" max="10" value="{s.watchlist_bonus}"></section>
    <section class="card"><h2>Email</h2><label>From</label><input name="sender" value="{html.escape(settings.email.sender, quote=True)}"><label>Recipients</label><input name="recipients" value="{html.escape(', '.join(settings.email.recipients), quote=True)}"><label>Subject</label><input name="subject" value="{html.escape(settings.email.subject, quote=True)}"><label>Maximum articles</label><input name="max_items" type="number" min="1" max="200" value="{settings.email.max_items}"><div class="row"><label>SMTP host<input name="smtp_host" value="{html.escape(settings.email.smtp.host, quote=True)}"></label><label>Port<input name="smtp_port" type="number" value="{settings.email.smtp.port}"></label></div><label>SMTP username<input name="smtp_username" value="{html.escape(settings.email.smtp.username or '', quote=True)}"></label><label><input style="width:auto" type="checkbox" name="start_tls" value="yes"{checked(settings.email.smtp.start_tls)}> Use STARTTLS</label><small>Passwords are never saved here.</small></section>
    <section class="card"><h2>Daily schedule</h2><p>Automatically collect news and rescore it every day. Sending always remains a human-reviewed action.</p>
    <label><input style="width:auto" type="checkbox" name="schedule_enabled" value="yes"{checked(settings.schedule.enabled)}> Enable daily collection</label>
    <label>Run time<input name="daily_time" type="time" value="{settings.schedule.daily_time}"></label>
    <label>Report timezone<input name="report_timezone" value="{html.escape(settings.report.timezone, quote=True)}" placeholder="local or America/Chicago"></label>
    <small>Windows runs this task even when the dashboard is closed. Time uses this computer's local timezone.</small></section>
    <section class="card"><h2>News sources</h2><p>Select the feeds included during collection.</p><input type="hidden" name="source_controls_present" value="yes"><details><summary>Choose sources</summary>{source_controls}</details></section>
    <section class="card"><h2>Collection reliability</h2><div class="row"><label>Retention days<input name="retention_days" type="number" min="30" max="3650" value="{settings.collection.retention_days}"></label><label>Retry attempts<input name="retry_attempts" type="number" min="0" max="5" value="{settings.collection.retry_attempts}"></label><label>Retry backoff seconds<input name="retry_backoff_seconds" type="number" min="0" max="30" step="0.1" value="{settings.collection.retry_backoff_seconds}"></label><label>Stale after days<input name="stale_after_days" type="number" min="1" max="365" value="{settings.collection.stale_after_days}"></label></div></section>
    </div></details><div class="card" style="margin-top:16px"><div class="actions"><button name="action" value="save" class="good">Save settings</button><button name="action" value="rescore-apply" class="secondary">Rescore stored articles</button><a href="/backup?token={token}"><button type="button" class="secondary">Download settings backup</button></a><label style="margin:0"><span class="button-label">Restore settings</span><input id="restore-file" type="file" accept=".yml,.yaml" style="display:none"></label><button id="restore-submit" name="action" value="restore" type="submit" style="display:none">Restore</button><input id="backup-yaml" name="backup_yaml" type="hidden"></div><small>Backups never include an SMTP password.</small></div></form>
    <script>document.getElementById('restore-file').addEventListener('change',e=>{{const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=()=>{{if(confirm('Replace local settings with this validated backup?')){{document.getElementById('backup-yaml').value=r.result;document.getElementById('restore-submit').click();}}}};r.readAsText(f);}});</script>
    <script>document.querySelector('form').addEventListener('submit',e=>{{if(e.submitter&&e.submitter.value==='collect'){{let n=document.querySelector('.notice');if(!n){{n=document.createElement('div');n.className='notice';document.querySelector('main').prepend(n)}}n.textContent='Collecting news…';}}}})</script></main></body></html>"""
    return page.encode()


def run_dashboard(config_path: str | Path) -> None:
    path = Path(config_path).resolve()
    session_path = path.parent.parent / "data" / "dashboard.session.json"
    instance_lock = _acquire_instance_lock(path.parent.parent / "data" / "dashboard.lock")
    if instance_lock is None:
        try:
            existing = json.loads(session_path.read_text(encoding="utf-8"))
            existing_token = str(existing["token"])
        except Exception as error:
            raise RuntimeError("The dashboard is starting. Please try again.") from error
        webbrowser.open(
            f"http://127.0.0.1:8765/?token={urllib.parse.quote(existing_token)}"
        )
        return
    token = secrets.token_urlsafe(24)
    state: dict[str, object] = {"message": "", "popup": "", "busy": False}
    state_lock = threading.Lock()

    def command(*arguments: str, wait: bool = True) -> str:
        args = [sys.executable, "-m", "ccip.cli", "--config", str(path), *arguments]
        if wait:
            completed = subprocess.run(args, capture_output=True, text=True, timeout=600, check=False)
            output = (completed.stdout or completed.stderr).strip()
            if completed.returncode != 0:
                raise RuntimeError(output or f"Command failed with exit code {completed.returncode}")
            return output or "Action completed."
        subprocess.Popen(args)  # noqa: S603
        return "Opened in a new browser tab."

    def set_status(message: str, *, busy: bool) -> None:
        with state_lock:
            state["message"] = message
            state["busy"] = busy

    def collect_in_background() -> None:
        try:
            set_status("Fetching news sources...", busy=True)
            output = command("collect")
            stored = "unknown"
            elapsed = "unknown"
            for line in reversed(output.splitlines()):
                if '"stored"' not in line:
                    continue
                try:
                    event = json.loads(line)
                    stored = str(event.get("stored", "unknown"))
                    elapsed = str(event.get("total_seconds", "unknown"))
                except ValueError:
                    pass
                break
            set_status("News collected. Updating article scores...", busy=True)
            rescore_started = perf_counter()
            command("rescore", "--apply")
            record_rescore_seconds(perf_counter() - rescore_started)
            set_status(
                f"Collection completed in {elapsed} seconds. {stored} new articles "
                "found and scores updated.",
                busy=False,
            )
        except Exception as error:
            set_status(f"Collection failed: {error}", busy=False)

    def microsoft_sign_in_in_background(
        authenticator: CopilotDeviceAuthenticator, sign_in: DeviceSignIn
    ) -> None:
        try:
            authenticator.wait_for_sign_in(sign_in)
            set_status(
                "Microsoft work-account sign-in succeeded. The test token was discarded.",
                busy=False,
            )
        except Exception as error:
            set_status(f"Microsoft sign-in failed: {error}", busy=False)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _page(self) -> None:
            body = render_dashboard(
                load_settings(path),
                token,
                str(state["message"] or ""),
                str(state["popup"] or ""),
                load_collection_status(),
                _delivery_status(load_settings(path)),
            )
            state["popup"] = ""
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("token") != [token]: self.send_error(403); return
            if urllib.parse.urlsplit(self.path).path == "/backup":
                body = dashboard_config_backup(path)
                self.send_response(200); self.send_header("Content-Type", "application/yaml"); self.send_header("Content-Disposition", 'attachment; filename="cyber-daily-news-settings.yml"'); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if urllib.parse.urlsplit(self.path).path == "/status":
                with state_lock:
                    body = json.dumps(
                        {"message": str(state["message"]), "busy": bool(state["busy"])}
                    ).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            self._page()

        def do_POST(self) -> None:  # noqa: N802
            form = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
            if form.get("token") != [token]: self.send_error(403); return
            action = _form_value(form, "action", "save")
            try:
                if action in {
                    "save", "collect", "preview", "rescore-apply", "review-send",
                    "m365-sign-in",
                }:
                    save_dashboard_config(path, form)
                if action == "restore":
                    restore_dashboard_config(path, _form_value(form, "backup_yaml"))
                    state["message"] = "Settings backup restored and validated."
                elif action == "save":
                    settings = load_settings(path)
                    schedule_message = configure_windows_task(
                        path, settings.schedule.daily_time, enabled=settings.schedule.enabled
                    )
                    state["message"] = f"Settings saved locally. {schedule_message}"
                elif action == "collect":
                    with state_lock:
                        already_running = bool(state["busy"])
                    if already_running:
                        state["message"] = "Collection is already running."
                    else:
                        set_status("Starting news collection...", busy=True)
                        threading.Thread(target=collect_in_background, daemon=True).start()
                elif action == "preview": state["message"] = command("preview", "--open")
                elif action == "rescore-apply": state["message"] = command("rescore", "--apply")
                elif action == "review-send": state["message"] = command("send", "--confirm-send", wait=False)
                elif action == "m365-sign-in":
                    microsoft = load_settings(path).microsoft_365_copilot
                    readiness = evaluate_copilot_readiness(
                        microsoft.tenant_id, microsoft.client_id, enabled=microsoft.enabled
                    )
                    if not readiness.ready_for_sign_in:
                        state["message"] = " ".join(readiness.issues)
                    else:
                        authenticator = CopilotDeviceAuthenticator(
                            microsoft.tenant_id, microsoft.client_id
                        )
                        sign_in = authenticator.initiate()
                        set_status(
                            f"Enter code {sign_in.user_code} at "
                            f"{sign_in.verification_uri}. Waiting for sign-in...",
                            busy=True,
                        )
                        webbrowser.open(sign_in.verification_uri)
                        threading.Thread(
                            target=microsoft_sign_in_in_background,
                            args=(authenticator, sign_in),
                            daemon=True,
                        ).start()
                elif action == "ollama-check":
                    summary = load_settings(path).summarization
                    state["message"] = check_ollama(
                        summary.endpoint, summary.model
                    ).message
            except Exception as error:
                state["message"] = f"Action failed: {error}"
            self._page()

    port = 8765
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        try:
            existing = json.loads(session_path.read_text(encoding="utf-8"))
            existing_token = str(existing["token"])
        except Exception as error:
            raise RuntimeError(f"dashboard port {port} is already in use") from error
        webbrowser.open(
            f"http://127.0.0.1:{port}/?token={urllib.parse.quote(existing_token)}"
        )
        return
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps({"token": token}), encoding="utf-8")
    webbrowser.open(f"http://127.0.0.1:{port}/?token={urllib.parse.quote(token)}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            recorded_token = str(
                json.loads(session_path.read_text(encoding="utf-8")).get("token", "")
            )
        except (OSError, ValueError):
            recorded_token = ""
        if recorded_token == token:
            session_path.unlink(missing_ok=True)
        try:
            import msvcrt

            instance_lock.seek(0)
            msvcrt.locking(instance_lock.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            instance_lock.close()
