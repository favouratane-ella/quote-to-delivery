"""Simulated ERP, CRM, supply inbox and customer outbox, stored in the app database."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models as m
from ..engine import Snapshot
from .base import CRMConnector, ERPConnector, MailboxConnector, OutboxConnector


def po_dict(p: m.PurchaseOrder) -> dict:
    return {"po": p.po, "supplier": p.supplier, "sku": p.sku, "deliveries": list(p.deliveries), "original": list(p.original)}


def customer_dict(c: m.Customer) -> dict:
    return {"id": c.id, "name": c.name, "tier": c.tier, "arr": c.arr, "renewal": c.renewal, "contact": c.contact, "email": c.email, "lane": c.lane, "owner": c.owner,
            "flex": c.flex, "max_slip": c.max_slip, "hard_reason": c.hard_reason, "reply_style": c.reply_style}


def order_dict(o: m.SalesOrder) -> dict:
    return {"so": o.so, "customer_id": o.customer_id, "sku": o.sku, "qty": o.qty, "value": o.value, "promised": o.promised, "stock_qty": o.stock_qty, "po": o.po, "po_qty": o.po_qty,
            "expedite": bool(o.expedite), "parent": o.parent, "original_promised": o.original_promised, "note": o.note or ""}


def email_dict(e: m.Email) -> dict:
    return {"id": e.id, "sender": e.sender, "address": e.address, "received_at": e.received_at, "subject": e.subject, "body": e.body, "attachment": e.attachment, "status": e.status, "run_id": e.run_id}


def quote_dict(q: m.Quote) -> dict:
    return {"q": q.q, "customer_id": q.customer_id, "sku": q.sku, "qty": q.qty, "requested": q.requested, "status": q.status, "run_id": q.run_id, "final": q.final}


class SimulatedSystems(ERPConnector, CRMConnector, MailboxConnector, OutboxConnector):
    def __init__(self, db: Session, world_id: str):
        self.db, self.w = db, world_id

    # ERP
    def snapshot(self, today: str) -> Snapshot:
        q = lambda t: self.db.query(t).filter(t.world_id == self.w)  # noqa: E731
        return Snapshot(
            today=today,
            items={i.sku: {"sku": i.sku, "name": i.name, "on_hand": i.on_hand, "unit": i.unit, "reorder_point": i.reorder_point, "reorder_qty": i.reorder_qty, "substitute": i.substitute} for i in q(m.Item)},
            pos={p.po: po_dict(p) for p in q(m.PurchaseOrder)},
            customers={c.id: customer_dict(c) for c in q(m.Customer)},
            lanes={l.name: l.days for l in q(m.Lane)},
            express={l.name: (l.express_saves, l.express_cost) for l in q(m.Lane)},
            orders=[order_dict(o) for o in q(m.SalesOrder).order_by(m.SalesOrder.so)],
        )

    def get_po(self, po: str) -> dict | None:
        p = self.db.get(m.PurchaseOrder, (self.w, po))
        return po_dict(p) if p else None

    def list_pos(self) -> list[dict]:
        return [po_dict(p) for p in self.db.query(m.PurchaseOrder).filter(m.PurchaseOrder.world_id == self.w).order_by(m.PurchaseOrder.po)]

    def get_order(self, so: str) -> m.SalesOrder | None:
        return self.db.get(m.SalesOrder, (self.w, so))

    def update_order(self, so: str, **fields) -> None:
        o = self.db.get(m.SalesOrder, (self.w, so))
        for k, v in fields.items():
            setattr(o, k, v)
        self.db.commit()

    def add_order(self, **fields) -> m.SalesOrder:
        o = m.SalesOrder(world_id=self.w, **fields)
        self.db.add(o)
        self.db.commit()
        return o

    def update_po_deliveries(self, po: str, deliveries: list[dict]) -> None:
        p = self.db.get(m.PurchaseOrder, (self.w, po))
        p.deliveries = [dict(d) for d in deliveries]
        self.db.commit()

    # CRM
    def get_customer(self, customer_id: str) -> dict | None:
        c = self.db.get(m.Customer, (self.w, customer_id))
        return customer_dict(c) if c else None

    def add_note(self, customer_id: str, text: str) -> None:
        self.db.add(m.CrmNote(world_id=self.w, customer_id=customer_id, text=text))
        self.db.commit()

    def get_quote(self, q: str) -> dict | None:
        r = self.db.get(m.Quote, (self.w, q))
        return quote_dict(r) if r else None

    def update_quote(self, q: str, **fields) -> None:
        r = self.db.get(m.Quote, (self.w, q))
        for k, v in fields.items():
            setattr(r, k, v)
        self.db.commit()

    # Mailbox
    def get_email(self, email_id: int) -> dict | None:
        e = self.db.get(m.Email, email_id)
        return email_dict(e) if e and e.world_id == self.w else None

    def set_status(self, email_id: int, status: str, run_id: int | None = None) -> None:
        e = self.db.get(m.Email, email_id)
        e.status = status
        if run_id is not None:
            e.run_id = run_id
        self.db.commit()

    # Outbox
    def send(self, *, to: str, customer_id: str, so: str, subject: str, body: str, sent_by: str, kind: str = "customer") -> None:
        self.db.add(m.OutboxMessage(world_id=self.w, to=to, customer_id=customer_id, so=so, subject=subject, body=body, sent_by=sent_by, kind=kind))
        self.db.commit()
