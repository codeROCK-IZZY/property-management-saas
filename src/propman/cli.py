"""Command line: triage a request, a tenant's balance, the console, and the evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="propman", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("triage", help="triage a maintenance request (Claude too with ANTHROPIC_API_KEY)")
    t.add_argument("text")
    sub.add_parser("board", help="the demo portfolio's requests since Friday, by urgency")
    s = sub.add_parser("serve", help="the console with the demo portfolio")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    ev = sub.add_parser("evaluate", help="triage and dispatch on validation and fresh phrasings, and the rent ledger")
    ev.add_argument("--out", default="eval/reports")
    ev.add_argument("--gate", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "evaluate":
        from .evaluate import run, save

        result = run(gate=args.gate)
        save(result, Path(args.out))
        print((Path(args.out) / "report.md").read_text(encoding="utf-8"))
        return 1 if args.gate and not result["gate"]["passed"] else 0
    if args.cmd == "serve":
        import uvicorn

        from .app import demo_app

        uvicorn.run(demo_app(), host=args.host, port=args.port)
        return 0
    if args.cmd == "triage":
        import os

        from .app import demo_console, triage_text
        from .reader import Reader

        c = demo_console(Reader() if os.environ.get("ANTHROPIC_API_KEY") else None)
        print(json.dumps(triage_text(c, args.text), indent=2))
        return 0
    from .app import demo_console

    c = demo_console()
    for urg in ("emergency", "urgent", "routine"):
        for tk in (x for x in c.tickets if x.decision.urgency == urg):
            print(f"{urg:9s} {tk.decision.trade:10s} {tk.unit.id:6s} {tk.at:%a %H:%M}  {tk.request.text[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
