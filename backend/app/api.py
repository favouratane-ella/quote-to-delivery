"""REST API. Every route works on the "main" world; scenarios make their own."""
from __future__ import annotations

import copy
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import models as m
from . import prompts
from .agent import Agent, utcnow
from .chat_tools import TOOLS, make_runner
from .config import settings
from .connectors.simulated import SimulatedSystems, customer_dict, email_dict, po_dict, quote_dict
from .db import SessionLocal, get_db
from .engine import Engine, add_days, fmt_date
from .llm import get_llm, parse_json
from .rules_reader import read_email as rules_read
from .recovery import risk_tier
from .scenarios import SCENARIOS, run_scenario
from .sim_bg import reply_bg
from .seed import SUPPLIERS, TEMPLATES, TEST_PACK, create_world

router = APIRouter(prefix="/api")
W = "main"


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def cfg(db: Session) -> m.Settings:
    return db.get(m.Settings, W)


def agent_bg(fn_name: str, *args, **kwargs) -> None:
    """Run an agent job in the background with its own database session."""
    db = SessionLocal()
    try:
        getattr(Agent(db, W), fn_name)(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        db.add(m.ActivityLog(world_id=W, at=utcnow(), actor="System", system="Agent", text=f"Agent job {fn_name} failed: {e}"))
        db.commit()
    finally:
        db.close()


def run_out(r: m.Run, with_steps: bool = True) -> dict:
    d = {"id": r.id, "title": r.title, "status": r.status, "mode": r.mode, "trigger": r.trigger, "started_at": iso(r.started_at), "ended_at": iso(r.ended_at),
         "pending": r.pending, "result": r.result, "options": r.options, "step_count": len(r.steps)}
    if with_steps:
        d["steps"] = [{"seq": s.seq, "kind": s.kind, "system": s.system, "title": s.title, "text": s.text, "payload": s.payload or {}, "at": s.at_seconds} for s in r.steps]
    return d


def approval_out(a: m.Approval, customers: dict) -> dict:
    c = customers.get(a.customer_id, {})
    return {"id": a.id, "run_id": a.run_id, "so": a.so, "customer_id": a.customer_id, "customer": c.get("name"), "contact": c.get("contact"), "email": c.get("email"),
            "value": a.value, "subject": a.subject, "body": a.body, "note": a.note, "reader": a.reader, "wording_ok": a.wording_ok, "status": a.status, "reason": a.reason,
            "rank": a.rank, "new_date": a.new_date, "decided_by": a.decided_by, "decided_at": iso(a.decided_at)}


# ---------------- status and settings ----------------
@router.get("/health")
def health():
    return {"ok": True}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    s = cfg(db)
    llm = get_llm()
    running = db.query(m.Run).filter(m.Run.world_id == W, m.Run.status == "running").order_by(m.Run.id.desc()).first()
    last = running.steps[-1].title if running and running.steps else None
    return {
        "today": settings.today, "today_label": fmt_date(settings.today), "ai_available": llm.available, "model": llm.model if llm.available else None,
        "ai_mode": s.ai_mode, "ai_active": s.ai_mode == "auto" and llm.available,
        "counts": {
            "unprocessed": db.query(m.Email).filter(m.Email.world_id == W, m.Email.status == "Not processed").count(),
            "waiting_person": db.query(m.Run).filter(m.Run.world_id == W, m.Run.status == "waiting_person").count(),
            "approvals": db.query(m.Approval).filter(m.Approval.world_id == W, m.Approval.status.in_(["Needs approval", "Ready"])).count(),
            "proposals": db.query(m.Proposal).filter(m.Proposal.world_id == W, m.Proposal.status == "Proposed").count(),
            "replies": db.query(m.CustomerReply).filter(m.CustomerReply.world_id == W, m.CustomerReply.status.in_(["New", "Needs a person"])).count(),
            "cases_open": db.query(m.OrderCase).filter(m.OrderCase.world_id == W, m.OrderCase.status.notin_(["resolved", "lost"])).count(),
            "running": db.query(m.Run).filter(m.Run.world_id == W, m.Run.status == "running").count(),
            "runs": db.query(m.Run).filter(m.Run.world_id == W).count(),
        },
        "running": {"id": running.id, "title": running.title, "step": last} if running else None,
    }


class SettingsIn(BaseModel):
    auto_run: bool
    ai_mode: str = Field(pattern="^(auto|rules)$")
    approval_limit: float = Field(ge=0)
    pass_mark: float = Field(ge=0.5, le=1)
    tone: str
    sim_customers: bool = True


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    s = cfg(db)
    return {"auto_run": s.auto_run, "ai_mode": s.ai_mode, "approval_limit": s.approval_limit, "pass_mark": s.pass_mark, "tone": s.tone, "sim_customers": s.sim_customers}


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    s = cfg(db)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.add(m.ActivityLog(world_id=W, at=utcnow(), actor="Ops manager", system="Settings", text=f"Settings saved: {'AI' if s.ai_mode == 'auto' else 'rules'} mode, approval from ${s.approval_limit:,.0f}, pass mark {round(s.pass_mark * 100)}%."))
    db.commit()
    return get_settings(db)


@router.post("/world/reset")
def reset_world(db: Session = Depends(get_db)):
    old = cfg(db)
    keep = {k: getattr(old, k) for k in ("auto_run", "ai_mode", "approval_limit", "pass_mark", "tone", "sim_customers")} if old else {}
    create_world(db, W)
    s = cfg(db)
    for k, v in keep.items():
        setattr(s, k, v)
    db.commit()
    return {"ok": True}


# ---------------- supplier mailbox ----------------
class EmailIn(BaseModel):
    sender: str
    subject: str = ""
    body: str = ""


@router.get("/mailbox")
def mailbox(db: Session = Depends(get_db)):
    rows = db.query(m.Email).filter(m.Email.world_id == W).order_by(m.Email.id.desc()).all()
    return [email_dict(e) for e in rows]


@router.get("/mailbox/templates")
def templates():
    return [{"key": k, "label": v[0], "sender": v[1], "subject": v[2], "body": v[3]} for k, v in TEMPLATES.items()]


@router.get("/suppliers")
def suppliers(db: Session = Depends(get_db)):
    return [{"name": s.name, "email": s.email} for s in db.query(m.Supplier).filter(m.Supplier.world_id == W)]


@router.post("/mailbox")
def send_email(body: EmailIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    sup = db.get(m.Supplier, (W, body.sender))
    e = m.Email(world_id=W, sender=body.sender, address=sup.email if sup else SUPPLIERS.get(body.sender, "supplier@example.com"),
                received_at=settings.today + "T" + utcnow().strftime("%H:%M"), subject=body.subject or "(no subject)", body=body.body, attachment=None)
    db.add(e)
    db.add(m.ActivityLog(world_id=W, at=utcnow(), actor="Supplier", system="Email", text=f'{body.sender} sent "{e.subject}".'))
    db.commit()
    if cfg(db).auto_run:
        bg.add_task(agent_bg, "run_email", e.id)
    return email_dict(e)


@router.post("/mailbox/{email_id}/process")
def process_email(email_id: int, bg: BackgroundTasks, db: Session = Depends(get_db)):
    e = db.get(m.Email, email_id)
    if not e or e.world_id != W:
        raise HTTPException(404, "Email not found")
    if e.run_id:
        raise HTTPException(409, "The agent already handled this email")
    bg.add_task(agent_bg, "run_email", email_id)
    return {"ok": True}


@router.post("/mailbox/process-all")
def process_all(bg: BackgroundTasks, db: Session = Depends(get_db)):
    ids = [e.id for e in db.query(m.Email).filter(m.Email.world_id == W, m.Email.status == "Not processed").order_by(m.Email.id)]

    def job():
        for i in ids:
            agent_bg("run_email", i)

    bg.add_task(job)
    return {"queued": len(ids)}


# ---------------- ERP ----------------
def engine(db: Session) -> Engine:
    return Engine(SimulatedSystems(db, W).snapshot(settings.today))


@router.get("/erp/items")
def items(db: Session = Depends(get_db)):
    e = engine(db)
    return [{**i, "reserved": sum(o["stock_qty"] for o in e.s.orders if o["sku"] == i["sku"]), "free": e.free_stock(i["sku"])} for i in e.s.items.values()]


class StockIn(BaseModel):
    on_hand: int = Field(ge=0)


@router.put("/erp/items/{sku}")
def put_item(sku: str, body: StockIn, db: Session = Depends(get_db)):
    it = db.get(m.Item, (W, sku))
    if not it:
        raise HTTPException(404, "Unknown SKU")
    db.add(m.ActivityLog(world_id=W, at=utcnow(), actor="Planner", system="ERP", text=f"{sku} on hand changed from {it.on_hand} to {body.on_hand}."))
    it.on_hand = body.on_hand
    db.commit()
    return {"ok": True}


@router.get("/erp/purchase-orders")
def purchase_orders(db: Session = Depends(get_db)):
    e = engine(db)
    return [{**p, "qty": e.po_total(p), "arrival": e.last_date(p["deliveries"]), "changed": p["deliveries"] != p["original"]} for p in e.s.pos.values()]


class ArrivalIn(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.put("/erp/purchase-orders/{po}/arrival")
def put_arrival(po: str, body: ArrivalIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    p = db.get(m.PurchaseOrder, (W, po))
    if not p:
        raise HTTPException(404, "Unknown PO")
    before = copy.deepcopy(p.deliveries)
    if max(d["date"] for d in before) == body.date:
        raise HTTPException(400, "That is already the arrival date")
    after = [dict(d) for d in before]
    after[-1]["date"] = body.date
    p.deliveries = after
    db.add(m.ActivityLog(world_id=W, at=utcnow(), actor="Planner", system="ERP", text=f"{po} arrival edited in the ERP to {fmt_date(body.date)}."))
    db.commit()
    started = cfg(db).auto_run
    if started:
        bg.add_task(agent_bg, "run_erp_change", po, before, after, "Planner")
    return {"ok": True, "agent_started": started}


@router.get("/erp/sales-orders")
def sales_orders(db: Session = Depends(get_db)):
    e = engine(db)
    latest: dict[str, m.OrderCase] = {}
    for c in db.query(m.OrderCase).filter(m.OrderCase.world_id == W).order_by(m.OrderCase.id):
        latest[c.so] = c
    out = []
    for o in e.s.orders:
        v, cust, c = e.order_view(o), e.s.customers[o["customer_id"]], latest.get(o["so"])
        t = risk_tier(v, cust, {"status": c.status, "resolution": c.resolution} if c else None)
        out.append({**v, "risk": t["tier"], "risk_why": t["why"], "case_status": c.status if c else None, "resolution": c.resolution if c else "", "flex": cust["flex"], "max_slip": cust["max_slip"]})
    return out


class OrderIn(BaseModel):
    customer_id: str
    sku: str
    qty: int = Field(gt=0)
    value: float = Field(ge=0)
    promised: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/erp/sales-orders")
def add_order(body: OrderIn, db: Session = Depends(get_db)):
    e = engine(db)
    if body.sku not in e.s.items or body.customer_id not in e.s.customers:
        raise HTTPException(400, "Unknown customer or SKU")
    from_stock = min(e.free_stock(body.sku), body.qty)
    need, po = body.qty - from_stock, None
    if need:
        cands = []
        for p in e.s.pos.values():
            if p["sku"] == body.sku:
                free = e.po_total(p) - sum(o["po_qty"] for o in e.s.orders if o["po"] == p["po"])
                if free >= need:
                    cands.append((e.last_date(p["deliveries"]), p["po"]))
        if not cands:
            raise HTTPException(400, f"Not enough stock or inbound supply for {body.qty} {body.sku}")
        po = sorted(cands)[0][1]
    so = f"SO-{5600 + len(e.s.orders)}"
    db.add(m.SalesOrder(world_id=W, so=so, customer_id=body.customer_id, sku=body.sku, qty=body.qty, value=body.value, promised=body.promised, stock_qty=from_stock, po=po, po_qty=need))
    db.add(m.ActivityLog(world_id=W, at=utcnow(), actor="Sales rep", system="ERP", text=f"Added {so}: {body.qty} {body.sku} for {e.s.customers[body.customer_id]['name']}" + (f" ({need} on {po})." if po else " from stock.")))
    db.commit()
    return {"so": so, "stock_qty": from_stock, "po": po, "po_qty": need}


@router.get("/erp/inventory")
def inventory(db: Session = Depends(get_db)):
    return Agent(db, W).inventory()


@router.post("/inventory/scan")
def inventory_scan(bg: BackgroundTasks, db: Session = Depends(get_db)):
    bg.add_task(agent_bg, "run_inventory_scan")
    return {"ok": True}


@router.get("/erp/lanes")
def lanes(db: Session = Depends(get_db)):
    return [{"name": l.name, "days": l.days, "express_saves": l.express_saves, "express_cost": l.express_cost} for l in db.query(m.Lane).filter(m.Lane.world_id == W)]


# ---------------- CRM ----------------
@router.get("/crm/customers")
def customers(db: Session = Depends(get_db)):
    return [customer_dict(c) for c in db.query(m.Customer).filter(m.Customer.world_id == W).order_by(m.Customer.name)]


@router.get("/crm/notes")
def notes(db: Session = Depends(get_db)):
    cs = {c.id: c.name for c in db.query(m.Customer).filter(m.Customer.world_id == W)}
    return [{"id": n.id, "at": iso(n.at), "customer_id": n.customer_id, "customer": cs.get(n.customer_id), "text": n.text} for n in db.query(m.CrmNote).filter(m.CrmNote.world_id == W).order_by(m.CrmNote.id.desc())]


@router.get("/crm/quotes")
def quotes(db: Session = Depends(get_db)):
    cs = {c.id: c.name for c in db.query(m.Customer).filter(m.Customer.world_id == W)}
    return [{**quote_dict(q), "customer": cs.get(q.customer_id)} for q in db.query(m.Quote).filter(m.Quote.world_id == W).order_by(m.Quote.created_at.desc(), m.Quote.q.desc())]


class QuoteIn(BaseModel):
    customer_id: str
    sku: str
    qty: int = Field(gt=0)
    requested: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/crm/quotes")
def new_quote(body: QuoteIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    n = db.query(m.Quote).filter(m.Quote.world_id == W).count()
    q = f"Q-{2041 + n}"
    while db.get(m.Quote, (W, q)):
        n += 1
        q = f"Q-{2041 + n}"
    db.add(m.Quote(world_id=W, q=q, **body.model_dump()))
    db.add(m.ActivityLog(world_id=W, at=utcnow(), actor="Sales rep", system="CRM", text=f"Created {q}."))
    db.commit()
    bg.add_task(agent_bg, "run_quote", q)
    return {"q": q}


@router.post("/crm/quotes/{q}/check")
def check_quote(q: str, bg: BackgroundTasks, db: Session = Depends(get_db)):
    r = db.get(m.Quote, (W, q))
    if not r:
        raise HTTPException(404, "Unknown quote")
    if r.run_id:
        raise HTTPException(409, "Already checked")
    bg.add_task(agent_bg, "run_quote", q)
    return {"ok": True}


class ChoiceIn(BaseModel):
    option: str


@router.post("/crm/quotes/{q}/choose")
def choose(q: str, body: ChoiceIn, db: Session = Depends(get_db)):
    try:
        run = Agent(db, W).choose_quote(q, body.option)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return run_out(run)


# ---------------- agent runs ----------------
@router.get("/runs")
def runs(db: Session = Depends(get_db)):
    return [run_out(r, with_steps=False) for r in db.query(m.Run).filter(m.Run.world_id == W).order_by(m.Run.id.desc()).limit(200)]


@router.get("/runs/{run_id}")
def run_detail(run_id: int, db: Session = Depends(get_db)):
    r = db.get(m.Run, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return run_out(r)


class ResolveIn(BaseModel):
    dismiss: bool = False
    po: str | None = None
    new_date: str | None = None
    type: str | None = Field(default=None, pattern="^(delay|partial)$")
    sku: str | None = None
    on_hand: int | None = Field(default=None, ge=0)


@router.post("/runs/{run_id}/resolve")
def resolve(run_id: int, body: ResolveIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    r = db.get(m.Run, run_id)
    if not r or r.world_id != W or r.status != "waiting_person" or r.trigger.get("type") != "email":
        raise HTTPException(400, "This run is not waiting for a planner check")
    if body.dismiss:
        Agent(db, W).resolve_check(run_id, None)
        return {"ok": True}
    if r.pending and "stock" in r.pending:
        if body.on_hand is None:
            raise HTTPException(400, "Enter the counted quantity")
        bg.add_task(agent_bg, "resolve_check", run_id, {"sku": body.sku or r.pending["stock"]["sku"], "on_hand": body.on_hand})
        return {"ok": True}
    if not body.po or not db.get(m.PurchaseOrder, (W, body.po)) or not body.new_date:
        raise HTTPException(400, "Pick an open PO and a new date")
    fields = {"po": body.po, "new_date": body.new_date, "type": body.type or "delay"}
    if fields["type"] != "partial":
        fields["split"] = None
    bg.add_task(agent_bg, "resolve_check", run_id, fields)
    return {"ok": True}


# ---------------- approvals and outbox ----------------
@router.get("/approvals")
def approvals(db: Session = Depends(get_db)):
    cs = {c.id: customer_dict(c) for c in db.query(m.Customer).filter(m.Customer.world_id == W)}
    return [approval_out(a, cs) for a in db.query(m.Approval).filter(m.Approval.world_id == W).order_by(m.Approval.id)]


class DecisionIn(BaseModel):
    subject: str | None = None
    body: str | None = None
    note: str | None = None


@router.post("/approvals/{approval_id}/send")
def send_approval(approval_id: int, body: DecisionIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        a = Agent(db, W).decide_approval(approval_id, True, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    bg.add_task(reply_bg, a.so, "notice", None)  # the customer reads it and answers
    return {"ok": True}


@router.post("/approvals/{approval_id}/reject")
def reject_approval(approval_id: int, db: Session = Depends(get_db)):
    try:
        Agent(db, W).decide_approval(approval_id, False)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@router.get("/outbox")
def outbox(db: Session = Depends(get_db)):
    return [{"id": o.id, "at": iso(o.at), "to": o.to, "so": o.so, "subject": o.subject, "body": o.body, "sent_by": o.sent_by} for o in db.query(m.OutboxMessage).filter(m.OutboxMessage.world_id == W).order_by(m.OutboxMessage.id.desc())]


@router.get("/log")
def activity(db: Session = Depends(get_db)):
    return [{"at": iso(l.at), "actor": l.actor, "system": l.system, "text": l.text} for l in db.query(m.ActivityLog).filter(m.ActivityLog.world_id == W).order_by(m.ActivityLog.id.desc()).limit(500)]


# ---------------- scenarios and test pack ----------------
def scenario_out(sc: dict, res: m.ScenarioResult | None, db: Session) -> dict:
    out = {"id": sc["id"], "title": sc["title"], "what": sc["what"], "expect": [e[0] for e in sc["expect"]],
           "input": sc.get("email") or sc.get("quote") or {"steps": sc.get("story", [])}, "kind": "email" if "email" in sc else "story" if "flow" in sc else "quote", "group": sc.get("group", "Supplier emails and quotes"), "result": None}
    if res:
        run = db.get(m.Run, res.run_id) if res.run_id else None
        out["result"] = {"passed": res.passed, "checks": res.checks, "mode": res.mode, "at": iso(res.at), "run": run_out(run) if run else None}
    return out


@router.get("/scenarios")
def scenarios(db: Session = Depends(get_db)):
    return [scenario_out(sc, db.get(m.ScenarioResult, sc["id"]), db) for sc in SCENARIOS]


@router.post("/scenarios/{scenario_id}/run")
def run_one(scenario_id: str, db: Session = Depends(get_db)):
    sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
    if not sc:
        raise HTTPException(404, "Unknown scenario")
    res = run_scenario(db, scenario_id, ai_mode=cfg(db).ai_mode)
    return scenario_out(sc, res, db)


def grade(case: tuple, got: dict) -> bool:
    _, _, kind, po, d = case
    ok_type = got.get("type") == kind
    ok_po = kind == "other" or (got.get("po") or None) == po
    ok_date = kind not in ("delay", "partial") or (got.get("new_date") or None) == d
    return ok_type and ok_po and ok_date


@router.get("/testpack")
def testpack(db: Session = Depends(get_db)):
    res = {r.mode: {"results": r.results, "at": iso(r.at)} for r in db.query(m.ReaderPackResult)}
    return {"cases": [{"id": c[0], "text": c[1], "type": c[2], "po": c[3], "date": c[4]} for c in TEST_PACK], "results": res}


@router.post("/testpack/run/{mode}")
def run_testpack(mode: str, db: Session = Depends(get_db)):
    if mode == "rules":
        out = []
        for c in TEST_PACK:
            g = rules_read(c[1], settings.today, {p.po: max(d["date"] for d in p.original) for p in db.query(m.PurchaseOrder).filter(m.PurchaseOrder.world_id == W)})
            out.append({"id": c[0], "type": g["type"], "po": g["po"], "date": g["new_date"], "pass": grade(c, g)})
    elif mode == "ai":
        llm = get_llm()
        if not llm.available:
            raise HTTPException(400, "AI is not configured. Set ANTHROPIC_API_KEY.")
        pos = [po_dict(p) for p in db.query(m.PurchaseOrder).filter(m.PurchaseOrder.world_id == W)]
        for p in pos:
            p["deliveries"] = p["original"]
        try:
            arr = parse_json(llm.complete(prompts.reader_pack(pos, TEST_PACK, settings.today), 2500))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"AI call failed: {e}") from e
        arr = arr if isinstance(arr, list) else []
        out = []
        for c in TEST_PACK:
            g = next((x for x in arr if isinstance(x, dict) and x.get("id") == c[0]), {})
            out.append({"id": c[0], "type": g.get("type") or "missing", "po": g.get("po"), "date": g.get("new_date"), "pass": grade(c, g)})
    else:
        raise HTTPException(404, "Mode must be ai or rules")
    row = db.get(m.ReaderPackResult, mode) or m.ReaderPackResult(mode=mode)
    row.results, row.at = out, utcnow()
    db.add(row)
    db.commit()
    return testpack(db)


# ---------------- chat ----------------
class ChatIn(BaseModel):
    messages: list[dict]


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    llm = get_llm()
    msgs = [{"role": x["role"], "content": str(x["content"])} for x in body.messages[-10:] if x.get("role") in ("user", "assistant") and x.get("content")]
    if not msgs or msgs[-1]["role"] != "user":
        raise HTTPException(400, "The last message must be from the user")
    if not llm.available or cfg(db).ai_mode != "auto":
        from .chat_rules import answer

        text, used = answer(msgs[-1]["content"], make_runner(db, W), settings.today)
        return {"reply": text, "tools": sorted(set(used)), "mode": "rules"}
    try:
        text, used = llm.chat(prompts.chat_system(settings.today, fmt_date(settings.today)), msgs, TOOLS, make_runner(db, W))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI call failed: {e}") from e
    return {"reply": text, "tools": sorted(set(used)), "mode": "ai"}


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    """Reference data for forms."""
    return {"today": settings.today, "next_week": add_days(settings.today, 7),
            "customers": [{"id": c.id, "name": c.name} for c in db.query(m.Customer).filter(m.Customer.world_id == W).order_by(m.Customer.name)],
            "items": [{"sku": i.sku, "name": i.name} for i in db.query(m.Item).filter(m.Item.world_id == W).order_by(m.Item.sku)],
            "pos": [p.po for p in db.query(m.PurchaseOrder).filter(m.PurchaseOrder.world_id == W).order_by(m.PurchaseOrder.po)]}
