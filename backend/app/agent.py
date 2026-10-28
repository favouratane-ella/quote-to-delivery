"""The Quote-to-Delivery agent.

It wakes on a trigger (a supplier email, an ERP change or a quote), then works
through traced steps. Each step records its kind:

  event   something changed in a system
  read    the agent read data from a system
  ai      Claude made a judgement (prompt and raw reply are stored)
  rules   the keyword reader or a template stood in for Claude
  code    deterministic calculation (engine.py)
  guard   a guardrail check decided what happens next
  write   the agent wrote to a system
  person  a person acted
  wait    the agent is waiting (for Claude or for a person)
  done    the run finished

Claude only reads and writes language. Dates, quantities, money and routing are code.
"""
from __future__ import annotations

import copy
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models as m
from . import prompts
from .config import settings
from .agent_inventory import INTERNAL, InventoryMixin
from .agent_recovery import RecoveryMixin
from .connectors.simulated import SimulatedSystems
from .engine import Engine, days_between, fmt_date, money, plural
from .llm import get_llm, parse_json
from .rules_reader import read_email as rules_read


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


TYPE_LABEL = {"delay": "delivery delay", "partial": "split delivery", "confirmation": "confirmation, no change",
              "unclear": "possible change, no firm date", "other": "not about a delivery date"}


def type_label(t: str) -> str:
    return TYPE_LABEL.get(t, t)


class Agent(InventoryMixin, RecoveryMixin):
    def __init__(self, db: Session, world_id: str = "main", llm=None, delay_ms: int | None = None):
        self.db, self.w = db, world_id
        self.sys = SimulatedSystems(db, world_id)
        self.llm = llm if llm is not None else get_llm()
        self.delay = (settings.AGENT_STEP_DELAY_MS if world_id == "main" else 0) if delay_ms is None else delay_ms
        self.cfg = db.get(m.Settings, world_id)
        self.today = settings.today

    # ---------- plumbing ----------
    def use_ai(self) -> bool:
        return self.cfg.ai_mode == "auto" and bool(getattr(self.llm, "available", False))

    def engine(self) -> Engine:
        return Engine(self.sys.snapshot(self.today))

    def pace(self) -> None:
        if self.delay:
            time.sleep(self.delay / 1000)

    def log(self, actor: str, system: str, text: str) -> None:
        self.db.add(m.ActivityLog(world_id=self.w, at=utcnow(), actor=actor, system=system, text=text))
        self.db.commit()

    def new_run(self, trigger: dict, title: str) -> m.Run:
        run = m.Run(world_id=self.w, trigger=trigger, title=title, status="running", mode="ai" if self.use_ai() else "rules", started_at=utcnow())
        self.db.add(run)
        self.db.commit()
        return run

    def step(self, run: m.Run, kind: str, system: str, title: str, text: str = "", **payload) -> m.RunStep:
        seq = (max((s.seq for s in run.steps), default=0)) + 1
        s = m.RunStep(run_id=run.id, seq=seq, kind=kind, system=system, title=title, text=text or "",
                      payload=payload or None, at_seconds=round((utcnow() - run.started_at).total_seconds(), 1))
        run.steps.append(s)
        self.db.commit()
        return s

    def clear_waits(self, run: m.Run) -> None:
        for s in [s for s in run.steps if s.kind == "wait"]:
            run.steps.remove(s)
        self.db.commit()

    def finish(self, run: m.Run, status: str, text: str) -> None:
        run.status, run.ended_at = status, utcnow()
        self.step(run, "done", "Agent", "Run finished", text)

    # ---------- trigger: supplier email ----------
    def run_email(self, email_id: int) -> m.Run | None:
        e = self.sys.get_email(email_id)
        if not e or e["run_id"]:
            return None
        run = self.new_run({"type": "email", "email_id": email_id}, "Supplier email: " + e["subject"])
        self.sys.set_status(email_id, "Agent working", run.id)
        self.step(run, "event", "Supplier mailbox", "New email arrived", f'From {e["sender"]}: "{e["subject"]}". The agent wakes up.'); self.pace()
        if e["sender"] in INTERNAL:  # a stock note from our own warehouse, not a supplier email
            return self._run_stock_note(run, e)
        att = e.get("attachment")
        self.step(run, "read", "Supplier mailbox", "Read the email" + (" and attachment" if att else ""),
                  (f"Attachment: {att['name']}. " if att else "") + f"{plural(len(e['body']), 'character')}.", data=prompts.email_text(e)); self.pace()
        pos = self.sys.list_pos()
        self.step(run, "read", "ERP", "Look up open purchase orders", f"{plural(len(pos), 'open PO')} loaded for matching.", data=_json(prompts.po_context(pos))); self.pace()
        ext = None
        if run.mode == "ai":
            prompt = prompts.read_email(pos, e, self.today)
            self.step(run, "wait", "Claude", "Asking Claude to read the email", "Sent the email and the PO list. Waiting for structured fields back.")
            try:
                raw = self.llm.complete(prompt, 800)
                v = parse_json(raw)
                ext = {"type": str(v.get("type") or "other"), "po": str(v["po"]).upper() if v.get("po") else None, "new_date": v.get("new_date") or None,
                       "split": [{"qty": int(x["qty"]), "date": str(x["date"])} for x in v["split"]] if isinstance(v.get("split"), list) and v["split"] else None,
                       "confidence": max(0.0, min(1.0, float(v.get("confidence") or 0))), "summary": str(v.get("summary") or ""), "reader": "ai"}
                self.clear_waits(run)
                self.step(run, "ai", "Claude", "Read the email: " + type_label(ext["type"]), ext["summary"], fields=ext,
                          data=f"PROMPT SENT TO CLAUDE\n\n{prompt}\n\n----------\nCLAUDE REPLIED\n\n{raw}")
            except Exception as err:  # noqa: BLE001
                self.clear_waits(run)
                self.step(run, "guard", "Claude", f"AI read failed: {type(err).__name__}", "Falling back to the rules reader so the run can continue.")
        if not ext:
            text = e["subject"] + "\n" + e["body"] + ("\n" + "\n".join(" ".join(r) for r in att["rows"]) if att else "")
            ext = rules_read(text, self.today, {p["po"]: max(d["date"] for d in p["deliveries"]) for p in pos}, subject=e["subject"])
            self.step(run, "rules", "Rules engine", "Read the email: " + type_label(ext["type"]), ext["summary"], fields=ext)
        self.pace()
        ext["sender"] = e["sender"]
        self._decide_email(run, ext)
        return run

    def email_checks(self, ext: dict) -> list[dict]:
        """Every check must pass before the agent changes the ERP on its own."""
        p = self.sys.get_po(ext["po"]) if ext.get("po") else None
        cur = max(d["date"] for d in p["deliveries"]) if p else None
        nd = ext.get("new_date")
        date_ok = bool(nd and len(nd) == 10 and nd[4] == "-" and nd >= self.today)
        horizon_ok = bool(date_ok and days_between(nd, self.today) <= 120)
        checks = [
            {"ok": ext["type"] in ("delay", "partial"), "label": f"Email changes a delivery date ({type_label(ext['type'])})"},
            {"ok": bool(p), "label": (ext["po"] + (" exists in the ERP" if p else " is not an open PO in the ERP")) if ext.get("po") else "No PO number found"},
        ]
        sender = (ext.get("sender") or "").strip().lower()
        if p and sender:
            same = sender == p["supplier"].lower()
            checks.append({"ok": same, "label": f"Sender matches the PO's supplier ({p['supplier']})" if same else f"Sender {ext['sender']} is not the supplier on {p['po']} ({p['supplier']})"})
        checks += [
            {"ok": date_ok, "label": f"New date {fmt_date(nd)} is a valid future date" if date_ok else ("New date is in the past" if nd else "No valid new date found")},
            {"ok": horizon_ok or not date_ok, "label": "New date is within 120 days" if horizon_ok or not date_ok else f"New date {fmt_date(nd)} is more than 120 days away; check it"},
            {"ok": bool(p and date_ok and nd != cur), "label": f"Date already matches the ERP ({fmt_date(cur)})" if p and date_ok and nd == cur else "New date differs from the ERP" + (f" ({fmt_date(cur)})" if cur else "")},
        ]
        if ext["type"] == "partial" and p:
            total = sum(d["qty"] for d in p["deliveries"])
            got = sum(int(x["qty"]) for x in (ext.get("split") or []))
            checks.append({"ok": got == total, "label": f"Split quantities add up to the PO ({got} of {total})" if got == total else f"Split quantities add up to {got}, but the PO is for {total}"})
        checks.append({"ok": ext["confidence"] >= self.cfg.pass_mark, "label": f"Confidence {round(ext['confidence'] * 100)}% vs pass mark {round(self.cfg.pass_mark * 100)}%"})
        return checks

    def _decide_email(self, run: m.Run, ext: dict) -> None:
        eid = run.trigger["email_id"]
        e = self.sys.get_email(eid)
        if ext["type"] in ("confirmation", "other"):
            p = self.sys.get_po(ext["po"]) if ext.get("po") else None
            self.step(run, "guard", "Agent code", "Decide: no change needed",
                      "The supplier confirms the current date. The ERP is left as it is." if ext["type"] == "confirmation" else "The email is not about a delivery date.",
                      checks=[{"ok": True, "label": "Nothing to change" + (f": {p['po']} stays {fmt_date(max(d['date'] for d in p['deliveries']))}" if p else "")}])
            self.step(run, "write", "Supplier mailbox", "File the email", "Marked as handled. No ERP or customer changes.")
            self.sys.set_status(eid, "Filed, no change")
            self.finish(run, "no_action", "No action needed.")
            self.log("Agent", "Email", f'Filed "{e["subject"]}": {type_label(ext["type"])}.')
            return
        checks = self.email_checks(ext)
        ok = all(c["ok"] for c in checks)
        self.step(run, "guard", "Agent code", "Decide: safe to update the ERP" if ok else "Decide: a person must check this first",
                  "All guardrail checks passed." if ok else "At least one check failed, so the agent will not change the ERP on its own.", checks=checks)
        if not ok:
            run.status, run.pending = "waiting_person", {"ext": ext}
            self.sys.set_status(eid, "Waiting for a person")
            self.step(run, "wait", "Planner", "Waiting for the planner", "The planner confirms or corrects the fields, or dismisses the email.")
            self.log("Agent", "Email", f'Asked the planner to check "{e["subject"]}".')
            return
        self._apply(run, ext, "Agent")

    def _apply(self, run: m.Run, ext: dict, by: str) -> None:
        p = self.sys.get_po(ext["po"])
        before = copy.deepcopy(p["deliveries"])
        total = sum(d["qty"] for d in before)
        if ext["type"] == "partial" and ext.get("split"):
            after = [{"qty": int(x["qty"]), "date": x["date"]} for x in ext["split"]]
            diff = total - sum(d["qty"] for d in after)
            after[-1]["qty"] += diff
            after[-1]["date"] = ext["new_date"]
        else:
            after = [{"qty": total, "date": ext["new_date"]}]
        self.sys.update_po_deliveries(p["po"], after)
        sched = ", ".join(f"{d['qty']} on {fmt_date(d['date'])}" for d in after)
        self.step(run, "write", "ERP", f"Update {p['po']} arrival", ", ".join(fmt_date(d["date"]) for d in before) + " → " + sched + ("" if by == "Agent" else f" (confirmed by {by})"))
        self.log(by, "ERP", f"{p['po']} arrival changed to {sched}.")
        if run.trigger.get("email_id"):
            self.sys.set_status(run.trigger["email_id"], "Applied to ERP")
        self.pace()
        self._impact_and_draft(run, p["po"], before, after)

    # ---------- find, rank, draft, route ----------
    def _impact_and_draft(self, run: m.Run, po_id: str, before: list[dict], after: list[dict]) -> None:
        en = self.engine()
        imp = en.impact_of(po_id, before, after)
        rows = imp["affected"] + imp["fine"]
        cust = en.s.customers
        self.step(run, "read", "ERP", f"Load orders waiting on {po_id}", f"{plural(len(rows), 'sales order')} {'depends' if len(rows) == 1 else 'depend'} on this purchase order.",
                  data=_json([{"so": o["so"], "customer": cust[o["customer_id"]]["name"], "qty_from_po": o["po_qty"], "promised": o["promised"], "lane": cust[o["customer_id"]]["lane"]} for o in en.s.orders if o["po"] == po_id])); self.pace()
        self.step(run, "code", "Agent code", "Recalculate delivery dates",
                  f"{len(imp['affected'])} of {plural(len(rows), 'order')} now {'misses' if len(imp['affected']) == 1 else 'miss'} the promised date. Arrival = supply date + carrier transit.",
                  table={"head": ["Order", "Customer", "Promised", "Before", "Now", "Result"],
                         "rows": [[r["so"], cust[r["customer_id"]]["name"], fmt_date(r["promised"]), fmt_date(r["before"]), fmt_date(r["after"]),
                                   ("Late " + (f"{r['days_late']}d" if r["days_late"] is not None else "(no supply)")) if r["late"] and r["moved"] else "On time"] for r in rows]}); self.pace()
        run.result = {"affected": [a["so"] for a in imp["affected"]]}
        self.db.commit()
        self.open_cases(run, imp, po_id)
        if not imp["affected"]:
            self.step(run, "guard", "Agent code", "Decide: no customer needs telling",
                      f"Every order on {po_id} still arrives by its promised date." if rows else f"No orders wait on {po_id}.", checks=[{"ok": True, "label": "No late orders"}])
            self.finish(run, "done", "ERP updated. No customer impact.")
            self.log("Agent", "ERP", f"Checked {plural(len(rows), 'order')} on {po_id}: none late.")
            return
        self.step(run, "code", "Agent code", "Rank customers by priority",
                  "Score = order value (up to 40) + customer tier (up to 25) + renewal within 45 days (20) + days late (up to 15).",
                  table={"head": ["#", "Customer", "Value", "Tier", "Renewal", "Late", "Score"],
                         "rows": [[str(i + 1), cust[a["customer_id"]]["name"], money(a["value"]), f"{cust[a['customer_id']]['tier']} +{a['risk']['parts']['tier']}",
                                   f"in {a['risk']['to_renewal']}d +20" if a["risk"]["parts"]["renewal"] else "no", (f"{a['days_late']}d" if a["days_late"] is not None else "no supply") + f" +{a['risk']['parts']['late']}",
                                   f"{a['risk']['score']} {a['risk']['level']}"] for i, a in enumerate(imp["affected"])]}); self.pace()
        orders = {o["so"]: o for o in en.s.orders}
        facts = []
        for a in imp["affected"]:
            c, o = cust[a["customer_id"]], orders[a["so"]]
            it = en.s.items[o["sku"]]
            facts.append({"so": a["so"], "company": c["name"], "contact_first_name": c["contact"].split(" ")[0], "sender": c["owner"], "item": it["name"], "qty": o["qty"],
                          "unit": it["unit"], "promised": fmt_date(a["promised"]), "new_date": fmt_date(a["after"]), "days_late": a["days_late"],
                          "renewal_in_days": days_between(c["renewal"], self.today), "units_free_in_stock_now": min(en.free_stock(o["sku"]), o["qty"])})
        self.step(run, "read", "CRM", "Look up contacts and account context", f"Contact names, account owners and renewal dates for {plural(len(facts), 'customer')}.", data=_json(facts)); self.pace()
        drafts, reader = None, "rules"
        if run.mode == "ai":
            prompt = prompts.draft_updates(en.s.pos[po_id]["supplier"], po_id, facts, self.cfg.tone)
            self.step(run, "wait", "Claude", f"Asking Claude to write {plural(len(facts), 'customer update')}", "Sent the facts above. Waiting for drafts.")
            try:
                raw = self.llm.complete(prompt, 3000)
                v = parse_json(raw)
                if isinstance(v, list):
                    drafts, reader = v, "ai"
                self.clear_waits(run)
                self.step(run, "ai", "Claude", "Write customer updates and CRM notes", f"{plural(len(drafts or []), 'draft')} written from the facts only.",
                          data=f"PROMPT SENT TO CLAUDE\n\n{prompt}\n\n----------\nCLAUDE REPLIED\n\n{raw}")
            except Exception as err:  # noqa: BLE001
                self.clear_waits(run)
                self.step(run, "guard", "Claude", f"AI drafting failed: {type(err).__name__}", "Using message templates instead.")
        if not drafts:
            self.step(run, "rules", "Rules engine", "Write customer updates from templates", f"Template in the \"{self.cfg.tone}\" tone, filled only with the facts above. Nothing is invented.")
        self.pace()
        items, checks = [], []
        for i, a in enumerate(imp["affected"]):
            hit = next((d for d in (drafts or []) if isinstance(d, dict) and d.get("so") == a["so"]), None)
            d = hit or self._template(en, a, facts[i])
            subj, body = str(d.get("subject") or ""), str(d.get("body") or "")
            wording_ok = fmt_date(a["after"]) in subj + body and a["so"] in subj + body
            big = a["value"] >= self.cfg.approval_limit
            status = "Needs approval" if big or not wording_ok else "Ready"
            reason = (f"Order worth {money(a['value'])} (limit {money(self.cfg.approval_limit)})" if big else
                      "Wording check failed: new date or order number missing" if not wording_ok else
                      f"Under {money(self.cfg.approval_limit)} and wording check passed")
            items.append(m.Approval(world_id=self.w, run_id=run.id, so=a["so"], customer_id=a["customer_id"], value=a["value"], subject=subj, body=body,
                                    note=str(d.get("crm_note") or ""), reader=reader if hit else "rules", wording_ok=wording_ok, status=status, reason=reason, rank=i + 1, new_date=a["after"]))
            checks.append({"ok": wording_ok, "label": f"{a['so']} {cust[a['customer_id']]['name']}: " + ("states order and new date" if wording_ok else "missing order or date") + " → " + ("manager approval" if status == "Needs approval" else "one check")})
        need = sum(1 for x in items if x.status == "Needs approval")
        self.step(run, "guard", "Agent code", "Check wording and route for approval", f"{need} {'needs' if need == 1 else 'need'} the ops manager; {len(items) - need} can go after one check.", checks=checks); self.pace()
        self.db.add_all(items)
        self.db.commit()
        self.step(run, "write", "Approvals", f"Queue {plural(len(items), 'update')} for people", "Nothing is sent to a customer until a person approves it.")
        run.status = "waiting_approval"
        self.step(run, "wait", "Ops manager", "Waiting for approvals", "Each approval or rejection is added to this run.")
        self.log("Agent", "Approvals", f"Queued {plural(len(items), 'customer update')} for {po_id} ({'AI drafts' if reader == 'ai' else 'templates'}).")

    def _template(self, en: Engine, a: dict, f: dict) -> dict:
        """Deterministic customer update. Wording follows the tone set in Settings."""
        free, unit, so = f["units_free_in_stock_now"], f["unit"], a["so"]
        tone = (self.cfg.tone or "").lower()
        if tone.startswith("short"):
            subject = f"{so}: new delivery date {f['new_date']}"
            body = (f"Hi {f['contact_first_name']},\n\nOrder {so} will now arrive {f['new_date']}, not {f['promised']}, because of a supplier delay. Sorry about that."
                    + (f" We can send {free} {unit} from stock now if that helps." if free else " Reply if you need part of it sooner.")
                    + f"\n\n{f['sender']}\nOrder desk")
        elif tone.startswith("formal"):
            subject = f"Revised delivery date for order {so}"
            body = (f"Dear {f['contact_first_name']},\n\nWe regret to inform you that, owing to a delay at our supplier, order {so} ({f['qty']} {unit}) is now scheduled to arrive on {f['new_date']} rather than {f['promised']}. "
                    "We apologise for the inconvenience.\n\n"
                    + (f"Should it be helpful, we can dispatch {free} {unit} from stock immediately, with the balance to follow." if free else "Please let us know if an earlier part delivery would assist, and we will review the options.")
                    + f"\n\nKind regards,\n{f['sender']}\nOrder desk")
        else:
            subject = f"Order {so}: new delivery date {f['new_date']}"
            body = (f"Hi {f['contact_first_name']},\n\nA delay from our supplier means order {so} ({f['qty']} {unit}) will now arrive on {f['new_date']} instead of {f['promised']}. We are sorry for the change.\n\n"
                    + (f"If it helps, we can send up to {free} {unit} from stock right away and the rest when the supply lands." if free else "If you need part of the order sooner, reply and we will see what we can move.")
                    + f"\n\nBest,\n{f['sender']}\nOrder desk")
        note = f"Delay notice for {so}: new date {f['new_date']} (was {f['promised']})."
        if 0 <= f["renewal_in_days"] <= 45:
            note += f" Renewal due in {f['renewal_in_days']} days; suggest a call today."
        return {"subject": subject, "body": body, "crm_note": note}

    # ---------- people ----------
    def resolve_check(self, run_id: int, fields: dict | None, by: str = "Planner") -> None:
        run = self.db.get(m.Run, run_id)
        if not run or run.status != "waiting_person" or run.trigger.get("type") != "email":
            raise ValueError("This run is not waiting for a planner check.")
        if run.pending and "stock" in run.pending:
            return self.resolve_stock(run, fields, by)
        eid = run.trigger["email_id"]
        self.clear_waits(run)
        if fields is None:
            self.step(run, "person", by, "Dismissed: no change", "The planner decided this email needs no ERP change.")
            self.sys.set_status(eid, "Dismissed by planner")
            self.finish(run, "no_action", "Nothing changed.")
            self.log(by, "Email", f"Dismissed \"{self.sys.get_email(eid)['subject']}\".")
            return
        ext = {**run.pending["ext"], **fields, "confidence": 1.0}
        if not self.sys.get_po(ext["po"]) or not ext.get("new_date"):
            raise ValueError("Pick an open PO and a new date.")
        self.step(run, "person", by, "Checked and confirmed the fields", f"{ext['po']}, {type_label(ext['type'])}, new date {fmt_date(ext['new_date'])}.")
        run.status, run.pending = "running", None
        self.db.commit()
        self._apply(run, ext, by)

    def decide_approval(self, approval_id: int, send: bool, edits: dict | None = None, by: str | None = None) -> m.Approval:
        a = self.db.get(m.Approval, approval_id)
        if not a or a.world_id != self.w or a.status in ("Sent", "Rejected"):
            raise ValueError("This update is not waiting for a decision.")
        edits = edits or {}
        edited = any(k in edits and edits[k] is not None and edits[k] != getattr(a, k) for k in ("subject", "body"))
        for k in ("subject", "body", "note"):
            if edits.get(k) is not None:
                setattr(a, k, edits[k])
        c = self.sys.get_customer(a.customer_id)
        run = self.db.get(m.Run, a.run_id)
        if run:
            self.clear_waits(run)
        who = by or ("Ops manager" if a.status == "Needs approval" else "Account manager")
        a.decided_by, a.decided_at = who, utcnow()
        if send:
            a.status = "Sent"
            self.sys.send(to=f"{c['contact']} <{c['email']}>", customer_id=a.customer_id, so=a.so, subject=a.subject, body=a.body, sent_by=who)
            self.sys.add_note(a.customer_id, a.note)
            if run:
                self.step(run, "person", who, ("Approved" if who == "Ops manager" else "Checked") + f" and sent the update to {c['name']}", "Edited the draft before sending." if edited else "Sent as drafted.")
                self.step(run, "write", "Email + CRM", f"Deliver to {c['contact']} and add a CRM note", a.note)
            self.log(who, "Email + CRM", f"Sent delay notice for {a.so} to {c['name']}.")
        else:
            a.status = "Rejected"
            if run:
                self.step(run, "person", who, f"Rejected the update to {c['name']}", "Not sent.")
            self.log(who, "Approvals", f"Rejected the draft for {a.so}.")
        self.db.commit()
        self.note_notified(a, send, who)
        if run and run.status == "waiting_approval":
            left = self.db.query(m.Approval).filter(m.Approval.run_id == run.id, m.Approval.status.in_(["Needs approval", "Ready"])).count()
            if left:
                self.step(run, "wait", "Ops manager", "Waiting for the remaining approvals", "")
            else:
                sent = self.db.query(m.Approval).filter(m.Approval.run_id == run.id, m.Approval.status == "Sent").count()
                self.finish(run, "done", f"{sent} customers told. Every step above is in the activity log.")
        return a

    # ---------- trigger: ERP change made by a person ----------
    def run_erp_change(self, po_id: str, before: list[dict], after: list[dict], by: str = "Planner") -> m.Run:
        run = self.new_run({"type": "erp", "po": po_id}, f"ERP change: {po_id} arrival moved")
        self.step(run, "event", "ERP", f"{by} changed {po_id} in the ERP",
                  ", ".join(fmt_date(d["date"]) for d in before) + " → " + ", ".join(f"{d['qty']} on {fmt_date(d['date'])}" for d in after) + ". The agent wakes up."); self.pace()
        self._impact_and_draft(run, po_id, before, after)
        return run

    # ---------- trigger: quote ----------
    def run_quote(self, q: str) -> m.Run:
        quote = self.sys.get_quote(q)
        en = self.engine()
        c = en.s.customers[quote["customer_id"]]
        run = self.new_run({"type": "quote", "q": q}, f"Quote check: {q} for {c['name']}")
        self.sys.update_quote(q, run_id=run.id, status="Agent checking")
        self.step(run, "event", "CRM", f"Sales rep submitted {q}", f"{quote['qty']} × {quote['sku']} for {c['name']}, wanted by {fmt_date(quote['requested'])}."); self.pace()
        r = en.check_quote(quote["customer_id"], quote["sku"], quote["qty"], quote["requested"])
        self.step(run, "read", "ERP", f"Read stock and inbound purchase orders for {quote['sku']}",
                  f"On hand {en.s.items[quote['sku']]['on_hand']}, not yet reserved {r['steps'][0]['qty']}.", data=_json(r["steps"])); self.pace()
        self.step(run, "read", "Carrier lanes", f"Read transit time to {c['name']}", f"{c['lane']} lane: {r['transit_days']} days."); self.pace()
        self.step(run, "code", "Agent code", "Work out the earliest delivery date",
                  f"Full quantity can arrive {fmt_date(r['eta'])}." if r["covered"] else f"Supply is {r['shortfall']} {r['unit']} short.",
                  table={"head": ["Supply", "Available", "Ready"], "rows": [[s["label"], str(s["qty"]), "Now" if s["date"] == self.today else fmt_date(s["date"])] for s in r["steps"]] + [[f"Carrier transit ({c['lane']})", f"{r['transit_days']} days", ""]]}); self.pace()
        opts = []
        if r["feasible"]:
            opts.append({"k": "accept", "label": f"Confirm {fmt_date(quote['requested'])}"})
        else:
            if r["covered"]:
                opts.append({"k": "earliest", "label": f"Quote {fmt_date(r['eta'])} instead"})
            if r["split"]:
                sp = r["split"]
                opts.append({"k": "split", "label": f"Split: {sp['now']} by {fmt_date(sp['now_eta'])}" + (f", {sp['rest']} by {fmt_date(sp['rest_eta'])}" if sp["rest_eta"] else ", rest on a new PO")})
        if not opts:
            opts.append({"k": "hold", "label": "Hold the quote until a new PO is raised"})
        self.step(run, "guard", "Agent code", "Decide: the requested date can be met" if r["feasible"] else "Decide: the requested date cannot be met",
                  "Options for the sales rep: " + "; ".join(o["label"] for o in opts) + ".",
                  checks=[{"ok": r["covered"], "label": "Enough supply for the full quantity" if r["covered"] else f"Not enough supply: {r['shortfall']} short"},
                          {"ok": r["feasible"], "label": f"Arrives by {fmt_date(quote['requested'])}" + (f" (earliest {fmt_date(r['eta'])})" if r["eta"] else "")}])
        run.result = {k: r[k] for k in ("feasible", "eta", "covered", "split", "shortfall")}
        run.options = opts
        status = "Checked: date can be met" if r["feasible"] else "Checked: date cannot be met"
        self.sys.update_quote(q, status=status)
        self.step(run, "write", "CRM", f"Write the recommendation on {q}", status + ".")
        run.status = "waiting_person"
        self.step(run, "wait", "Sales rep", "Waiting for the sales rep to choose", "The rep picks an option on the quote desk.")
        self.log("Agent", "CRM", f"{q} checked: {'can be met' if r['feasible'] else 'cannot be met'}.")
        return run

    def choose_quote(self, q: str, option: str) -> m.Run:
        quote = self.sys.get_quote(q)
        run = self.db.get(m.Run, quote["run_id"]) if quote else None
        if not run or run.status != "waiting_person":
            raise ValueError("This quote is not waiting for a decision.")
        o = next((x for x in run.options or [] if x["k"] == option), None)
        if not o:
            raise ValueError("Unknown option.")
        self.clear_waits(run)
        self.sys.update_quote(q, status=o["label"], final=True)
        self.step(run, "person", "Sales rep", "Chose: " + o["label"])
        self.step(run, "write", "CRM", f"Update {q} and add a note", o["label"])
        self.sys.add_note(quote["customer_id"], f"{q}: {o['label']}.")
        self.finish(run, "done", "Quote updated in the CRM.")
        self.log("Sales rep", "CRM", f"{q}: {o['label']}.")
        return run


def _json(v) -> str:
    import json

    return json.dumps(v, indent=1, default=str)
