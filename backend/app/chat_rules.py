"""Deterministic "Ask the agent": answers common questions without AI.

It recognises a handful of question types, runs the same read-only tools the AI
chat uses, and writes the answer from a template. Anything it does not recognise
gets a short list of what it can answer.
"""
from __future__ import annotations

import re
from datetime import date

from .engine import fmt_date, money, plural
from .rules_reader import NUMBERS, find_dates

HELP = ("I can answer these without AI:\n"
        "- Which orders are late?\n"
        "- What happens if PO-8850 slips by 3 days?\n"
        "- Can we promise 300 CC-210 to Kestrel Hotels by 20 Nov?\n"
        "- What is waiting for a person?\n"
        "- Tell me about SO-5532, PO-8841 or a customer by name.")


def late_text(days: int | None) -> str:
    return f"{plural(days, 'day')} late" if days else "on time"


def arrivals(parts: list[dict]) -> str:
    return ", ".join(f"{plural(d['qty'], 'unit')} on {fmt_date(d['date'])}" for d in parts)


def answer(question: str, run_tool, today: str) -> tuple[str, list[str]]:
    q = question.strip()
    low = q.lower()
    used: list[str] = []

    def tool(name, args=None):
        used.append(name)
        return run_tool(name, args or {})

    po = re.search(r"\b(?:P\.?\s?O\.?)\s*-?\s*(\d{3,6})\b", q, re.I)
    po_id = f"PO-{po.group(1)}" if po else None
    so = re.search(r"\bSO\s*-?\s*(\d{3,6})\b", q, re.I)

    # what-if: a PO slipping by N days or weeks
    shift = re.search(r"(\d+|a|an|one|two|three|four|five|six|seven|ten|a couple of)\s+(business\s+days?|working\s+days?|days?|weeks?)", low)
    if po_id and shift and re.search(r"\b(slip|delay|late|push|move|what if|what happens)", low):
        n = int(shift.group(1)) if shift.group(1).isdigit() else NUMBERS.get(shift.group(1), 1)
        days = n * 7 if "week" in shift.group(2) else n
        r = tool("simulate_po_delay", {"po": po_id, "days": days})
        lines = [f"If {po_id} slips {plural(days, 'day')}, it would arrive {arrivals(r['new_arrival'])}. This is a what-if; nothing was changed."]
        if r["would_be_late"]:
            n_late = len(r["would_be_late"]); lines.append(f"{n_late} {'order' if n_late == 1 else 'orders'} would miss the promised date, highest priority first:")
            for x in sorted(r["would_be_late"], key=lambda x: -x["priority"]):
                lines.append(f"- {x['so']} {x['customer']} ({money(x['value'])}): promised {fmt_date(x['promised'])}, would arrive {fmt_date(x['new_arrival'])}, {late_text(x['days_late'])}, priority {x['priority']}")
        else:
            lines.append("No order would miss its promised date.")
        if r["still_on_time"]:
            lines.append("Still on time: " + ", ".join(r["still_on_time"]) + ".")
        return "\n".join(lines), used

    # quote check: "can we promise / deliver N SKU to Customer by DATE"
    sku = re.search(r"\b([A-Z]{2,3}-\d{2,3})\b", q.upper())
    qty = re.search(r"\b(\d[\d,]*)\s*(?:x\s*)?(?:[A-Z]{2,3}-\d{2,3}|units?|crates?|boxes|tags|packs|liners)", q, re.I)
    if sku and re.search(r"\b(promise|deliver|ship|get|send|quote|make)\b", low):
        dates = find_dates(q, date.fromisoformat(today))
        cust_name = None
        m = re.search(r"\b(?:to|for)\s+([A-Z][\w&' ]+?)(?:\s+by\b|\s+before\b|\s+on\b|\?|$)", q)
        if m:
            cust_name = m.group(1).strip()
        if not (qty and dates and cust_name):
            return "To check a quote I need a quantity, an item code, a customer and a date. For example: Can we promise 300 CC-210 to Kestrel Hotels by 20 Nov?", used
        try:
            r = tool("check_quote", {"customer": cust_name, "sku": sku.group(1), "qty": int(qty.group(1).replace(",", "")), "requested": dates[-1].value})
        except ValueError as e:
            return str(e), used
        want = fmt_date(dates[-1].value)
        if r["feasible"]:
            return f"Yes. {qty.group(1)} x {sku.group(1)} can reach {cust_name} by {fmt_date(r['eta'])}, inside {want}. Use the Quote desk to record it.", used
        if r["eta"]:
            txt = f"No. The earliest the full {qty.group(1)} x {sku.group(1)} can arrive is {fmt_date(r['eta'])}, after {want}."
        else:
            txt = f"No. Stock and open purchase orders are {plural(r['shortfall'], 'unit')} short, so a new PO is needed before promising a date."
        if r["split"]:
            sp = r["split"]
            txt += f" You could offer {plural(sp['now'], 'unit')} by {fmt_date(sp['now_eta'])}" + (f" and the other {plural(sp['rest'], 'unit')} by {fmt_date(sp['rest_eta'])}." if sp["rest_eta"] else " and the rest once a new PO is raised.")
        return txt + " Use the Quote desk to record the decision.", used

    if re.search(r"\b(waiting|pending|approv|need[s]?\s+(?:me|a person|someone)|to do|my queue)\b", low):
        r = tool("waiting_for_people")
        lines = []
        if r["waiting_runs"]:
            lines.append(f"{plural(len(r['waiting_runs']), 'check or decision').replace('check or decisions', 'checks or decisions')} waiting:")
            lines += [f"- {t}" for t in r["waiting_runs"]]
        if r["approvals"]:
            lines.append(f"{plural(len(r['approvals']), 'customer update')} waiting:")
            lines += [f"- {a['so']} {a['customer']} ({money(a['value'])}): {a['status']}" for a in r["approvals"]]
        return ("\n".join(lines) + "\nOpen Approvals and checks to act on them.") if lines else "Nothing is waiting for a person right now.", used

    if re.search(r"\b(late|behind|at risk|delayed|miss(?:ing)?)\b", low) and not po_id and not so:
        orders = tool("list_orders")
        late = [o for o in orders if o["days_late"]]
        if not late:
            return f"No open orders are late. All {len(orders)} arrive by their promised dates.", used
        lines = [f"{len(late)} of {len(orders)} open {'order is' if len(orders) == 1 else 'orders are'} late:"]
        for o in sorted(late, key=lambda o: -(o["days_late"] or 99)):
            lines.append(f"- {o['so']} {o['customer']} ({money(o['value'])}): promised {fmt_date(o['promised'])}, now {fmt_date(o['eta'])}, {late_text(o['days_late'])}" + (f", waiting on {o['po']}" if o["po"] else ""))
        return "\n".join(lines), used

    if so:
        sid = f"SO-{so.group(1)}"
        o = next((x for x in tool("list_orders") if x["so"] == sid), None)
        if not o:
            return f"I cannot find {sid} in the ERP.", used
        state = late_text(o["days_late"])
        return f"{sid} for {o['customer']}: {o['qty']:,} x {o['sku']}, worth {money(o['value'])}. Promised {fmt_date(o['promised'])}, arriving {fmt_date(o['eta'])}, so {state}." + (f" It waits on {o['po']}." if o["po"] else " It ships from stock."), used

    if po_id:
        p = next((x for x in tool("list_purchase_orders") if x["po"] == po_id), None)
        if not p:
            return f"{po_id} is not an open purchase order in the ERP.", used
        deps = [o for o in tool("list_orders") if o["po"] == po_id]
        now = arrivals(p["arrival_now"])
        orig = ", ".join(fmt_date(d["date"]) for d in p["arrival_original"])
        txt = f"{po_id} from {p['supplier']} ({p['sku']}) arrives {now}" + (f" (originally {orig})." if p["arrival_now"] != p["arrival_original"] else ".")
        if deps:
            txt += f" {plural(len(deps), 'order')} {'waits' if len(deps) == 1 else 'wait'} on it: " + ", ".join(f"{o['so']} {o['customer']}" + (f" ({late_text(o['days_late'])})" if o["days_late"] else "") for o in deps) + "."
        return txt, used

    for name_word in re.findall(r"[A-Z][a-z]+", q):
        try:
            c = tool("get_customer", {"name": name_word})
        except ValueError:
            used.pop()
            continue
        orders = [o for o in tool("list_orders") if o["customer"] == c["name"]]
        txt = (f"{c['name']}: tier {c['tier']}, {money(c['arr'])} a year, renewal {fmt_date(c['renewal'])}. Contact {c['contact']}, account owner {c['owner']}, {c['lane']} lane.")
        if orders:
            txt += " Open orders: " + "; ".join(f"{o['so']} promised {fmt_date(o['promised'])}, " + late_text(o["days_late"]) for o in orders) + "."
        if c.get("notes"):
            txt += " Latest note: " + c["notes"][0]
        return txt, used

    return HELP, used
