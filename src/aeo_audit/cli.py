"""Command line: audit a URL or a saved page, or run the offline demo."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from aeo_audit.audit import audit_html, audit_url
from aeo_audit.fetch import FetchError
from aeo_audit.model import Audit
from aeo_audit.report import render_report

_BAR = 20
_DEMO_NOW = datetime(2026, 10, 17, tzinfo=UTC)
_DEMO_PAGES = (
    ("well-structured", "https://tidepool-coffee.example/guides/how-long-does-cold-brew-last"),
    ("thin", "https://harborroast.example/"),
)


def _bar(score: int) -> str:
    filled = round(score / 100 * _BAR)
    return "█" * filled + "░" * (_BAR - filled)


def format_text(audit: Audit) -> str:
    lines = [f"{audit.url}", f"Score {audit.score}/100  Grade {audit.grade}", ""]
    for signal in audit.signals:
        lines.append(
            f"  {signal.label:<34} {_bar(signal.score)} {signal.score:>3}  [{signal.basis}]"
        )
        lines.append(f"      {signal.found}")
    if audit.blocked_agents:
        lines += ["", "Blocked by robots.txt: " + ", ".join(audit.blocked_agents)]
    if audit.recommendations:
        lines += ["", "What to fix, by points available:"]
        lines += [f"  +{r.points:<3} {r.fix}" for r in audit.recommendations]
    lines += [f"note: {note}" for note in audit.notes]
    return "\n".join(lines)


def _to_json(audit: Audit) -> str:
    return json.dumps(asdict(audit), default=lambda v: v.isoformat(), indent=2)


def _emit(audit: Audit, args: argparse.Namespace) -> None:
    print(_to_json(audit) if args.json else format_text(audit))
    if args.html:
        Path(args.html).write_text(render_report(audit), encoding="utf-8")
        print(f"\nwrote {args.html}", file=sys.stderr)


def _audit(args: argparse.Namespace) -> int:
    try:
        if args.offline:
            html = Path(args.offline).read_text(encoding="utf-8", errors="replace")
            robots = Path(args.robots).read_text(encoding="utf-8") if args.robots else None
            audit = audit_html(html, args.url or args.offline, robots_text=robots)
        else:
            audit = audit_url(args.url, timeout=args.timeout, allow_private=args.allow_private)
    except (FetchError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    _emit(audit, args)
    return 1 if audit.score < args.fail_under else 0


def _demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = files("aeo_audit") / "fixtures"
    robots = (fixtures / "robots-open.txt").read_text(encoding="utf-8")
    for name, url in _DEMO_PAGES:
        html = (fixtures / f"{name}.html").read_text(encoding="utf-8")
        audit = audit_html(html, url, robots_text=robots, now=_DEMO_NOW)
        (out / f"{name}.html").write_text(render_report(audit), encoding="utf-8")
        print(format_text(audit), end="\n\n")
    blocking = (fixtures / "robots-blocking.txt").read_text(encoding="utf-8")
    page = (fixtures / "well-structured.html").read_text(encoding="utf-8")
    audit = audit_html(page, _DEMO_PAGES[0][1], robots_text=blocking, now=_DEMO_NOW)
    (out / "well-structured-blocked.html").write_text(render_report(audit), encoding="utf-8")
    print("Same good page, but robots.txt blocks OAI-SearchBot and PerplexityBot:")
    print(f"  score {audit.score}/100, blocked: {', '.join(audit.blocked_agents)}\n")
    print(f"reports written to {out}/")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aeo-audit", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit", help="audit a live URL, or a saved page with --offline")
    audit.add_argument(
        "url", nargs="?", help="page URL (with --offline: the URL it was saved from)"
    )
    audit.add_argument("--offline", metavar="FILE", help="audit this saved HTML file, no network")
    audit.add_argument("--robots", metavar="FILE", help="robots.txt to use with --offline")
    audit.add_argument("--json", action="store_true", help="print JSON instead of text")
    audit.add_argument("--html", metavar="FILE", help="also write a self-contained HTML report")
    audit.add_argument("--fail-under", type=int, default=0, metavar="N", help="exit 1 below N")
    audit.add_argument("--timeout", type=float, default=10.0)
    audit.add_argument(
        "--allow-private", action="store_true", help="allow localhost and private addresses"
    )
    audit.set_defaults(run=_audit)

    demo = commands.add_parser("demo", help="audit two bundled pages offline and write reports")
    demo.add_argument("--out", default="aeo-demo")
    demo.set_defaults(run=_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit" and not (args.url or args.offline):
        build_parser().error("audit needs a URL or --offline FILE")
    return int(args.run(args))


if __name__ == "__main__":
    raise SystemExit(main())
