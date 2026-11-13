"""Markdown and HTML versions of the evaluation."""

from __future__ import annotations

import html
from typing import Any

CLASSIFIERS = {
    "keywords": "Keyword rules",
    "words only": "Learned model, words only",
    "triage": "Triage (hazard screen + model)",
}
POLICIES = {
    "inbox": "Inbox order, no triage",
    "keywords": "Keyword rules flag emergencies",
    "triage": "Triage flags emergencies",
}
BANKS = {
    "validation": "Validation phrasings (seen while the lexicon was written)",
    "fresh": "Fresh phrasings (written after the freeze): the test",
}


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def usd(c: float) -> str:
    return f"${c / 100:,.0f}"


def markdown(r: dict[str, Any]) -> str:
    t = r["tuning"]
    out = [
        "# Property management: evaluation",
        "",
        "Maintenance requests written the way tenants write them, triaged by urgency and trade, then a simulated "
        "month per portfolio of who gets to an emergency how fast. Plus a year of rent through two ways of "
        "allocating payments.",
        "",
        f"Trained on {t['messages']:,} messages using the tuning phrasings. Word regularisation {t['l2_words']} and "
        f"emergency threshold {t['threshold']} were chosen by cross-validation holding out whole phrasings "
        f"(false-alarm budget {pct(t['false_alarm_budget'])}).",
        "",
    ]
    for bank, label in BANKS.items():
        if bank not in r["classify"]:
            continue
        ex = r["examples"][bank]
        out += [
            f"## {label}",
            "",
            f"{ex['kinds']} kinds of problem, {ex['phrasings']} phrasings.",
            "",
            "| Messages | Emergencies caught | False alarms | Urgency right | Trade right |",
            "|---|---:|---:|---:|---:|",
        ]
        for k, name in CLASSIFIERS.items():
            c = r["classify"][bank][k]
            out.append(
                f"| {name} | {pct(c['emergency_recall'])} | {pct(c['false_alarm_rate'])} | "
                f"{pct(c['urgency_accuracy'])} | {pct(c['trade_accuracy'])} |"
            )
        p = r["portfolios"][bank]
        n = int(p["inbox"]["emergencies"])
        out += [
            "",
            f"Simulated months: {int(p['inbox']['requests']):,} requests, {n} emergencies.",
            "",
            "| Policy | Emergencies attended within 4 h | Median | 90th percentile | Worst | False alarms a week | At night |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for k, name in POLICIES.items():
            a = p[k]
            out.append(
                f"| {name} | {int(a['emergencies_within_4h'])} of {n} ({pct(a['within_4h_share'])}) | "
                f"{a['emergency_median_h']:.1f} h | {a['emergency_p90_h']:.1f} h | {a['emergency_worst_h']:.1f} h | "
                f"{a['false_alarms_per_week']:.1f} | {a['night_false_alarms_per_week']:.1f} |"
            )
        if ex["missed_emergencies"]:
            out += ["", "Emergencies triage missed (sample):", ""] + [f"- {m}" for m in ex["missed_emergencies"]]
        out.append("")
    out += [
        "## Tuning (phrasing-held-out cross-validation)",
        "",
        "| Word L2 | Threshold | Emergencies caught | Urgency right | Trade right |",
        "|---:|---:|---:|---:|---:|",
    ]
    for g in t["grid"]:
        out.append(
            f"| {g['l2_words']} | {g['threshold']} | {pct(g['emergency_recall'])} | {pct(g['urgency_accuracy'])} | "
            f"{pct(g['trade_accuracy'])} |"
        )
    led = r["ledger"]
    out += [
        "",
        "## Rent ledger: a year, 5 portfolios",
        "",
        "| Allocation | Late fees | Fees total | Fees while all rent was paid | Paid all rent, shown owing rent |",
        "|---|---:|---:|---:|---:|",
    ]
    for k, a in led.items():
        out.append(
            f"| {k} | {int(a['late_fees']):,} | {usd(a['fees_total'])} | {int(a['fees_while_all_rent_paid']):,} | "
            f"{int(a['paid_all_rent_but_shown_owing_rent'])} of {int(a['paid_all_rent'])} |"
        )
    g = r.get("gate")
    if g:
        out += ["", "## Gate (regression limits)", "", "PASSED" if g["passed"] else "FAILED"]
        out += [f"- {f}" for f in g["failures"]]
    return "\n".join(out) + "\n"


CSS = """
:root{--bg:#0d1016;--panel:#151b24;--line:#263042;--ink:#e8edf4;--ink2:#97a3b6;--ok:#3ccf8e;--bad:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:34px 28px 56px}h1{font-size:28px;margin:0 0 4px}h2{font-size:18px;
margin:28px 0 12px}.sub{color:var(--ink2);margin:0 0 20px}.tiles{display:grid;grid-template-columns:repeat(4,1fr);
gap:12px}.tile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px}.tile b{
display:block;font-size:26px}.tile span{color:var(--ink2);font-size:13px}table{width:100%;border-collapse:collapse;
background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13.5px}th,td{
padding:8px 12px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}
th{color:var(--ink2);font-weight:500;font-size:12px}.good{color:var(--ok);font-weight:600}.bad{color:var(--bad);
font-weight:600}ul{color:var(--ink2)}@media(max-width:800px){.tiles{grid-template-columns:1fr 1fr}}
"""


def html_report(r: dict[str, Any]) -> str:
    e = html.escape
    bank = "fresh" if "fresh" in r["classify"] else "validation"
    c = r["classify"][bank]
    p = r["portfolios"][bank]
    led = r["ledger"]
    tiles = [
        (
            pct(p["triage"]["within_4h_share"]),
            f"of emergencies attended within 4 hours with triage, vs {pct(p['keywords']['within_4h_share'])} with keyword "
            f"rules and {pct(p['inbox']['within_4h_share'])} in inbox order ({bank} phrasings)",
        ),
        (
            f"{p['triage']['emergency_worst_h']:.0f} h vs {p['inbox']['emergency_worst_h']:.0f} h",
            "longest wait for an emergency: triage vs inbox order",
        ),
        (
            pct(c["triage"]["emergency_recall"]),
            f"of emergency messages caught, vs {pct(c['keywords']['emergency_recall'])} for keyword rules, at "
            f"{pct(c['triage']['false_alarm_rate'])} false alarms",
        ),
        (
            f"0 vs {int(led['oldest first']['fees_while_all_rent_paid']):,}",
            "late fees charged while all rent was paid: rent-first allocation vs strictly oldest first",
        ),
    ]
    out = [
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
        f"initial-scale=1'><title>Property management evaluation</title><style>{CSS}</style><main><h1>Property "
        "management: evaluation</h1><p class='sub'>Maintenance requests in tenants' own words, triaged and dispatched "
        "in simulated months; and a year of rent through two ways of allocating payments.</p><div class='tiles'>"
    ]
    out += [f"<div class='tile'><b>{e(v)}</b><span>{e(t)}</span></div>" for v, t in tiles]
    out.append("</div>")
    for b, label in BANKS.items():
        if b not in r["classify"]:
            continue
        cb, pb = r["classify"][b], r["portfolios"][b]
        best = max(cb[k]["emergency_recall"] for k in CLASSIFIERS)
        out.append(
            f"<h2>{e(label)}</h2><table><tr><th>Messages</th><th>Emergencies caught</th><th>False alarms</th>"
            "<th>Urgency right</th><th>Trade right</th></tr>"
        )
        for k, name in CLASSIFIERS.items():
            a = cb[k]
            out.append(
                f"<tr><td>{e(name)}</td><td class='{'good' if a['emergency_recall'] == best else ''}'>"
                f"{pct(a['emergency_recall'])}</td><td>{pct(a['false_alarm_rate'])}</td><td>"
                f"{pct(a['urgency_accuracy'])}</td><td>{pct(a['trade_accuracy'])}</td></tr>"
            )
        n = int(pb["inbox"]["emergencies"])
        out.append(
            f"</table><p class='sub' style='margin-top:12px'>Simulated months: {int(pb['inbox']['requests']):,} "
            f"requests, {n} emergencies.</p><table><tr><th>Policy</th><th>Within 4 h</th><th>Median</th>"
            "<th>90th pct</th><th>Worst</th><th>False alarms / week</th><th>At night</th></tr>"
        )
        top = max(pb[k]["within_4h_share"] for k in POLICIES)
        for k, name in POLICIES.items():
            a = pb[k]
            out.append(
                f"<tr><td>{e(name)}</td><td class='{'good' if a['within_4h_share'] == top else ''}'>"
                f"{pct(a['within_4h_share'])}</td><td>{a['emergency_median_h']:.1f} h</td><td>"
                f"{a['emergency_p90_h']:.1f} h</td><td>{a['emergency_worst_h']:.1f} h</td><td>"
                f"{a['false_alarms_per_week']:.1f}</td><td>{a['night_false_alarms_per_week']:.1f}</td></tr>"
            )
        out.append("</table>")
        missed = r["examples"][b]["missed_emergencies"]
        if missed:
            out.append(
                "<p class='sub' style='margin-top:12px'>Emergencies triage missed (sample):</p><ul>"
                + "".join(f"<li>{e(m)}</li>" for m in missed)
                + "</ul>"
            )
    out.append(
        "<h2>Rent ledger: a year, 5 portfolios</h2><table><tr><th>Allocation</th><th>Late fees</th>"
        "<th>Fees total</th><th>Fees while all rent was paid</th><th>Paid all rent, shown owing rent</th></tr>"
    )
    for k, a in led.items():
        bad = "bad" if a["fees_while_all_rent_paid"] else "good"
        out.append(
            f"<tr><td>{e(k)}</td><td>{int(a['late_fees']):,}</td><td>{usd(a['fees_total'])}</td>"
            f"<td class='{bad}'>{int(a['fees_while_all_rent_paid']):,}</td><td>"
            f"{int(a['paid_all_rent_but_shown_owing_rent'])} of {int(a['paid_all_rent'])}</td></tr>"
        )
    out.append("</table>")
    g = r.get("gate")
    if g:
        out.append(
            f"<h2>Gate (regression limits)</h2><p class='{'good' if g['passed'] else 'bad'}'>"
            f"{'Passed' if g['passed'] else 'Failed'}</p>"
        )
        if g["failures"]:
            out.append("<ul>" + "".join(f"<li>{e(f)}</li>" for f in g["failures"]) + "</ul>")
    out.append("</main></html>")
    return "".join(out) + "\n"
