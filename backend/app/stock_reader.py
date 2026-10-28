"""Reads a warehouse stock note with plain rules. No AI.

  "40 bags were damaged and written off. Counted on hand is now 160."   ->  on hand 160 (change -40)
  "Found 25 extra boxes behind the racking."                           ->  change +25
  "Recount shows only 30 on the shelf."                                ->  on hand 30
"""
from __future__ import annotations

import re

SKU = re.compile(r"\b([A-Z]{2,3}-\d{2,3})\b")
NUM = r"(?<![\w#-])(\d[\d,]*)"  # not part of an item code such as DI-55
LOSS = re.compile(NUM + r"\s+(?:[\w-]+\s+){0,5}?(?:were|are|was|have been|has been)?\s*(?:damaged|lost|missing|spoiled|expired|written\s+off|scrapped|stolen|short)", re.I)
FOUND = re.compile(r"(?:found|located|extra)\s+" + NUM, re.I)
ABSOLUTE = [
    re.compile(r"(?:counted\s+)?on[- ]hand\s+(?:is\s+)?(?:now|only)?\s*(?:is\s+)?" + NUM, re.I),
    re.compile(r"(?:shows?|count(?:ed)?|only|total of)\s+(?:only\s+)?" + NUM + r"\s+(?:on\s+the\s+shelf|on\s+hand|in\s+stock|left|remaining|units|bags|boxes|tags|crates|rolls|strips|loggers|liners|packs)", re.I),
]
HEDGE = re.compile(r"\b(maybe|might|not sure|unsure|possibly|approximately|roughly|about|around)\b", re.I)


def _n(s: str) -> int:
    return int(s.replace(",", ""))


def read_stock_note(text: str, on_hand: dict[str, int] | None = None) -> dict:
    """Returns sku, new_on_hand (or None), change, reasons and a confidence. on_hand maps sku to the ERP quantity."""
    on_hand = on_hand or {}
    reasons: list[str] = []
    skus = list(dict.fromkeys(SKU.findall(text)))
    r = {"type": "stock_note", "sku": None, "new_on_hand": None, "change": None, "reasons": reasons, "confidence": 0.97}
    if not skus:
        r.update(type="other", confidence=0.3)
        reasons.append("No item code found")
        return r
    known = [s for s in skus if s in on_hand]
    r["sku"] = (known or skus)[0]
    reasons.append(f"Found item {r['sku']}")
    if len(skus) > 1:
        r["confidence"] -= 0.4
        reasons.append(f"More than one item mentioned ({', '.join(skus)}): picked {r['sku']} (confidence -40)")
    cur = on_hand.get(r["sku"])
    absolute = next((m for rx in ABSOLUTE if (m := rx.search(text))), None)
    loss, found = LOSS.search(text), FOUND.search(text)
    if absolute:
        r["new_on_hand"] = _n(absolute.group(1))
        reasons.append(f"The note gives the counted quantity: {r['new_on_hand']}")
        if cur is not None:
            r["change"] = r["new_on_hand"] - cur
    elif loss and cur is not None:
        r["change"] = -_n(loss.group(1))
        r["new_on_hand"] = cur + r["change"]
        reasons.append(f"{_n(loss.group(1))} lost or damaged, so on hand falls from {cur} to {r['new_on_hand']}")
    elif found and cur is not None:
        r["change"] = _n(found.group(1))
        r["new_on_hand"] = cur + r["change"]
        reasons.append(f"{_n(found.group(1))} extra found, so on hand rises from {cur} to {r['new_on_hand']}")
    else:
        r.update(type="other", confidence=0.3)
        reasons.append("No counted quantity or change found")
        return r
    if loss and absolute and cur is not None and cur - _n(loss.group(1)) != r["new_on_hand"]:
        r["confidence"] -= 0.3
        reasons.append("The loss and the counted quantity do not agree (confidence -30)")
    if HEDGE.search(text):
        r["confidence"] -= 0.25
        reasons.append("Hedged wording (confidence -25)")
    r["confidence"] = round(max(0.0, r["confidence"]), 2)
    return r
