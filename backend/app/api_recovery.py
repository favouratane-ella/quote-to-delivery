"""REST routes for cases, customer replies and recovery proposals."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import models as m
from .agent import Agent
from .api import agent_bg, iso, run_out
from .connectors.simulated import SimulatedSystems, customer_dict
from .customer_sim import compose_reply
from .db import get_db
from .recovery import options_for, risk_tier
from .sim_bg import reply_bg

router = APIRouter(prefix="/api")
W = "main"
STYLES = ["accept", "hard", "partial", "expedite", "credit", "cancel", "question", "silent"]


def case_out(c: m.OrderCase) -> dict:
    return {"id": c.id, "so": c.so, "status": c.status, "resolution": c.resolution, "reason": c.reason, "original_promised": c.original_promised, "eta": c.eta, "days_late": c.days_late,
            "pending_proposal": c.pending_proposal, "opened_at": iso(c.opened_at), "closed_at": iso(c.closed_at), "run_id": c.run_id}


def proposal_out(p: m.Proposal, customers: dict) -> dict:
    return {"id": p.id, "run_id": p.run_id, "so": p.so, "customer_id": p.customer_id, "customer": customers.get(p.customer_id, {}).get("name"), "contact": customers.get(p.customer_id, {}).get("contact"),
            "kind": p.kind, "title": p.title, "summary": p.summary, "detail": p.detail or {}, "cost": p.cost, "value": p.value, "meets_promised": p.meets_promised,
            "needs_customer_ok": p.needs_customer_ok, "needs": p.needs, "status": p.status, "to": p.to, "subject": p.subject, "body": p.body, "note": p.note, "reason": p.reason,
            "created_at": iso(p.created_at), "decided_by": p.decided_by, "decided_at": iso(p.decided_at)}


def reply_out(r: m.CustomerReply, customers: dict) -> dict:
    c = customers.get(r.customer_id, {})
    return {"id": r.id, "so": r.so, "customer_id": r.customer_id, "customer": c.get("name"), "contact": c.get("contact"), "at": iso(r.at), "subject": r.subject, "body": r.body,
            "source": r.source, "status": r.status, "intent": r.intent, "run_id": r.run_id}


def _customers(db: Session) -> dict:
    return {c.id: customer_dict(c) for c in db.query(m.Customer).filter(m.Customer.world_id == W)}


@router.get("/cases")
def cases(db: Session = Depends(get_db)):
    sysm = SimulatedSystems(db, W)
    from .engine import Engine

    en = Engine(sysm.snapshot(Agent(db, W).today))
    latest: dict[str, m.OrderCase] = {}
    for c in db.query(m.OrderCase).filter(m.OrderCase.world_id == W).order_by(m.OrderCase.id):
        latest[c.so] = c
    out = []
    for so, c in latest.items():
        o = next((x for x in en.s.orders if x["so"] == so), None)
        if not o:
            continue
        v, cust = en.order_view(o), en.s.customers[o["customer_id"]]
        t = risk_tier(v, cust, {"status": c.status, "resolution": c.resolution})
        out.append({**case_out(c), "customer": cust["name"], "customer_id": cust["id"], "flex": cust["flex"], "value": o["value"], "promised": o["promised"], "now_eta": v["eta"], "now_late": v["days_late"], "risk": t["tier"]})
    return sorted(out, key=lambda x: (x["status"] == "resolved", -x["value"]))


@router.get("/cases/{so}")
def case_detail(so: str, db: Session = Depends(get_db)):
    agent = Agent(db, W)
    en = agent.engine_held()
    o = next((x for x in en.s.orders if x["so"] == so), None)
    if not o:
        raise HTTPException(404, "Unknown order")
    cust = en.s.customers[o["customer_id"]]
    cs = db.query(m.OrderCase).filter(m.OrderCase.world_id == W, m.OrderCase.so == so).order_by(m.OrderCase.id.desc()).all()
    case = cs[0] if cs else None
    v = en.order_view(o)
    tier = risk_tier(v, cust, {"status": case.status, "resolution": case.resolution} if case else None)
    customers = _customers(db)
    lines = [x for x in en.s.orders if x["so"] == so or x.get("parent") == so or x["so"] == o.get("parent") or (o.get("parent") and x.get("parent") == o["parent"])]
    options = options_for(en, so, agent.cfg.approval_limit) if v["late"] and case and case.status != "resolved" else None
    return {
        "order": {**v, "risk": tier["tier"], "risk_why": tier["why"]},
        "customer": cust,
        "case": case_out(case) if case else None,
        "events": [{"at": iso(e.at), "actor": e.actor, "kind": e.kind, "text": e.text} for e in db.query(m.CaseEvent).filter(m.CaseEvent.world_id == W, m.CaseEvent.so == so).order_by(m.CaseEvent.id)],
        "replies": [reply_out(r, customers) for r in db.query(m.CustomerReply).filter(m.CustomerReply.world_id == W, m.CustomerReply.so == so).order_by(m.CustomerReply.id)],
        "proposals": [proposal_out(p, customers) for p in db.query(m.Proposal).filter(m.Proposal.world_id == W, m.Proposal.so == so).order_by(m.Proposal.id)],
        "messages": [{"id": x.id, "at": iso(x.at), "to": x.to, "subject": x.subject, "body": x.body, "sent_by": x.sent_by, "kind": x.kind}
                     for x in db.query(m.OutboxMessage).filter(m.OutboxMessage.world_id == W, m.OutboxMessage.so == so).order_by(m.OutboxMessage.id)],
        "lines": [{"so": x["so"], "sku": x["sku"], "qty": x["qty"], "promised": x["promised"], "parent": x.get("parent"), "note": x.get("note", "")} for x in lines],
        "options": options,
    }


# ---------------- customer replies ----------------
@router.get("/replies")
def replies(db: Session = Depends(get_db)):
    customers = _customers(db)
    return [reply_out(r, customers) for r in db.query(m.CustomerReply).filter(m.CustomerReply.world_id == W).order_by(m.CustomerReply.id.desc())]


class ReplyIn(BaseModel):
    so: str
    body: str = Field(min_length=2)


@router.post("/replies")
def type_reply(body: ReplyIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    agent = Agent(db, W)
    try:
        r = agent.make_reply(body.so, "notice", text=body.body, source="typed")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not r:
        raise HTTPException(400, "That order has no open case, so there is nothing to reply to.")
    if agent.cfg.auto_run:
        bg.add_task(agent_bg, "run_reply", r.id)
    return {"id": r.id}


class SimIn(BaseModel):
    so: str
    style: str = Field(pattern="^(" + "|".join(STYLES) + ")$")


@router.post("/replies/simulate")
def simulate_reply(body: SimIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    agent = Agent(db, W)
    en = agent.engine()
    o = next((x for x in en.s.orders if x["so"] == body.so), None)
    if not o or not agent.case(body.so):
        raise HTTPException(400, "That order has no open case.")
    cust = {**en.s.customers[o["customer_id"]], "reply_style": body.style}
    stage = "offer" if agent.case(body.so).pending_proposal else "notice"
    composed = compose_reply(cust, o, en.s.items[o["sku"]]["unit"], en.order_view(o)["eta"], stage)
    if not composed:
        raise HTTPException(400, f"{cust['name']} stays silent in that style, so there is no reply to add.")
    r = agent.make_reply(body.so, stage, text=composed[1], source="simulated")
    if agent.cfg.auto_run:
        bg.add_task(agent_bg, "run_reply", r.id)
    return {"id": r.id}


@router.post("/replies/{reply_id}/process")
def process_reply(reply_id: int, bg: BackgroundTasks, db: Session = Depends(get_db)):
    r = db.get(m.CustomerReply, reply_id)
    if not r or r.world_id != W:
        raise HTTPException(404, "Unknown reply")
    if r.run_id:
        raise HTTPException(400, "The agent has already read this reply.")
    bg.add_task(agent_bg, "run_reply", reply_id)
    return {"ok": True}


class ReplyResolveIn(BaseModel):
    intent: str
    date: str | None = None


@router.post("/replies/{reply_id}/resolve")
def resolve_reply(reply_id: int, body: ReplyResolveIn, db: Session = Depends(get_db)):
    try:
        run = Agent(db, W).resolve_reply(reply_id, body.intent, body.date)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"run_id": run.id, "status": run.status}


# ---------------- proposals ----------------
@router.get("/proposals")
def proposals(db: Session = Depends(get_db)):
    customers = _customers(db)
    return [proposal_out(p, customers) for p in db.query(m.Proposal).filter(m.Proposal.world_id == W).order_by(m.Proposal.id.desc())]


class ProposalIn(BaseModel):
    subject: str | None = None
    body: str | None = None


@router.post("/proposals/{pid}/approve")
def approve_proposal(pid: int, body: ProposalIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        p = Agent(db, W).decide_proposal(pid, True, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if p.status == "Offered":
        bg.add_task(reply_bg, p.so, "offer", p.id)
    return {"ok": True, "status": p.status}


@router.post("/proposals/{pid}/reject")
def reject_proposal(pid: int, db: Session = Depends(get_db)):
    try:
        Agent(db, W).decide_proposal(pid, False)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}
