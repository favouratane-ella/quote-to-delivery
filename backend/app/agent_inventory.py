"""Inventory work for the agent: stock counts, replanning orders that lose stock, and reorders.

Three jobs, all with the same guardrails as the delivery work (checks first, a person approves anything
that changes supply or costs money, numbers come from code):

  stock note      the warehouse reports damaged or found stock. Update the ERP if the checks pass.
  replan          if on hand drops below what is reserved for orders, cover the gap from inbound
                  supply and say which orders get later.
  reorder scan    find items whose free stock plus unpromised inbound is at or below the reorder point
                  and propose a purchase order.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import models as m
from .engine import Engine, add_days, days_between, fmt_date, money, plural
from .stock_reader import read_stock_note

INTERNAL = {"Warehouse team"}
LEAD_DAYS = 14  # how long a new purchase order usually takes to arrive
BIG_CHANGE = 0.4  # a count that moves stock by more than this share of on hand needs a person to check it


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InventoryMixin:
    # ---------- the picture ----------
    def inventory(self, en: Engine | None = None) -> list[dict]:
        en = en or self.engine()
        rows = []
        for sku, it in en.s.items.items():
            reserved = sum(o["stock_qty"] for o in en.s.orders if o["sku"] == sku)
            free = max(0, it["on_hand"] - reserved)
            tl = en.supply_timeline(sku)
            inbound_total = sum(en.po_total(p) for p in en.s.pos.values() if p["sku"] == sku)
            inbound_free = sum(x["qty"] for x in tl)
            projected = free + inbound_free
            demand = sum(o["po_qty"] for o in en.s.orders if o["sku"] == sku and o["po"])
            rp = it["reorder_point"]
            short = [o["so"] for o in en.s.orders if o["sku"] == sku and en.order_view(o)["eta"] is None]
            status = "Short" if short or reserved > it["on_hand"] else "Reorder" if rp and projected <= rp else "Healthy"
            rows.append({"sku": sku, "name": it["name"], "unit": it["unit"], "on_hand": it["on_hand"], "reserved": reserved, "free": free, "inbound": inbound_total, "inbound_free": inbound_free,
                         "next_inbound": tl[0]["date"] if tl else None, "demand_on_po": demand, "projected_free": projected, "reorder_point": rp, "reorder_qty": it["reorder_qty"],
                         "substitute": it["substitute"], "status": status, "over_reserved": max(0, reserved - it["on_hand"]), "short_orders": short})
        return rows

    # ---------- trigger: a warehouse note ----------
    def _run_stock_note(self, run: m.Run, e: dict) -> m.Run:
        en = self.engine()
        on_hand = {k: v["on_hand"] for k, v in en.s.items.items()}
        self.step(run, "read", "Warehouse mailbox", "Read the stock note", f"{plural(len(e['body']), 'character')}.", data=e["subject"] + "\n\n" + e["body"]); self.pace()
        ext = read_stock_note(e["subject"] + "\n" + e["body"], on_hand)
        self.step(run, "rules", "Rules engine", "Read the note: " + ("stock count" if ext["type"] == "stock_note" else "not a stock count"), "; ".join(ext["reasons"]),
                  fields={"type": "stock_note" if ext["type"] == "stock_note" else "other", "po": ext.get("sku"), "new_date": None, "confidence": ext["confidence"], "reasons": ext["reasons"], "split": None,
                          "sku": ext.get("sku"), "new_on_hand": ext.get("new_on_hand"), "change": ext.get("change")}); self.pace()
        if ext["type"] != "stock_note":
            self.step(run, "guard", "Agent code", "Decide: no stock change found", "The note does not state a count or a change.", checks=[{"ok": True, "label": "Nothing to change"}])
            self.sys.set_status(e["id"], "Filed, no change")
            self.finish(run, "no_action", "No action needed.")
            return run
        cur = on_hand[ext["sku"]]
        checks = [
            {"ok": True, "label": f"{ext['sku']} exists in the ERP"},
            {"ok": e["sender"] in INTERNAL, "label": "Sent by the warehouse team" if e["sender"] in INTERNAL else f"{e['sender']} is not the warehouse team"},
            {"ok": ext["new_on_hand"] >= 0, "label": f"New on hand {ext['new_on_hand']} is not negative"},
            {"ok": cur == 0 or abs(ext["change"]) <= BIG_CHANGE * cur, "label": f"Change of {ext['change']:+,} is within {round(BIG_CHANGE * 100)}% of the {cur:,} on hand" if cur == 0 or abs(ext["change"]) <= BIG_CHANGE * cur
             else f"Change of {ext['change']:+,} is more than {round(BIG_CHANGE * 100)}% of the {cur:,} on hand: check the count"},
            {"ok": ext["confidence"] >= self.cfg.pass_mark, "label": f"Confidence {round(ext['confidence'] * 100)}% vs pass mark {round(self.cfg.pass_mark * 100)}%"},
        ]
        ok = all(c["ok"] for c in checks)
        self.step(run, "guard", "Agent code", "Decide: safe to update stock" if ok else "Decide: a person must check this count", "All checks passed." if ok else "At least one check failed, so the ERP is not changed.", checks=checks)
        if not ok:
            run.status, run.pending = "waiting_person", {"stock": {"sku": ext["sku"], "new_on_hand": ext["new_on_hand"], "change": ext["change"]}}
            self.sys.set_status(e["id"], "Waiting for a person")
            self.step(run, "wait", "Planner", "Waiting for the planner", "The planner confirms or corrects the count, or dismisses the note.")
            self.db.commit()
            self.log("Agent", "Email", f'Asked the planner to check the stock note "{e["subject"]}".')
            return run
        self._apply_stock(run, ext["sku"], ext["new_on_hand"], "Agent")
        self.sys.set_status(e["id"], "Applied to ERP")
        return run

    def resolve_stock(self, run: m.Run, fields: dict | None, by: str = "Planner") -> None:
        eid = run.trigger["email_id"]
        self.clear_waits(run)
        if fields is None:
            self.step(run, "person", by, "Dismissed: no stock change", "The planner decided the count is wrong or not needed.")
            self.sys.set_status(eid, "Dismissed by planner")
            self.finish(run, "no_action", "Nothing changed.")
            return
        st = run.pending["stock"]
        sku, new = fields.get("sku") or st["sku"], fields.get("on_hand")
        if new is None or new < 0 or not self.db.get(m.Item, (self.w, sku)):
            raise ValueError("Pick an item and a quantity of zero or more.")
        self.step(run, "person", by, "Checked and confirmed the count", f"{sku} on hand: {new:,}.")
        run.status, run.pending = "running", None
        self.db.commit()
        self._apply_stock(run, sku, new, by)
        self.sys.set_status(eid, "Applied to ERP")

    def _apply_stock(self, run: m.Run, sku: str, new_on_hand: int, by: str) -> None:
        it = self.db.get(m.Item, (self.w, sku))
        old = it.on_hand
        it.on_hand = new_on_hand
        self.db.commit()
        self.step(run, "write", "ERP", f"Update {sku} on hand", f"{old:,} to {new_on_hand:,} {it.unit}" + ("" if by == "Agent" else f" (confirmed by {by})"))
        self.log(by, "ERP", f"{sku} on hand changed from {old:,} to {new_on_hand:,}.")
        self.pace()
        self._replan(run, sku)

    # ---------- replan orders that lost their stock ----------
    def _replan(self, run: m.Run, sku: str) -> None:
        en = self.engine_held()
        inv = next(r for r in self.inventory(en) if r["sku"] == sku)
        over = inv["over_reserved"]
        self.step(run, "code", "Agent code", "Compare stock with what orders have reserved",
                  f"On hand {inv['on_hand']:,}, reserved {inv['reserved']:,}: " + (f"{over:,} short." if over else "enough for every order."),
                  table={"head": ["On hand", "Reserved by orders", "Free", "Inbound not yet promised", "Reorder point"],
                         "rows": [[f"{inv['on_hand']:,}", f"{inv['reserved']:,}", f"{inv['free']:,}", f"{inv['inbound_free']:,}", f"{inv['reorder_point']:,}"]]}); self.pace()
        if over <= 0:
            self.finish(run, "done", "Stock updated. Every order is still covered.")
            self._scan(run, only=sku)
            return
        holders = sorted((o for o in en.s.orders if o["sku"] == sku and o["stock_qty"] > 0), key=lambda o: en.risk(o, 0)["score"])
        inbound = en.supply_timeline(sku)
        plan, left = [], over
        for o in holders:
            if left <= 0:
                break
            cut = min(o["stock_qty"], left)
            row = next((r for r in inbound if r["qty"] >= cut and o["po"] in (None, r["po"])), None)
            cust = en.s.customers[o["customer_id"]]
            if row:
                eta = add_days(max(self.today, row["date"]), en.transit(cust, o))
                late = max(0, days_between(eta, o["promised"]))
                row["qty"] -= cut
            else:
                eta, late = None, None
            plan.append({"so": o["so"], "customer": cust["name"], "customer_id": cust["id"], "units": cut, "po": row["po"] if row else None, "po_date": row["date"] if row else None, "new_eta": eta, "days_late": late, "value": o["value"], "promised": o["promised"]})
            left -= cut
        self.step(run, "code", "Agent code", f"Cover the {over:,} missing {inv['unit']} from inbound supply", "Orders that lose stock first are the lowest priority.",
                  table={"head": ["Order", "Customer", "Units to move", "Covered by", "Arrives", "Against promise"],
                         "rows": [[p["so"], p["customer"], f"{p['units']:,}", p["po"] or "nothing available", fmt_date(p["new_eta"]) if p["new_eta"] else "no supply", ("on time" if p["days_late"] == 0 else f"{p['days_late']} days late") if p["days_late"] is not None else "no date"] for p in plan]}); self.pace()
        for p in plan:
            late = p["days_late"]
            title = f"Cover {p['units']:,} {inv['unit']} for {p['so']} from {p['po']}" if p["po"] else f"No supply for {p['units']:,} {inv['unit']} on {p['so']}"
            summary = (f"{p['customer']} keeps its date: the {inv['unit']} now come from {p['po']}, arriving {fmt_date(p['po_date'])}. Arrives {fmt_date(p['new_eta'])}." if p["po"] and late == 0 else
                       f"{p['customer']} gets the order {plural(late, 'day')} late ({fmt_date(p['new_eta'])}). A customer update is drafted when this is approved." if p["po"] else
                       f"Nothing inbound covers these {inv['unit']}. Raise a purchase order and tell {p['customer']}.")
            prop = m.Proposal(world_id=self.w, run_id=run.id, so=p["so"], customer_id=p["customer_id"], kind="resupply", title=title, summary=summary,
                              detail={"sku": sku, "units": p["units"], "po": p["po"], "po_date": p["po_date"], "new_eta": p["new_eta"], "days_late": late, "promised": p["promised"], "side_effects": [summary]},
                              cost=0, value=p["value"], meets_promised=late == 0, needs="Planner", reason=f"Stock count removed {over:,} {inv['unit']}", rank=1)
            self.db.add(prop)
        self.db.commit()
        self.step(run, "write", "Approvals", f"Queue {plural(len(plan), 'replan')} for the planner", "Nothing in the ERP moves until the planner approves.")
        run.status = "waiting_approval"
        self.step(run, "wait", "Planner", "Waiting for approval", "")
        self.db.commit()
        self.log("Agent", "Approvals", f"Stock count on {sku} left {over:,} short. Proposed {plural(len(plan), 'replan')}.")

    def apply_resupply(self, p: m.Proposal, by: str, run: m.Run | None) -> None:
        d = p.detail or {}
        o = self.sys.get_order(p.so)
        if not d.get("po"):
            raise ValueError("There is no inbound supply to move this order to. Raise a purchase order first.")
        self.sys.update_order(p.so, stock_qty=max(0, o.stock_qty - d["units"]), po=d["po"], po_qty=o.po_qty + d["units"], note=(o.note + " " if o.note else "") + f"{d['units']} units moved to {d['po']} after a stock count.")
        self.event(p.so, by, "person", f"{d['units']:,} units moved from stock to {d['po']} (arriving {fmt_date(d['po_date'])}).")
        if d.get("days_late"):
            self._queue_update_for(p.so, p.run_id)
            if run:
                self.step(run, "write", "Approvals", f"Draft a customer update for {p.so}", "The order is now late, so the customer must be told. It waits for approval.")
        if run:
            self.step(run, "write", "ERP", f"Move {p.so} to {d['po']}", f"{d['units']:,} units, arriving {fmt_date(d['po_date'])}.")

    # ---------- reorder scan ----------
    def run_inventory_scan(self, sku: str | None = None) -> m.Run:
        run = self.new_run({"type": "inventory", "sku": sku}, "Inventory check" + (f": {sku}" if sku else ": all items"))
        self.step(run, "event", "Planner", "Inventory check started", "Compares free stock plus unpromised inbound with each item's reorder point."); self.pace()
        self._scan(run, only=sku)
        return run

    def _scan(self, run: m.Run, only: str | None = None) -> None:
        en = self.engine_held()
        rows = [r for r in self.inventory(en) if (not only or r["sku"] == only)]
        pend: dict[str, int] = {}
        for pr in self.db.query(m.Proposal).filter(m.Proposal.world_id == self.w, m.Proposal.kind == "resupply", m.Proposal.status == "Proposed"):
            pend[pr.detail["sku"]] = pend.get(pr.detail["sku"], 0) + pr.detail["units"]
        for r in rows:  # a replan the planner has not approved yet already claims some inbound supply
            n = pend.get(r["sku"], 0)
            if n:
                r["over_reserved"] = max(0, r["over_reserved"] - n)
                r["inbound_free"] -= n
                r["projected_free"] -= n
                r["status"] = "Short" if r["over_reserved"] or r["short_orders"] else "Reorder" if r["reorder_point"] and r["projected_free"] <= r["reorder_point"] else "Healthy"
        self.step(run, "read", "ERP", "Read stock, orders and inbound supply", f"{plural(len(rows), 'item')} checked.",
                  table={"head": ["Item", "On hand", "Reserved", "Free", "Inbound free", "Projected", "Reorder at", "Status"],
                         "rows": [[r["sku"], f"{r['on_hand']:,}", f"{r['reserved']:,}", f"{r['free']:,}", f"{r['inbound_free']:,}", f"{r['projected_free']:,}", f"{r['reorder_point']:,}", r["status"]] for r in rows]}); self.pace()
        flagged = [r for r in rows if r["status"] in ("Reorder", "Short")]
        existing = {p.detail.get("sku") for p in self.db.query(m.Proposal).filter(m.Proposal.world_id == self.w, m.Proposal.kind == "raise_po", m.Proposal.status == "Proposed") if p.detail}
        made = 0
        for r in flagged:
            if r["sku"] in existing:
                continue
            qty = max(r["reorder_qty"], r["reorder_point"] * 2 - r["projected_free"]) + r["over_reserved"]
            pos = [p for p in en.s.pos.values() if p["sku"] == r["sku"]]
            sup = pos[-1]["supplier"] if pos else next(iter(self.db.query(m.Supplier).filter_by(world_id=self.w)), None) and self.db.query(m.Supplier).filter_by(world_id=self.w).first().name
            due = add_days(self.today, LEAD_DAYS)
            why = (f"Free stock {r['free']:,} plus {r['inbound_free']:,} inbound not yet promised is {r['projected_free']:,}, at or below the reorder point of {r['reorder_point']:,}." if r["status"] == "Reorder"
                   else f"{r['over_reserved']:,} units more are reserved than are on hand.")
            row = self.db.query(m.Supplier).filter_by(world_id=self.w, name=sup).first()
            self.db.add(m.Proposal(
                world_id=self.w, run_id=run.id, so="", customer_id="", kind="raise_po", title=f"Raise a PO for {qty:,} {r['unit']} of {r['sku']} from {sup}", summary=why + f" Expected around {fmt_date(due)}.",
                detail={"sku": r["sku"], "qty": qty, "supplier": sup, "date": due, "side_effects": [why, f"Lead time assumed {LEAD_DAYS} days"]}, cost=0, value=0, needs="Planner", reason="New purchase order",
                to=f"{sup} <{row.email}>" if row else (sup or ""), subject=f"New order: {qty:,} x {r['sku']}",
                body=f"Hello,\n\nPlease can you confirm an order of {qty:,} {r['unit']} of {r['sku']} ({r['name']}), delivered by {fmt_date(due)}. Let us know if that date is not possible.\n\nThank you,\nSupply planning", note=f"Raised a PO for {qty:,} x {r['sku']}.", rank=1))
            made += 1
        self.db.commit()
        if made:
            self.step(run, "guard", "Agent code", f"Decide: {plural(made, 'item')} below the reorder point", "A purchase order is proposed for each. Nothing is ordered until the planner approves.",
                      checks=[{"ok": False, "label": f"{r['sku']}: {r['status'].lower()} ({r['projected_free']:,} projected, reorder at {r['reorder_point']:,})"} for r in flagged])
            self.step(run, "write", "Approvals", f"Queue {plural(made, 'purchase order')} for the planner", "")
            if run.status != "waiting_approval":
                run.status = "waiting_approval"
                self.step(run, "wait", "Planner", "Waiting for approval", "")
            self.db.commit()
        elif run.status in ("running",):
            self.step(run, "guard", "Agent code", "Decide: nothing to order", "Every item is above its reorder point.", checks=[{"ok": True, "label": "All items healthy"}])
            self.finish(run, "done", "Stock is healthy. No purchase orders needed.")
        elif run.status == "done":
            pass

    def apply_raise_po(self, p: m.Proposal, by: str, run: m.Run | None) -> None:
        d = p.detail or {}
        n = max([int(x.po.split("-")[1]) for x in self.db.query(m.PurchaseOrder).filter_by(world_id=self.w)] + [8000]) + 3
        po = f"PO-{n}"
        deliveries = [{"qty": d["qty"], "date": d["date"]}]
        self.db.add(m.PurchaseOrder(world_id=self.w, po=po, supplier=d["supplier"], sku=d["sku"], deliveries=deliveries, original=[dict(x) for x in deliveries]))
        self.db.commit()
        # orders that had no supply at all now have a PO to wait on
        en = self.engine()
        gap = [o for o in en.s.orders if o["sku"] == d["sku"] and en.order_view(o)["eta"] is None]
        for o in gap:
            self.sys.update_order(o["so"], po=po)
        if p.subject:
            self.sys.send(to=p.to, customer_id="", so="", subject=p.subject, body=p.body, sent_by=by, kind="supplier")
        if run:
            self.step(run, "write", "ERP", f"Create {po}", f"{d['qty']:,} x {d['sku']} from {d['supplier']}, expected {fmt_date(d['date'])}.")
            self.step(run, "write", "Email", f"Order sent to {d['supplier']}", p.subject)
        self.log(by, "ERP", f"Created {po}: {d['qty']:,} x {d['sku']} from {d['supplier']}.")
        p.detail = {**d, "po": po}
