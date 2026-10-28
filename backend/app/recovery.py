"""Recovery options for an order that will arrive late. Pure maths, no AI: same input, same answer.

For one late order we work out every realistic way to rescue it, what each costs, who else it
hurts, and which one to recommend for this customer:

  stock        ship the whole order from free stock now
  split        ship what is in stock now, the rest when the supply lands
  reallocate   take stock from lower-priority orders that can live with a later date
  expedite     pay for express shipping from the supplier's arrival date
  substitute   cover the gap with a compatible item (the customer must agree)
  new_date     ask the customer to accept the later date (must be within what they can live with)
  supplier     ask the supplier to expedite or part-ship (outcome is not in our hands)
  credit       compensate the customer for the delay

Customers differ. A hard-deadline customer only counts an option as a rescue if the promised date
is kept. A partial customer will take a split. A flexible customer will usually take a new date.
"""
from __future__ import annotations

from .engine import Engine, add_days, days_between, fmt_date, money, plural

EXTRA_COST_LIMIT = 500  # an option that costs more than this needs the ops manager
KIND_ORDER = {"stock": 0, "reallocate": 1, "expedite": 2, "substitute": 3, "split": 4, "new_date": 5, "supplier": 6, "credit": 7}


def risk_tier(view: dict, customer: dict, case: dict | None = None, today: str = "") -> dict:
    """Critical, High, Medium, Watch or Low. A resolved case is always Low."""
    if case and case.get("status") == "resolved":
        return {"tier": "Low", "why": "Resolved: " + (case.get("resolution") or "closed").replace("_", " ")}
    esc = bool(case and case.get("status") == "escalated")
    hard = customer.get("flex") == "hard"
    if view["late"]:
        if hard or (esc and hard):
            return {"tier": "Critical", "why": "Late for a customer with a hard deadline"}
        dl = view["days_late"]
        if esc or dl is None or dl > customer.get("max_slip", 0):
            return {"tier": "High", "why": "Later than the customer can live with" if not esc else "Escalated: no option fixes it"}
        return {"tier": "Medium", "why": "Late, within what the customer can live with"}
    slack = days_between(view["promised"], view["eta"]) if view.get("eta") else 99
    if slack <= 1:
        return {"tier": "Watch", "why": "On time with no more than a day to spare"}
    return {"tier": "Low", "why": "On track"}


def approver(value: float, cost: float, affects_others: bool, limit: float) -> str:
    return "Ops manager" if value >= limit or cost >= EXTRA_COST_LIMIT or affects_others else "Account manager"


def options_for(en: Engine, so: str, limit: float = 25000, target: str | None = None) -> dict:
    """Every way to rescue one order, ranked, with a recommendation. `target` overrides the promised date."""
    o = next(x for x in en.s.orders if x["so"] == so)
    c = en.s.customers[o["customer_id"]]
    items, today = en.s.items, en.s.today
    it = items[o["sku"]]
    promised = target or o["promised"]
    v = en.order_view(o)
    eta = v["eta"]
    late_days = None if eta is None else days_between(eta, promised)
    late = eta is None or (late_days or 0) > 0
    out = {"so": so, "customer": c["name"], "flex": c["flex"], "max_slip": c["max_slip"], "hard_reason": c.get("hard_reason", ""), "promised": promised,
           "eta": eta, "days_late": late_days if late else 0, "late": late, "options": [], "recommended": None, "escalate": False}
    if not late:
        return out
    unit, need = it["unit"], o["po_qty"] if o["po"] else 0
    free = en.free_stock(o["sku"])
    lane_days = en.transit(c, o)
    now_eta = add_days(today, lane_days)
    opts: list[dict] = []

    def add(kind, title, summary, new_eta, meets, cost=0.0, side=None, customer_ok=False, others=False, detail=None):
        opts.append({"kind": kind, "title": title, "summary": summary, "new_eta": new_eta, "meets_promised": bool(meets), "cost": round(cost, 2), "side_effects": side or [],
                     "needs_customer_ok": customer_ok, "needs": approver(o["value"], cost, others, limit), "detail": detail or {}})

    # A / B: ship from stock, in full or in part
    if need > 0 and free >= need:
        add("stock", "Ship the whole order from stock now", f"{plural(need, unit[:-1] if unit.endswith('s') else unit)} are free in stock. Arrives {fmt_date(now_eta)}.",
            now_eta, now_eta <= promised, side=[f"Uses {need:,} of the {free:,} free {unit} in stock"], detail={"units": need})
    elif need > 0 and 0 < free < need:
        rest_eta = eta
        rest_late = None if rest_eta is None else days_between(rest_eta, promised)
        ok = rest_late is not None and rest_late <= c["max_slip"] and c["flex"] != "hard"
        add("split", f"Split: {free:,} now, {need - free:,} later",
            f"Ship {free:,} {unit} from stock, arriving {fmt_date(now_eta)}, and the other {need - free:,} on {fmt_date(rest_eta) if rest_eta else 'a date to be set'}.",
            rest_eta, False, side=[f"Uses all {free:,} free {unit} in stock",
                                   f"The rest arrives {fmt_date(rest_eta)}" + (f", {plural(rest_late, 'day')} after the promised date" if rest_late else "") if rest_eta else "The rest has no supply date yet"],
            customer_ok=True, detail={"now": free, "now_eta": now_eta, "rest": need - free, "rest_eta": rest_eta, "acceptable": ok})

    # C: reallocate stock held by orders that can live with a later date
    short = need - min(free, need)
    if need > 0 and short > 0:
        inbound = en.supply_timeline(o["sku"])
        donors = sorted((x for x in en.s.orders if x["so"] != so and x["sku"] == o["sku"] and x["stock_qty"] > 0 and en.s.customers[x["customer_id"]]["flex"] != "hard"),
                        key=lambda x: en.risk(x, 0)["score"])
        takes, remaining = [], short
        for d in donors:
            if remaining <= 0:
                break
            take = min(d["stock_qty"], remaining)
            row = next((r for r in inbound if r["qty"] >= take and d["po"] in (None, r["po"])), None)
            if not row:
                continue
            dc = en.s.customers[d["customer_id"]]
            d_eta = add_days(max(today, row["date"]), en.transit(dc, d))
            d_late = max(0, days_between(d_eta, d["promised"]))
            if d_late > dc["max_slip"]:
                continue
            takes.append({"so": d["so"], "customer": dc["name"], "customer_id": d["customer_id"], "units": take, "po": row["po"], "new_eta": d_eta, "days_late": d_late, "promised": d["promised"]})
            row["qty"] -= take
            remaining -= take
        if takes and remaining == 0:
            side = [f"{t['customer']} ({t['so']}): {t['units']:,} {unit} move to {t['po']}, arriving {fmt_date(t['new_eta'])}" +
                    (f", {plural(t['days_late'], 'day')} after their promised date" if t["days_late"] else ", still on time") for t in takes]
            add("reallocate", "Take stock from lower-priority orders",
                f"{short:,} {unit} come from {', '.join(t['customer'] for t in takes)}. Arrives {fmt_date(now_eta)}.", now_eta, now_eta <= promised,
                side=([f"Uses {min(free, need):,} free {unit} first"] if free else []) + side, others=any(t["days_late"] for t in takes),
                detail={"free_used": min(free, need), "takes": takes})

    # D: express shipping
    saves, cost = en.s.express.get(c["lane"], (0, 0.0))
    if need > 0 and saves > 0 and not o["expedite"] and eta:
        new_eta = add_days(eta, -saves)
        add("expedite", f"Express shipping on the {c['lane']} lane", f"Saves {plural(saves, 'day')}: arrives {fmt_date(new_eta)} instead of {fmt_date(eta)}.", new_eta, new_eta <= promised,
            cost=cost, side=[f"Costs {money(cost)}"], detail={"saves": saves})

    # E: substitute with a compatible item
    sub = it.get("substitute")
    if need > 0 and sub and sub in items:
        main_units = min(free, need)
        sub_units = need - main_units
        sub_free = en.free_stock(sub)
        if 0 < sub_units <= sub_free:
            add("substitute", f"Cover {sub_units:,} {unit} with {sub}", f"{main_units:,} as {o['sku']} and {sub_units:,} as {sub} ({items[sub]['name']}). Arrives {fmt_date(now_eta)}.",
                now_eta, now_eta <= promised, side=[f"{sub_units:,} units are {sub}, not {o['sku']}: the customer must accept", f"Uses {sub_units:,} of the {sub_free:,} free {sub} in stock"],
                customer_ok=True, detail={"main": main_units, "sub_units": sub_units, "sub": sub})

    # F: ask the customer to take the later date
    if eta and late_days is not None and late_days <= c["max_slip"] and c["flex"] != "hard":
        add("new_date", f"Agree the new date: {fmt_date(eta)}", f"The customer can live with {plural(late_days, 'day')} late. Update the promise to {fmt_date(eta)}.", eta, False,
            side=[f"{plural(late_days, 'day')} later than promised, within the {plural(c['max_slip'], 'day')} this customer tolerates"], customer_ok=True, detail={"date": eta})

    # G: chase the supplier
    if o["po"] and o["po"] in en.s.pos:
        sup = en.s.pos[o["po"]]["supplier"]
        add("supplier", f"Ask {sup} to expedite", f"Ask {sup} to part-ship or expedite {o['po']}. Nothing is guaranteed.", None, False, side=["The outcome depends on the supplier"], detail={"supplier": sup, "po": o["po"]})

    # H: credit
    pct = 10 if late_days is None else min(10, 2 * late_days)
    amount = o["value"] * pct / 100
    add("credit", f"Offer a {pct}% credit ({money(amount)})", f"Compensate {c['name']} for the delay. It does not fix the date.", None, False, cost=amount, side=[f"Credit of {money(amount)}"],
        customer_ok=False, detail={"pct": pct, "amount": round(amount, 2)})

    # recommend
    fixes = [x for x in opts if x["meets_promised"]]
    score = lambda x: (x["cost"] + 2000 * sum(1 for t in x["detail"].get("takes", []) if t["days_late"]) + 25 * x["needs_customer_ok"], KIND_ORDER[x["kind"]])  # noqa: E731
    pick = None
    if fixes:
        pick = sorted(fixes, key=score)[0]
    elif c["flex"] == "partial":
        pick = next((x for x in opts if x["kind"] == "split" and x["detail"].get("acceptable")), None) or next((x for x in opts if x["kind"] == "new_date"), None)
    elif c["flex"] == "flexible":
        pick = next((x for x in opts if x["kind"] == "new_date"), None) or next((x for x in opts if x["kind"] == "split" and x["detail"].get("acceptable")), None)
    out["escalate"] = pick is None
    out["recommended"] = pick["kind"] if pick else None
    for i, x in enumerate(sorted(opts, key=lambda x: (x is not pick, not x["meets_promised"], score(x)))):
        x["rank"], x["recommended"] = i + 1, x is pick
    out["options"] = sorted(opts, key=lambda x: x["rank"])
    return out
