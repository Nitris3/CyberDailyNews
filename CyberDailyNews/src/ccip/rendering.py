"""Jinja-based HTML and plain-text report rendering."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ccip.domain import DailyReport


class ReportRenderer:
    def __init__(self, template_directory: str | Path) -> None:
        self.environment = Environment(
            loader=FileSystemLoader(template_directory),
            autoescape=select_autoescape(("html", "xml")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_html(self, report: DailyReport) -> str:
        return self.environment.get_template("daily_news.html.j2").render(report=report)

    def render_text(self, report: DailyReport) -> str:
        return self.environment.get_template("daily_news.txt.j2").render(report=report)

    def render_subject(self, subject_template: str, report: DailyReport) -> str:
        return self.environment.from_string(subject_template).render(report_date=report.report_date)

