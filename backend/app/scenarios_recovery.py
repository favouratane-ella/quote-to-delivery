"""Recovery scenarios: what happens after the customer is told.

Each one plays a whole story in its own throwaway world: a supplier slips, the customer is told,
the customer answers, and the agent rescues the order, agrees a new date, or escalates. The
checks look at the data afterwards, not at the wording.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import models as m
from .agent import Agent
from .seed import EMAILS, SUPPLIERS, TEMPLATES


def _email(db: Session, w: str, agent: Agent, sender: str, subject: str, body: str, attachment=None) -> m.Run:
    e = m.Email(world_id=w, sender=sender, address=SUPPLIERS.get(sender, "supplier@example.com"), received_at="2026-10-26T09:00", subject=subject, body=body, attachment=attachment)
    db.add(e)
    db.commit()
    return agent.run_email(e.id)


def seed_run(db, w, agent, subject: str) -> m.Run:
    e = next(x for x in EMAILS if x["subject"] == subject)
    return _email(db, w, agent, e["sender"], e["subject"], e["body"], e.get("attachment"))


def template_run(db, w, agent, key: str) -> m.Run:
    _, sender, subject, body = TEMPLATES[key]
    return _email(db, w, agent, sender, subject, body)


def approve_all(db, w, agent, run: m.Run) -> None:
    for a in db.query(m.Approval).filter(m.Approval.world_id == w, m.Approval.run_id == run.id, m.Approval.status.in_(["Needs approval", "Ready"])).order_by(m.Approval.rank):
        agent.decide_approval(a.id, True)


def reply(agent: Agent, so: str, text: str | None = None, stage: str = "notice", prop: int | None = None) -> m.Run | None:
    r = agent.make_reply(so, stage, agent.db.get(m.Proposal, prop) if prop else None, text=text, source="typed" if text else "simulated")
    return agent.run_reply(r.id) if r else None


def proposal(db, w, so: str, kind: str | None = None) -> m.Proposal | None:
    q = db.query(m.Proposal).filter(m.Proposal.world_id == w, m.Proposal.so == so)
    if kind:
        q = q.filter(m.Proposal.kind == kind)
    return q.order_by(m.Proposal.id.desc()).first()


def order(db, w, so: str) -> m.SalesOrder:
    return db.get(m.SalesOrder, (w, so))


def case(db, w, so: str) -> m.OrderCase | None:
    return db.query(m.OrderCase).filter(m.OrderCase.world_id == w, m.OrderCase.so == so).order_by(m.OrderCase.id.desc()).first()


def msgs(db, w) -> int:
    return db.query(m.OutboxMessage).filter(m.OutboxMessage.world_id == w).count()


# ---------------- the stories ----------------
def f_accept(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8841 delayed, new ship date"))
    return reply(agent, "SO-5561")


def f_split(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8841 delayed, new ship date"))
    reply(agent, "SO-5532")
    p = proposal(db, w, "SO-5532", "split")
    agent.decide_proposal(p.id, True)
    return reply(agent, "SO-5532", stage="offer", prop=p.id)


def f_substitute(db, w, agent):
    approve_all(db, w, agent, template_run(db, w, agent, "big"))
    reply(agent, "SO-5575")
    p = proposal(db, w, "SO-5575", "substitute")
    agent.decide_proposal(p.id, True)
    return reply(agent, "SO-5575", stage="offer", prop=p.id)


def f_hard_escalate(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8880 delayed, new ship date"))
    return reply(agent, "SO-5601")


def f_credit(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8841 delayed, new ship date"))
    return reply(agent, "SO-5547")


def f_cancel(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "Re: PO-8863"))
    return reply(agent, "SO-5552")


def f_question(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8841 delayed, new ship date"))
    return reply(agent, "SO-5561", text="Hi, can you tell me which warehouse this ships from, and whether our other orders are affected?")


def f_silent(db, w, agent):
    run = template_run(db, w, agent, "relative")
    approve_all(db, w, agent, run)
    agent.sim_followup("SO-5538")
    return run


def f_unclear(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8841 delayed, new ship date"))
    run = reply(agent, "SO-5561", text="Sent from my phone")
    rep = db.query(m.CustomerReply).filter(m.CustomerReply.world_id == w).order_by(m.CustomerReply.id.desc()).first()
    agent.resolve_reply(rep.id, "accept")
    db.refresh(run)
    return run


def f_expedite(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8880 delayed, new ship date"))
    reply(agent, "SO-5606")
    p = proposal(db, w, "SO-5606", "expedite")
    agent.decide_proposal(p.id, True)
    return db.get(m.Run, p.run_id)


def f_supplier_recovers(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8841 delayed, new ship date"))
    return _email(db, w, agent, "Lakeside Plastics", "PO-8841 back on track", "Good news: we caught up. PO-8841 will now arrive on 2 November after all, not 7 November.")


def f_double_booking(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8841 delayed, new ship date"))
    reply(agent, "SO-5532")  # Northwind's split proposal holds the free crates
    return reply(agent, "SO-5547", text="We cannot accept this. We need all 100 crates by 5 Nov at the latest.")


def f_hard_rescued(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8841 delayed, new ship date"))
    # a correction pushes PO-8841 two days further, so Kestrel (hard deadline, 10 crates) is now one day late
    run = _email(db, w, agent, "Lakeside Plastics", "Correction: PO-8841", "Hi,\n\nPO-8841 now arriving 9 Nov. Ignore our earlier note that said 7 Nov.\n\nMarta")
    approve_all(db, w, agent, run)
    return reply(agent, "SO-5570")


# ---------------- inventory stories ----------------
def f_stock_damage(db, w, agent):
    return seed_run(db, w, agent, "Cycle count variance: DI-55")


def f_stock_variance(db, w, agent):
    return seed_run(db, w, agent, "Recount: TS-88")


def f_reorder(db, w, agent):
    run = agent.run_inventory_scan()
    p = db.query(m.Proposal).filter_by(world_id=w, kind="raise_po").first()
    agent.decide_proposal(p.id, True)
    return run


def f_replan_late(db, w, agent):
    approve_all(db, w, agent, seed_run(db, w, agent, "PO-8886 delayed"))
    run = _email(db, w, agent, "Warehouse team", "Cycle count: DI-55", "Cycle count on DI-55: 40 bags were damaged and written off. Counted on hand is now 160 bags.")
    p = proposal(db, w, "SO-5624", "resupply")
    agent.decide_proposal(p.id, True)
    return run


def item(db, w, sku: str) -> m.Item:
    return db.get(m.Item, (w, sku))


SC_RECOVERY: list[dict] = [
    {"id": "SC15", "title": "Customer accepts the new date", "what": "Delta Catering is told its crates are two days late and replies that the new date works.",
     "story": ["PO-8841 slips to 7 Nov", "Delta is told", "Delta: \"Sun 8 Nov works for us\""], "flow": f_accept, "group": "Recovery",
     "expect": [("The reply is read as an acceptance", lambda db, w, r: db.query(m.CustomerReply).filter_by(world_id=w).order_by(m.CustomerReply.id.desc()).first().intent == "accept"),
                ("The promised date moves to Sun 8 Nov", lambda db, w, r: order(db, w, "SO-5561").promised == "2026-11-08"),
                ("The case closes as agreed, order back to low risk", lambda db, w, r: case(db, w, "SO-5561").status == "resolved" and case(db, w, "SO-5561").resolution == "agreed"),
                ("No customer message is sent by the agent", lambda db, w, r: msgs(db, w) == 3),
                ("The original date is kept on record", lambda db, w, r: order(db, w, "SO-5561").original_promised == "2026-11-06")]},
    {"id": "SC16", "title": "Customer takes a part delivery", "what": "Northwind cannot get all 160 crates by the promised date. It asks for what is in stock now, then agrees to the offer.",
     "story": ["PO-8841 slips to 7 Nov", "Northwind: \"send what you have now\"", "Agent offers 120 now, 40 on 9 Nov", "Manager approves", "Northwind says yes"], "flow": f_split, "group": "Recovery",
     "expect": [("Offer needs the ops manager (large order)", lambda db, w, r: proposal(db, w, "SO-5532", "split").needs == "Ops manager"),
                ("The order is split: 120 crates ship from stock", lambda db, w, r: order(db, w, "SO-5532").qty == 120 and order(db, w, "SO-5532").stock_qty == 120),
                ("The other 40 become a new line on Mon 9 Nov", lambda db, w, r: order(db, w, "SO-5532-B").qty == 40 and order(db, w, "SO-5532-B").promised == "2026-11-09" and order(db, w, "SO-5532-B").po == "PO-8841"),
                ("Value is shared between the two lines", lambda db, w, r: abs(order(db, w, "SO-5532").value + order(db, w, "SO-5532-B").value - 48200) < 1),
                ("The case closes as a split", lambda db, w, r: case(db, w, "SO-5532").resolution == "split")]},
    {"id": "SC17", "title": "Hard deadline rescued with a substitute item", "what": "Meridian Pharma cannot accept any delay. 300 of its 600 sensor tags are in stock; the rest can ship as the long-life tag, if Meridian agrees.",
     "story": ["PO-8850 slips to 5 Nov", "Meridian: \"we cannot accept, need all 600 by 2 Nov\"", "Agent finds: 300 TS-88 + 300 TS-90 from stock", "Manager approves the offer", "Meridian says yes"], "flow": f_substitute, "group": "Recovery",
     "expect": [("Proposes the substitute (keeps the date)", lambda db, w, r: proposal(db, w, "SO-5575", "substitute").meets_promised is True),
                ("It is an offer first: Meridian must agree", lambda db, w, r: proposal(db, w, "SO-5575", "substitute").needs_customer_ok is True),
                ("Original line keeps 300 TS-88 from stock", lambda db, w, r: order(db, w, "SO-5575").qty == 300 and order(db, w, "SO-5575").sku == "TS-88" and order(db, w, "SO-5575").stock_qty == 300),
                ("New line has 300 TS-90 from stock, same date", lambda db, w, r: order(db, w, "SO-5575-B").sku == "TS-90" and order(db, w, "SO-5575-B").promised == "2026-11-02"),
                ("Back to low risk", lambda db, w, r: case(db, w, "SO-5575").status == "resolved")]},
    {"id": "SC18", "title": "Hard deadline with no way out is escalated", "what": "Atlas Labs needs 150 data loggers by 12 Nov. The supplier now ships 18 Nov and only 60 are in stock. Nothing keeps the date.",
     "story": ["PO-8880 slips to 18 Nov", "Atlas: \"cannot accept, locked to 12 Nov\"", "No stock, reallocation, express or substitute keeps the date", "Escalated to the ops manager with fallbacks"], "flow": f_hard_escalate, "group": "Recovery",
     "expect": [("Reads the reply as a hard deadline", lambda db, w, r: db.query(m.CustomerReply).filter_by(world_id=w).first().intent == "hard_deadline"),
                ("Escalates to the ops manager", lambda db, w, r: proposal(db, w, "SO-5601").kind == "escalate" and proposal(db, w, "SO-5601").needs == "Ops manager"),
                ("Lists fallbacks for the manager", lambda db, w, r: len(proposal(db, w, "SO-5601").detail.get("fallbacks", [])) >= 2),
                ("Case is escalated, not closed", lambda db, w, r: case(db, w, "SO-5601").status == "escalated"),
                ("Does not touch the order", lambda db, w, r: order(db, w, "SO-5601").qty == 150 and order(db, w, "SO-5601").po == "PO-8880" and order(db, w, "SO-5601").stock_qty == 0)]},
    {"id": "SC19", "title": "Customer accepts the date but wants a credit", "what": "Harbor Grocers can live with 10 Nov but expects compensation for the second delay this quarter.",
     "story": ["PO-8841 slips to 7 Nov", "Harbor: \"we can live with 10 Nov, but we expect a credit\""], "flow": f_credit, "group": "Recovery",
     "expect": [("The new date is agreed and written in", lambda db, w, r: order(db, w, "SO-5547").promised == "2026-11-10"),
                ("A 10% credit is proposed ($3,190)", lambda db, w, r: proposal(db, w, "SO-5547", "credit").cost == 3190.0),
                ("The ops manager must approve the credit", lambda db, w, r: proposal(db, w, "SO-5547", "credit").needs == "Ops manager"),
                ("The credit is not given until approved", lambda db, w, r: proposal(db, w, "SO-5547", "credit").status == "Proposed")]},
    {"id": "SC20", "title": "Customer wants to cancel", "what": "Juno Bakery says the delay is too late and asks to cancel its order.",
     "story": ["PO-8863 slips to 20 Nov", "Juno: \"please cancel\""], "flow": f_cancel, "group": "Recovery",
     "expect": [("Reads the reply as a cancellation", lambda db, w, r: db.query(m.CustomerReply).filter_by(world_id=w).first().intent == "cancel"),
                ("Escalates a retention call to the ops manager", lambda db, w, r: proposal(db, w, "SO-5552", "escalate").needs == "Ops manager"),
                ("The agent never cancels an order itself", lambda db, w, r: order(db, w, "SO-5552") is not None and order(db, w, "SO-5552").qty == 400),
                ("Case is escalated", lambda db, w, r: case(db, w, "SO-5552").status == "escalated")]},
    {"id": "SC21", "title": "Customer asks a question", "what": "Delta asks which warehouse the order ships from and whether other orders are affected.",
     "story": ["PO-8841 slips to 7 Nov", "Delta asks a question"], "flow": f_question, "group": "Recovery",
     "expect": [("Reads the reply as a question", lambda db, w, r: db.query(m.CustomerReply).filter_by(world_id=w).first().intent == "question"),
                ("Drafts an answer for the account manager", lambda db, w, r: proposal(db, w, "SO-5561", "reply").needs == "Account manager"),
                ("The answer uses account data", lambda db, w, r: "main warehouse" in proposal(db, w, "SO-5561", "reply").body),
                ("Nothing is sent or changed yet", lambda db, w, r: msgs(db, w) == 3 and order(db, w, "SO-5561").promised == "2026-11-06")]},
    {"id": "SC22", "title": "Customer never replies", "what": "Fernhill Foods is told its gel packs are late and says nothing.",
     "story": ["PO-8860 slips a week", "Fernhill is told", "No reply"], "flow": f_silent, "group": "Recovery",
     "expect": [("No reply arrives", lambda db, w, r: db.query(m.CustomerReply).filter_by(world_id=w).count() == 0),
                ("The case stays open, waiting for the customer", lambda db, w, r: case(db, w, "SO-5538").status == "notified"),
                ("The order is left alone", lambda db, w, r: order(db, w, "SO-5538").promised == "2026-11-09")]},
    {"id": "SC23", "title": "Reply the agent cannot read", "what": "A customer replies \"Sent from my phone\". The agent must not guess.",
     "story": ["PO-8841 slips to 7 Nov", "Delta replies with no content", "A person reads it and picks \"accepts\""], "flow": f_unclear, "group": "Recovery",
     "expect": [("The agent stopped and asked a person", lambda db, w, r: any(s.kind == "wait" or (s.kind == "guard" and "person" in s.title) for s in r.steps)),
                ("Nothing changed until the person decided", lambda db, w, r: any(s.kind == "person" for s in r.steps)),
                ("After the person chose, the date was agreed", lambda db, w, r: order(db, w, "SO-5561").promised == "2026-11-08" and case(db, w, "SO-5561").status == "resolved")]},
    {"id": "SC24", "title": "Customer asks for faster shipping", "what": "Fjord Logistics will pay for express shipping to get 120 loggers closer to its date.",
     "story": ["PO-8880 slips to 18 Nov", "Fjord: \"can you expedite? we will pay\"", "Agent costs express on the National lane", "Manager approves"], "flow": f_expedite, "group": "Recovery",
     "expect": [("Proposes express shipping with its cost", lambda db, w, r: proposal(db, w, "SO-5606", "expedite").cost == 850.0),
                ("Ops manager approves (cost over $500)", lambda db, w, r: proposal(db, w, "SO-5606", "expedite").needs == "Ops manager"),
                ("The order is switched to express", lambda db, w, r: order(db, w, "SO-5606").expedite is True),
                ("The customer is told", lambda db, w, r: any(x.so == "SO-5606" and "express" in x.subject.lower() for x in db.query(m.OutboxMessage).filter_by(world_id=w)))]},
    {"id": "SC25", "title": "Supplier recovers: cases close by themselves", "what": "After customers are told, the supplier catches up and the original date holds.",
     "story": ["PO-8841 slips to 7 Nov", "Customers are told", "Supplier: \"back on track for 2 Nov\""], "flow": f_supplier_recovers, "group": "Recovery",
     "expect": [("PO-8841 is back to Mon 2 Nov", lambda db, w, r: max(d["date"] for d in db.get(m.PurchaseOrder, (w, "PO-8841")).deliveries) == "2026-11-02"),
                ("All three cases close as supply recovered", lambda db, w, r: all(case(db, w, so).resolution == "supply_recovered" for so in ("SO-5532", "SO-5547", "SO-5561"))),
                ("No order is late any more", lambda db, w, r: not any(x for x in db.query(m.OrderCase).filter(m.OrderCase.world_id == w, m.OrderCase.status != "resolved")))]},
    {"id": "SC26", "title": "Two customers want the same stock", "what": "Northwind's part-delivery offer already holds the 120 free crates. Harbor then demands its date. The agent must not promise the same stock twice.",
     "story": ["PO-8841 slips to 7 Nov", "Northwind: part delivery (holds 120 crates)", "Harbor: \"need all 100 by 5 Nov\"", "No free stock is left to promise"], "flow": f_double_booking, "group": "Recovery",
     "expect": [("Northwind's offer holds the crates", lambda db, w, r: proposal(db, w, "SO-5532", "split").status == "Proposed"),
                ("Harbor is not promised the same stock", lambda db, w, r: all(p.kind != "stock" for p in db.query(m.Proposal).filter_by(world_id=w, so="SO-5547"))),
                ("Harbor is escalated instead", lambda db, w, r: proposal(db, w, "SO-5547").kind == "escalate")]},
    {"id": "SC27", "title": "Hard-deadline customer rescued from stock", "what": "Kestrel Hotels (opening weekend) is one day late on 10 crates. Free stock can cover it, so the date is kept.",
     "story": ["PO-8841 slips to 9 Nov", "Kestrel is told", "Kestrel: \"cannot accept\"", "Agent ships 10 crates from stock"], "flow": f_hard_rescued, "group": "Recovery",
     "expect": [("Proposes shipping from stock", lambda db, w, r: proposal(db, w, "SO-5570", "stock").meets_promised is True),
                ("No customer agreement needed", lambda db, w, r: proposal(db, w, "SO-5570", "stock").needs_customer_ok is False),
                ("One check by the account manager", lambda db, w, r: proposal(db, w, "SO-5570", "stock").needs == "Account manager"),
                ("Approving it moves the crates and closes the case", lambda db, w, r: (Agent(db, w, delay_ms=0).decide_proposal(proposal(db, w, "SO-5570", "stock").id, True) is not None)
                 and order(db, w, "SO-5570").stock_qty == 10 and order(db, w, "SO-5570").po is None and case(db, w, "SO-5570").resolution == "recovered")]},
    {"id": "SC28", "title": "Stock count finds damaged goods", "what": "The warehouse reports 40 of 200 bags of dry ice damaged. Dunmore Pharmacy had all 200 reserved from stock.",
     "story": ["Warehouse: \"40 bags damaged, on hand is now 160\"", "Agent updates stock", "Dunmore is 40 short", "Covers them from the next inbound PO"], "flow": f_stock_damage, "group": "Inventory",
     "expect": [("Stock on hand is updated to 160", lambda db, w, r: item(db, w, "DI-55").on_hand == 160),
                ("Finds Dunmore's order short by 40", lambda db, w, r: proposal(db, w, "SO-5624", "resupply").detail["units"] == 40),
                ("Proposes covering it from PO-8886, date kept", lambda db, w, r: proposal(db, w, "SO-5624", "resupply").detail["po"] == "PO-8886" and proposal(db, w, "SO-5624", "resupply").meets_promised is True),
                ("The planner approves, nothing moves before that", lambda db, w, r: order(db, w, "SO-5624").po is None),
                ("Approving moves 40 bags to the PO and the customer is not bothered", lambda db, w, r: (Agent(db, w, delay_ms=0).decide_proposal(proposal(db, w, "SO-5624", "resupply").id, True) is not None)
                 and order(db, w, "SO-5624").po == "PO-8886" and order(db, w, "SO-5624").po_qty == 40 and order(db, w, "SO-5624").stock_qty == 160
                 and db.query(m.Approval).filter_by(world_id=w, so="SO-5624").count() == 0)]},
    {"id": "SC29", "title": "A stock count that looks wrong is not trusted", "what": "The warehouse says only 30 of 300 sensor tags are on the shelf, a 90% drop. Could be a typo, could be real.",
     "story": ["Warehouse: \"only 30 on the shelf\"", "Agent sees a 90% change", "Stops and asks the planner"], "flow": f_stock_variance, "group": "Inventory",
     "expect": [("Stops and asks a person", lambda db, w, r: r.status == "waiting_person"),
                ("Stock is not changed", lambda db, w, r: item(db, w, "TS-88").on_hand == 300),
                ("Explains the change is too big", lambda db, w, r: any("check the count" in c["label"] for s in r.steps for c in (s.payload or {}).get("checks", [])))]},
    {"id": "SC30", "title": "Reorder point reached", "what": "Dry ice has no free stock and only 300 bags inbound that are not promised, at the reorder point of 300.",
     "story": ["Inventory check runs", "DI-55 is at its reorder point", "Agent proposes a purchase order", "Planner approves, the supplier is emailed"], "flow": f_reorder, "group": "Inventory",
     "expect": [("Only DI-55 needs ordering", lambda db, w, r: [p.detail["sku"] for p in db.query(m.Proposal).filter_by(world_id=w, kind="raise_po")] == ["DI-55"]),
                ("Proposes 800 bags from Frostline Supplies", lambda db, w, r: db.query(m.Proposal).filter_by(world_id=w, kind="raise_po").first().detail["qty"] == 800
                 and db.query(m.Proposal).filter_by(world_id=w, kind="raise_po").first().detail["supplier"] == "Frostline Supplies"),
                ("After approval the PO exists in the ERP", lambda db, w, r: db.get(m.PurchaseOrder, (w, "PO-8895")) is not None and db.get(m.PurchaseOrder, (w, "PO-8895")).deliveries[0]["qty"] == 800),
                ("The supplier is emailed, not a customer", lambda db, w, r: any(x.kind == "supplier" and "DI-55" in x.subject for x in db.query(m.OutboxMessage).filter_by(world_id=w)))]},
    {"id": "SC31", "title": "A stock count makes an order late", "what": "The dry ice PO has already slipped to 8 Nov. Then 40 bags are found damaged. Covering Dunmore from that PO makes it late.",
     "story": ["PO-8886 slips to 8 Nov", "Warehouse: 40 bags damaged", "Covering Dunmore means 3 days late", "Planner approves, a customer update is drafted"], "flow": f_replan_late, "group": "Inventory",
     "expect": [("The replan says Dunmore would be 3 days late", lambda db, w, r: proposal(db, w, "SO-5624", "resupply").detail["days_late"] == 3),
                ("It does not keep the date", lambda db, w, r: proposal(db, w, "SO-5624", "resupply").meets_promised is False),
                ("Approving drafts a customer update for approval", lambda db, w, r: db.query(m.Approval).filter_by(world_id=w, so="SO-5624").count() == 1),
                ("A case is opened for the order", lambda db, w, r: case(db, w, "SO-5624") is not None and case(db, w, "SO-5624").status == "at_risk")]},
]
