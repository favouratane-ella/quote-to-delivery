"""Every prompt the agent sends to Claude. Each run stores the exact prompt and reply."""
from __future__ import annotations

import json


def po_context(pos: list[dict]) -> list[dict]:
    return [{"po": p["po"], "supplier": p["supplier"], "sku": p["sku"], "qty": sum(d["qty"] for d in p["deliveries"]),
             "arrives": ", ".join(f"{d['qty']} on {d['date']}" for d in p["deliveries"])} for p in pos]


def email_text(e: dict) -> str:
    t = f"From: {e['sender']} <{e['address']}>\nSubject: {e['subject']}\n\n{e['body']}"
    if e.get("attachment"):
        a = e["attachment"]
        t += f"\n\nAttachment {a['name']}:\n" + "\n".join(f"{r[0]}: {r[1]}" for r in a["rows"])
    return t


def read_email(pos: list[dict], email: dict, today: str) -> str:
    year = today[:4]
    return (
        f"You read supplier emails for a distributor's order desk. Today is {today}.\n"
        f"Open purchase orders in the ERP:\n{json.dumps(po_context(pos))}\n\n"
        f'Email:\n"""\n{email_text(email)}\n"""\n\n'
        'Reply with only one JSON object:\n'
        '{"type":"delay"|"partial"|"confirmation"|"unclear"|"other","po":"PO-0000" or null,"new_date":"YYYY-MM-DD" or null,'
        '"split":[{"qty":number,"date":"YYYY-MM-DD"}] or null,"confidence":number from 0 to 1,"summary":"one plain sentence"}\n'
        'Rules: "delay" = the whole order arrives later. "partial" = it arrives in parts; list every part in split and put the last date in new_date. '
        '"confirmation" = the date stays the same, including emails that say it is not delayed. "unclear" = it warns of a possible change but gives no firm new date. '
        '"other" = not about a delivery date. Resolve relative dates such as "one week later" from the PO\'s current arrival. '
        f"Copy the PO number exactly as written, even if it is not in the list. Use the year {year}."
    )


def draft_updates(supplier: str, po: str, facts: list[dict], tone: str) -> str:
    return (
        f"Write delay notices from a distributor's order desk to customers. Supplier {supplier} delayed {po}. Use only these facts:\n"
        f"{json.dumps(facts, indent=1)}\n\n"
        f"For each order write an email and a CRM note. Rules: {tone.lower()} tone; under 110 words; greet by first name; "
        "state the promised date and the new date exactly as written in the facts; mention the order number; apologise once; "
        "offer one practical option (if units are free in stock, offer to send that many now; otherwise offer a call); "
        'do not invent reasons, prices or dates; sign off with the sender name and "Order desk". '
        "The CRM note is one sentence; if renewal_in_days is 45 or less, suggest a call today.\n"
        'Reply with only a JSON array: [{"so":"SO-0000","subject":"...","body":"...","crm_note":"..."}]'
    )


def reader_pack(pos: list[dict], cases: list[tuple], today: str) -> str:
    return (
        f"Classify each supplier message for a distributor's order desk. Today is {today}. "
        f"Open purchase orders and current arrival dates:\n{json.dumps(po_context(pos))}\n\nMessages:\n"
        + "\n".join(f"{c[0]}: {c[1]}" for c in cases)
        + '\n\nFor each message give {"id","type","po","new_date"}. type: "delay" (whole order later), "partial" (in parts; new_date = last part), '
        '"confirmation" (date unchanged, including "not delayed"), "unclear" (possible change, no firm date) or "other" (no date change). '
        "po: the PO number mentioned, or null. new_date: YYYY-MM-DD for delay and partial, else null; resolve relative dates from the PO's current arrival; "
        f"when a message corrects an earlier date, use the corrected one. Reply with only a JSON array of {len(cases)} objects."
    )


def chat_system(today: str, today_label: str) -> str:
    return (
        f"You are the Quote-to-Delivery agent for a distributor's order desk. Today is {today} ({today_label}). "
        "Use the tools before answering; never invent orders, dates or numbers. Answer in short plain sentences or a few bullets. "
        'Dates like "Mon 9 Nov", money like "$48,200". You cannot change data; say which screen to use for actions '
        "(Supplier mailbox, ERP, Quote desk, Approvals and checks)."
    )
