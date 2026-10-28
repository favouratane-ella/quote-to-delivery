"""Tables.

Every row belongs to a *world*. "main" is the world people use; each test scenario
gets its own throwaway world, so tests never touch the main data.

Simulated systems: Item, PurchaseOrder, Customer, Lane, SalesOrder, Quote, Email,
OutboxMessage, CrmNote. Agent records: Run, RunStep, Approval, ActivityLog.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class World(Base):
    __tablename__ = "worlds"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="main")  # main | scenario
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Settings(Base):
    __tablename__ = "settings"
    world_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    auto_run: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_mode: Mapped[str] = mapped_column(String(8), default="auto")  # auto | rules
    approval_limit: Mapped[float] = mapped_column(Float, default=25000)
    pass_mark: Mapped[float] = mapped_column(Float, default=0.9)
    tone: Mapped[str] = mapped_column(String(40), default="Warm and clear")
    sim_customers: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")  # simulated customers reply by themselves


# ---------- Simulated ERP ----------
class Item(Base):
    __tablename__ = "items"
    world_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    on_hand: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(24))
    reorder_point: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reorder_qty: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    substitute: Mapped[str | None] = mapped_column(String(32), nullable=True)  # compatible SKU the customer could accept instead


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    world_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    po: Mapped[str] = mapped_column(String(32), primary_key=True)
    supplier: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str] = mapped_column(String(32))
    deliveries: Mapped[list] = mapped_column(JSON)  # [{"qty": 280, "date": "2026-11-02"}]
    original: Mapped[list] = mapped_column(JSON)


class SalesOrder(Base):
    __tablename__ = "sales_orders"
    world_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    so: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(40))
    sku: Mapped[str] = mapped_column(String(32))
    qty: Mapped[int] = mapped_column(Integer)
    value: Mapped[float] = mapped_column(Float)
    promised: Mapped[str] = mapped_column(String(10))
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)  # reserved from stock on hand
    po: Mapped[str | None] = mapped_column(String(32), nullable=True)  # waiting on this PO
    po_qty: Mapped[int] = mapped_column(Integer, default=0)
    original_promised: Mapped[str | None] = mapped_column(String(10), nullable=True)  # set when the date is renegotiated
    parent: Mapped[str | None] = mapped_column(String(32), nullable=True)  # the order this line was split from
    expedite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # shipping express
    note: Mapped[str] = mapped_column(Text, default="", server_default="")


class Supplier(Base):
    __tablename__ = "suppliers"
    world_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), primary_key=True)
    email: Mapped[str] = mapped_column(String(160))


class Lane(Base):
    __tablename__ = "lanes"
    world_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    days: Mapped[int] = mapped_column(Integer)
    express_saves: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # days saved by express shipping
    express_cost: Mapped[float] = mapped_column(Float, default=0, server_default="0")


# ---------- Simulated CRM ----------
class Customer(Base):
    __tablename__ = "customers"
    world_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tier: Mapped[str] = mapped_column(String(2))
    arr: Mapped[float] = mapped_column(Float)
    renewal: Mapped[str] = mapped_column(String(10))
    contact: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160))
    lane: Mapped[str] = mapped_column(String(32))
    owner: Mapped[str] = mapped_column(String(120))
    flex: Mapped[str] = mapped_column(String(12), default="flexible", server_default="flexible")  # hard | partial | flexible
    max_slip: Mapped[int] = mapped_column(Integer, default=14, server_default="14")  # days late the customer can live with
    hard_reason: Mapped[str] = mapped_column(String(240), default="", server_default="")
    reply_style: Mapped[str] = mapped_column(String(16), default="accept", server_default="accept")  # how the simulated customer answers


class Quote(Base):
    __tablename__ = "quotes"
    world_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    q: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(40))
    sku: Mapped[str] = mapped_column(String(32))
    qty: Mapped[int] = mapped_column(Integer)
    requested: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(160), default="Not checked")
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CrmNote(Base):
    __tablename__ = "crm_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    customer_id: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)


# ---------- Simulated mailboxes ----------
class Email(Base):
    __tablename__ = "emails"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    sender: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(160))
    received_at: Mapped[str] = mapped_column(String(19))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    attachment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="Not processed")
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OutboxMessage(Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    to: Mapped[str] = mapped_column(String(240))
    customer_id: Mapped[str] = mapped_column(String(40))
    so: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    sent_by: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(12), default="customer", server_default="customer")  # customer | supplier


# ---------- Agent records ----------
class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[dict] = mapped_column(JSON)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(24), default="running")
    mode: Mapped[str] = mapped_column(String(8), default="rules")  # ai | rules
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pending: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    steps: Mapped[list["RunStep"]] = relationship(back_populates="run", order_by="RunStep.seq", cascade="all, delete-orphan")


class RunStep(Base):
    __tablename__ = "run_steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))  # event read ai rules code guard write person wait done
    system: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # fields, checks, table, data
    at_seconds: Mapped[float] = mapped_column(Float, default=0)
    run: Mapped[Run] = relationship(back_populates="steps")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int] = mapped_column(Integer)
    so: Mapped[str] = mapped_column(String(32))
    customer_id: Mapped[str] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Float)
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    reader: Mapped[str] = mapped_column(String(8))  # ai | rules
    wording_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20))  # Needs approval | Ready | Sent | Rejected
    reason: Mapped[str] = mapped_column(String(240))
    rank: Mapped[int] = mapped_column(Integer)
    new_date: Mapped[str] = mapped_column(String(10))
    decided_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actor: Mapped[str] = mapped_column(String(60))
    system: Mapped[str] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(Text)


class ScenarioResult(Base):
    __tablename__ = "scenario_results"
    scenario_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(8))
    passed: Mapped[bool] = mapped_column(Boolean)
    checks: Mapped[list] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ReaderPackResult(Base):
    __tablename__ = "testpack_results"
    mode: Mapped[str] = mapped_column(String(8), primary_key=True)
    results: Mapped[list] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# ---------- Recovery: what happens after a customer is told ----------
class OrderCase(Base):
    """One case per order that was pushed past its promised date. It lives until the order is back to low risk."""
    __tablename__ = "order_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    so: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20), default="at_risk")  # at_risk notified offer_sent plan_proposed escalated resolved lost
    resolution: Mapped[str] = mapped_column(String(24), default="", server_default="")  # recovered agreed split credited supply_recovered lost
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(String(240), default="")
    original_promised: Mapped[str] = mapped_column(String(10))
    eta: Mapped[str | None] = mapped_column(String(10), nullable=True)
    days_late: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_proposal: Mapped[int | None] = mapped_column(Integer, nullable=True)  # an offer waiting for the customer to say yes
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CaseEvent(Base):
    __tablename__ = "case_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    so: Mapped[str] = mapped_column(String(32), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actor: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(12))  # system customer person
    text: Mapped[str] = mapped_column(Text)


class CustomerReply(Base):
    __tablename__ = "customer_replies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    so: Mapped[str] = mapped_column(String(32))
    customer_id: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(12), default="simulated")  # simulated | typed
    status: Mapped[str] = mapped_column(String(20), default="New")  # New | Handled | Needs a person
    intent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Proposal(Base):
    """A recovery action the agent recommends. Nothing changes until a person approves it."""
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    so: Mapped[str] = mapped_column(String(32), default="")
    customer_id: Mapped[str] = mapped_column(String(40), default="")
    kind: Mapped[str] = mapped_column(String(16))  # stock reallocate expedite substitute split new_date credit supplier escalate reply raise_po
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost: Mapped[float] = mapped_column(Float, default=0)
    value: Mapped[float] = mapped_column(Float, default=0)  # order value at stake
    meets_promised: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_customer_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    needs: Mapped[str] = mapped_column(String(24), default="Account manager")  # who must approve
    status: Mapped[str] = mapped_column(String(16), default="Proposed")  # Proposed Applied Offered Rejected
    to: Mapped[str] = mapped_column(String(240), default="")
    subject: Mapped[str] = mapped_column(String(240), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(String(240), default="")
    rank: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


WORLD_TABLES = [Settings, Item, PurchaseOrder, SalesOrder, Supplier, Lane, Customer, Quote, CrmNote, Email, OutboxMessage, Approval, ActivityLog,
                OrderCase, CaseEvent, CustomerReply, Proposal]
