"""The evaluation: does triage get emergencies to someone faster, without waking people for nothing?

Three sets of wording, kept apart:

- **tuning**: the first four phrasings of each kind of problem. The model is trained on these, and its settings are
  chosen by cross-validation that holds whole phrasings out.
- **validation**: the other phrasings written at the same time. They were looked at while the hazard lexicon was
  being written (ADR 1), so they are reported but they are not a clean test.
- **fresh**: phrasings in `fresh.py`, written after the classifier and this file were committed (the freeze commit
  is named in the README). This is the test.

Each set is measured twice: as messages (does the classifier get urgency and trade right?) and as simulated months
of a portfolio (how long do emergencies wait?). The gate's limits were written before the fresh phrasings existed.
"""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from . import ledger_sim
from .corpus import TEMPLATES, TRADES, Request, generate, split
from .dispatch import arrivals, simulate, summary
from .triage import Decision, hazards, out_of_fold, pick_threshold, rules, train

L2_GRID = (0.001, 0.01, 0.03, 0.1, 0.3)
FALSE_ALARM_BUDGET = 0.15  # share of non-emergencies the on-call coordinator may be asked to call back
TRAIN_SEED, TRAIN_N = 1, 1500
PORTFOLIOS = {"validation": (101, 102, 103, 104, 105, 106), "fresh": (201, 202, 203, 204, 205, 206, 207, 208)}
MESSAGES_SEED = {"validation": 501, "fresh": 601}
LEDGER_SEEDS = (1, 2, 3, 4, 5)

GATE = {
    "fresh_emergency_recall_min": 0.85,  # of fresh emergency messages flagged
    "fresh_within_4h_min": 0.90,  # of emergencies in fresh portfolios attended within 4 hours
    "fresh_within_4h_over_keywords_min": 0.15,  # percentage points over keyword rules
    "fresh_false_alarm_rate_max": 0.20,  # of fresh non-emergency messages flagged
    "fresh_night_false_alarms_per_week_max": 3.0,  # per portfolio
    "fresh_trade_accuracy_min": 0.70,
}


def fresh_templates() -> dict[tuple[str, str], list[str]] | None:
    try:
        mod = importlib.import_module("propman.fresh")
    except ModuleNotFoundError:
        return None
    out: dict[tuple[str, str], list[str]] = mod.FRESH
    return out


def tune(requests: Sequence[Request]) -> tuple[float, list[dict[str, float]]]:
    """Choose the word regularisation by phrasing-held-out urgency and trade accuracy."""
    rows = []
    for l2 in L2_GRID:
        oof = out_of_fold(requests, l2)
        th = pick_threshold(oof, FALSE_ALARM_BUDGET)
        urg = []
        for r, pu, _ in oof:
            u = (
                "emergency"
                if tri_flags(r.text, pu["emergency"], th)
                else max(("urgent", "routine"), key=lambda c: pu[c])
            )
            urg.append(u == r.urgency)
        em = [tri_flags(r.text, pu["emergency"], th) for r, pu, _ in oof if r.urgency == "emergency"]
        trade = [max(TRADES, key=lambda c: pt[c]) == r.trade for r, _, pt in oof]
        rows.append(
            {
                "l2_words": l2,
                "threshold": th,
                "emergency_recall": float(np.mean(em)),
                "urgency_accuracy": float(np.mean(urg)),
                "trade_accuracy": float(np.mean(trade)),
            }
        )
    best = max(rows, key=lambda r: (r["urgency_accuracy"] + r["trade_accuracy"], -r["l2_words"]))
    return best["l2_words"], rows


def tri_flags(text: str, p_emergency: float, threshold: float) -> bool:
    return bool(hazards(text)) or p_emergency >= threshold


def classify(decide: Callable[[str], Decision], bank: Sequence[Request]) -> dict[str, float]:
    d = [decide(r.text) for r in bank]
    em = [x.urgency == "emergency" for x, r in zip(d, bank, strict=True) if r.urgency == "emergency"]
    calm = [x.urgency == "emergency" for x, r in zip(d, bank, strict=True) if r.urgency != "emergency"]
    return {
        "messages": len(bank),
        "emergency_recall": float(np.mean(em)),
        "false_alarm_rate": float(np.mean(calm)),
        "urgency_accuracy": float(np.mean([x.urgency == r.urgency for x, r in zip(d, bank, strict=True)])),
        "trade_accuracy": float(np.mean([x.trade == r.trade for x, r in zip(d, bank, strict=True)])),
    }


def portfolios(
    templates: dict[tuple[str, str], list[str]],
    seeds: Sequence[int],
    policies: dict[str, Callable[[str], Decision] | None],
) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, list[float]]] = {}
    for seed in seeds:
        jobs = arrivals(generate(800, seed, templates), seed)
        for name, dec in policies.items():
            s = summary(simulate(jobs, name, dec, seed))
            for k, v in s.items():
                totals.setdefault(name, {}).setdefault(k, []).append(float(v))
    counts = ("requests", "emergencies", "emergencies_within_4h", "urgent", "urgent_within_24h")
    out: dict[str, dict[str, float]] = {}
    for name, d in totals.items():
        row = {k: (float(sum(v)) if k in counts else float(np.mean(v))) for k, v in d.items()}
        row["within_4h_share"] = row["emergencies_within_4h"] / max(1.0, row["emergencies"])
        row["urgent_24h_share"] = row["urgent_within_24h"] / max(1.0, row["urgent"])
        out[name] = row
    return out


def run(gate: bool = False) -> dict[str, Any]:
    t0 = time.time()
    tuning = split(TEMPLATES, "tuning")
    dev = generate(TRAIN_N, TRAIN_SEED, tuning)
    l2, grid = tune(dev)
    model = train(dev, l2_words=l2, false_alarm_budget=FALSE_ALARM_BUDGET)
    words_only = train(dev, l2_words=l2, false_alarm_budget=FALSE_ALARM_BUDGET, lexicon=False)
    deciders: dict[str, Callable[[str], Decision]] = {
        "keywords": rules,
        "words only": words_only.decide,
        "triage": model.decide,
    }
    banks = {"validation": split(TEMPLATES, "heldout")}
    fresh = fresh_templates()
    if fresh is not None:
        banks["fresh"] = fresh
    result: dict[str, Any] = {
        "tuning": {
            "grid": grid,
            "l2_words": l2,
            "threshold": model.emergency_threshold,
            "false_alarm_budget": FALSE_ALARM_BUDGET,
            "messages": len(dev),
        },
        "classify": {},
        "portfolios": {},
        "examples": {},
    }
    for name, templates in banks.items():
        msgs = generate(1500, MESSAGES_SEED[name], templates)
        result["classify"][name] = {k: classify(f, msgs) for k, f in deciders.items()}
        result["portfolios"][name] = portfolios(
            templates, PORTFOLIOS[name], {"inbox": None, "keywords": rules, "triage": model.decide}
        )
        missed = [r.text for r in msgs if r.urgency == "emergency" and model.decide(r.text).urgency != "emergency"]
        result["examples"][name] = {
            "missed_emergencies": sorted(set(missed))[:8],
            "kinds": len(templates),
            "phrasings": sum(len(v) for v in templates.values()),
        }
    result["ledger"] = ledger_year(LEDGER_SEEDS)
    result["seconds"] = round(time.time() - t0, 1)
    if gate:
        result["gate"] = check_gate(result)
    return result


def ledger_year(seeds: Sequence[int]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for seed in seeds:
        for allocation, row in ledger_sim.run(seed).items():
            acc = out.setdefault(allocation, {})
            for k, v in row.items():
                acc[k] = acc.get(k, 0) + v
    return out


def check_gate(result: dict[str, Any]) -> dict[str, Any]:
    fails = []
    led = result["ledger"]["rent first"]
    if led["fees_while_all_rent_paid"] or led["paid_all_rent_but_shown_owing_rent"]:
        fails.append("the ledger charged a fee while all rent was paid, or showed a fully paid tenant owing rent")
    if "fresh" not in result["classify"]:
        return {"passed": False, "failures": [*fails, "no fresh phrasings"], "limits": GATE}
    c = result["classify"]["fresh"]["triage"]
    p = result["portfolios"]["fresh"]
    if c["emergency_recall"] < GATE["fresh_emergency_recall_min"]:
        fails.append(f"fresh emergency recall {c['emergency_recall']:.3f} < {GATE['fresh_emergency_recall_min']}")
    if c["trade_accuracy"] < GATE["fresh_trade_accuracy_min"]:
        fails.append(f"fresh trade accuracy {c['trade_accuracy']:.3f} < {GATE['fresh_trade_accuracy_min']}")
    share = p["triage"]["within_4h_share"]
    if share < GATE["fresh_within_4h_min"]:
        fails.append(f"fresh emergencies within 4 h {share:.3f} < {GATE['fresh_within_4h_min']}")
    gain = share - p["keywords"]["within_4h_share"]
    if gain < GATE["fresh_within_4h_over_keywords_min"]:
        fails.append(f"gain over keywords {gain:.3f} < {GATE['fresh_within_4h_over_keywords_min']}")
    if c["false_alarm_rate"] > GATE["fresh_false_alarm_rate_max"]:
        fails.append(f"fresh false alarm rate {c['false_alarm_rate']:.3f} > {GATE['fresh_false_alarm_rate_max']}")
    night = p["triage"]["night_false_alarms_per_week"]
    if night > GATE["fresh_night_false_alarms_per_week_max"]:
        fails.append(f"night false alarms per week {night:.2f} > {GATE['fresh_night_false_alarms_per_week_max']}")
    return {"passed": not fails, "failures": fails, "limits": GATE}
