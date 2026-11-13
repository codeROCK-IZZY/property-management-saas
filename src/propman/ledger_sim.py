"""A year of rent in a synthetic portfolio, to compare how payments are allocated.

Tenants pay the way real tenants do: most on time, some late once, some often late, a few short. Every payment is
that month's rent (or part of it); nobody pays a late fee separately, which is common. The same payments are run
through a ledger that applies payments to rent before fees and one that applies them strictly oldest first.

Measured: late fees charged; fees charged while the tenant had paid every cent of rent charged so far (fee
pyramiding: the only thing unpaid was an earlier fee); fees for a month whose own rent was paid in full and on time;
and tenants who paid all the rent charged but whom the ledger shows owing rent at year end (in many places, grounds
to start eviction).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from .ledger import ALLOCATIONS, Lease, Ledger, rent_for

HABITS = {"on time": 0.6, "late once": 0.15, "often late": 0.15, "short": 0.1}


@dataclass(frozen=True)
class Pay:
    lease: str
    period: str
    on: date
    amount: int
    on_time_in_full: bool


def tenants(seed: int, n: int = 200, year: int = 2026) -> list[tuple[Lease, str]]:
    g = np.random.default_rng(seed)
    names = list(HABITS)
    p = np.array(list(HABITS.values()))
    out = []
    for i in range(n):
        rent = int(g.integers(9, 30)) * 10_000
        habit = names[int(g.choice(len(names), p=p / p.sum()))]
        start = date(year, 1, 1) + timedelta(days=int(g.integers(0, 28)))
        lease = Lease(
            f"L{i:03d}",
            f"Tenant {i:03d}",
            f"U{i:03d}",
            f"Owner {i % 12:02d}",
            start,
            date(year + 1, 12, 31),
            rent,
            due_day=1 if g.random() < 0.8 else 15,
        )
        out.append((lease, habit))
    return out


def payments(seed: int, people: list[tuple[Lease, str]], year: int = 2026) -> list[Pay]:
    """Every payment in the year. Each follows that month's rent, whatever the ledger says is owed."""
    g = np.random.default_rng(seed + 1)
    out = []
    for lease, habit in people:
        late_month = int(g.integers(1, 12))
        for m in range(1, 13):
            amount, _ = rent_for(lease, year, m)
            if not amount:
                continue
            due = max(date(year, m, lease.due_day), lease.start)
            delay = 0
            full = amount
            if (habit == "late once" and m == late_month) or (habit == "often late" and g.random() < 0.3):
                delay = int(g.integers(8, 20))
            elif habit == "short" and g.random() < 0.4:
                amount = int(amount * float(g.uniform(0.7, 0.95)))
            on = min(due + timedelta(days=delay), date(year, 12, 31))
            out.append(
                Pay(
                    lease.id,
                    f"{year}-{m:02d}",
                    on,
                    amount,
                    amount >= full and on <= due + timedelta(days=lease.grace_days),
                )
            )
    out.sort(key=lambda p: (p.on, p.lease))
    return out


def run(seed: int, year: int = 2026) -> dict[str, dict[str, Any]]:
    people = tenants(seed, year=year)
    pays = payments(seed, people, year)
    good_months = {(p.lease, p.period) for p in pays if p.on_time_in_full}
    by_day: dict[date, list[Pay]] = {}
    for p in pays:
        by_day.setdefault(p.on, []).append(p)
    result = {}
    for allocation in ALLOCATIONS:
        led = Ledger([lease for lease, _ in people], allocation)
        d = date(year, 1, 1)
        pyramided = 0
        while d <= date(year, 12, 31):
            led.charge_rent(d)
            for p in by_day.get(d, []):
                led.pay(p.lease, d, p.amount)
            for fee in led.charge_late_fees(d):
                paid = sum(p.amount for p in led.payments if p.lease == fee.lease)
                rent = sum(c.amount for c in led.charges if c.lease == fee.lease and c.kind == "rent")
                pyramided += paid >= rent
            d += timedelta(days=1)
        fees = [c for c in led.charges if c.kind == "late fee"]
        paid_all = shown_owing = 0
        for lease, _ in people:
            b = led.balance(lease.id)
            rent_charged = sum(c.amount for c in led.charges if c.lease == lease.id and c.kind == "rent")
            if b["paid"] >= rent_charged:
                paid_all += 1
                shown_owing += b["rent_open"] > 0
        result[allocation] = {
            "tenants": len(people),
            "late_fees": len(fees),
            "fees_total": sum(c.amount for c in fees),
            "fees_while_all_rent_paid": pyramided,
            "fees_for_months_paid_on_time": sum((c.lease, c.period) in good_months for c in fees),
            "tenants_with_fees": len({c.lease for c in fees}),
            "paid_all_rent": paid_all,
            "paid_all_rent_but_shown_owing_rent": shown_owing,
        }
    return result
