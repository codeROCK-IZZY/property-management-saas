"""What happens to maintenance requests after they are sent: a simulated month of a property manager's portfolio.

Requests arrive at any hour from the tenant portal. The office coordinator checks the maintenance inbox three times
each working day (9:00, 13:00 and 16:00, Monday to Friday) and reads everything waiting, so on reading a request
they know its real urgency and dispatch a contractor. Some tenants with an emergency also phone the out-of-hours
line themselves, whatever the policy.

A policy decides which requests go straight to the on-call coordinator, who calls the tenant back within a quarter of
an hour, day or night. On that call they learn the truth: a real emergency is dispatched at once, anything else waits
for the inbox. A flagged request that was not an emergency is a false alarm: a phone call, and at night a person
woken for nothing.

- `inbox`: no flags, the inbox is read in arrival order.
- `keywords`: requests with an emergency keyword are flagged.
- `triage`: the hazard screen and the model flag; the inbox is read most urgent first.

Contractors attend an emergency 1 to 3 hours after dispatch. Measured: how long emergencies wait to be dispatched and
attended, what share are attended within 4 hours of the tenant writing in (a common service level), how many urgent
requests are dispatched within a day, and the false alarms.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from .corpus import Request
from .triage import Decision

CHECKS = (9.0, 13.0, 16.0)
CALL_BACK_H = 0.25
PHONE_RATE = 0.4  # emergencies whose tenant also phones the out-of-hours line
NIGHT = (22.0, 7.0)
READ_MIN = 3.0  # minutes to read and dispatch one request from the inbox


@dataclass
class Job:
    id: int
    request: Request
    at: float  # hours since Monday 00:00 of week 1
    decision: Decision | None = None
    flagged: bool = False
    phoned: float | None = None
    dispatched: float | None = None
    attended: float | None = None
    route: str = ""


@dataclass
class Month:
    jobs: list[Job] = field(default_factory=list)
    false_alarms: int = 0
    night_false_alarms: int = 0
    days: int = 28


def is_night(t: float) -> bool:
    h = t % 24
    return h >= NIGHT[0] or h < NIGHT[1]


def next_check(t: float) -> float:
    """The first inbox check at or after `t`."""
    day = int(t // 24)
    while True:
        if day % 7 < 5:
            for h in CHECKS:
                if day * 24 + h >= t:
                    return day * 24 + h
        day += 1


def arrivals(requests: Sequence[Request], seed: int, days: int = 28, per_day: float = 14.0) -> list[Job]:
    """Spread `requests` (in order) over `days` with a daily rhythm: fewer at night, more in the evening."""
    g = np.random.default_rng(seed)
    rhythm = np.array([0.3] * 7 + [1.0] * 10 + [1.6] * 5 + [0.8] * 2)
    rhythm = rhythm / rhythm.sum()
    n = min(len(requests), int(g.poisson(per_day * days)))
    out = []
    for i in range(n):
        day = int(g.integers(days))
        hour = float(g.choice(24, p=rhythm)) + float(g.random())
        out.append(Job(i, requests[i], day * 24 + hour))
    out.sort(key=lambda j: (j.at, j.id))
    for i, j in enumerate(out):
        j.id = i
    return out


URGENCY_ORDER = {"emergency": 0, "urgent": 1, "routine": 2}


def simulate(
    jobs: Sequence[Job], policy: str, decide: Callable[[str], Decision] | None, seed: int, days: int = 28
) -> Month:
    """Run one month. `decide` is the policy's classifier (none for `inbox`)."""
    g = np.random.default_rng(seed)
    month = Month([Job(j.id, j.request, j.at) for j in jobs], days=days)
    for j in month.jobs:
        if decide is not None:
            j.decision = decide(j.request.text)
            j.flagged = j.decision.urgency == "emergency"
        if j.request.urgency == "emergency" and g.random() < PHONE_RATE:
            j.phoned = j.at + float(g.uniform(0.1, 0.75))
        attend = float(g.uniform(1.0, 3.0))
        # on-call: a flag or the tenant's own call, whichever comes first
        times = [t for t in ((j.at + CALL_BACK_H) if j.flagged else None, j.phoned) if t is not None]
        if times:
            t = min(times)
            if j.request.urgency == "emergency":
                j.dispatched, j.route = t, "on-call"
            elif j.flagged:
                month.false_alarms += 1
                month.night_false_alarms += is_night(j.at)
        if j.dispatched is None:
            j.dispatched, j.route = next_check(j.at), "inbox"
        j.attended = j.dispatched + (attend if j.request.urgency == "emergency" else 0.0)
    # Within one inbox check, the order of reading decides who is dispatched first (a minute or two each).
    by_check: dict[float, list[Job]] = {}
    for j in month.jobs:
        if j.route == "inbox":
            by_check.setdefault(j.dispatched or 0.0, []).append(j)

    def order(j: Job) -> tuple[int, float]:
        if policy == "triage" and j.decision is not None:
            return URGENCY_ORDER[j.decision.urgency], j.at
        return 0, j.at

    for t, group in by_check.items():
        for i, j in enumerate(sorted(group, key=order)):
            shift = i * READ_MIN / 60
            j.dispatched = t + shift
            if j.attended is not None:
                j.attended += shift
    return month


def summary(month: Month) -> dict[str, float]:
    em = [j for j in month.jobs if j.request.urgency == "emergency"]
    ur = [j for j in month.jobs if j.request.urgency == "urgent"]
    wait = np.array([(j.attended or 0) - j.at for j in em]) if em else np.zeros(1)
    weeks = month.days / 7
    return {
        "requests": len(month.jobs),
        "emergencies": len(em),
        "emergencies_within_4h": sum(w <= 4.0 for w in wait),
        "emergency_median_h": float(np.median(wait)),
        "emergency_p90_h": float(np.quantile(wait, 0.9)),
        "emergency_worst_h": float(wait.max()),
        "urgent": len(ur),
        "urgent_within_24h": sum((j.dispatched or 0) - j.at <= 24.0 for j in ur),
        "false_alarms_per_week": month.false_alarms / weeks,
        "night_false_alarms_per_week": month.night_false_alarms / weeks,
    }
