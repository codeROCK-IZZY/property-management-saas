"""The rent ledger: what each tenant owes, what they paid, and what each owner is due.

Money is held in whole cents. The rules (ADR 2):

- **Rent is charged monthly** on the lease's due day. A first or last month that is only partly in the lease is
  prorated by the days actually let, out of the days in that month.
- **A late fee** is charged once per month, when that month's rent is still not fully paid by the end of the grace
  period. It is a flat fee or a percentage of the rent, capped.
- **Payments go to rent before fees, oldest first.** A tenant who pays every month's rent in full is never shown in
  rent arrears because of an old fee. Strictly oldest-first allocation (the other option, for comparison) lets one
  unpaid fee eat into each later month's rent, so every month looks late and draws a new fee: fee pyramiding.
  Anything left over is credit, applied to the next charges.
- **The owner statement** for a month lists rent collected (not rent charged), less the management fee on what was
  collected and less maintenance paid for the owner's units.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

ALLOCATIONS = ("rent first", "oldest first")


def cents(amount: float) -> int:
    return round(amount * 100)


def money(c: int) -> str:
    sign = "-" if c < 0 else ""
    return f"{sign}${abs(c) // 100:,}.{abs(c) % 100:02d}"


@dataclass(frozen=True)
class Lease:
    id: str
    tenant: str
    unit: str
    owner: str
    start: date
    end: date  # last day of the lease
    rent: int  # cents per month
    due_day: int = 1
    grace_days: int = 5
    late_flat: int = 5_000  # cents
    late_percent: float = 0.0  # of the month's rent, used instead of the flat fee when above zero
    late_cap: int = 10_000


@dataclass
class Charge:
    lease: str
    kind: str  # "rent" or "late fee"
    period: str  # "2026-11"
    due: date
    amount: int
    paid: int = 0
    note: str = ""

    @property
    def open(self) -> int:
        return self.amount - self.paid


@dataclass
class Payment:
    lease: str
    on: date
    amount: int
    allocations: list[tuple[str, str, int]] = field(default_factory=list)  # (period, kind, cents)


def month_days(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def months(start: date, end: date) -> list[tuple[int, int]]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def rent_for(lease: Lease, y: int, m: int) -> tuple[int, str]:
    """The rent for one month, prorated when the lease covers only part of it."""
    first = date(y, m, 1)
    last = date(y, m, month_days(y, m))
    a, b = max(first, lease.start), min(last, lease.end)
    if a > b:
        return 0, ""
    let = (b - a).days + 1
    total = month_days(y, m)
    if let == total:
        return lease.rent, ""
    return round(lease.rent * let / total), f"{let} of {total} days"


def due_date(lease: Lease, y: int, m: int) -> date:
    d = date(y, m, min(lease.due_day, month_days(y, m)))
    return max(d, lease.start)


class Ledger:
    def __init__(self, leases: Sequence[Lease], allocation: str = "rent first") -> None:
        if allocation not in ALLOCATIONS:
            raise ValueError(f"allocation must be one of {ALLOCATIONS}")
        self.allocation = allocation
        self.leases = {lease.id: lease for lease in leases}
        self.charges: list[Charge] = []
        self.payments: list[Payment] = []
        self.credit: dict[str, int] = {lease.id: 0 for lease in leases}
        self._charged: set[tuple[str, str, str]] = set()

    # -- charging -------------------------------------------------------------------------------------------------

    def charge_rent(self, through: date) -> None:
        """Charge every month's rent due on or before `through` that hasn't been charged yet."""
        for lease in self.leases.values():
            for y, m in months(lease.start, min(lease.end, through)):
                due = due_date(lease, y, m)
                key = (lease.id, "rent", f"{y}-{m:02d}")
                if due > through or key in self._charged:
                    continue
                amount, note = rent_for(lease, y, m)
                if amount:
                    self._add(Charge(lease.id, "rent", key[2], due, amount, note=note))

    def charge_late_fees(self, on: date) -> list[Charge]:
        """Charge a late fee for each month whose rent is still open after the grace period. Once per month."""
        new = []
        for c in [c for c in self.charges if c.kind == "rent" and c.open > 0]:
            lease = self.leases[c.lease]
            key = (c.lease, "late fee", c.period)
            if on <= c.due + timedelta(days=lease.grace_days) or key in self._charged:
                continue
            fee = lease.late_flat if lease.late_percent <= 0 else round(c.amount * lease.late_percent)
            fee = min(fee, lease.late_cap)
            charge = Charge(c.lease, "late fee", c.period, on, fee, note=f"rent for {c.period} open after grace")
            self._add(charge)
            new.append(charge)
        return new

    def _add(self, charge: Charge) -> None:
        self.charges.append(charge)
        self._charged.add((charge.lease, charge.kind, charge.period))
        if self.credit[charge.lease]:
            take = min(self.credit[charge.lease], charge.open)
            charge.paid += take
            self.credit[charge.lease] -= take

    # -- paying ---------------------------------------------------------------------------------------------------

    def pay(self, lease_id: str, on: date, amount: int) -> Payment:
        """Apply a payment: rent before fees, oldest first (or strictly oldest first); the rest is credit."""
        if amount <= 0:
            raise ValueError("a payment must be positive")
        p = Payment(lease_id, on, amount)
        left = amount
        mine = [c for c in self.charges if c.lease == lease_id and c.open > 0]
        if self.allocation == "rent first":
            mine.sort(key=lambda c: (c.kind != "rent", c.due, c.period))
        else:
            mine.sort(key=lambda c: (c.due, c.kind != "rent", c.period))
        for c in mine:
            if not left:
                break
            take = min(left, c.open)
            c.paid += take
            left -= take
            p.allocations.append((c.period, c.kind, take))
        self.credit[lease_id] += left
        if left:
            p.allocations.append(("", "credit", left))
        self.payments.append(p)
        return p

    # -- reading --------------------------------------------------------------------------------------------------

    def balance(self, lease_id: str) -> dict[str, int]:
        mine = [c for c in self.charges if c.lease == lease_id]
        return {
            "rent_open": sum(c.open for c in mine if c.kind == "rent"),
            "fees_open": sum(c.open for c in mine if c.kind == "late fee"),
            "credit": self.credit[lease_id],
            "charged": sum(c.amount for c in mine),
            "paid": sum(p.amount for p in self.payments if p.lease == lease_id),
        }

    def statement(
        self, owner: str, y: int, m: int, fee_rate: float = 0.08, maintenance: Sequence[tuple[str, str, int]] = ()
    ) -> dict[str, Any]:
        """An owner's month: rent collected by unit, the management fee on it, maintenance paid, and the payout.

        `maintenance` is (unit, description, cents) for jobs paid that month. Payments towards late fees are kept by
        the manager and are not the owner's; payments beyond what was owed (credit) count as rent collected.
        """
        period = f"{y}-{m:02d}"
        units = {lease.unit for lease in self.leases.values() if lease.owner == owner}
        lines: list[dict[str, Any]] = []
        for p in self.payments:
            lease = self.leases[p.lease]
            if lease.owner != owner or (p.on.year, p.on.month) != (y, m):
                continue
            rent = sum(c for _, kind, c in p.allocations if kind in ("rent", "credit"))
            if rent:
                lines.append({"unit": lease.unit, "tenant": lease.tenant, "on": p.on.isoformat(), "rent": rent})
        collected = sum(int(line["rent"]) for line in lines)
        fee = round(collected * fee_rate)
        jobs = [{"unit": u, "what": w, "cost": c} for u, w, c in maintenance if u in units]
        spent = sum(c for u, _, c in maintenance if u in units)
        return {
            "owner": owner,
            "period": period,
            "lines": lines,
            "collected": collected,
            "fee_rate": fee_rate,
            "fee": fee,
            "maintenance": jobs,
            "maintenance_total": spent,
            "payout": collected - fee - spent,
        }
