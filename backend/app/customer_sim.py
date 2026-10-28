"""Simulated customers. Each one answers a delay notice or an offer in character, so the demo
runs end to end without a real mailbox. The reply style is set per customer in the sample data.

  accept    takes the new date
  hard      cannot move, will pay to keep the date
  partial   wants what is in stock now and the rest later
  expedite  asks for faster shipping
  credit    takes the date but expects compensation
  cancel    walks away
  question  asks something before deciding
  silent    never answers
"""
from __future__ import annotations

from .engine import add_days, fmt_date


def compose_reply(customer: dict, order: dict, unit: str, eta: str | None, stage: str = "notice", offer_meets: bool = True) -> tuple[str, str] | None:
    """Return (subject, body), or None when the customer stays silent. stage: notice | offer."""
    style = customer.get("reply_style", "accept")
    first = customer["owner"].split(" ")[0]
    me = customer["contact"].split(" ")[0]
    so, qty = order["so"], order["qty"]
    promised = fmt_date(order["promised"])
    new = fmt_date(eta) if eta else "that date"
    subject = f"Re: Order {so}"
    if style == "silent":
        return None
    if stage == "offer":
        if style == "hard" and not offer_meets:
            return subject, (f"Hi {first},\n\nThat does not solve it. {customer.get('hard_reason', '')} We need all {qty:,} {unit} by {promised} at the latest, this is not negotiable. "
                             f"Please escalate this to someone senior today.\n\n{me}")
        if style == "hard":
            return subject, f"Hi {first},\n\nYes, that works for us as long as it arrives by {promised}. Please go ahead.\n\n{me}"
        return subject, f"Hi {first},\n\nYes, that works for us. Please go ahead.\n\nThanks,\n{me}"
    if style == "hard":
        return subject, (f"Hi {first},\n\nWe cannot accept {new}. {customer.get('hard_reason', '')} We need all {qty:,} {unit} by {promised} at the latest, this is not negotiable. "
                         f"Please tell us what you can do. We are open to paying for faster shipping.\n\n{me}")
    if style == "partial":
        rest = fmt_date(add_days(order["promised"], customer.get("max_slip", 5)))
        return subject, (f"Hi {first},\n\nThanks for the heads up. We can take part of the order now if you send what you have in stock, and the rest by {rest}. "
                         f"Please send the available units as soon as possible.\n\n{me}")
    if style == "expedite":
        return subject, f"Hi {first},\n\nThat is a problem for us. Can you expedite this? We will pay for express shipping if it gets the order to us closer to {promised}.\n\n{me}"
    if style == "credit":
        return subject, (f"Hi {first},\n\nThis is the second delay we have had this quarter. We can live with {new}, but we expect a credit for the trouble. "
                         f"Please confirm what you can offer.\n\n{me}")
    if style == "cancel":
        return subject, f"Hi {first},\n\nThis is too late for us. Please cancel order {so}. We will source it elsewhere.\n\n{me}"
    if style == "question":
        return subject, (f"Hi {first},\n\nThanks for the note. Can you tell me exactly which warehouse the order will ship from, "
                         f"and whether the delay affects anything else on our account?\n\n{me}")
    return subject, f"Hi {first},\n\nThanks for letting us know. {new} works for us, no problem.\n\n{me}"
