from app import models as m
from app.agent import Agent
from app.connectors.simulated import SimulatedSystems
from app.engine import Engine, fmt_date
from app.rules_reader import read_email
from app.scenarios import SCENARIOS, run_scenario
from app.seed import POS, TEST_PACK

from .fake_llm import FakeLLM


def engine(db):
    return Engine(SimulatedSystems(db, "main").snapshot("2026-10-26"))


def test_dates():
    assert fmt_date("2026-11-07") == "Sat 7 Nov"
    assert fmt_date(None) == "No date"


def test_delay_flags_only_late_orders(db):
    e = engine(db)
    imp = e.impact_of("PO-8841", e.s.pos["PO-8841"]["deliveries"], [{"qty": 280, "date": "2026-11-07"}])
    assert [(a["so"], a["after"], a["days_late"], a["risk"]["score"]) for a in imp["affected"]] == [
        ("SO-5532", "2026-11-09", 5, 99), ("SO-5547", "2026-11-10", 5, 66), ("SO-5561", "2026-11-08", 2, 31)]
    assert [f["so"] for f in imp["fine"]] == ["SO-5570"]


def test_quote_checks(db):
    e = engine(db)
    r = e.check_quote("orchard", "CC-210", 400, "2026-10-30")
    assert (r["feasible"], r["eta"], r["split"]["now"], r["split"]["now_eta"]) == (False, "2026-11-18", 120, "2026-10-28")
    assert e.check_quote("meridian", "TS-88", 500, "2026-11-03")["eta"] == "2026-11-01"
    assert e.check_quote("kestrel", "IB-12", 500, "2026-11-10")["covered"] is False


def test_rules_reader_on_test_pack():
    pos = {p[0]: max(d["date"] for d in p[3]) for p in POS}

    def ok(case):
        _, text, kind, po, d = case
        g = read_email(text, "2026-10-26", pos)
        return g["type"] == kind and (kind == "other" or g["po"] == po) and (kind not in ("delay", "partial") or g["new_date"] == d)
    failed = [c[0] for c in TEST_PACK if not ok(c)]
    assert len(TEST_PACK) == 75 and failed == []


def test_reader_explains_itself():
    g = read_email("PO-8860 is pushed back by one week.", "2026-10-26", {"PO-8860": "2026-11-06"})
    assert g["new_date"] == "2026-11-13" and any("one week" in r for r in g["reasons"])
    g = read_email("PO-8863 is not delayed and will arrive 9 Nov as planned.", "2026-10-26", {"PO-8863": "2026-11-09"})
    assert g["type"] == "confirmation"


def test_scenarios_rules_mode(db):
    results = {s["id"]: run_scenario(db, s["id"], ai_mode="rules").passed for s in SCENARIOS}
    assert len(results) == len(SCENARIOS) == 31 and all(results.values()), results


def test_scenarios_ai_path_with_fake_model(db):
    fake = FakeLLM()
    results = {s["id"]: run_scenario(db, s["id"], ai_mode="auto", llm=fake).passed for s in SCENARIOS}
    assert all(results.values()), results
    assert any(p.startswith("Write delay notices") for p in fake.calls)


def test_run_trace_and_approvals(db):
    agent = Agent(db, "main", llm=FakeLLM(), delay_ms=0)
    e = db.query(m.Email).filter_by(world_id="main", subject="PO-8841 delayed, new ship date").one()
    run = agent.run_email(e.id)
    kinds = [s.kind for s in run.steps]
    assert kinds[:4] == ["event", "read", "read", "ai"] and "code" in kinds and "guard" in kinds and kinds[-1] == "wait"
    ai_step = next(s for s in run.steps if s.kind == "ai")
    assert "PROMPT SENT TO CLAUDE" in ai_step.payload["data"]
    aps = db.query(m.Approval).filter_by(run_id=run.id).order_by(m.Approval.rank).all()
    assert [a.status for a in aps] == ["Needs approval", "Needs approval", "Ready"]
    for a in aps:
        agent.decide_approval(a.id, True)
    db.refresh(run)
    assert run.status == "done"
    assert db.query(m.OutboxMessage).filter_by(world_id="main").count() == 3
    assert db.query(m.CrmNote).filter_by(world_id="main").count() == 3


def test_planner_check_then_continue(db):
    agent = Agent(db, "main", delay_ms=0)  # rules mode: no AI configured
    db.add(m.Email(world_id="main", sender="Lakeside Plastics", address="x@example.com", received_at="2026-10-26T10:00",
                   subject="PO-8841 possible delay", body="PO-8841 might slip to 9 November.", attachment=None))
    db.commit()
    e = db.query(m.Email).filter_by(world_id="main", subject="PO-8841 possible delay").one()
    run = agent.run_email(e.id)
    assert run.status == "waiting_person"
    agent.resolve_check(run.id, {"po": "PO-8841", "new_date": "2026-11-09", "type": "delay", "split": None})
    db.refresh(run)
    assert run.status == "waiting_approval"
    assert any(s.kind == "person" for s in run.steps)


def test_quote_uses_free_part_of_a_split_po(db):
    e = engine(db)
    e.s.pos["PO-8856"]["deliveries"] = [{"qty": 400, "date": "2026-11-04"}, {"qty": 200, "date": "2026-11-12"}]
    assert e.supply_timeline("IB-12") == [{"po": "PO-8856", "supplier": "Vexa Packaging", "date": "2026-11-04", "qty": 100},
                                           {"po": "PO-8856", "supplier": "Vexa Packaging", "date": "2026-11-12", "qty": 200}]
    assert e.check_quote("kestrel", "IB-12", 150, "2026-11-10")["eta"] == "2026-11-07"


def test_templates_follow_tone(db):
    for tone, word in (("Formal", "regret"), ("Short and direct", "Sorry"), ("Warm and clear", "sorry for the change")):
        db.get(m.Settings, "main").tone = tone
        db.commit()
        a = Agent(db, "main", delay_ms=0)
        f = {"units_free_in_stock_now": 0, "unit": "crates", "contact_first_name": "Dana", "new_date": "Mon 9 Nov", "promised": "Wed 4 Nov", "sender": "Sam", "qty": 10, "renewal_in_days": 90}
        assert word in a._template(None, {"so": "SO-1"}, f)["body"]
