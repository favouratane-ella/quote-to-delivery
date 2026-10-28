"""Test scenarios: known situations with the result each should produce.

Each scenario runs in its own throwaway world, so tests never touch the main data.
Run them from the UI, the API (POST /api/scenarios/{id}/run), the command line
(python -m app.cli scenarios) or pytest.
"""
from __future__ import annotations

import uuid
from typing import Callable

from sqlalchemy.orm import Session

from . import models as m
from .agent import Agent
from .seed import EMAILS, SUPPLIERS, create_world, delete_world


def _seed_email(subject: str) -> dict:
    return next(e for e in EMAILS if e["subject"] == subject)


def _po_last(db: Session, w: str, po: str) -> str:
    return max(d["date"] for d in db.get(m.PurchaseOrder, (w, po)).deliveries)


def _po_unchanged(db: Session, w: str) -> bool:
    return all(p.deliveries == p.original for p in db.query(m.PurchaseOrder).filter(m.PurchaseOrder.world_id == w))


def _approvals(db: Session, w: str) -> list[m.Approval]:
    return db.query(m.Approval).filter(m.Approval.world_id == w).order_by(m.Approval.rank).all()


def _sos(db: Session, w: str) -> str:
    return ",".join(sorted(a.so for a in _approvals(db, w)))


Check = Callable[[Session, str, m.Run], bool]

SCENARIOS: list[dict] = [
    {"id": "SC1", "title": "Supplier delays a large order", "what": "Lakeside Plastics moves PO-8841 (280 crates) from 2 Nov to 7 Nov.",
     "email": {"sender": "Lakeside Plastics", "subject": _seed_email("PO-8841 delayed, new ship date")["subject"], "body": _seed_email("PO-8841 delayed, new ship date")["body"]},
     "expect": [
         ("ERP: PO-8841 now arrives Sat 7 Nov", lambda db, w, r: _po_last(db, w, "PO-8841") == "2026-11-07"),
         ("Flags Northwind, Harbor and Delta as late", lambda db, w, r: _sos(db, w) == "SO-5532,SO-5547,SO-5561"),
         ("Leaves Kestrel alone: still on time", lambda db, w, r: all(a.so != "SO-5570" for a in _approvals(db, w))),
         ("Northwind and Harbor need manager approval", lambda db, w, r: ",".join(sorted(a.so for a in _approvals(db, w) if a.value >= 25000 and a.status == "Needs approval")) == "SO-5532,SO-5547"),
         ("Ranks Northwind first", lambda db, w, r: bool(_approvals(db, w)) and _approvals(db, w)[0].so == "SO-5532"),
     ]},
    {"id": "SC2", "title": "Split shipment that still covers every order", "what": "Vexa sends PO-8856 in two parts. The first part covers the only order waiting on it.",
     "email": {"sender": "Vexa Packaging", "subject": _seed_email("PO-8856 split shipment")["subject"], "body": _seed_email("PO-8856 split shipment")["body"]},
     "expect": [
         ("ERP: PO-8856 saved as 400 then 200", lambda db, w, r: [d["qty"] for d in db.get(m.PurchaseOrder, (w, "PO-8856")).deliveries] == [400, 200]),
         ("No order flagged", lambda db, w, r: not _approvals(db, w)),
         ("No customer emailed", lambda db, w, r: db.query(m.OutboxMessage).filter(m.OutboxMessage.world_id == w).count() == 0),
     ]},
    {"id": "SC3", "title": "Supplier says the order is not delayed", "what": 'The email contains the word "delayed" but confirms the planned date.',
     "email": {"sender": "Vexa Packaging", "subject": "PO-8863 update", "body": "Hi,\n\nGood news: PO-8863 is not delayed and the liners will arrive on 9 November as planned.\n\nCarla"},
     "expect": [
         ("ERP unchanged", lambda db, w, r: _po_unchanged(db, w)),
         ("Filed with no action", lambda db, w, r: r.status == "no_action"),
     ]},
    {"id": "SC4", "title": 'Delay given as "one week later"', "what": "No date is written. The agent must work it out from the ERP date.",
     "email": {"sender": "Coolchain Gel Co", "subject": "PO-8860 delay", "body": "Hello,\n\nDue to a port strike, PO-8860 (5,000 gel packs) is pushed back by one week.\n\nRegards,\nCoolchain Gel Co"},
     "expect": [
         ("ERP: PO-8860 now arrives Fri 13 Nov", lambda db, w, r: _po_last(db, w, "PO-8860") == "2026-11-13"),
         ("Flags Fernhill Foods as late", lambda db, w, r: _sos(db, w) == "SO-5538"),
         ("Small order can go after one check", lambda db, w, r: bool(_approvals(db, w)) and _approvals(db, w)[0].status == "Ready"),
     ]},
    {"id": "SC5", "title": "Email names a PO we do not have", "what": "The supplier quotes PO-9921, which is not in the ERP.",
     "email": {"sender": "Lakeside Plastics", "subject": "PO-9921 new date", "body": "Hello,\n\nPO-9921 will now arrive on 12 November instead of 5 November.\n\nMarta"},
     "expect": [
         ("Stops and asks a person", lambda db, w, r: r.status == "waiting_person"),
         ("ERP unchanged", lambda db, w, r: _po_unchanged(db, w)),
         ("No customer emails drafted", lambda db, w, r: not _approvals(db, w)),
     ]},
    {"id": "SC6", "title": "Vague warning with no firm date", "what": '"Might slip next week, will confirm." Nothing should change yet.',
     "email": {"sender": "Nordtherm Sensors", "subject": "Heads up on PO-8850", "body": "Hi team,\n\nHeads up: the sensor tags on PO-8850 might slip next week. We will confirm a firm date by Friday.\n\nJonas"},
     "expect": [
         ("ERP unchanged", lambda db, w, r: _po_unchanged(db, w)),
         ("No customer emails drafted", lambda db, w, r: not _approvals(db, w)),
         ("Asks a person or files it", lambda db, w, r: r.status in ("waiting_person", "no_action")),
     ]},
    {"id": "SC9", "title": "Email from the wrong supplier", "what": "Nordtherm writes about PO-8841, which belongs to Lakeside Plastics.",
     "email": {"sender": "Nordtherm Sensors", "subject": "PO-8841 delay", "body": "Hello,\n\nPO-8841 will now arrive on 12 November instead of 2 November.\n\nJonas"},
     "expect": [
         ("Stops and asks a person", lambda db, w, r: r.status == "waiting_person"),
         ("ERP unchanged", lambda db, w, r: _po_unchanged(db, w)),
     ]},
    {"id": "SC10", "title": "Uncertain wording with a date", "what": '"Might slip to 9 Nov." A date is given, but the supplier is not sure.',
     "email": {"sender": "Lakeside Plastics", "subject": "PO-8841 possible delay", "body": "Hi,\n\nPO-8841 might slip to 9 November. We will know more on Friday.\n\nMarta"},
     "expect": [
         ("Stops and asks a person", lambda db, w, r: r.status == "waiting_person"),
         ("ERP unchanged", lambda db, w, r: _po_unchanged(db, w)),
     ]},
    {"id": "SC11", "title": "Supplier delivers early", "what": "PO-8860 arrives three days early. The ERP should change, and no customer needs telling.",
     "email": {"sender": "Coolchain Gel Co", "subject": "PO-8860 early", "body": "Good news, PO-8860 is coming early: expect it on 3 November."},
     "expect": [
         ("ERP: PO-8860 now arrives Tue 3 Nov", lambda db, w, r: _po_last(db, w, "PO-8860") == "2026-11-03"),
         ("No customer emails drafted", lambda db, w, r: not _approvals(db, w)),
         ("Run finishes on its own", lambda db, w, r: r.status == "done"),
     ]},
    {"id": "SC12", "title": "Supplier corrects an earlier email", "what": '"Now 9 Nov. Ignore our earlier note that said 7 Nov." The corrected date must win, and two extra days also push Kestrel past its promise.',
     "email": {"sender": "Lakeside Plastics", "subject": "Correction: PO-8841", "body": "Hi,\n\nPO-8841 now arriving 9 Nov. Ignore our earlier note that said 7 Nov.\n\nMarta"},
     "expect": [
         ("ERP: PO-8841 now arrives Mon 9 Nov", lambda db, w, r: _po_last(db, w, "PO-8841") == "2026-11-09"),
         ("Flags all four orders, including Kestrel (now 1 day late)", lambda db, w, r: _sos(db, w) == "SO-5532,SO-5547,SO-5561,SO-5570"),
     ]},
    {"id": "SC13", "title": "Supplier asks a question", "what": '"Can you confirm the delivery address?" Contains "confirm" but is not a confirmation.',
     "email": {"sender": "Vexa Packaging", "subject": "PO-8856 address", "body": "Hi,\n\nCan you confirm the delivery address for PO-8856?\n\nCarla"},
     "expect": [
         ("Filed with no action", lambda db, w, r: r.status == "no_action"),
         ("ERP unchanged", lambda db, w, r: _po_unchanged(db, w)),
     ]},
    {"id": "SC14", "title": "Split shipment that does not add up", "what": "Vexa offers 1,000 + 300 liners, but PO-8863 is for 1,500.",
     "email": {"sender": "Vexa Packaging", "subject": "PO-8863 in two parts", "body": "Hi,\n\nWe can ship 1,000 thermal liners from PO-8863 on 9 November and the remaining 300 on 18 November.\n\nCarla"},
     "expect": [
         ("Stops and asks a person", lambda db, w, r: r.status == "waiting_person"),
         ("ERP unchanged", lambda db, w, r: _po_unchanged(db, w)),
     ]},
    {"id": "SC7", "title": "Quote that cannot be met", "what": "Orchard & Pine wants 400 crates by Fri 30 Oct. Only 120 are free.",
     "quote": {"customer_id": "orchard", "sku": "CC-210", "qty": 400, "requested": "2026-10-30"},
     "expect": [
         ("Says Fri 30 Oct cannot be met", lambda db, w, r: r.result["feasible"] is False),
         ("Earliest full delivery Wed 18 Nov", lambda db, w, r: r.result["eta"] == "2026-11-18"),
         ("Offers 120 crates by Wed 28 Oct", lambda db, w, r: bool(r.result["split"]) and r.result["split"]["now"] == 120 and r.result["split"]["now_eta"] == "2026-10-28"),
     ]},
    {"id": "SC8", "title": "Quote that can be met", "what": "Meridian Pharma wants 500 sensor tags by Tue 3 Nov.",
     "quote": {"customer_id": "meridian", "sku": "TS-88", "qty": 500, "requested": "2026-11-03"},
     "expect": [
         ("Confirms the date can be met", lambda db, w, r: r.result["feasible"] is True),
         ("Arrives Sun 1 Nov", lambda db, w, r: r.result["eta"] == "2026-11-01"),
     ]},
]
from .scenarios_recovery import SC_RECOVERY  # noqa: E402

SCENARIOS += SC_RECOVERY
BY_ID = {s["id"]: s for s in SCENARIOS}


def run_scenario(db: Session, scenario_id: str, ai_mode: str = "auto", llm=None) -> m.ScenarioResult:
    sc = BY_ID[scenario_id]
    old = db.get(m.ScenarioResult, scenario_id)
    if old:
        delete_world(db, old.world_id)
    w = f"scn-{scenario_id.lower()}-{uuid.uuid4().hex[:6]}"
    create_world(db, w, kind="scenario", with_mail=False, with_quotes=False)
    db.get(m.Settings, w).ai_mode = ai_mode
    db.commit()
    agent = Agent(db, w, llm=llm, delay_ms=0)
    if "flow" in sc:
        run = sc["flow"](db, w, agent)
    elif "email" in sc:
        e = m.Email(world_id=w, sender=sc["email"]["sender"], address=SUPPLIERS.get(sc["email"]["sender"], "supplier@example.com"), received_at="2026-10-26T09:00",
                    subject=sc["email"]["subject"], body=sc["email"]["body"], attachment=None)
        db.add(e)
        db.commit()
        run = agent.run_email(e.id)
    else:
        q = m.Quote(world_id=w, q="Q-T" + scenario_id[2:], **sc["quote"])
        db.add(q)
        db.commit()
        run = agent.run_quote(q.q)
    checks = []
    for label, fn in sc["expect"]:
        try:
            ok = bool(fn(db, w, run))
        except Exception:  # noqa: BLE001
            ok = False
        checks.append({"label": label, "ok": ok})
    res = old or m.ScenarioResult(scenario_id=scenario_id)
    res.world_id, res.run_id, res.mode, res.checks, res.passed = w, run.id, run.mode, checks, all(c["ok"] for c in checks)
    db.add(res)
    db.commit()
    return res
