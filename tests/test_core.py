"""Triage, the dispatch simulation and the rent ledger."""

from __future__ import annotations

from datetime import date

import pytest

from propman.corpus import TEMPLATES, TUNING_PHRASINGS, generate, split
from propman.dispatch import Job, next_check, simulate, summary
from propman.fresh import FRESH
from propman.ledger import Lease, Ledger, money, rent_for
from propman.ledger_sim import run as ledger_year
from propman.triage import Decision, concepts, fit, hazards, pick_threshold, rules, tokens


@pytest.fixture(scope="module")
def tri():  # type: ignore[no-untyped-def]
    return fit(generate(900, 1, split(TEMPLATES, "tuning")))


def test_corpus_is_deterministic_and_splits_by_phrasing() -> None:
    a = generate(50, 3)
    assert a == generate(50, 3) and a != generate(50, 4)
    tuning, held = split(TEMPLATES, "tuning"), split(TEMPLATES, "heldout")
    for k, v in TEMPLATES.items():
        assert tuning[k] == v[:TUNING_PHRASINGS] and held[k] == v[TUNING_PHRASINGS:] and held[k]
        assert not set(tuning[k]) & set(held[k])
    assert set(FRESH) == set(TEMPLATES)
    assert not {p for v in FRESH.values() for p in v} & {p for v in TEMPLATES.values() for p in v}


def test_tone_does_not_set_the_label() -> None:
    reqs = generate(600, 5)
    loud_routine = [r for r in reqs if r.urgency == "routine" and ("URGENT" in r.text or "urgent!!" in r.text)]
    calm_emergency = [r for r in reqs if r.urgency == "emergency" and ("bother" in r.text or "No rush" in r.text)]
    assert loud_routine and calm_emergency


def test_hazard_lexicon_reads_different_words_for_the_same_danger() -> None:
    assert hazards("the fuse box is smoking") == ["heat or fire"]
    assert hazards("a socket is scorched black") == ["heat or fire"]
    assert hazards("there's a smell like rotten eggs") == ["gas or fumes"]
    assert hazards("I'm locked out") == ["home not secure"]
    assert hazards("I’m locked out") == ["home not secure"]
    assert hazards("the bathroom tap drips") == []
    assert hazards("the smoke alarm battery chirps") == []  # equipment is not a hazard
    assert "@electrical parts" in concepts("the smoke alarm battery chirps")
    assert "a_b" in tokens("A b") and "@heat or fire" not in tokens("burning", lexicon=False)


def test_triage_explains_and_flags_hazards(tri) -> None:  # type: ignore[no-untyped-def]
    d = tri.decide("Sorry to bother you, but the fuse box is smoking")
    assert d.urgency == "emergency" and "heat or fire" in d.hazards and d.why[0] == "hazard: heat or fire"
    calm = tri.decide("URGENT!! the bedroom door squeaks")
    assert calm.urgency != "emergency" and calm.trade == "general"
    assert tri.decide("the fridge isn't cooling and the food is going off").trade == "appliance"


def test_keyword_rules_follow_tone_not_problem() -> None:
    assert rules("URGENT!! the bedroom door squeaks").urgency == "emergency"
    assert rules("water is pouring through the ceiling").urgency != "emergency"
    assert rules("the boiler is noisy").trade == "heating"


def test_threshold_respects_the_false_alarm_budget() -> None:
    r = generate(40, 9)
    oof = [(x, {"emergency": 0.3 if x.urgency != "emergency" else 0.9}, {}) for x in r]
    calm = [x for x in r if x.urgency != "emergency"]
    screened = sum(bool(hazards(x.text)) for x in calm) / len(calm)
    th = pick_threshold(oof, 1.0)
    assert th <= 0.3
    assert pick_threshold(oof, max(0.0, screened)) > 0.3


def test_inbox_checks_skip_nights_and_weekends() -> None:
    assert next_check(8.0) == 9.0
    assert next_check(13.5) == 16.0
    assert next_check(16.5) == 24 + 9.0
    assert next_check(4 * 24 + 17) == 7 * 24 + 9.0  # Friday evening waits for Monday


def test_flagged_emergency_goes_to_on_call_and_false_alarms_count() -> None:
    reqs = generate(200, 2)
    em = next(r for r in reqs if r.urgency == "emergency")
    calm = next(r for r in reqs if r.urgency == "routine")
    fri_night = 4 * 24 + 23.0
    jobs = [Job(0, em, fri_night), Job(1, calm, fri_night + 0.1)]

    def flag_all(_: str) -> Decision:
        return Decision("emergency", "general", 1.0)

    inbox = simulate(jobs, "inbox", None, seed=1)
    flagged = simulate(jobs, "triage", flag_all, seed=1)
    wait_inbox = (inbox.jobs[0].attended or 0) - fri_night
    wait_flag = (flagged.jobs[0].attended or 0) - fri_night
    assert wait_flag <= 0.25 + 3.0 + 1e-9
    assert flagged.jobs[0].route == "on-call"
    assert wait_inbox > wait_flag or inbox.jobs[0].route == "on-call"  # unless the tenant phoned
    assert flagged.false_alarms == 1 and flagged.night_false_alarms == 1 and inbox.false_alarms == 0
    s = summary(flagged)
    assert s["emergencies"] == 1 and s["emergencies_within_4h"] == 1


def test_prorated_first_and_last_month() -> None:
    lease = Lease("L", "T", "U", "O", date(2026, 9, 15), date(2027, 3, 10), 150_000)
    assert rent_for(lease, 2026, 9) == (80_000, "16 of 30 days")
    assert rent_for(lease, 2026, 10) == (150_000, "")
    assert rent_for(lease, 2027, 3) == (round(150_000 * 10 / 31), "10 of 31 days")
    assert rent_for(lease, 2027, 4) == (0, "")
    assert money(-123_456) == "-$1,234.56"


def test_late_fee_once_after_grace_and_payments_go_to_rent_first() -> None:
    lease = Lease("L", "T", "U", "O", date(2026, 1, 1), date(2026, 12, 31), 100_000, grace_days=5, late_flat=5_000)
    led = Ledger([lease])
    led.charge_rent(date(2026, 1, 1))
    assert led.charge_late_fees(date(2026, 1, 6)) == []  # still in grace
    assert len(led.charge_late_fees(date(2026, 1, 7))) == 1
    assert led.charge_late_fees(date(2026, 1, 8)) == []  # once per month
    led.pay("L", date(2026, 1, 8), 100_000)
    led.charge_rent(date(2026, 2, 1))
    p = led.pay("L", date(2026, 2, 1), 100_000)
    assert p.allocations == [("2026-02", "rent", 100_000)]
    assert led.charge_late_fees(date(2026, 2, 20)) == []
    b = led.balance("L")
    assert b["rent_open"] == 0 and b["fees_open"] == 5_000


def test_oldest_first_allocation_pyramids_fees() -> None:
    lease = Lease("L", "T", "U", "O", date(2026, 1, 1), date(2026, 12, 31), 100_000)
    led = Ledger([lease], "oldest first")
    led.charge_rent(date(2026, 1, 1))
    led.charge_late_fees(date(2026, 1, 7))
    led.pay("L", date(2026, 1, 8), 100_000)
    led.charge_rent(date(2026, 2, 1))
    led.pay("L", date(2026, 2, 1), 100_000)
    assert led.balance("L")["rent_open"] == 5_000  # the old fee ate into February's rent
    assert len(led.charge_late_fees(date(2026, 2, 7))) == 1
    with pytest.raises(ValueError, match="allocation"):
        Ledger([lease], "newest first")


def test_overpayment_becomes_credit_and_is_used_next() -> None:
    lease = Lease("L", "T", "U", "O", date(2026, 1, 1), date(2026, 12, 31), 100_000)
    led = Ledger([lease])
    led.charge_rent(date(2026, 1, 1))
    led.pay("L", date(2026, 1, 1), 150_000)
    assert led.balance("L")["credit"] == 50_000
    led.charge_rent(date(2026, 2, 1))
    assert led.balance("L") | {} == {
        "rent_open": 50_000,
        "fees_open": 0,
        "credit": 0,
        "charged": 200_000,
        "paid": 150_000,
    }
    with pytest.raises(ValueError, match="positive"):
        led.pay("L", date(2026, 2, 2), 0)


def test_owner_statement_counts_collected_rent_less_fee_and_maintenance() -> None:
    a = Lease("A", "Ann", "U1", "Owner", date(2026, 1, 1), date(2026, 12, 31), 100_000)
    b = Lease("B", "Bo", "U2", "Other", date(2026, 1, 1), date(2026, 12, 31), 90_000)
    led = Ledger([a, b])
    led.charge_rent(date(2026, 10, 1))
    led.charge_late_fees(date(2026, 10, 1))
    led.pay("A", date(2026, 10, 3), 100_000)
    led.pay("B", date(2026, 10, 3), 90_000)
    s = led.statement("Owner", 2026, 10, 0.1, [("U1", "tap", 5_000), ("U2", "lock", 7_000)])
    assert s["collected"] == 100_000 and s["fee"] == 10_000 and s["maintenance_total"] == 5_000
    assert s["payout"] == 85_000 and [x["unit"] for x in s["lines"]] == ["U1"]


def test_ledger_year_rent_first_never_pyramids() -> None:
    r = ledger_year(3)
    assert r["rent first"]["fees_while_all_rent_paid"] == 0
    assert r["rent first"]["paid_all_rent_but_shown_owing_rent"] == 0
    assert r["oldest first"]["fees_while_all_rent_paid"] > 0
