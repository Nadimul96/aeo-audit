from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest

from aeo_audit import audit_html, render_report
from aeo_audit.cli import main
from conftest import GOOD_URL, NOW, fixture_text

FIXTURES = Path(str(files("aeo_audit") / "fixtures"))


def test_demo_writes_three_reports_and_prints_both_audits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Score 99/100  Grade A" in out
    assert "Grade F" in out
    assert {p.name for p in tmp_path.iterdir()} == {
        "well-structured.html",
        "thin.html",
        "well-structured-blocked.html",
    }


def test_offline_audit_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "audit",
            GOOD_URL,
            "--offline",
            str(FIXTURES / "well-structured.html"),
            "--robots",
            str(FIXTURES / "robots-blocking.txt"),
            "--json",
        ]
    )
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["url"] == GOOD_URL
    assert data["blocked_agents"] == ["OAI-SearchBot", "GPTBot", "PerplexityBot"]
    assert data["signals"][0]["id"] == "crawl_access"


def test_fail_under_sets_the_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    thin = ["audit", "--offline", str(FIXTURES / "thin.html"), "--fail-under", "50"]
    assert main(thin) == 1
    assert main([*thin[:-1], "10"]) == 0
    capsys.readouterr()


def test_html_report_is_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "r.html"
    main(["audit", "--offline", str(FIXTURES / "thin.html"), "--html", str(target)])
    assert "Grade F" in target.read_text(encoding="utf-8")
    capsys.readouterr()


def test_errors_exit_with_code_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["audit", "http://127.0.0.1:1/"]) == 2
    assert main(["audit", "--offline", "/definitely/not/here.html"]) == 2
    assert "error:" in capsys.readouterr().err


def test_audit_without_a_target_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as stop:
        main(["audit"])
    assert stop.value.code == 2


def test_report_escapes_hostile_content() -> None:
    html = "<title>t</title><h2>Is <script>alert(1)</script> bad?</h2><p>text</p>"
    audit = audit_html(html, 'https://x.example/"><script>alert(2)</script>', now=NOW)
    report = render_report(audit)
    assert "<script>alert" not in report
    assert "&lt;script&gt;" in report


def test_report_headline_flags_blocked_crawlers_even_on_an_a() -> None:
    audit = audit_html(
        fixture_text("well-structured.html"),
        GOOD_URL,
        robots_text=fixture_text("robots-blocking.txt"),
        now=NOW,
    )
    report = render_report(audit)
    assert audit.grade == "A"
    assert "robots.txt blocks some AI crawlers" in report
    assert "OAI-SearchBot blocked" in report
