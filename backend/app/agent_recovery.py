"""What happens after a customer has been told: cases, replies and recovery.

A *case* is opened for every order a supplier delay pushes past its promised date. It is closed when
the order is back to low risk: the date was kept, the customer agreed a new one, or the order was
split. This module reads the customer's reply, works out the options (recovery.py), proposes the best
one for a person to approve, applies it, and keeps the case timeline.

Same guardrails as the rest of the agent: the agent never changes the ERP on a hunch and never sends
a customer message without a person. The one exception is applying a change the customer has just
agreed to in writing (for example "that date works for us").
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import models as m
from .customer_sim import compose_reply
from .engine import Engine, add_days, days_between, fmt_date, money, plural
from .recovery import options_for
from .reply_reader import INTENT_LABEL, read_reply


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _first(name: str) -> str:
    return name.split(" ")[0]


class RecoveryMixin:
    # ---------- cases ----------
    def case(self, so: str, open_only: bool = True) -> m.OrderCase | None:
        q = self.db.query(m.OrderCase).filter(m.OrderCase.world_id == self.w, m.OrderCase.so == so)
        if open_only:
            q = q.filter(m.OrderCase.status.notin_(["resolved", "lost"]))
        return q.order_by(m.OrderCase.id.desc()).first()

    def event(self, so: str, actor: str, kind: str, text: str) -> None:
        self.db.add(m.CaseEvent(world_id=self.w, so=so, at=_now(), actor=actor, kind=kind, text=text))
        self.db.commit()

    def open_cases(self, run: m.Run, imp: dict, po_id: str) -> None:
        """Called after a PO date changes: open or update a case for every late order, close the ones that recovered by themselves."""
        for a in imp["affected"]:
            c = self.case(a["so"])
            note = f"{po_id} moved: now arrives {fmt_date(a['after'])}, " + (f"{plural(a['days_late'], 'day')} after the promised date" if a["days_late"] is not None else "no supply date")
            if c:
                c.eta, c.days_late, c.reason = a["after"], a["days_late"], f"{po_id} moved again"
                self.db.commit()
                self.event(a["so"], "System", "system", "Date moved again. " + note)
            else:
                self.db.add(m.OrderCase(world_id=self.w, so=a["so"], status="at_risk", run_id=run.id, reason=f"{po_id} delayed", original_promised=a["promised"], eta=a["after"], days_late=a["days_late"]))
                self.db.commit()
                self.event(a["so"], "System", "system", "Flagged as at risk. " + note)
        for r in imp["fine"]:
            c = self.case(r["so"])
            if c and r["moved"] and not r["late"]:
                self.close_case(c, "supply_recovered", f"{po_id} now arrives in time, so the order is back on schedule.")

    def close_case(self, c: m.OrderCase, resolution: str, text: str, actor: str = "System") -> None:
        c.status, c.resolution, c.closed_at, c.pending_proposal = "resolved", resolution, _now(), None
        self.db.commit()
        self.event(c.so, actor, "system", text)

    def note_notified(self, a: m.Approval, sent: bool, who: str) -> None:
        c = self.case(a.so)
        if not c:
            return
        if sent:
            c.status = "notified"
            self.db.commit()
            self.event(a.so, who, "person", f"Update sent to the customer: new date {fmt_date(a.new_date)}.")
        else:
            self.event(a.so, who, "person", "Customer update rejected, so the customer has not been told.")

    # ---------- stock already promised to pending proposals ----------
    def engine_held(self, exclude: int | None = None) -> Engine:
        """The engine, with stock that pending proposals have already claimed taken out of what looks free."""
        snap = self.sys.snapshot(self.today)
        for p in self.db.query(m.Proposal).filter(m.Proposal.world_id == self.w, m.Proposal.status == "Proposed"):
            if p.id == exclude or not p.detail:
                continue
            d, sku = p.detail, p.detail.get("sku")
            holds = {"stock": [(sku, d.get("units", 0))], "split": [(sku, d.get("now", 0))], "reallocate": [(sku, d.get("free_used", 0))],
                     "substitute": [(sku, d.get("main", 0)), (d.get("sub"), d.get("sub_units", 0))]}.get(p.kind, [])
            for k, n in holds:
                if k in snap.items and n:
                    snap.items[k]["on_hand"] = max(0, snap.items[k]["on_hand"] - n)
        return Engine(snap)

    # ---------- customer replies ----------
    def make_reply(self, so: str, stage: str = "notice", proposal: m.Proposal | None = None, text: str | None = None, source: str = "simulated") -> m.CustomerReply | None:
        o = self.sys.get_order(so)
        if not o:
            raise ValueError(f"Unknown order {so}.")
        if not self.case(so):
            return None
        en = self.engine()
        cust = en.s.customers[o.customer_id]
        od = next(x for x in en.s.orders if x["so"] == so)
        view = en.order_view(od)
        if text is None:
            composed = compose_reply(cust, od, en.s.items[o.sku]["unit"], view["eta"], stage, proposal.meets_promised if proposal else True)
            if not composed:
                return None
            subject, body = composed
        else:
            subject, body = f"Re: Order {so}", text
        r = m.CustomerReply(world_id=self.w, so=so, customer_id=o.customer_id, at=_now(), subject=subject, body=body, source=source)
        self.db.add(r)
        self.db.commit()
        self.event(so, cust["contact"], "customer", "Replied to us.")
        self.log(cust["name"], "Customer", f"Replied about {so}.")
        return r

    def sim_followup(self, so: str, stage: str = "notice", proposal_id: int | None = None) -> int | None:
        """A simulated customer answers, if simulated customers are switched on."""
        if not self.cfg.sim_customers:
            return None
        prop = self.db.get(m.Proposal, proposal_id) if proposal_id else None
        r = self.make_reply(so, stage, prop)
        return r.id if r else None

    def run_reply(self, reply_id: int) -> m.Run | None:
        r = self.db.get(m.CustomerReply, reply_id)
        if not r or r.world_id != self.w or r.run_id:
            return None
        en = self.engine()
        cust = en.s.customers[r.customer_id]
        o = next((x for x in en.s.orders if x["so"] == r.so), None)
        case = self.case(r.so)
        run = self.new_run({"type": "reply", "reply_id": r.id, "so": r.so}, f"Customer reply: {cust['name']} on {r.so}")
        r.run_id, r.status = run.id, "Reading"
        self.db.commit()
        self.step(run, "event", "Customer mailbox", "Customer replied", f'{cust["contact"]} at {cust["name"]}: "{r.subject}". The agent wakes up.'); self.pace()
        self.step(run, "read", "Customer mailbox", "Read the reply", f"{plural(len(r.body), 'character')}.", data=f"From: {cust['contact']} <{cust['email']}>\nSubject: {r.subject}\n\n{r.body}"); self.pace()
        view = en.order_view(o) if o else None
        facts = {"order": r.so, "promised": fmt_date(o["promised"]) if o else None, "arriving now": fmt_date(view["eta"]) if view else None, "days late": view["days_late"] if view else None,
                 "customer flexibility": {"hard": "hard deadline", "partial": "accepts part deliveries", "flexible": "flexible on dates"}[cust["flex"]], "can live with (days late)": cust["max_slip"],
                 "why": cust.get("hard_reason") or "none recorded", "case": case.status if case else "no open case"}
        self.step(run, "read", "CRM + ERP", "Look up the customer and the order", f"{cust['name']}: {facts['customer flexibility']}. Order {r.so} promised {facts['promised']}, arriving {facts['arriving now']}.",
                  table={"head": ["Fact", "Value"], "rows": [[k, str(v)] for k, v in facts.items()]}); self.pace()
        ext = read_reply(r.subject + "\n" + r.body, self.today, {"promised": o["promised"] if o else None, "eta": view["eta"] if view else None})
        self.step(run, "rules", "Rules engine", "Read the reply: " + ext["label"], "; ".join(ext["reasons"]) or "No special wording found.",
                  fields={"type": ext["intent"], "po": None, "new_date": ext["date"], "confidence": ext["confidence"], "reasons": ext["reasons"], "split": None}); self.pace()
        r.intent = ext["intent"]
        self.db.commit()
        checks = [{"ok": bool(o), "label": f"Order {r.so} exists" if o else f"Order {r.so} not found"},
                  {"ok": bool(case), "label": "There is an open case for this order" if case else "No open case: the order is not at risk"},
                  {"ok": ext["confidence"] >= self.cfg.pass_mark, "label": f"Confidence {round(ext['confidence'] * 100)}% vs pass mark {round(self.cfg.pass_mark * 100)}%"},
                  {"ok": ext["intent"] != "unclear", "label": "The reply says something the agent can act on"}]
        ok = all(c["ok"] for c in checks)
        self.step(run, "guard", "Agent code", "Decide: safe to act on this reply" if ok else "Decide: a person must read this reply", "All checks passed." if ok else "At least one check failed, so nothing changes until a person decides.", checks=checks)
        if not ok:
            r.status, run.status, run.pending = "Needs a person", "waiting_person", {"ext": ext, "reply_id": r.id}
            self.step(run, "wait", "Account manager", "Waiting for a person to read the reply", "Choose what the customer means, and the agent continues.")
            self.db.commit()
            return run
        self._act_on_reply(run, r, ext)
        return run

    def resolve_reply(self, reply_id: int, intent: str, date: str | None = None, by: str = "Account manager") -> m.Run:
        r = self.db.get(m.CustomerReply, reply_id)
        run = self.db.get(m.Run, r.run_id) if r and r.run_id else None
        if not run or run.status != "waiting_person" or intent not in INTENT_LABEL or intent == "unclear":
            raise ValueError("This reply is not waiting for a person.")
        if not self.case(r.so):
            raise ValueError("There is no open case for this order.")
        self.clear_waits(run)
        ext = {"intent": intent, "confidence": 1.0, "date": date, "flags": {"accepts": intent == "accept", "willing_to_pay": intent in ("hard_deadline", "expedite")}, "reasons": ["Chosen by a person"], "label": INTENT_LABEL[intent]}
        self.step(run, "person", by, f"Read the reply as: {ext['label']}", "The agent continues from here.")
        run.status, run.pending = "running", None
        self.db.commit()
        self._act_on_reply(run, r, ext)
        return run

    # ---------- deciding what to do ----------
    def _act_on_reply(self, run: m.Run, r: m.CustomerReply, ext: dict) -> None:
        so, intent = r.so, ext["intent"]
        case = self.case(so)
        en = self.engine_held()
        o = next(x for x in en.s.orders if x["so"] == so)
        cust = en.s.customers[o["customer_id"]]
        view = en.order_view(o)
        r.status = "Handled"
        self.db.commit()

        # the customer says yes to an offer we made
        if case.pending_proposal and intent in ("accept", "reschedule", "partial_ok"):
            prop = self.db.get(m.Proposal, case.pending_proposal)
            if prop and prop.status == "Offered":
                self.step(run, "guard", "Agent code", "Decide: the customer agreed to our offer", "Applying the change the customer just agreed to.", checks=[{"ok": True, "label": f"Offer: {prop.title}"}])
                try:
                    self._apply_proposal(prop, "Customer agreed", send=False, run=run)
                    prop.status = "Applied"
                    self.db.commit()
                    self.finish(run, "done", "Offer accepted and applied. The order is back to low risk.")
                except ValueError as e:
                    self.step(run, "guard", "Agent code", "The offer can no longer be applied", str(e), checks=[{"ok": False, "label": str(e)}])
                    run.status = "waiting_person"
                    run.pending = {"reply_id": r.id}
                    self.step(run, "wait", "Account manager", "Waiting for a person", "Things changed since the offer was made.")
                    self.db.commit()
                return
        if case.pending_proposal:
            case.pending_proposal = None
            self.db.commit()

        if not view["late"]:
            self.step(run, "guard", "Agent code", "Decide: nothing to recover", "The order is no longer late, so there is nothing to change.", checks=[{"ok": True, "label": "Order arrives by the promised date"}])
            self.finish(run, "done", "Nothing to do.")
            return

        late = view["days_late"]
        if intent == "accept" or (intent == "credit" and ext["flags"].get("accepts")):
            # the customer accepted the date we told them: write it into the order
            self.step(run, "guard", "Agent code", "Decide: the customer accepted the new date",
                      f"Moving the promised date to {fmt_date(view['eta'])}. This is a change the customer has just agreed to in writing.",
                      checks=[{"ok": True, "label": f"Reply accepts {fmt_date(view['eta'])}"}, {"ok": cust["flex"] != "hard" or late is not None, "label": f"{plural(late or 0, 'day')} later than promised (customer can live with {plural(cust['max_slip'], 'day')})"}])
            self._write_new_date(so, view["eta"], "Customer agreed", run)
            case = self.case(so)
            if case:
                self.close_case(case, "agreed", f"Customer accepted {fmt_date(view['eta'])}. Order back to low risk.", cust["contact"])
            if intent == "credit":
                self._propose(run, en, o, cust, self._credit_option(o, late), r)
                run.status = "waiting_approval"
                self.step(run, "wait", "Ops manager", "Waiting for approval of the credit", "")
                self.db.commit()
                return
            self.finish(run, "done", "New date agreed and written into the order.")
            return

        target = ext["date"] if intent in ("hard_deadline", "reschedule") else None
        if intent == "reschedule" and target and target >= view["eta"]:
            self.step(run, "guard", "Agent code", "Decide: the customer proposed a date we can meet", f"{fmt_date(target)} is not before the new arrival date {fmt_date(view['eta'])}.", checks=[{"ok": True, "label": "Proposed date is achievable"}])
            self._write_new_date(so, target, "Customer proposed", run)
            case = self.case(so)
            if case:
                self.close_case(case, "agreed", f"Customer proposed {fmt_date(target)}, which works. Order back to low risk.", cust["contact"])
            self.finish(run, "done", "Customer's date written into the order.")
            return

        if intent == "cancel":
            opt = {"kind": "escalate", "title": f"Retention call: {cust['name']} wants to cancel {so}", "summary": f"{cust['name']} has asked to cancel {so} ({money(o['value'])}). Call before the cancellation is confirmed.",
                   "new_eta": None, "meets_promised": False, "cost": 0.0, "side_effects": [f"{money(o['value'])} of revenue at stake", f"Customer is tier {cust['tier']}, worth {money(cust['arr'])} a year"],
                   "needs_customer_ok": False, "needs": "Ops manager", "detail": {"reason": "cancel"}}
            self.step(run, "guard", "Agent code", "Decide: escalate, the customer wants to cancel", f"{money(o['value'])} order, {money(cust['arr'])} account. A person must call.", checks=[{"ok": False, "label": "The agent never cancels or lets go of an order by itself"}])
            self._propose(run, en, o, cust, opt, r)
            self._set_case(so, "escalated", "Customer asked to cancel. Escalated to the ops manager.")
            return self._wait_for_approval(run)
        if intent == "question":
            opt = self._answer_option(en, o, cust)
            self.step(run, "guard", "Agent code", "Decide: the customer asked a question", "A draft answer is ready for the account manager to check.", checks=[{"ok": True, "label": "Answer drafted from the order and account data"}])
            self._propose(run, en, o, cust, opt, r)
            return self._wait_for_approval(run)
        if intent == "credit":
            self.step(run, "guard", "Agent code", "Decide: the customer wants a credit", "The credit is calculated from the days late and the order value.", checks=[{"ok": True, "label": f"{plural(late or 0, 'day')} late"}])
            self._propose(run, en, o, cust, self._credit_option(o, late), r)
            return self._wait_for_approval(run)

        # hard deadline, partial, expedite or a date earlier than we can reach: find a way to rescue the order
        res = options_for(en, so, self.cfg.approval_limit, target=target)
        self.step(run, "code", "Agent code", "Work out the ways to rescue this order",
                  f"{len(res['options'])} options" + (f" against {fmt_date(res['promised'])}." if res["promised"] else "."),
                  table={"head": ["#", "Option", "Arrives", "Keeps the date", "Cost", "Who decides"],
                         "rows": [[str(x["rank"]) + (" *" if x["recommended"] else ""), x["title"], fmt_date(x["new_eta"]) if x["new_eta"] else "-", "Yes" if x["meets_promised"] else "No", money(x["cost"]) if x["cost"] else "-", x["needs"]] for x in res["options"]]}); self.pace()
        pick = next((x for x in res["options"] if x["recommended"]), None)
        if intent in ("hard_deadline", "reschedule") and pick and not pick["meets_promised"]:
            pick = None  # the customer said no to a later date, so offering one is not an answer
        if intent == "expedite" and not pick:
            pick = next((x for x in res["options"] if x["kind"] == "expedite"), None)
        if intent == "partial_ok" and not (pick and pick["kind"] in ("stock", "split", "reallocate")):
            pick = next((x for x in res["options"] if x["kind"] in ("stock", "reallocate")), None) or next((x for x in res["options"] if x["kind"] == "split"), None) or pick
        if intent == "expedite" and pick and pick["kind"] != "expedite":
            alt = next((x for x in res["options"] if x["kind"] == "expedite" and x["meets_promised"]), None)
            pick = alt or pick
        if not pick:
            fall = [x for x in res["options"] if x["kind"] in ("split", "expedite", "supplier", "credit")]
            opt = {"kind": "escalate", "title": f"No option keeps {fmt_date(res['promised'])} for {cust['name']}", "summary": f"{cust['name']} {('has a hard deadline: ' + cust['hard_reason'].rstrip('.')) if cust['flex'] == 'hard' else 'cannot take this date'}. Stock, reallocation, express shipping and substitutes cannot keep {fmt_date(res['promised'])}. A senior person should call.",
                   "new_eta": view["eta"], "meets_promised": False, "cost": 0.0, "side_effects": [f"Best fallback: {fall[0]['title']}" if fall else "No fallback"] + [f"{money(o['value'])} order, tier {cust['tier']} customer"],
                   "needs_customer_ok": False, "needs": "Ops manager", "detail": {"reason": "no_option", "fallbacks": [{"kind": x["kind"], "title": x["title"], "new_eta": x["new_eta"], "cost": x["cost"]} for x in fall]}}
            self.step(run, "guard", "Agent code", "Decide: no option keeps the date, escalate", "Nothing available keeps the customer's date. A person must decide how to handle it.",
                      checks=[{"ok": False, "label": f"Keeps {fmt_date(res['promised'])}: no option does"}, {"ok": True, "label": "Fallbacks listed for the manager"}])
            self._propose(run, en, o, cust, opt, r)
            self._set_case(so, "escalated", f"No option keeps {fmt_date(res['promised'])}. Escalated to the ops manager.")
            return self._wait_for_approval(run)
        self.step(run, "guard", "Agent code", f"Decide: recommend {pick['title'].lower()}", pick["summary"],
                  checks=[{"ok": pick["meets_promised"] or intent == "partial_ok", "label": "Keeps the promised date" if pick["meets_promised"] else "Does not keep the date, but is the best the customer will take"},
                          {"ok": True, "label": f"Approval needed from the {pick['needs'].lower()}"}] + ([{"ok": True, "label": "Customer must say yes before anything changes"}] if pick["needs_customer_ok"] else []))
        self._propose(run, en, o, cust, pick, r)
        self._set_case(so, "plan_proposed", f"Recovery plan proposed: {pick['title']}.")
        return self._wait_for_approval(run)

    def _wait_for_approval(self, run: m.Run) -> None:
        run.status = "waiting_approval"
        self.step(run, "wait", "Ops manager", "Waiting for approval", "Nothing changes until a person approves.")
        self.db.commit()

    def _set_case(self, so: str, status: str, text: str) -> None:
        c = self.case(so)
        if c:
            c.status = status
            self.db.commit()
            self.event(so, "Agent", "system", text)

    def _credit_option(self, o: dict, late: int | None) -> dict:
        pct = 10 if late is None else min(10, 2 * late)
        amt = round(o["value"] * pct / 100, 2)
        return {"kind": "credit", "title": f"Offer a {pct}% credit ({money(amt)})", "summary": "Compensate the customer for the delay.", "new_eta": None, "meets_promised": False, "cost": amt,
                "side_effects": [f"Credit of {money(amt)}"], "needs_customer_ok": False, "needs": "Ops manager" if amt >= 500 else "Account manager", "detail": {"pct": pct, "amount": amt}}

    def _answer_option(self, en: Engine, o: dict, cust: dict) -> dict:
        others = [x for x in en.s.orders if x["customer_id"] == cust["id"] and x["so"] != o["so"]]
        lines = []
        for x in others:
            v = en.order_view(x)
            lines.append(f"{x['so']}: " + ("on track" if not v["late"] else f"now arriving {fmt_date(v['eta'])}"))
        warehouse = "our main warehouse"
        txt = (f"The order ships from {warehouse}. " + ("Your other open orders: " + "; ".join(lines) + "." if lines else "You have no other open orders, so nothing else on your account is affected."))
        return {"kind": "reply", "title": f"Answer {cust['contact'].split(' ')[0]}'s question", "summary": "A draft answer built from the order and account data.", "new_eta": None, "meets_promised": False, "cost": 0.0,
                "side_effects": [], "needs_customer_ok": False, "needs": "Account manager", "detail": {"answer": txt}}

    # ---------- proposals ----------
    def _draft(self, kind: str, o: dict, cust: dict, opt: dict, en: Engine) -> tuple[str, str, str, str]:
        """(to, subject, body, crm note). Warm and plain; facts only."""
        so, unit = o["so"], en.s.items[o["sku"]]["unit"]
        me, owner = cust["contact"].split(" ")[0], cust["owner"].split(" ")[0]
        to = f"{cust['contact']} <{cust['email']}>"
        d, sign = opt["detail"], f"\n\nBest,\n{owner}\nOrder desk"
        if kind in ("stock", "reallocate"):
            return to, f"Order {so}: back on track for {fmt_date(opt['new_eta'])}", f"Hi {me},\n\nGood news. We have found stock for order {so}, so it will now arrive on {fmt_date(opt['new_eta'])}, by your date of {fmt_date(o['promised'])}. Thank you for your patience." + sign, f"{so}: recovered from stock, arriving {fmt_date(opt['new_eta'])}."
        if kind == "expedite":
            return to, f"Order {so}: shipping express", f"Hi {me},\n\nWe will ship order {so} by express as soon as the stock lands, so it will arrive on {fmt_date(opt['new_eta'])}." + sign, f"{so}: express shipping, arriving {fmt_date(opt['new_eta'])}."
        if kind == "split":
            return to, f"Order {so}: part now, the rest on {fmt_date(d['rest_eta'])}", (f"Hi {me},\n\nWe can send {d['now']:,} {unit} now, arriving {fmt_date(d['now_eta'])}, and the remaining {d['rest']:,} {unit} on {fmt_date(d['rest_eta'])}. "
                                                                                       f"Does that work for you? Reply yes and we will go ahead." + sign), f"{so}: offered a part delivery ({d['now']} now, {d['rest']} on {fmt_date(d['rest_eta'])})."
        if kind == "substitute":
            return to, f"Order {so}: can we use {d['sub']} for part of it?", (f"Hi {me},\n\nWe can deliver all {o['qty']:,} {unit} by {fmt_date(opt['new_eta'])} if you accept {d['sub_units']:,} of them as {d['sub']} ({en.s.items[d['sub']]['name']}) "
                                                                              f"instead of {o['sku']}. Does that work for you? Reply yes and we will go ahead." + sign), f"{so}: offered {d['sub_units']} as {d['sub']} to keep the date."
        if kind == "new_date":
            return to, f"Order {so}: new delivery date {fmt_date(opt['new_eta'])}", f"Hi {me},\n\nCan we confirm {fmt_date(opt['new_eta'])} as the delivery date for order {so}? Reply yes and we will update it." + sign, f"{so}: asked to confirm {fmt_date(opt['new_eta'])}."
        if kind == "credit":
            return to, f"Order {so}: a credit for the delay", f"Hi {me},\n\nWe are sorry for the delay on order {so}. We would like to offer a credit of {money(d['amount'])} ({d['pct']}% of the order) on your next invoice." + sign, f"{so}: credit of {money(d['amount'])} offered."
        if kind == "reply":
            return to, f"Re: Order {so}", f"Hi {me},\n\n{d['answer']}" + sign, f"{so}: answered a customer question."
        if kind == "supplier":
            sup = en.s.pos[d["po"]]["supplier"]
            return sup, f"{d['po']}: can you expedite or part-ship?", f"Hello,\n\nPO {d['po']} is now late and customers are waiting. Can you part-ship what you have, or expedite the rest? Please tell us the earliest date you can commit to.\n\nThank you,\nSupply planning", f"{so}: asked {sup} to expedite {d['po']}."
        return "", "", "", f"{so}: escalated to a person."

    def _propose(self, run: m.Run, en: Engine, o: dict, cust: dict, opt: dict, reply: m.CustomerReply | None) -> m.Proposal:
        to, subject, body, note = self._draft(opt["kind"], o, cust, opt, en)
        if opt["kind"] == "supplier":
            sup = opt["detail"]["supplier"]
            row = self.db.query(m.Supplier).filter_by(world_id=self.w, name=sup).first()
            to = f"{sup} <{row.email}>" if row else sup
        detail = {**opt["detail"], "sku": o["sku"], "side_effects": opt["side_effects"], "new_eta": opt["new_eta"]}
        p = m.Proposal(world_id=self.w, run_id=run.id, so=o["so"], customer_id=cust["id"], kind=opt["kind"], title=opt["title"], summary=opt["summary"], detail=detail, cost=opt["cost"], value=o["value"],
                       meets_promised=opt["meets_promised"], needs_customer_ok=opt["needs_customer_ok"], needs=opt["needs"], to=to, subject=subject, body=body, note=note,
                       reason=("Nothing keeps the date: a senior person decides" if opt["kind"] == "escalate" and opt["detail"].get("reason") != "cancel" else "The customer wants to cancel: a senior person calls" if opt["kind"] == "escalate"
                               else "Costs " + money(opt["cost"]) if opt["cost"] >= 500 else f"Order worth {money(o['value'])} (limit {money(self.cfg.approval_limit)})" if o["value"] >= self.cfg.approval_limit
                               else "Affects another customer" if any(t.get("days_late") for t in opt["detail"].get("takes", [])) else "One check by the account manager"),
                       rank=1)
        self.db.add(p)
        self.db.commit()
        self.step(run, "write", "Approvals", f"Queue a recovery action for {cust['name']}", f"{opt['title']}. {('Approver: ' + opt['needs'] + '.')}")
        self.log("Agent", "Approvals", f"Proposed '{opt['title']}' for {o['so']}.")
        return p

    def _write_new_date(self, so: str, new_date: str, by: str, run: m.Run | None = None) -> None:
        o = self.sys.get_order(so)
        old = o.promised
        self.sys.update_order(so, promised=new_date, original_promised=o.original_promised or old)
        if run:
            self.step(run, "write", "ERP", f"Move the promised date on {so}", f"{fmt_date(old)} to {fmt_date(new_date)} ({by}).")
        self.log(by, "ERP", f"{so} promised date moved from {fmt_date(old)} to {fmt_date(new_date)}.")
        self.sys.add_note(o.customer_id, f"{so}: promised date moved from {fmt_date(old)} to {fmt_date(new_date)} ({by}).")

    def _revalidate(self, p: m.Proposal) -> None:
        en = self.engine_held(exclude=p.id)
        d, o = p.detail or {}, next((x for x in en.s.orders if x["so"] == p.so), None)
        if p.kind in ("stock", "split", "reallocate", "substitute"):
            if not o:
                raise ValueError("The order no longer exists.")
            need_main = d.get("units") or d.get("now") or d.get("free_used") or d.get("main") or 0
            if need_main > en.free_stock(o["sku"]):
                raise ValueError(f"Stock has changed: only {en.free_stock(o['sku']):,} are free now, the plan needs {need_main:,}. Ask the agent to work out a new plan.")
            if p.kind == "substitute" and d["sub_units"] > en.free_stock(d["sub"]):
                raise ValueError(f"Stock of {d['sub']} has changed. Ask the agent to work out a new plan.")
            if p.kind == "reallocate":
                for t in d["takes"]:
                    dn = next((x for x in en.s.orders if x["so"] == t["so"]), None)
                    if not dn or dn["stock_qty"] < t["units"]:
                        raise ValueError(f"{t['so']} no longer holds the stock this plan takes.")

    def _apply_proposal(self, p: m.Proposal, by: str, send: bool = True, run: m.Run | None = None) -> None:
        """Make the change in the ERP/CRM. Raises ValueError if the world has moved on."""
        if p.kind == "raise_po":
            return self.apply_raise_po(p, by, run)
        if p.kind == "resupply":
            return self.apply_resupply(p, by, run)
        self._revalidate(p)
        o = self.sys.get_order(p.so)
        d, kind = p.detail or {}, p.kind
        en = self.engine()
        cust = en.s.customers[o.customer_id]
        resolution = ""
        if kind == "stock":
            self.sys.update_order(o.so, stock_qty=o.stock_qty + d["units"], po_qty=max(0, o.po_qty - d["units"]), po=None if o.po_qty - d["units"] <= 0 else o.po)
            resolution = "recovered"
        elif kind == "split":
            now, rest = d["now"], d["rest"]
            total_stock = o.stock_qty + now
            child_value = round(o.value * rest / o.qty, 2)
            cid = self._child_id(o.so)
            self.sys.add_order(so=cid, customer_id=o.customer_id, sku=o.sku, qty=rest, value=child_value, promised=d["rest_eta"], stock_qty=0, po=o.po, po_qty=rest, parent=o.so, original_promised=o.promised,
                               note=f"Rest of {o.so}: agreed with the customer.")
            self.sys.update_order(o.so, qty=total_stock, value=round(o.value - child_value, 2), stock_qty=total_stock, po=None, po_qty=0, note=f"First part of the original order. The rest is {cid}.")
            resolution = "split"
        elif kind == "reallocate":
            for t in d["takes"]:
                dn = self.sys.get_order(t["so"])
                self.sys.update_order(dn.so, stock_qty=dn.stock_qty - t["units"], po=t["po"], po_qty=dn.po_qty + t["units"], note=(dn.note + " " if dn.note else "") + f"{t['units']} units moved to {t['po']} to cover {o.so}.")
                self.event(dn.so, "Agent", "system", f"{t['units']:,} units were moved to {t['po']} (arriving {fmt_date(t['new_eta'])}) to rescue {o.so}.")
                self._queue_update_for(t["so"], p.run_id)
            self.sys.update_order(o.so, stock_qty=o.stock_qty + o.po_qty, po=None, po_qty=0)
            resolution = "recovered"
        elif kind == "expedite":
            self.sys.update_order(o.so, expedite=True)
            resolution = "recovered" if p.meets_promised else ""
        elif kind == "substitute":
            main, sub_units, sub = d["main"], d["sub_units"], d["sub"]
            if main > 0:
                child_value = round(o.value * sub_units / o.qty, 2)
                cid = self._child_id(o.so)
                self.sys.add_order(so=cid, customer_id=o.customer_id, sku=sub, qty=sub_units, value=child_value, promised=o.promised, stock_qty=sub_units, po=None, po_qty=0, parent=o.so,
                                   note=f"{sub_units} units supplied as {sub} instead of {o.sku}: agreed with the customer.")
                self.sys.update_order(o.so, qty=o.stock_qty + main, value=round(o.value - child_value, 2), stock_qty=o.stock_qty + main, po=None, po_qty=0, note=f"First part of the original order. {sub_units} units are on {cid} as {sub}.")
            else:
                self.sys.update_order(o.so, sku=sub, stock_qty=o.qty, po=None, po_qty=0, note=f"Supplied as {sub} instead of {o.sku}: agreed with the customer.")
            resolution = "recovered"
        elif kind == "new_date":
            self._write_new_date(o.so, d["date"], by, run)
            resolution = "agreed"
        elif kind == "credit":
            resolution = ""
        if run and kind not in ("new_date",):
            self.step(run, "write", "ERP", f"Applied: {p.title}", "; ".join(d.get("side_effects", [])) or "Done.")
        if send and p.kind != "escalate" and p.subject:
            if kind == "supplier":
                self.sys.send(to=p.to, customer_id="", so=p.so, subject=p.subject, body=p.body, sent_by=by, kind="supplier")
            else:
                self.sys.send(to=p.to, customer_id=p.customer_id, so=p.so, subject=p.subject, body=p.body, sent_by=by)
        if p.note:
            self.sys.add_note(o.customer_id, p.note)
        c = self.case(o.so)
        if c:
            c.pending_proposal = None
            self.db.commit()
            if resolution:
                self.close_case(c, resolution, f"{p.title}. Order back to low risk.", by)
            else:
                self.event(o.so, by, "person", f"Applied: {p.title}.")
        self.log(by, "ERP", f"Applied '{p.title}' on {o.so}.")

    def _child_id(self, so: str) -> str:
        for suffix in "BCDEFGH":
            if not self.sys.get_order(f"{so}-{suffix}"):
                return f"{so}-{suffix}"
        raise ValueError("Too many splits on one order.")

    def _queue_update_for(self, so: str, run_id: int | None) -> None:
        """An order that gave up stock now arrives later. Draft its customer update and open a case if it is late."""
        en = self.engine()
        o = next(x for x in en.s.orders if x["so"] == so)
        v = en.order_view(o)
        if not v["late"]:
            return
        cust = en.s.customers[o["customer_id"]]
        it = en.s.items[o["sku"]]
        f = {"so": so, "company": cust["name"], "contact_first_name": cust["contact"].split(" ")[0], "sender": cust["owner"], "item": it["name"], "qty": o["qty"], "unit": it["unit"],
             "promised": fmt_date(o["promised"]), "new_date": fmt_date(v["eta"]), "days_late": v["days_late"], "renewal_in_days": days_between(cust["renewal"], self.today), "units_free_in_stock_now": 0}
        d = self._template(en, {"so": so, "after": v["eta"]}, f)
        big = o["value"] >= self.cfg.approval_limit
        self.db.add(m.Approval(world_id=self.w, run_id=run_id or 0, so=so, customer_id=o["customer_id"], value=o["value"], subject=d["subject"], body=d["body"], note=d["crm_note"], reader="rules", wording_ok=True,
                               status="Needs approval" if big else "Ready", reason=(f"Order worth {money(o['value'])} (limit {money(self.cfg.approval_limit)})" if big else "Gave up stock to rescue another order") , rank=9, new_date=v["eta"]))
        self.db.commit()
        if not self.case(so):
            self.db.add(m.OrderCase(world_id=self.w, so=so, status="at_risk", run_id=run_id, reason="Gave up stock to rescue another order", original_promised=o["promised"], eta=v["eta"], days_late=v["days_late"]))
            self.db.commit()
            self.event(so, "System", "system", f"Flagged as at risk: now arrives {fmt_date(v['eta'])}.")

    # ---------- deciding on a proposal ----------
    def decide_proposal(self, pid: int, approve: bool, edits: dict | None = None, by: str | None = None) -> m.Proposal:
        p = self.db.get(m.Proposal, pid)
        if not p or p.world_id != self.w or p.status != "Proposed":
            raise ValueError("This action is not waiting for a decision.")
        for k in ("subject", "body"):
            if edits and edits.get(k) is not None:
                setattr(p, k, edits[k])
        who = by or p.needs
        p.decided_by, p.decided_at = who, _now()
        run = self.db.get(m.Run, p.run_id) if p.run_id else None
        if run:
            self.clear_waits(run)
        if not approve:
            p.status = "Rejected"
            if run:
                self.step(run, "person", who, f"Rejected: {p.title}", "Nothing changed.")
            c = self.case(p.so)
            if c and c.status == "plan_proposed":
                c.status = "notified"
                self.db.commit()
            self.event(p.so, who, "person", f"Rejected the plan: {p.title}.")
        elif p.needs_customer_ok:
            # an offer: tell the customer, change nothing until they say yes
            self._revalidate(p)
            self.sys.send(to=p.to, customer_id=p.customer_id, so=p.so, subject=p.subject, body=p.body, sent_by=who)
            p.status = "Offered"
            c = self.case(p.so)
            if c:
                c.status, c.pending_proposal = "offer_sent", p.id
                self.db.commit()
            self.event(p.so, who, "person", f"Offer sent to the customer: {p.title}. Waiting for their answer.")
            if run:
                self.step(run, "person", who, f"Approved and sent the offer to the customer", p.title)
                self.step(run, "write", "Email", f"Offer sent to {self.sys.get_customer(p.customer_id)['name']}", "The ERP changes only when the customer says yes.")
        else:
            self._apply_proposal(p, who, send=True, run=run)
            p.status = "Applied"
            if run:
                self.step(run, "person", who, f"Approved: {p.title}", "Applied and the customer was told." if p.kind not in ("escalate", "supplier", "raise_po", "resupply") else "Done.")
            if p.kind == "escalate":
                self.event(p.so, who, "person", "Escalation accepted: a senior person owns this customer now.")
        self.db.commit()
        if run and run.status == "waiting_approval":
            left = self.db.query(m.Proposal).filter(m.Proposal.run_id == run.id, m.Proposal.status == "Proposed").count()
            if left:
                self.step(run, "wait", "Ops manager", "Waiting for the remaining approvals", "")
            else:
                waiting_offer = self.db.query(m.Proposal).filter(m.Proposal.run_id == run.id, m.Proposal.status == "Offered").count()
                self.finish(run, "done", "Offer sent. Waiting for the customer's answer." if waiting_offer else "Decisions made and applied.")
        return p
