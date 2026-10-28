from fastapi.testclient import TestClient

from app.main import app


def client():
    c = TestClient(app)
    c.__enter__()
    c.post("/api/world/reset")
    return c


def test_status_and_lists():
    c = client()
    s = c.get("/api/status").json()
    assert s["ai_available"] is False and s["counts"]["unprocessed"] == 14
    assert len(c.get("/api/erp/purchase-orders").json()) == 11
    assert len(c.get("/api/crm/customers").json()) == 16
    assert len(c.get("/api/scenarios").json()) == 31


def test_email_to_customer_outbox():
    c = client()
    e = next(x for x in c.get("/api/mailbox").json() if x["subject"].startswith("PO-8841"))
    assert c.post(f"/api/mailbox/{e['id']}/process").status_code == 200  # background task runs inside TestClient
    run = c.get("/api/runs").json()[0]
    assert run["status"] == "waiting_approval"
    detail = c.get(f"/api/runs/{run['id']}").json()
    assert any(s["kind"] == "code" for s in detail["steps"])
    for a in c.get("/api/approvals").json():
        assert c.post(f"/api/approvals/{a['id']}/send", json={}).status_code == 200
    assert len(c.get("/api/outbox").json()) == 3
    assert c.get(f"/api/runs/{run['id']}").json()["status"] == "done"


def test_compose_unknown_po_and_dismiss():
    c = client()
    c.post("/api/mailbox", json={"sender": "Lakeside Plastics", "subject": "PO-9921 new date", "body": "PO-9921 will now arrive on 12 November instead of 5 November."})
    run = c.get("/api/runs").json()[0]
    assert run["status"] == "waiting_person"
    assert c.post(f"/api/runs/{run['id']}/resolve", json={"dismiss": True}).status_code == 200
    assert c.get(f"/api/runs/{run['id']}").json()["status"] == "no_action"


def test_erp_edit_triggers_agent_and_quote_flow():
    c = client()
    assert c.put("/api/erp/purchase-orders/PO-8850/arrival", json={"date": "2026-11-06"}).json()["agent_started"]
    run = c.get("/api/runs").json()[0]
    assert run["trigger"]["type"] == "erp" and run["status"] == "waiting_approval"
    q = c.post("/api/crm/quotes", json={"customer_id": "orchard", "sku": "CC-210", "qty": 400, "requested": "2026-10-30"}).json()["q"]
    qrow = next(x for x in c.get("/api/crm/quotes").json() if x["q"] == q)
    qrun = c.get(f"/api/runs/{qrow['run_id']}").json()
    assert qrun["result"]["feasible"] is False
    assert c.post(f"/api/crm/quotes/{q}/choose", json={"option": qrun["options"][0]["k"]}).json()["status"] == "done"


def test_scenario_and_testpack_endpoints():
    c = client()
    r = c.post("/api/scenarios/SC1/run").json()
    assert r["result"]["passed"] is True and r["result"]["run"]["steps"]
    tp = c.post("/api/testpack/run/rules").json()
    assert sum(x["pass"] for x in tp["results"]["rules"]["results"]) == 75
    assert c.post("/api/testpack/run/ai").status_code == 400  # no API key in tests


def test_chat_uses_tools_with_fake_model():
    from app.llm import get_llm, set_llm

    class ChatFake:
        available, model = True, "fake"

        def chat(self, system, messages, tools, run_tool, max_rounds=6):
            orders = run_tool("list_orders", {})
            late = [o["so"] for o in orders if o["days_late"]]
            return f"{len(late)} orders are late.", ["list_orders"]

    old = get_llm()
    set_llm(ChatFake())
    try:
        c = client()
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "Which orders are late?"}]}).json()
        assert r == {"reply": "0 orders are late.", "tools": ["list_orders"], "mode": "ai"}
    finally:
        set_llm(old)


def test_chat_without_ai_answers_from_rules():
    c = client()
    r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "What happens if PO-8850 slips by 3 days?"}]}).json()
    assert r["mode"] == "rules" and "SO-5575" in r["reply"] and r["tools"] == ["simulate_po_delay"]
