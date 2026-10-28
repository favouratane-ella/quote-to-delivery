"""Command line: python -m app.cli [seed|reset|scenarios [--mode rules|auto]]"""
from __future__ import annotations

import argparse
import sys

from .db import SessionLocal, init_db
from .scenarios import SCENARIOS, run_scenario
from .seed import create_world, ensure_main_world


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="Create the main world if it does not exist")
    sub.add_parser("reset", help="Reset the main world to the sample data")
    sc = sub.add_parser("scenarios", help="Run all test scenarios and print pass/fail")
    sc.add_argument("--mode", choices=["auto", "rules"], default="auto", help="auto uses Claude when ANTHROPIC_API_KEY is set")
    a = ap.parse_args()
    init_db()
    db = SessionLocal()
    try:
        if a.cmd == "seed":
            ensure_main_world(db)
            print("Main world ready.")
        elif a.cmd == "reset":
            create_world(db, "main")
            print("Main world reset.")
        else:
            passed = 0
            for s in SCENARIOS:
                r = run_scenario(db, s["id"], ai_mode=a.mode)
                passed += r.passed
                print(f"{'PASS' if r.passed else 'FAIL'}  {s['id']}  {s['title']}  [{r.mode}]")
                for c in r.checks:
                    print(f"        {'ok ' if c['ok'] else 'NO '} {c['label']}")
            print(f"\n{passed}/{len(SCENARIOS)} scenarios passed")
            return 0 if passed == len(SCENARIOS) else 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
