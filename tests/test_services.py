"""Claude's second reading (real SDK, canned responses), the console and the CLI."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from propman.app import Console, create_app, demo_console
from propman.cli import main
from propman.reader import FALLBACK_BETA, MODEL, Reader
from propman.triage import Decision

MSG = "Sorry to bother you, the kitchen ceiling is bulging and water is coming through the light"


def message(*content: dict[str, Any], stop: str = "tool_use") -> dict[str, Any]:
    return {
        "id": "m",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": list(content),
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


class Script:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses: Iterator[dict[str, Any]] = iter(responses)
        self.requests: list[dict[str, Any]] = []
        self.headers: list[httpx2.Headers] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        self.headers.append(request.headers)
        return httpx2.Response(200, json=next(self.responses))


def reader(script: Script) -> Reader:
    client = anthropic.Anthropic(
        api_key="test",
        base_url="http://api.test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(script)),
    )
    return Reader(client)


def call(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "urgency": "emergency",
        "trade": "plumbing",
        "job": "Leak through kitchen ceiling light",
        "quote": "water is coming through the light",
    }
    base.update(fields)
    return {"type": "tool_use", "id": "t", "name": "triage_request", "input": base}


LOCAL = Decision("urgent", "electrical", 0.08, [], ["light"])


def test_request_shape_and_claude_raises_urgency_with_a_quote() -> None:
    script = Script([message(call())])
    r = reader(script).read(MSG, LOCAL)
    assert r.source == "claude" and r.decision.urgency == "emergency" and r.decision.trade == "electrical"
    assert "raised from urgent to emergency" in r.notes and "Claude suggests plumbing rather than electrical" in r.notes
    assert r.decision.why[0].startswith("Claude:") and r.job.startswith("Leak")
    assert LOCAL.urgency == "urgent"  # the local decision is not mutated
    req = script.requests[0]
    assert req["model"] == MODEL and req["output_config"] == {"effort": "low"} and req["fallbacks"] == "default"
    assert "thinking" not in req and "tool_choice" not in req and req["tools"][0]["strict"] is True
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"} and "<request>" in req["messages"][0]["content"]
    assert FALLBACK_BETA in script.headers[0]["anthropic-beta"]


def test_claude_never_lowers_urgency() -> None:
    local = Decision("emergency", "heating", 0.9, ["gas or fumes"], ["hazard: gas or fumes"])
    r = reader(Script([message(call(urgency="routine", quote="smell of gas"))])).read("there's a smell of gas", local)
    assert r.decision.urgency == "emergency" and any("never lowered" in n for n in r.notes)


def test_unquoted_or_unknown_answers_are_ignored() -> None:
    r = reader(Script([message(call(quote="the house is on fire"))])).read(MSG, LOCAL)
    assert r.decision.urgency == "urgent" and r.source == "local" and "quote is not in the message" in r.notes[0]
    r = reader(Script([message(call(trade="roofing"))])).read(MSG, LOCAL)
    assert r.decision.urgency == "urgent" and "not a known" in r.notes[0]


def test_refusal_keeps_local_triage() -> None:
    r = reader(Script([message({"type": "text", "text": "no"}, stop="refusal")])).read(MSG, LOCAL)
    assert r.decision is LOCAL and "Claude gave no answer" in r.notes[0]


@pytest.fixture(scope="module")
def console() -> Console:
    return demo_console()


@pytest.fixture(scope="module")
def client(console: Console) -> TestClient:
    return TestClient(create_app(console))


def test_console_pages(client: TestClient, console: Console) -> None:
    assert client.get("/healthz").json()["requests"] == len(console.tickets)
    home = client.get("/").text
    assert "Call back now" in home and "Urgent: dispatch today" in home and "Routine: schedule" in home
    t = console.tickets[0]
    page = client.get(f"/requests/{t.id}").text
    assert t.unit.id in page and "Triage" in page
    assert client.get("/requests/999").status_code == 404
    assert "Rent owed" in client.get("/tenants").text
    lease = next(iter(console.ledger.leases))
    assert "Ledger" in client.get(f"/tenants/{lease}").text
    assert client.get("/tenants/nope").status_code == 404
    assert "October 2026" in client.get("/owners").text and "Payout" in client.get("/owners").text
    assert "rent collected" in client.get("/owners/0").text and client.get("/owners/9").status_code == 404
    assert "Local triage" in client.get("/triage").text


def test_console_api_and_form(client: TestClient) -> None:
    r = client.post("/api/triage", json={"text": "I can smell gas in the hallway"}).json()
    assert r["final"]["urgency"] == "emergency" and "gas or fumes" in r["final"]["hazards"] and r["source"] == "local"
    assert client.post("/api/triage", json={"text": " "}).status_code == 422
    assert client.post("/triage", data={"text": ""}).status_code == 422
    assert "emergency" in client.post("/triage", data={"text": "sparks from the socket"}).text
    reqs = client.get("/api/requests").json()
    assert reqs and {"urgency", "trade", "why", "unit"} <= set(reqs[0])
    tenants = client.get("/api/tenants").json()
    assert tenants and {"rent_open", "fees_open", "credit"} <= set(tenants[0])


def test_cli_triage_and_board(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["triage", "the boiler smells of gas"]) == 0
    assert json.loads(capsys.readouterr().out)["final"]["urgency"] == "emergency"
    assert main(["board"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("emergency")
