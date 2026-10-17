"""A self-contained HTML report: no scripts, no network, follows light and dark mode."""

from __future__ import annotations

import math
from html import escape

from aeo_audit.model import Audit, Signal

_STYLE = """
:root {
  color-scheme: light dark;
  --bg: #f7f7f8; --panel: #ffffff; --ink: #15171c; --muted: #646a76; --line: #e3e5ea;
  --good: #1f8f5f; --ok: #2f6bed; --warn: #c98a1d; --bad: #c4432f; --track: #e9ebef;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e1013; --panel: #16191e; --ink: #eceef2; --muted: #98a0ad; --line: #262a32;
    --good: #4cc58f; --ok: #6b9bff; --warn: #e3a244; --bad: #ee7a66; --track: #262a32;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 960px; margin: 0 auto; padding: 40px 16px 72px; }
h1 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
  margin: 0 0 6px; font-weight: 600; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
  margin: 36px 0 12px; font-weight: 600; }
.url { font-family: var(--mono); font-size: 15px; overflow-wrap: anywhere; }
.sub { color: var(--muted); font-size: 13px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; }
.hero { display: flex; gap: 28px; align-items: center; padding: 22px 24px; margin-top: 18px; }
.ring { position: relative; width: 132px; height: 132px; flex: none; }
.ring svg { transform: rotate(-90deg); }
.ring .track { stroke: var(--track); } .ring .arc { stroke: var(--tone); stroke-linecap: round; }
.ring .num { position: absolute; inset: 0; display: grid; place-content: center;
  text-align: center; }
.ring .num b { font-size: 34px; letter-spacing: -0.02em; line-height: 1;
  font-variant-numeric: tabular-nums; }
.ring .num span { font-size: 13px; color: var(--muted); }
.hero h3 { margin: 0 0 4px; font-size: 20px; letter-spacing: -0.01em; }
.hero p { margin: 0; color: var(--muted); font-size: 14px; max-width: 54ch; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.chip { font-family: var(--mono); font-size: 12px; padding: 2px 8px; border-radius: 99px;
  border: 1px solid var(--line); color: var(--muted); }
.chip.blocked { color: var(--bad); border-color: var(--bad); }
.fixes { padding: 4px 0; }
.fix { display: grid; grid-template-columns: 56px 1fr; gap: 12px; padding: 12px 18px;
  border-top: 1px solid var(--line); }
.fix:first-child { border-top: 0; }
.fix .pts { font-weight: 650; color: var(--ok); font-variant-numeric: tabular-nums; }
.fix .name { font-weight: 600; font-size: 14px; }
.fix .text { color: var(--muted); font-size: 14px; }
.signals { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 12px; }
.signal { padding: 16px 18px; }
.signal-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
.signal-head b { font-size: 15px; }
.tag { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted);
  border: 1px solid var(--line); border-radius: 4px; padding: 0 6px; margin-left: 8px;
  white-space: nowrap; }
.value { font-variant-numeric: tabular-nums; font-weight: 650; color: var(--tone);
  white-space: nowrap; }
.bar { height: 8px; border-radius: 99px; background: var(--track); margin: 10px 0 10px;
  overflow: hidden; }
.bar span { display: block; height: 100%; background: var(--tone); border-radius: 99px; }
.found { margin: 0; font-size: 14px; }
.evidence { margin: 8px 0 0; padding-left: 18px; color: var(--muted); font-size: 13px; }
.evidence li { font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
details { margin-top: 10px; font-size: 13px; color: var(--muted); }
summary { cursor: pointer; }
footer { margin-top: 36px; color: var(--muted); font-size: 12px; }
.t-good { --tone: var(--good); } .t-ok { --tone: var(--ok); }
.t-warn { --tone: var(--warn); } .t-bad { --tone: var(--bad); }
@media (max-width: 560px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .signals { grid-template-columns: 1fr; }
}
"""


def _tone(score: int) -> str:
    if score >= 90:
        return "t-good"
    if score >= 70:
        return "t-ok"
    if score >= 45:
        return "t-warn"
    return "t-bad"


def _ring(score: int) -> str:
    circumference = 2 * math.pi * 56
    arc = circumference * score / 100
    return f"""<div class="ring {_tone(score)}">
      <svg width="132" height="132" viewBox="0 0 132 132" aria-hidden="true">
        <circle class="track" cx="66" cy="66" r="56" fill="none" stroke-width="10"/>
        <circle class="arc" cx="66" cy="66" r="56" fill="none" stroke-width="10"
                stroke-dasharray="{arc:.1f} {circumference:.1f}"/>
      </svg>
      <div class="num"><b>{score}</b><span>out of 100</span></div>
    </div>"""


def _signal_card(signal: Signal) -> str:
    evidence = "".join(f"<li>{escape(item)}</li>" for item in signal.evidence)
    return f"""
    <section class="card signal {_tone(signal.score)}">
      <div class="signal-head">
        <span><b>{escape(signal.label)}</b><span class="tag">{signal.basis}</span></span>
        <span class="value">{signal.score}<span class="sub"> · weight {signal.weight}</span></span>
      </div>
      <div class="bar" role="img" aria-label="{signal.score} out of 100"><span
        style="width:{signal.score}%"></span></div>
      <p class="found">{escape(signal.found)}</p>
      {f'<ul class="evidence">{evidence}</ul>' if evidence else ""}
      <details><summary>Why this is checked</summary><p>{escape(signal.why)}</p></details>
    </section>"""


def render_report(audit: Audit) -> str:
    """Render one audit as a single HTML page."""
    labels = {s.id: s.label for s in audit.signals}
    nothing = (
        '<div class="fix"><span class="pts">·</span><div class="text">Nothing to fix.</div></div>'
    )
    fixes = (
        "".join(
            f"""
      <div class="fix">
        <span class="pts">+{rec.points}</span>
        <div><div class="name">{escape(labels[rec.signal_id])}</div>
        <div class="text">{escape(rec.fix)}</div></div>
      </div>"""
            for rec in audit.recommendations
        )
        or nothing
    )
    chips = "".join(
        f'<span class="chip blocked">{escape(token)} blocked</span>'
        for token in audit.blocked_agents
    )
    notes = "".join(f'<p class="sub">{escape(note)}</p>' for note in audit.notes)
    access = next((s for s in audit.signals if s.id == "crawl_access"), None)
    blocked = access is not None and access.fix is not None and access.score < 100
    headline = {
        "A": "Well set up to be fetched and quoted.",
        "B": "Mostly in good shape, with a few gaps.",
        "C": "Workable, with clear room to improve.",
        "D": "Several basics are missing.",
        "F": "Hard for a crawler or a reader to use as a source.",
    }[audit.grade]
    if blocked and audit.grade in ("A", "B"):
        headline = "Good content, but robots.txt blocks some AI crawlers."
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AEO audit · {escape(audit.url)}</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
  <h1>AEO audit</h1>
  <div class="url">{escape(audit.url)}</div>
  <div class="sub">{audit.audited_at:%b} {audit.audited_at.day}, {audit.audited_at.year}</div>
  {notes}
  <div class="card hero {_tone(audit.score)}">
    {_ring(audit.score)}
    <div>
      <h3>Grade {audit.grade}: {headline}</h3>
      <p>A rule-of-thumb score for how easily this page can be fetched and quoted by AI answer
      engines. It is not a prediction: no score guarantees a citation.</p>
      {f'<div class="chips">{chips}</div>' if chips else ""}
    </div>
  </div>
  <h2>What to fix, by points available</h2>
  <div class="card fixes">{fixes}</div>
  <h2>Signals</h2>
  <div class="signals">{"".join(_signal_card(s) for s in audit.signals)}</div>
  <footer>
    "mechanical" signals report a plain fact about the page. "heuristic" signals are
    rules of thumb whose weights are my judgment and have not been validated against real
    citation data.
  </footer>
</main>
</body>
</html>
"""
