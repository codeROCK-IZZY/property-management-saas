"""The property manager's console: the maintenance board after a weekend, each request's triage and why, tenant
ledgers, owner statements, and triaging a new request."""

from __future__ import annotations

import datetime as dt
import html
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .corpus import TEMPLATES, Request, generate, split
from .dispatch import CALL_BACK_H
from .ledger import Lease, Ledger, money
from .reader import Reader, Reading
from .triage import Decision, Triage, fit

e = html.escape
NOW = dt.datetime(2026, 11, 16, 8, 30)  # Monday morning, after a weekend of requests
TODAY = NOW.date()
BUILDINGS = {"Quayside Court": 12, "Elm Terrace": 8, "Mill Lane": 10}
OWNERS = ["Harrow Holdings", "Okoye Family", "Linden Trust", "Castillo Lettings"]
FIRST = [
    "Maria",
    "James",
    "Aisha",
    "Wei",
    "Sofia",
    "Kwame",
    "Hannah",
    "Tomás",
    "Grace",
    "Oliver",
    "Leila",
    "Daniel",
    "Chloe",
    "Priya",
    "Noah",
    "Amara",
    "Lucas",
    "Mei",
    "Samuel",
    "Zara",
]
LAST = [
    "Lopez",
    "Brennan",
    "Bello",
    "Chen",
    "Rossi",
    "Mensah",
    "Becker",
    "Silva",
    "Kim",
    "Grant",
    "Haddad",
    "Novak",
    "Martin",
    "Nair",
    "Reed",
    "Okafor",
    "Brook",
    "Lin",
    "Adeyemi",
    "Price",
]
COLUMNS = (
    ("emergency", "Call back now", "bad"),
    ("urgent", "Urgent: dispatch today", "warn"),
    ("routine", "Routine: schedule", "info"),
)

CSS = """
:root{--bg:#0d1117;--panel:#151b24;--line:#263041;--ink:#e8edf4;--ink2:#97a3b6;--ok:#3ccf8e;--bad:#ff6b6b;--mid:#f5b54a;
--acc:#7aa2ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,system-ui,
sans-serif}a{color:inherit}header{padding:14px 26px;border-bottom:1px solid var(--line);display:flex;gap:18px;
align-items:baseline;flex-wrap:wrap}header b{font-size:17px}header nav a{color:var(--ink2);text-decoration:none;
margin-right:14px}main{padding:20px 26px 48px;max-width:1260px;margin:0 auto}.grid{display:grid;
grid-template-columns:repeat(4,1fr);gap:12px}.card{background:var(--panel);border:1px solid var(--line);
border-radius:12px;padding:14px 16px}.card b{display:block;font-size:24px}.muted{color:var(--ink2)}table{width:100%;
border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--ink2);
font-weight:500;font-size:12px}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.b{display:inline-block;padding:1px 9px;border-radius:99px;font-size:11.5px;font-weight:600;white-space:nowrap}
.ok{background:#3ccf8e22;color:var(--ok)}.warn{background:#f5b54a22;color:var(--mid)}.bad{background:#ff6b6b22;
color:var(--bad)}.info{background:#7aa2ff22;color:var(--acc)}h1{font-size:22px;margin:0 0 4px}h2{font-size:13px;
color:var(--ink2);text-transform:uppercase;letter-spacing:.05em;margin:24px 0 8px}.board{display:grid;
grid-template-columns:repeat(3,minmax(240px,1fr));gap:12px}.col{background:var(--panel);border:1px solid var(--line);
border-radius:12px;padding:12px}.col h3{margin:0 0 10px;font-size:14px}.chip{display:block;text-decoration:none;
border:1px solid var(--line);border-radius:9px;padding:9px 11px;margin-bottom:8px;font-size:13px}.chip:hover{
border-color:var(--acc)}.msg{font-style:italic;color:#c9d3e0}textarea{width:100%;min-height:110px;background:#0f141c;
color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:8px 10px;font:inherit}button{background:
var(--acc);color:#0b1020;border:0;border-radius:6px;padding:8px 14px;font:inherit;font-weight:600;cursor:pointer}
@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.board{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
        f"initial-scale=1'><title>{e(title)}</title><style>{CSS}</style><header><b>Keyhold Property Management</b><nav>"
        "<a href='/'>Maintenance</a><a href='/tenants'>Tenants</a><a href='/owners'>Owners</a>"
        "<a href='/triage'>Triage a request</a></nav><span class='muted'>demo portfolio, Monday 16 November 2026, "
        f"08:30</span></header><main>{body}</main></html>"
    )


@dataclass
class Unit:
    id: str
    building: str
    owner: str
    tenant: str


@dataclass
class Ticket:
    id: int
    unit: Unit
    at: dt.datetime
    request: Request
    decision: Decision

    @property
    def alerted(self) -> dt.datetime | None:
        if self.decision.urgency != "emergency":
            return None
        return self.at + dt.timedelta(hours=CALL_BACK_H)


@dataclass
class Console:
    triage: Triage
    units: list[Unit]
    tickets: list[Ticket]
    ledger: Ledger
    maintenance: list[tuple[str, str, int]] = field(default_factory=list)
    reader: Reader | None = None

    def lease_for(self, unit_id: str) -> Lease:
        return next(lease for lease in self.ledger.leases.values() if lease.unit == unit_id)


def _units() -> list[Unit]:
    out = []
    i = 0
    for b, n in BUILDINGS.items():
        for k in range(n):
            code = "".join(w[0] for w in b.split())
            out.append(
                Unit(
                    f"{code}-{k + 1:02d}",
                    b,
                    OWNERS[(i * 3 + k) % len(OWNERS)],
                    f"{FIRST[i % len(FIRST)]} {LAST[(i * 7 + 3) % len(LAST)]}",
                )
            )
            i += 1
    return out


def _ledger(units: list[Unit], seed: int = 7) -> Ledger:
    g = np.random.default_rng(seed)
    leases = []
    for i, u in enumerate(units):
        start = dt.date(2026, int(g.integers(1, 8)), int(g.choice([1, 1, 1, 10, 15, 20])))
        leases.append(
            Lease(
                f"L{i + 1:03d}",
                u.tenant,
                u.id,
                u.owner,
                start,
                start.replace(year=2027) - dt.timedelta(days=1),
                int(g.integers(9, 26)) * 10_000,
            )
        )
    led = Ledger(leases)
    habit = {lease.id: ("late" if g.random() < 0.2 else "short" if g.random() < 0.1 else "on time") for lease in leases}
    pays: dict[dt.date, list[tuple[str, int]]] = {}
    for lease in leases:
        y, m = lease.start.year, lease.start.month
        while dt.date(y, m, 1) <= TODAY:
            from .ledger import due_date, rent_for

            amount, _ = rent_for(lease, y, m)
            due = due_date(lease, y, m)
            delay = int(g.integers(8, 16)) if habit[lease.id] == "late" and g.random() < 0.5 else int(g.integers(0, 3))
            if habit[lease.id] == "short" and g.random() < 0.5:
                amount = int(amount * 0.8)
            if amount and due + dt.timedelta(days=delay) <= TODAY:
                pays.setdefault(due + dt.timedelta(days=delay), []).append((lease.id, amount))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    d = dt.date(2026, 1, 1)
    while d <= TODAY:
        led.charge_rent(d)
        for lease_id, amount in pays.get(d, []):
            led.pay(lease_id, d, amount)
        led.charge_late_fees(d)
        d += dt.timedelta(days=1)
    return led


def demo_console(reader: Reader | None = None) -> Console:
    tri = fit(generate(1500, 1, split(TEMPLATES, "tuning")))
    units = _units()
    g = np.random.default_rng(11)
    weekend = generate(26, 77, split(TEMPLATES, "heldout"))
    start = NOW - dt.timedelta(hours=63.5)  # Friday 17:00
    tickets = []
    for i, r in enumerate(weekend):
        at = start + dt.timedelta(hours=float(g.uniform(0, 63.0)))
        tickets.append(
            Ticket(i, units[int(g.integers(len(units)))], at.replace(second=0, microsecond=0), r, tri.decide(r.text))
        )
    tickets.sort(key=lambda t: t.at)
    for i, t in enumerate(tickets):
        t.id = i + 1
    maintenance = [
        (units[i].id, job, cost)
        for i, job, cost in (
            (0, "Boiler pressure reset", 9_500),
            (3, "Tap washer", 6_000),
            (12, "Lock barrel replaced", 14_500),
            (21, "Fridge thermostat", 11_000),
            (25, "Drain unblocked", 8_500),
        )
    ]
    return Console(tri, units, tickets, _ledger(units), maintenance, reader)


class TriageIn(BaseModel):
    text: str


def _when(t: dt.datetime) -> str:
    return t.strftime("%a %H:%M")


def _ago(t: dt.datetime) -> str:
    h = (NOW - t).total_seconds() / 3600
    return f"{h:.0f} h ago" if h >= 1 else f"{h * 60:.0f} min ago"


def decision_json(d: Decision) -> dict[str, Any]:
    return {"urgency": d.urgency, "trade": d.trade, "p_emergency": d.p_emergency, "hazards": d.hazards, "why": d.why}


def create_app(c: Console) -> FastAPI:
    app = FastAPI(title="Property management")

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "requests": len(c.tickets),
            "leases": len(c.ledger.leases),
            "claude": c.reader is not None,
        }

    @app.post("/api/triage")
    def api_triage(body: TriageIn) -> dict[str, Any]:
        if not body.text.strip():
            raise HTTPException(422, "describe the problem")
        return triage_text(c, body.text)

    @app.get("/api/requests")
    def api_requests() -> list[dict[str, Any]]:
        return [
            {"id": t.id, "unit": t.unit.id, "at": t.at.isoformat(), "text": t.request.text, **decision_json(t.decision)}
            for t in c.tickets
        ]

    @app.get("/api/tenants")
    def api_tenants() -> list[dict[str, Any]]:
        return [
            {"lease": lease.id, "tenant": lease.tenant, "unit": lease.unit, **c.ledger.balance(lease.id)}
            for lease in c.ledger.leases.values()
        ]

    @app.get("/", response_class=HTMLResponse)
    def board() -> str:
        cols = []
        for urg, label, cls in COLUMNS:
            mine = [t for t in c.tickets if t.decision.urgency == urg]
            chips = []
            for t in sorted(mine, key=lambda t: t.at):
                status = (
                    f"<span class='b bad'>on-call alerted {_when(t.alerted)}</span>"
                    if t.alerted
                    else f"<span class='b {cls}'>{e(t.decision.trade)}</span>"
                )
                chips.append(
                    f"<a class='chip' href='/requests/{t.id}'><div>{status} <span class='muted'>{e(t.unit.id)} · "
                    f"{_ago(t.at)}</span></div><div class='msg'>“{e(t.request.text[:120])}”</div></a>"
                )
            cols.append(
                f"<div class='col'><h3><span class='b {cls}'>{len(mine)}</span> {e(label)}</h3>{''.join(chips)}</div>"
            )
        em = [t for t in c.tickets if t.decision.urgency == "emergency"]
        night = [t for t in em if t.at.hour >= 22 or t.at.hour < 7]
        body = (
            "<h1>Maintenance after the weekend</h1><p class='muted'>Every request sent since Friday 17:00, triaged from "
            "the tenant's own words. Anything that looks like an emergency was sent to the on-call coordinator a "
            "quarter of an hour after it arrived, day or night. The rest waited for this morning, most urgent first.</p>"
            f"<div class='grid'><div class='card'><b>{len(c.tickets)}</b><span class='muted'>requests since Friday 17:00"
            f"</span></div><div class='card'><b>{len(em)}</b><span class='muted'>sent to on-call, {len(night)} at night"
            f"</span></div><div class='card'><b>{sum(t.decision.urgency == 'urgent' for t in c.tickets)}</b>"
            "<span class='muted'>urgent, to dispatch this morning</span></div><div class='card'><b>"
            f"{sum(t.decision.urgency == 'routine' for t in c.tickets)}</b><span class='muted'>routine, to schedule"
            f"</span></div></div><h2>Board</h2><div class='board'>{''.join(cols)}</div>"
        )
        return _page("Maintenance", body)

    @app.get("/requests/{rid}", response_class=HTMLResponse)
    def request_page(rid: int) -> str:
        t = next((t for t in c.tickets if t.id == rid), None)
        if t is None:
            raise HTTPException(404, "no such request")
        return _page(f"Request {rid}", ticket_body(c, t))

    @app.get("/tenants", response_class=HTMLResponse)
    def tenants() -> str:
        rows = []
        for lease in sorted(c.ledger.leases.values(), key=lambda x: -c.ledger.balance(x.id)["rent_open"]):
            b = c.ledger.balance(lease.id)
            state = (
                "<span class='b bad'>rent owed</span>"
                if b["rent_open"]
                else "<span class='b warn'>fees owed</span>"
                if b["fees_open"]
                else "<span class='b ok'>paid up</span>"
            )
            rows.append(
                f"<tr><td><a href='/tenants/{lease.id}'>{e(lease.tenant)}</a><div class='muted'>{e(lease.unit)}</div>"
                f"</td><td class='num'>{money(lease.rent)}</td><td class='num'>{money(b['rent_open'])}</td>"
                f"<td class='num'>{money(b['fees_open'])}</td><td class='num'>{money(b['credit'])}</td><td>{state}</td></tr>"
            )
        body = (
            "<h1>Tenants</h1><p class='muted'>Balances on 16 November. Payments go to rent before fees, oldest "
            "first, so a tenant who has paid all their rent never shows rent owed because of an old late fee.</p>"
            "<table><tr><th>Tenant</th><th class='num'>Monthly rent</th><th class='num'>Rent owed</th>"
            "<th class='num'>Fees owed</th><th class='num'>Credit</th><th></th></tr>" + "".join(rows) + "</table>"
        )
        return _page("Tenants", body)

    @app.get("/tenants/{lease_id}", response_class=HTMLResponse)
    def tenant(lease_id: str) -> str:
        lease = c.ledger.leases.get(lease_id)
        if lease is None:
            raise HTTPException(404, "no such lease")
        events: list[tuple[dt.date, int, str]] = []
        for ch in c.ledger.charges:
            if ch.lease == lease_id:
                label = f"{'Rent' if ch.kind == 'rent' else 'Late fee'} {ch.period}" + (
                    f" ({ch.note})" if ch.note else ""
                )
                events.append(
                    (
                        ch.due,
                        0,
                        f"<tr><td>{ch.due:%d %b}</td><td>{e(label)}</td><td class='num'>{money(ch.amount)}"
                        f"</td><td></td><td class='num'>{money(ch.open)}</td></tr>",
                    )
                )
        for p in c.ledger.payments:
            if p.lease == lease_id:
                alloc = "; ".join(f"{k} {per}: {money(v)}".replace(" :", ":") for per, k, v in p.allocations)
                events.append(
                    (
                        p.on,
                        1,
                        f"<tr><td>{p.on:%d %b}</td><td>Payment<div class='muted'>{e(alloc)}</div></td>"
                        f"<td></td><td class='num'>{money(p.amount)}</td><td></td></tr>",
                    )
                )
        b = c.ledger.balance(lease_id)
        body = (
            f"<h1>{e(lease.tenant)}</h1><p class='muted'>{e(lease.unit)} · lease {lease.start:%d %b %Y} to "
            f"{lease.end:%d %b %Y} · rent {money(lease.rent)} due on day {lease.due_day} · {lease.grace_days} days' "
            f"grace, late fee {money(lease.late_flat)}</p><div class='grid'><div class='card'><b>{money(b['rent_open'])}"
            f"</b><span class='muted'>rent owed</span></div><div class='card'><b>{money(b['fees_open'])}</b><span "
            f"class='muted'>fees owed</span></div><div class='card'><b>{money(b['paid'])}</b><span class='muted'>paid "
            f"in total</span></div><div class='card'><b>{money(b['credit'])}</b><span class='muted'>credit</span></div>"
            "</div><h2>Ledger</h2><table><tr><th>Date</th><th>Item</th><th class='num'>Charged</th><th class='num'>Paid"
            "</th><th class='num'>Still open</th></tr>"
            + "".join(x[2] for x in sorted(events, key=lambda x: (x[0], x[1])))
            + "</table>"
        )
        return _page(lease.tenant, body)

    @app.get("/owners", response_class=HTMLResponse)
    def owners() -> str:
        rows = []
        for i, o in enumerate(OWNERS):
            s = c.ledger.statement(o, 2026, 10, maintenance=c.maintenance)
            n = sum(u.owner == o for u in c.units)
            rows.append(
                f"<tr><td><a href='/owners/{i}'>{e(o)}</a></td><td class='num'>{n}</td><td class='num'>"
                f"{money(s['collected'])}</td><td class='num'>{money(s['fee'])}</td><td class='num'>"
                f"{money(s['maintenance_total'])}</td><td class='num'>{money(s['payout'])}</td></tr>"
            )
        body = (
            "<h1>Owners</h1><p class='muted'>October 2026 statements: rent actually collected, less the 8% "
            "management fee on it and maintenance paid for the owner's units.</p><table><tr><th>Owner</th>"
            "<th class='num'>Units</th><th class='num'>Collected</th><th class='num'>Fee</th><th class='num'>"
            "Maintenance</th><th class='num'>Payout</th></tr>" + "".join(rows) + "</table>"
        )
        return _page("Owners", body)

    @app.get("/owners/{oid}", response_class=HTMLResponse)
    def owner(oid: int) -> str:
        if not 0 <= oid < len(OWNERS):
            raise HTTPException(404, "no such owner")
        s = c.ledger.statement(OWNERS[oid], 2026, 10, maintenance=c.maintenance)
        lines = "".join(
            f"<tr><td>{e(x['unit'])}</td><td>{e(x['tenant'])}</td><td>{e(x['on'])}</td><td class='num'>"
            f"{money(x['rent'])}</td></tr>"
            for x in s["lines"]
        )
        jobs = (
            "".join(
                f"<tr><td>{e(j['unit'])}</td><td>{e(j['what'])}</td><td class='num'>{money(j['cost'])}</td></tr>"
                for j in s["maintenance"]
            )
            or "<tr><td colspan='3' class='muted'>None this month</td></tr>"
        )
        body = (
            f"<h1>{e(OWNERS[oid])}: October 2026</h1><div class='grid'><div class='card'><b>{money(s['collected'])}"
            f"</b><span class='muted'>rent collected</span></div><div class='card'><b>{money(s['fee'])}</b><span "
            f"class='muted'>management fee ({s['fee_rate']:.0%})</span></div><div class='card'><b>"
            f"{money(s['maintenance_total'])}</b><span class='muted'>maintenance</span></div><div class='card'><b>"
            f"{money(s['payout'])}</b><span class='muted'>paid to the owner</span></div></div><h2>Rent collected</h2>"
            f"<table><tr><th>Unit</th><th>Tenant</th><th>Paid on</th><th class='num'>Rent</th></tr>{lines}</table>"
            f"<h2>Maintenance</h2><table><tr><th>Unit</th><th>Job</th><th class='num'>Cost</th></tr>{jobs}</table>"
        )
        return _page(OWNERS[oid], body)

    sample = "Sorry to bother you on a Sunday, but the plug socket in the kitchen went bang and smells of hot plastic."

    @app.get("/triage", response_class=HTMLResponse)
    def triage_form() -> str:
        return triage_page(c, sample, triage_text(c, sample, use_claude=False))

    @app.post("/triage", response_class=HTMLResponse)
    def triage_post(text: str = Form("")) -> str:
        if not text.strip():
            raise HTTPException(422, "describe the problem")
        return triage_page(c, text, triage_text(c, text))

    return app


def triage_text(c: Console, text: str, use_claude: bool = True) -> dict[str, Any]:
    local = c.triage.decide(text)
    out: dict[str, Any] = {
        "local": decision_json(local),
        "final": decision_json(local),
        "notes": [],
        "job": "",
        "source": "local",
    }
    if use_claude and c.reader is not None:
        reading: Reading = c.reader.read(text, local)
        out.update(final=decision_json(reading.decision), notes=reading.notes, job=reading.job, source=reading.source)
    return out


def _decision_html(d: dict[str, Any]) -> str:
    cls = {"emergency": "bad", "urgent": "warn", "routine": "info"}[d["urgency"]]
    why = "".join(f"<li>{e(w)}</li>" for w in d["why"]) or "<li class='muted'>no strong signal</li>"
    return (
        f"<p><span class='b {cls}'>{e(d['urgency'])}</span> <span class='b ok'>{e(d['trade'])}</span> "
        f"<span class='muted'>model's emergency probability {d['p_emergency']:.0%}</span></p><ul>{why}</ul>"
    )


def ticket_body(c: Console, t: Ticket) -> str:
    d = decision_json(t.decision)
    lease = c.lease_for(t.unit.id)
    flagged = (
        f"Sent to the on-call coordinator at {_when(t.alerted)}, a quarter of an hour after it arrived."
        if t.alerted
        else "Waited for the inbox: the coordinator reads it this morning."
    )
    truth = (
        ""
        if t.request.urgency == t.decision.urgency
        else (
            f"<p class='b warn'>Demo note: this message was written as {e(t.request.urgency)}; triage read it as "
            f"{e(t.decision.urgency)}.</p>"
        )
    )
    return (
        f"<h1>Request {t.id}: {e(t.unit.id)}</h1><p class='muted'>{e(t.unit.tenant)} · {e(t.unit.building)} · sent "
        f"{_when(t.at)} ({_ago(t.at)})</p><div class='card'><p class='msg'>“{e(t.request.text)}”</p></div>"
        f"<h2>Triage</h2>{_decision_html(d)}<p>{e(flagged)}</p>{truth}<h2>Tenant</h2><p><a href='/tenants/{lease.id}'>"
        f"{e(lease.tenant)}'s ledger</a></p>"
    )


def triage_page(c: Console, text: str, res: dict[str, Any]) -> str:
    notes = "".join(f"<li>{e(n)}</li>" for n in res["notes"])
    claude = (
        "Claude reads it too and may raise the urgency, never lower it."
        if c.reader is not None
        else "No API key set: local triage only."
    )
    body = (
        f"<h1>Triage a request</h1><p class='muted'>Paste what a tenant wrote. {e(claude)}</p><form method='post' "
        f"action='/triage'><textarea name='text'>{e(text)}</textarea><p><button>Triage</button></p></form>"
        f"<h2>Local triage</h2>{_decision_html(res['local'])}"
        + (
            f"<h2>After Claude's reading</h2>{_decision_html(res['final'])}<ul>{notes}</ul>"
            + (f"<p class='muted'>For the contractor: {e(res['job'])}</p>" if res["job"] else "")
            if res["source"] == "claude" or res["notes"]
            else ""
        )
    )
    return _page("Triage a request", body)


def demo_app() -> FastAPI:
    import os

    return create_app(demo_console(Reader() if os.environ.get("ANTHROPIC_API_KEY") else None))


__all__ = ["Console", "create_app", "demo_app", "demo_console"]
