"""Read-only tools the chat agent can call. None of them change data."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import models as m
from .config import settings
from .connectors.simulated import SimulatedSystems
from .engine import Engine, add_days

TOOLS = [
    {"name": "list_orders", "description": "All open sales orders with customer, item, qty, value, promised date, current arrival estimate and days late.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_purchase_orders", "description": "Purchase orders with supplier, item, qty, current and original arrival.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_customer", "description": "A customer from the CRM by name: tier, yearly value, renewal, contact, owner, lane and recent notes.", "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "check_quote", "description": "Whether qty of a SKU can reach a customer by a date (YYYY-MM-DD), using free stock, inbound POs and transit. Returns feasibility, earliest date and a split option.",
     "input_schema": {"type": "object", "properties": {"customer": {"type": "string"}, "sku": {"type": "string"}, "qty": {"type": "number"}, "requested": {"type": "string"}}, "required": ["customer", "sku", "qty", "requested"]}},
    {"name": "simulate_po_delay", "description": "What-if only, changes nothing: shift a PO arrival by N days and return which orders would become late, with priority scores.",
     "input_schema": {"type": "object", "properties": {"po": {"type": "string"}, "days": {"type": "number"}}, "required": ["po", "days"]}},
    {"name": "waiting_for_people", "description": "Items waiting for a person: planner checks, quote decisions and customer updates awaiting approval.", "input_schema": {"type": "object", "properties": {}}},
]


def make_runner(db: Session, world_id: str = "main"):
    sysm = SimulatedSystems(db, world_id)

    def en() -> Engine:
        return Engine(sysm.snapshot(settings.today))

    def find_customer(e: Engine, name: str) -> dict:
        n = str(name or "").lower()
        for c in e.s.customers.values():
            if c["id"] == n or n in c["name"].lower():
                return c
        raise ValueError(f"No customer matches {name}")

    def run(name: str, args: dict):
        e = en()
        if name == "list_orders":
            return [{k: v for k, v in e.order_view(o).items() if k in ("so", "customer", "sku", "qty", "value", "promised", "eta", "days_late", "po")} for o in e.s.orders]
        if name == "list_purchase_orders":
            return [{"po": p["po"], "supplier": p["supplier"], "sku": p["sku"], "arrival_now": p["deliveries"], "arrival_original": p["original"]} for p in e.s.pos.values()]
        if name == "get_customer":
            c = find_customer(e, args.get("name"))
            notes = [n.text for n in db.query(m.CrmNote).filter(m.CrmNote.world_id == world_id, m.CrmNote.customer_id == c["id"]).order_by(m.CrmNote.id.desc()).limit(5)]
            return {**c, "notes": notes}
        if name == "check_quote":
            c = find_customer(e, args.get("customer"))
            sku = str(args.get("sku", "")).upper()
            if sku not in e.s.items:
                raise ValueError("Unknown SKU. Known: " + ", ".join(e.s.items))
            r = e.check_quote(c["id"], sku, int(args.get("qty", 0)), str(args.get("requested")))
            return {k: r[k] for k in ("feasible", "eta", "shortfall", "split", "transit_days", "steps")}
        if name == "simulate_po_delay":
            po = str(args.get("po", "")).upper()
            if po not in e.s.pos:
                raise ValueError("Unknown PO")
            before = e.s.pos[po]["deliveries"]
            after = [{"qty": d["qty"], "date": add_days(d["date"], int(args.get("days", 0)))} for d in before]
            r = e.impact_of(po, before, after)
            return {"new_arrival": after, "would_be_late": [{"so": a["so"], "customer": e.s.customers[a["customer_id"]]["name"], "value": a["value"], "promised": a["promised"],
                                                            "new_arrival": a["after"], "days_late": a["days_late"], "priority": a["risk"]["score"]} for a in r["affected"]],
                    "still_on_time": [f["so"] for f in r["fine"]]}
        if name == "waiting_for_people":
            runs = db.query(m.Run).filter(m.Run.world_id == world_id, m.Run.status == "waiting_person").all()
            aps = db.query(m.Approval).filter(m.Approval.world_id == world_id, m.Approval.status.in_(["Needs approval", "Ready"])).all()
            return {"waiting_runs": [r.title for r in runs], "approvals": [{"so": a.so, "customer": e.s.customers[a.customer_id]["name"], "value": a.value, "status": a.status} for a in aps]}
        raise ValueError(f"Unknown tool {name}")

    return run
