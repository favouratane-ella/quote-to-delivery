"""Reads a customer's reply to a delay notice with plain rules. No AI: same text, same answer.

It returns an intent, a confidence, an optional date and the reasons, like the supplier-email reader.

  accept         "that works for us"
  hard_deadline  "we cannot accept that, we need everything by 2 Nov"
  partial_ok     "send what you have in stock now, the rest later"
  expedite       "can you expedite this? we will pay for express"
  credit         "we expect a credit for the trouble"
  cancel         "please cancel the order"
  reschedule     "the latest we can take is 9 Nov"
  question       "which warehouse will it ship from?"
  unclear        anything else, or a reply that contradicts itself
"""
from __future__ import annotations

import re
from datetime import date

from .rules_reader import find_dates

INTENT_LABEL = {"accept": "accepts the new date", "hard_deadline": "cannot accept the new date", "partial_ok": "will take part now", "expedite": "asks for faster shipping",
                "credit": "asks for a credit", "cancel": "wants to cancel", "reschedule": "proposes a date", "question": "asks a question", "unclear": "unclear"}

CANCEL = re.compile(r"\b(cancel+(?:ing|ed)?|call off|pull (?:the|our) order|take (?:the|our) business)\b")
HARD = re.compile(r"(can(?:not|'t| not) (?:accept|wait|take|live with|work with)|not acceptable|unacceptable|non[- ]?negotiable|not negotiable|no flexibility|"
                  r"must (?:have|arrive|be)|need (?:all|everything|the full|the whole)|(?:no|not) later than|at the latest|hard deadline|fixed date|locked (?:in|to)|not possible for us)")
PARTIAL = re.compile(r"(part of (?:the|our) order|send what you have|what you have in stock|partial|part now|part[- ]ship|split (?:the )?(?:shipment|delivery|order)|first part|rest (?:later|to follow)|remaining (?:later|to follow)|in two (?:parts|shipments))")
EXPEDITE = re.compile(r"(expedit\w*|express|rush|faster (?:shipping|delivery)|speed (?:it|this) up|air ?freight|pay for (?:faster|express|shipping))")
CREDIT = re.compile(r"(credit|discount|compensat\w*|refund|penalt\w*|goodwill|money back)")
ACCEPT = re.compile(r"(works? for us|that works|no problem|that is fine|that's fine|we can live with|understood|go ahead|please proceed|agreed|that is ok|that's ok|\bokay\b|\bok\b|thanks for letting us know|happy with that|we accept)")
NEGATED_ACCEPT = re.compile(r"(not|n't|cannot|can't|no longer)\s+(?:\w+\s+)?(?:work|fine|ok|okay|acceptable|agreed|accept)")
QUESTION = re.compile(r"\?")
AUTO = re.compile(r"(out of (?:the )?office|auto[- ]?reply|automatic(?:ally generated)? reply|away from (?:my|the) (?:desk|office)|on (?:annual )?leave|on holiday|on vacation|do not reply to this|no[- ]?reply|delivery (?:status )?notification|undeliverable)")


def flags_default() -> dict:
    return {"accepts": False, "willing_to_pay": False}


def _strip_quotes(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith(">"):
            continue  # a quoted line from our own earlier message
        if re.match(r"^on .+wrote:\s*$", line.strip(), re.I):
            if any(x.strip() for x in out):
                break  # the reply is above the quote
            continue
        out.append(line)
    return "\n".join(out)


def read_reply(text: str, today: str, ctx: dict | None = None) -> dict:
    """ctx may carry: eta, promised (ISO dates of the order), offer (True when answering an offer, not a notice)."""
    ctx = ctx or {}
    body = _strip_quotes(text)
    low = body.lower().replace("’", "'")
    reasons: list[str] = []
    sig = {
        "cancel": bool(CANCEL.search(low)),
        "hard": bool(HARD.search(low)),
        "partial": bool(PARTIAL.search(low)),
        "expedite": bool(EXPEDITE.search(low)),
        "credit": bool(CREDIT.search(low)),
        "accept": bool(ACCEPT.search(low)) and not NEGATED_ACCEPT.search(low),
        "question": bool(QUESTION.search(low)),
    }
    for k, hit in sig.items():
        if hit:
            reasons.append(f"Found {k.replace('_', ' ')} wording")
    dates = [d.value for d in find_dates(body, date.fromisoformat(today)) if d.value >= today]
    flags = {"accepts": False, "willing_to_pay": False}
    conf = 0.96

    if AUTO.search(low):
        return {"intent": "unclear", "confidence": 0.2, "date": None, "flags": flags_default(), "reasons": ["Looks like an automatic out-of-office or system reply, not an answer from the customer"], "label": INTENT_LABEL["unclear"]}
    if sig["cancel"]:
        intent = "cancel"
    elif sig["hard"] and sig["partial"]:
        intent, conf = "partial_ok", 0.92
        reasons.append("Cannot accept the date but will take part now: treated as a part delivery")
    elif sig["hard"]:
        intent = "hard_deadline"
        flags["willing_to_pay"] = sig["expedite"] or "pay" in low
        if sig["accept"]:
            conf = 0.55
            reasons.append("Says both that it works and that it cannot be accepted: contradictory")
    elif sig["partial"]:
        intent = "partial_ok"
    elif sig["expedite"]:
        intent = "expedite"
        flags["willing_to_pay"] = "pay" in low or "cost" in low
    elif sig["credit"]:
        intent = "credit"
        flags["accepts"] = sig["accept"]
        if sig["accept"]:
            reasons.append("Accepts the date and also asks for a credit")
    elif sig["accept"]:
        intent = "accept"
        flags["accepts"] = True
        if sig["question"]:
            conf = 0.8
            reasons.append("Accepts but also asks a question")
    elif dates and re.search(r"(latest|by|before|no later|until|can you (?:do|make)|could you (?:do|make)|can we (?:have|get))", low):
        intent, conf = "reschedule", 0.85
    elif sig["question"]:
        intent, conf = "question", 0.9
    else:
        intent, conf = "unclear", 0.3
        reasons.append("No clear request, acceptance or refusal found")

    chosen = None
    if dates and intent in ("hard_deadline", "reschedule", "partial_ok", "expedite"):
        chosen = dates[-1] if intent in ("hard_deadline", "reschedule") else dates[0]
        reasons.append(f"Date mentioned: {chosen}")
    if intent == "hard_deadline" and not chosen and ctx.get("promised"):
        chosen = ctx["promised"]
        reasons.append("No new date given: the original promised date is the deadline")
    return {"intent": intent, "confidence": round(conf, 2), "date": chosen, "flags": flags, "reasons": reasons, "label": INTENT_LABEL[intent]}
