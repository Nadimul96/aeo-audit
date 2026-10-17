"""aeo-audit: audit how well a page is set up to be fetched and quoted by AI answer engines."""

from aeo_audit.audit import audit_html, audit_url, grade_for
from aeo_audit.fetch import FetchError
from aeo_audit.model import Audit, Recommendation, Signal
from aeo_audit.report import render_report

__all__ = [
    "Audit",
    "FetchError",
    "Recommendation",
    "Signal",
    "audit_html",
    "audit_url",
    "grade_for",
    "render_report",
]
