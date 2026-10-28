from fastapi.testclient import TestClient

from app import models as m
from app.connectors.simulated import SimulatedSystems
from app.engine import Engine
from app.main import app
from app.recovery import options_for, risk_tier
from app.reply_reader import read_reply

# (text, intent, date or None)
REPLY_PACK = [
    ("Thanks for letting us know. Mon 9 Nov works for us, no problem.", "accept", None),
    ("Yes, that works for us. Please go ahead.", "accept", None),
    ("ok", "accept", None),
    ("Understood, thanks for the update.", "accept", None),
    ("We cannot accept Mon 9 Nov. We need all 10 crates by 11 Nov at the latest, this is not negotiable.", "hard_deadline", "2026-11-11"),
    ("This is not acceptable. The opening is on 4 Nov and we must have everything before then.", "hard_deadline", None),
    ("We can take part of the order now if you send what you have in stock, and the rest by 12 Nov.", "partial_ok", "2026-11-12"),
    ("We cannot wait for all of it. Please send what you have in stock now and the rest later.", "partial_ok", None),
    ("Can you expedite this? We will pay for express shipping.", "expedite", None),
    ("Could you rush it? Happy to pay for faster delivery.", "expedite", None),
    ("We can live with 10 Nov, but we expect a credit for the trouble.", "credit", None),
    ("This is the second delay. We want a discount on this order.", "credit", None),
    ("This is too late. Please cancel order SO-5552.", "cancel", None),
    ("We are cancelling the order and will go elsewhere.", "cancel", None),
    ("Which warehouse does it ship from? Does the delay affect our other items?", "question", None),
    ("The latest we can take is 12 Nov.", "reschedule", "2026-11-12"),
    ("Sent from my phone", "unclear", None),
    ("Out of office until Monday.", "unclear", None),
    ("> On Mon, Dana wrote:\n> we cannot accept this\n\nThanks, that works for us.", "accept", None),
]


def test_reply_reader_pack():
    bad = []
    for text, intent, d in REPLY_PACK:
        g = read_reply(text, "2026-10-26", {"promised": "2026-11-04"})
        if g["intent"] != intent or (d and g["date"] != d):
            bad.append((text[:40], g["intent"], g["date"]))
    assert bad == []


def test_reply_reader_flags_contradictions():
    g = read_reply("Fine, that works for us, but we cannot accept this.", "2026-10-26")
    assert g["confidence"] < 0.9 or g["intent"] == "hard_deadline"
    assert read_reply("We can live with 10 Nov, but we expect a credit.", "2026-10-26")["flags"]["accepts"] is True


def _engine(db, po="PO-8841", date="2026-11-07"):
    s = SimulatedSystems(db, "main")
    total = sum(d["qty"] for d in s.get_po(po)["deliveries"])
    s.update_po_deliveries(po, [{"qty": total, "date": date}])
    return Engine(s.snapshot("2026-10-26"))


def test_options_engine_picks_by_customer_type(db):
    e = _engine(db)
    # Harbor (partial) and Delta (flexible): the 120 free crates cover them completely
    assert options_for(e, "SO-5561")["recommended"] == "stock"
    assert options_for(e, "SO-5547")["recommended"] == "stock"
    # Northwind needs 160 and only 120 are free: a part delivery is the answer
    nw = options_for(e, "SO-5532")
    assert nw["recommended"] == "split" and not nw["escalate"]
    assert next(o for o in nw["options"] if o["kind"] == "split")["detail"] == {"now": 120, "now_eta": "2026-10-28", "rest": 40, "rest_eta": "2026-11-09", "acceptable": True}
    # an order that is not late has nothing to recover
    assert options_for(e, "SO-5570")["late"] is False


def test_hard_deadline_needs_a_fix_that_keeps_the_date(db):
    e = _engine(db, "PO-8850", "2026-11-05")
    r = options_for(e, "SO-5575")  # Meridian, hard deadline
    assert r["recommended"] == "substitute" and r["options"][0]["meets_promised"] and r["options"][0]["needs_customer_ok"]
    e = _engine(db, "PO-8880", "2026-11-18")
    r = options_for(e, "SO-5601")  # Atlas, hard deadline, nothing helps
    assert r["escalate"] is True and not any(o["meets_promised"] for o in r["options"])


def test_risk_tiers(db):
    e = _engine(db)
    cust = e.s.customers
    v = e.order_view(next(o for o in e.s.orders if o["so"] == "SO-5532"))
    assert risk_tier(v, cust["northwind"])["tier"] == "Medium"  # 5 days late, Northwind can live with 5
    assert risk_tier(v, cust["northwind"], {"status": "resolved", "resolution": "split"})["tier"] == "Low"
    assert risk_tier(v, {**cust["northwind"], "flex": "hard", "max_slip": 0})["tier"] == "Critical"
    ok = e.order_view(next(o for o in e.s.orders if o["so"] == "SO-5601"))
    assert risk_tier(ok, cust["atlas"])["tier"] == "Watch"  # on time with no day to spare


def test_flow_through_the_api():
    c = TestClient(app)
    c.__enter__()
    c.post("/api/world/reset")
    e = next(x for x in c.get("/api/mailbox").json() if x["subject"].startswith("PO-8841"))
    c.post(f"/api/mailbox/{e['id']}/process")
    approvals = c.get("/api/approvals").json()
    assert len(approvals) == 3
    for a in approvals:
        assert c.post(f"/api/approvals/{a['id']}/send", json={}).status_code == 200  # simulated customers answer straight away in tests
    replies = {r["so"]: r for r in c.get("/api/replies").json()}
    assert {k: v["intent"] for k, v in replies.items()} == {"SO-5532": "partial_ok", "SO-5547": "credit", "SO-5561": "accept"}
    # Delta accepted: back to low risk with the new date
    orders = {o["so"]: o for o in c.get("/api/erp/sales-orders").json()}
    assert orders["SO-5561"]["risk"] == "Low" and orders["SO-5561"]["promised"] == "2026-11-08"
    # Northwind got an offer: approve it, the customer says yes, the order is split
    props = {p["so"]: p for p in c.get("/api/proposals").json() if p["status"] == "Proposed"}
    assert props["SO-5532"]["kind"] == "split" and props["SO-5547"]["kind"] == "credit"
    assert c.post(f"/api/proposals/{props['SO-5532']['id']}/approve", json={}).json()["status"] == "Offered"
    orders = {o["so"]: o for o in c.get("/api/erp/sales-orders").json()}
    assert "SO-5532-B" in orders and orders["SO-5532"]["case_status"] == "resolved"
    detail = c.get("/api/cases/SO-5532").json()
    assert [x["so"] for x in detail["lines"]] == ["SO-5532", "SO-5532-B"] and detail["case"]["resolution"] == "split"
    assert any(e["kind"] == "customer" for e in detail["events"])
    # a reply for an order with no open case is refused
    assert c.post("/api/replies", json={"so": "SO-5547", "body": "Please can you expedite this?"}).status_code == 400  # that case is already closed
    assert c.post("/api/replies", json={"so": "SO-5570", "body": "hello"}).status_code == 400  # never at risk, so no case
    # an old database picks up the new columns
    s = c.get("/api/status").json()["counts"]
    assert s["cases_open"] == 0 and s["proposals"] == 1 and "replies" in s  # only the credit for Harbor is still waiting


def test_old_database_is_upgraded(db):
    from sqlalchemy import text

    from app.db import engine as eng
    from app.db import ensure_columns

    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE customers DROP COLUMN reply_style"))
    ensure_columns()
    with eng.begin() as conn:
        assert conn.execute(text("SELECT reply_style FROM customers LIMIT 1")).scalar() in ("accept", "hard", "partial", "credit", "cancel", "expedite", "question", "silent", None)
