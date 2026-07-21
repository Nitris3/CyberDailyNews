"""Local browser-based human review for outbound reports."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import html
import secrets
import urllib.parse
import webbrowser
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

from ccip.domain import DailyReport, IntelligenceItem, Severity
from ccip.rendering import ReportRenderer
from ccip.reporting import unique_articles


@dataclass(frozen=True, slots=True)
class ApprovedReview:
    report: DailyReport
    credential: str | None


def update_report(report: DailyReport, form: dict[str, list[str]]) -> DailyReport:
    """Apply browser edits, inclusion choices, and ordering to a report."""
    order = form.get("order", [","]).pop().split(",")
    indexes = [int(value) for value in order if value.isdigit()]
    if sorted(indexes) != list(range(len(report.items))):
        indexes = list(range(len(report.items)))
    items = []
    for index in indexes:
        if form.get(f"include_{index}") != ["yes"]:
            continue
        item = report.items[index]
        title = form.get(f"title_{index}", [item.title])[0].strip()
        summary = form.get(f"summary_{index}", [item.summary])[0].strip()
        if title and summary:
            items.append(replace(item, title=title, summary=summary))
    return replace(report, items=tuple(items))


def render_review_page(
    report: DailyReport,
    renderer: ReportRenderer,
    *,
    token: str,
    sender: str,
    recipients: tuple[str, ...],
    subject: str,
    error: str | None = None,
) -> bytes:
    cards = []
    for index, item in enumerate(report.items):
        cards.append(
            f"""
            <article class="card" draggable="true" data-index="{index}">
              <div class="card-head"><span class="handle">☰</span>
                <span class="meta">Score {item.score:.1f} · {html.escape(item.source)}</span>
                <label><input type="checkbox" name="include_{index}" value="yes" checked> Include</label>
              </div>
              <label>Headline<input name="title_{index}" value="{html.escape(item.title, quote=True)}" required></label>
              <label>Summary<textarea name="summary_{index}" rows="3" required>{html.escape(item.summary)}</textarea></label>
            </article>"""
        )
    preview = html.escape(renderer.render_html(report), quote=True)
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    document = f"""<!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Review Cyber Daily News</title><style>
    *{{box-sizing:border-box}} body{{margin:0;font:15px Arial;background:#eef2f7;color:#172033}}
    header{{padding:18px 24px;background:#142b4a;color:white}} h1{{margin:0 0 5px;font-size:22px}}
    .layout{{display:grid;grid-template-columns:minmax(420px,1fr) minmax(420px,1fr);gap:18px;padding:18px}}
    .panel{{background:white;border-radius:10px;padding:18px;box-shadow:0 2px 9px #0001}}
    .details{{color:#dce5ef}} .card{{border:1px solid #ccd5e1;border-radius:8px;padding:14px;margin:0 0 12px;background:#fff}}
    .card.dragging{{opacity:.45}} .card-head{{display:flex;gap:10px;align-items:center;margin-bottom:10px}}
    .handle{{cursor:grab;font-size:20px}} .meta{{flex:1;color:#52647a;font-size:12px}}
    label{{display:block;font-weight:bold;margin:8px 0}} input[type=text],input:not([type]),textarea{{width:100%;padding:9px;border:1px solid #aeb9c8;border-radius:5px;margin-top:5px;font:inherit}}
    textarea{{resize:vertical}} iframe{{width:100%;height:72vh;border:1px solid #ccd5e1;border-radius:6px}}
    .actions{{position:sticky;bottom:0;background:white;padding:12px 0 0;display:flex;gap:8px;flex-wrap:wrap}}
    button{{border:0;border-radius:5px;padding:10px 14px;font-weight:bold;cursor:pointer}}
    .save{{background:#dce5ef}} .ai{{background:#6d4cc7;color:white}} .deny{{background:#b42318;color:white}}
    .approve{{background:#087443;color:white}} .credential{{flex:1;min-width:230px}}
    .error{{background:#fee4e2;color:#912018;padding:10px;border-radius:5px;margin-bottom:12px}}
    @media(max-width:950px){{.layout{{grid-template-columns:1fr}}}}
    </style></head><body><header><h1>Review Cyber Daily News</h1>
    <div class="details">From {html.escape(sender)} · To {html.escape(', '.join(recipients))} · {html.escape(subject)}</div></header>
    <main class="layout"><section class="panel"><h2>Articles</h2>{error_html}
    <form method="post" id="review-form"><input type="hidden" name="token" value="{token}">
    <input type="hidden" name="order" id="order"><div id="cards">{''.join(cards)}</div>
    <div class="card" style="background:#f7f9fc"><h3>Add an article to this email</h3>
    <label>Headline<input name="manual_title" placeholder="Article headline"></label>
    <label>Summary<textarea name="manual_summary" rows="3" placeholder="Short executive summary"></textarea></label>
    <label>Hyperlink<input name="manual_url" type="url" placeholder="https://example.com/article"></label>
    <button class="save" name="action" value="add">Add to preview</button></div>
    <div class="actions"><button class="save" name="action" value="save">Save & Preview</button>
    <button class="ai" name="action" value="ai">Rewrite with AI</button>
    <button class="deny" name="action" value="deny" formnovalidate>Deny</button>
    <label class="credential">Gmail app password<input type="password" name="credential" autocomplete="off"></label>
    <button class="approve" name="action" value="approve">Approve & Send</button></div></form></section>
    <section class="panel"><h2>Live email preview</h2><iframe srcdoc="{preview}"></iframe></section></main>
    <script>const cards=document.querySelector('#cards');let drag;
    cards.addEventListener('dragstart',e=>{{drag=e.target.closest('.card');drag.classList.add('dragging')}});
    cards.addEventListener('dragend',()=>{{drag.classList.remove('dragging');drag=null}});
    cards.addEventListener('dragover',e=>{{e.preventDefault();const target=e.target.closest('.card');if(target&&target!==drag){{const box=target.getBoundingClientRect();cards.insertBefore(drag,e.clientY<box.top+box.height/2?target:target.nextSibling)}}}});
    document.querySelector('#review-form').addEventListener('submit',()=>{{document.querySelector('#order').value=[...cards.children].map(x=>x.dataset.index).join(',')}});
    </script></body></html>"""
    return document.encode()


def run_web_review(
    report: DailyReport,
    renderer: ReportRenderer,
    *,
    sender: str,
    recipients: tuple[str, ...],
    subject: str,
    credential_required: bool,
    rewrite: Any = None,
) -> ApprovedReview | None:
    """Run a one-time localhost review session and wait for approval or denial."""
    token = secrets.token_urlsafe(24)
    state: dict[str, Any] = {"report": report, "result": False, "error": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _page(self) -> None:
            body = render_review_page(
                state["report"], renderer, token=token, sender=sender,
                recipients=recipients, subject=subject, error=state["error"],
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if query.get("token") != [token]:
                self.send_error(403)
                return
            self._page()

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            form = urllib.parse.parse_qs(self.rfile.read(length).decode())
            if form.get("token") != [token]:
                self.send_error(403)
                return
            action = form.get("action", ["save"])[0]
            state["error"] = None
            if action == "deny":
                state["result"] = None
                self._finish("Email denied. You may close this window.")
                return
            candidate = update_report(state["report"], form)
            if action == "add":
                title = form.get("manual_title", [""])[0].strip()
                summary = form.get("manual_summary", [""])[0].strip()
                url = form.get("manual_url", [""])[0].strip()
                if not title or not summary or not url:
                    state["error"] = "Headline, summary, and hyperlink are required."
                    self._page()
                    return
                if urllib.parse.urlsplit(url).scheme.lower() not in {"http", "https"}:
                    state["error"] = "Hyperlink must begin with http:// or https://."
                    self._page()
                    return
                identifier = hashlib.sha256(f"{title.lower()}|{url.lower()}".encode()).hexdigest()
                added = IntelligenceItem(
                    identifier,
                    "Manual review addition",
                    title,
                    url,
                    datetime.now(UTC),
                    summary,
                    "Manually selected",
                    Severity.HIGH,
                    8.0,
                )
                combined = [*candidate.items, added]
                if len(unique_articles(combined)) != len(combined):
                    state["error"] = "That story is already in the draft."
                    self._page()
                    return
                state["report"] = replace(candidate, items=(*candidate.items, added))
                self._page()
                return
            if action == "ai" and rewrite is not None:
                candidate = rewrite(candidate)
            state["report"] = candidate
            if action == "approve":
                credential = form.get("credential", [""])[0].strip()
                if not candidate.items:
                    state["error"] = "At least one article is required."
                elif credential_required and not credential:
                    state["error"] = "Enter the Gmail app password to approve delivery."
                else:
                    state["result"] = ApprovedReview(candidate, credential or None)
                    self._finish("Approved. Delivery is continuing securely; you may close this window.")
                    return
            self._page()

        def _finish(self, message: str) -> None:
            body = f"<html><body style='font:18px Arial;padding:40px'><h1>{html.escape(message)}</h1></body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    webbrowser.open(f"http://127.0.0.1:{port}/?token={urllib.parse.quote(token)}")
    while state["result"] is False:
        server.handle_request()
    server.server_close()
    return cast(ApprovedReview | None, state["result"])
