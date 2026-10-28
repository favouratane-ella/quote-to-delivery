"""Deterministic supply-chain maths. No AI here: same input, same answer, every time.

- Delivery estimate = max(today, supply arrival) + carrier transit days.
- Orders that share a purchase order are served in promised-date order.
- Priority score (0-100) = order value (up to 40) + customer tier (up to 25)
  + renewal within 45 days (20) + days late (up to 15).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def add_days(s: str, n: int) -> str:
    return (date.fromisoformat(s) + timedelta(days=n)).isoformat()


def days_between(a: str, b: str) -> int:
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def fmt_date(s: str | None) -> str:
    if not s:
        return "No date"
    d = date.fromisoformat(s)
    return f"{DOW[d.weekday()]} {d.day} {MON[d.month - 1]}"


def money(n: float) -> str:
    return "${:,}".format(int(n + 0.5))


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def jsround(x: float) -> int:
    return int(x + 0.5)


@dataclass
class Snapshot:
    """A read-only view of the ERP and CRM, as plain dicts."""
    today: str
    items: dict[str, dict]
    pos: dict[str, dict]           # po -> {po, supplier, sku, deliveries, original}
    customers: dict[str, dict]
    lanes: dict[str, int]
    orders: list[dict] = field(default_factory=list)
    express: dict[str, tuple[int, float]] = field(default_factory=dict)  # lane -> (days saved, cost)


class Engine:
    def __init__(self, snap: Snapshot):
        self.s = snap

    # ---------- helpers ----------
    @staticmethod
    def po_total(p: dict) -> int:
        return sum(d["qty"] for d in p["deliveries"])

    @staticmethod
    def last_date(dels: list[dict]) -> str:
        return max(d["date"] for d in dels)

    def transit(self, customer: dict, order: dict | None = None) -> int:
        days = self.s.lanes.get(customer["lane"], 2)
        if order and order.get("expedite"):
            days = max(0, days - self.s.express.get(customer["lane"], (0, 0))[0])
        return days

    def free_stock(self, sku: str) -> int:
        reserved = sum(o["stock_qty"] for o in self.s.orders if o["sku"] == sku)
        return max(0, self.s.items[sku]["on_hand"] - reserved)

    # ---------- delivery estimates ----------
    def po_arrivals(self, po_id: str, deliveries: list[dict]) -> dict[str, str | None]:
        orders = sorted((o for o in self.s.orders if o["po"] == po_id), key=lambda o: (o["promised"], o["so"]))
        dels = sorted(({**d} for d in deliveries), key=lambda d: d["date"])
        out: dict[str, str | None] = {}
        i = 0
        for o in orders:
            need, when = o["po_qty"], None
            while need > 0 and i < len(dels):
                take = min(need, dels[i]["qty"])
                need -= take
                dels[i]["qty"] -= take
                when = dels[i]["date"]
                if dels[i]["qty"] == 0:
                    i += 1
            out[o["so"]] = None if need > 0 else when
        return out

    def eta_for(self, o: dict, deliveries: list[dict] | None = None) -> dict:
        c = self.s.customers[o["customer_id"]]
        ready = self.s.today
        if o["po"] and o["po_qty"] > 0:
            dels = deliveries if deliveries is not None else self.s.pos[o["po"]]["deliveries"]
            arr = self.po_arrivals(o["po"], dels).get(o["so"])
            if not arr:
                return {"eta": None, "late": True, "days_late": None}
            ready = max(self.s.today, arr)
        eta = add_days(ready, self.transit(c, o))
        late = max(0, days_between(eta, o["promised"]))
        return {"eta": eta, "late": late > 0, "days_late": late}

    def order_view(self, o: dict) -> dict:
        e = self.eta_for(o)
        return {**o, "customer": self.s.customers[o["customer_id"]]["name"], "eta": e["eta"], "late": e["late"], "days_late": e["days_late"]}

    # ---------- priority ----------
    def risk(self, o: dict, days_late: int | None) -> dict:
        c = self.s.customers[o["customer_id"]]
        value = min(1.0, o["value"] / 50000) * 40
        tier = {"A": 25, "B": 15, "C": 5}.get(c["tier"], 5)
        to_renewal = days_between(c["renewal"], self.s.today)
        renewal = 20 if 0 <= to_renewal <= 45 else 0
        late = 15 if days_late is None else min(15, days_late * 3)
        score = jsround(value + tier + renewal + late)
        level = "High" if score >= 70 else "Medium" if score >= 45 else "Low"
        return {"score": score, "parts": {"value": jsround(value), "tier": tier, "renewal": renewal, "late": late}, "to_renewal": to_renewal, "level": level}

    def impact_of(self, po_id: str, before: list[dict], after: list[dict]) -> dict:
        rows = []
        for o in self.s.orders:
            if o["po"] != po_id:
                continue
            b, a = self.eta_for(o, before), self.eta_for(o, after)
            moved = a["eta"] != b["eta"]
            rows.append({"so": o["so"], "customer_id": o["customer_id"], "value": o["value"], "promised": o["promised"],
                         "before": b["eta"], "after": a["eta"], "days_late": a["days_late"], "late": a["late"], "moved": moved,
                         "risk": self.risk(o, a["days_late"]) if a["late"] else None})
        affected = sorted((r for r in rows if r["late"] and r["moved"]), key=lambda r: -r["risk"]["score"])
        fine = [r for r in rows if not (r["late"] and r["moved"])]
        return {"affected": affected, "fine": fine}

    # ---------- quotes ----------
    def supply_timeline(self, sku: str) -> list[dict]:
        """Inbound quantity not yet promised to any order, per delivery, in date order.

        Existing orders on a PO use up its deliveries in promised-date order, so a
        split PO can have free stock in its second delivery but not its first.
        """
        out = []
        for p in self.s.pos.values():
            if p["sku"] != sku:
                continue
            dels = sorted(({**d} for d in p["deliveries"]), key=lambda d: d["date"])
            i = 0
            for o in sorted((o for o in self.s.orders if o["po"] == p["po"]), key=lambda o: (o["promised"], o["so"])):
                need = o["po_qty"]
                while need > 0 and i < len(dels):
                    take = min(need, dels[i]["qty"])
                    need -= take
                    dels[i]["qty"] -= take
                    if dels[i]["qty"] == 0:
                        i += 1
            out += [{"po": p["po"], "supplier": p["supplier"], "date": d["date"], "qty": d["qty"]} for d in dels if d["qty"] > 0]
        return sorted(out, key=lambda x: (x["date"], x["po"]))

    def check_quote(self, customer_id: str, sku: str, qty: int, requested: str) -> dict:
        c, it, today = self.s.customers[customer_id], self.s.items[sku], self.s.today
        free = self.free_stock(sku)
        steps = [{"label": "Stock on hand, not yet reserved", "qty": free, "date": today, "source": "ERP stock"}]
        need = qty - min(qty, free)
        ready = today
        for p in self.supply_timeline(sku):
            steps.append({"label": f"Inbound {p['po']} ({p['supplier']}), not yet promised", "qty": p["qty"], "date": p["date"], "source": "ERP purchase orders"})
            if need > 0 and p["qty"] > 0:
                take = min(need, p["qty"])
                need -= take
                ready = max(ready, p["date"])
        lane = self.transit(c)
        covered = need == 0
        eta = add_days(ready, lane) if covered else None
        feasible = bool(covered and eta <= requested)
        split = None
        if not feasible and 0 < free < qty:
            now = min(free, qty)
            split = {"now": now, "now_eta": add_days(today, lane), "rest": qty - now, "rest_eta": eta}
        return {"customer": c["name"], "item": it["name"], "unit": it["unit"], "qty": qty, "requested": requested, "steps": steps,
                "lane": c["lane"], "transit_days": lane, "covered": covered, "shortfall": need, "eta": eta, "feasible": feasible, "split": split}
