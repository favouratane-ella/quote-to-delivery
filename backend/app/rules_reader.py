"""Deterministic supplier-email reader (the rules engine).

No AI. It turns a supplier email into structured fields and explains every
decision it makes in `reasons`, so a person can see exactly why it read the
email the way it did.

What it handles
- PO references: PO-8841, PO 8841, P.O. 8841, purchase order 8841.
- Dates: 7 Nov, 7th of November, November 7, Nov 7th, 2026-11-07, 07/11/2026 and
  10/11 (day first), weekday names ("Friday"), "the 20th", tomorrow.
- Relative shifts: "one week later", "3 days late", "two weeks behind schedule",
  "delayed by 5 business days", "slipped a week", anchored on an explicit
  "from <date>" or on the PO's current arrival date in the ERP.
- Old versus new dates: "instead of", "not", "from X to Y", "was", "originally",
  "ignore our earlier note that said".
- Negation: "not delayed", "no change", "still arriving", "as planned".
- Hedging: "might", "may", "could slip", "risk", "to be confirmed", "heads up".
- Questions and requests: "Could you...?", "Please confirm..." are not confirmations.
- Split shipments: "400 on 4 Nov and the remaining 200 on 12 Nov", "in three lots".

Confidence starts at 0.97 and drops for each thing that makes the read less certain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
          "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
          "dec": 12, "december": 12}
WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
            "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "eleven": 11, "twelve": 12, "fourteen": 14, "a couple of": 2, "couple of": 2}

_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DOW = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)"
_ORD = r"(?:st|nd|rd|th)?"
_NUMW = r"(\d+|a couple of|couple of|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen)"

RE_PO = re.compile(r"\b(?:P\.?\s?O\.?|purchase\s+order)\s*(?:#|no\.?|number)?\s*-?\s*(\d{3,6})\b", re.I)

# Words that mark a date as the OLD one, and as the NEW one. The keyword closest to the date wins.
OLD_KW = re.compile(r"(instead\s+of|rather\s+than|\bnot\b|n't\s+make|cannot\s+make|miss(?:ed)?|\bwas\b|\bwere\b|originally|previously|"
                    r"original\s+(?:\w+\s+)?(?:date|eta|arrival)|\bfrom\b|planned\s+for|scheduled\s+for|\bsaid\b|earlier\s+(?:note|email|message)|old\s+date|"
                    r"ahead\s+of|earlier\s+than|sooner\s+than|"
                    r"\bdue\b|as\s+planned\s+on)", re.I)
NEW_KW = re.compile(r"(\bnow\b|\bnew\b|revised|updated|\bto\b|until|slipping|moved|pushed|postponed?|arriv(?:e|es|ing|al)|reach(?:es)?|"
                    r"land(?:s|ing)?|deliver(?:y|ed)?|ship(?:s|ping)?|\beta\b|expect(?:ed)?|\bon\b|\bby\b|follows?|dispatch(?:ed)?|coming)", re.I)
META_SENT = re.compile(r"\b(confirm|advise|update\s+you|let\s+you\s+know|get\s+back|reply|respond|call\s+you)\b", re.I)
ARRIVAL_VERB = re.compile(r"\b(arriv\w*|land\w*|reach\w*|deliver\w*|ship\w*|dispatch\w*|send|sent|eta|due|follows?|lots?|parts?)\b", re.I)


def _closest(rx: re.Pattern, window: str) -> int:
    ends = [m.end() for m in rx.finditer(window)]
    return max(ends) if ends else -1


OLD_AFTER = re.compile(r"^[^.;:]{0,12}\b(as\s+(?:originally\s+)?(?:planned|scheduled|agreed)|was\s+wrong|originally)", re.I)

DELAY = re.compile(r"\b(delay(?:ed|s)?|late|slip(?:s|ped|ping)?|push(?:ed)?\s+back|pushed\s+to|postpone[ds]?|reschedul\w*|behind\s+schedule|held\s+up|"
                   r"on\s+hold|quality\s+(?:hold|issue|problem)|on\s+an?\s+\w+\s+hold|instead\s+of|instead|revised\s+(?:eta|arrival|date|delivery)|new\s+(?:eta|date|arrival|ship\s+date|delivery\s+date)|"
                   r"will\s+now|now\s+(?:arriv\w+|land\w*|reach\w*|ship\w*|due|expected)|moved\s+to|(?:date|eta|arrival|delivery)\s+(?:has\s+)?changed|changed\s+from|"
                   r"(?:can't|cannot|won't|unable\s+to)\s+(?:make|ship|deliver|meet)|miss(?:ed)?\s+the\s+date|coming\s+early|early|sooner|"
                   r"running\s+\w+\s+(?:days?|weeks?)\s+behind)\b", re.I)
NO_DELAY = re.compile(r"\b(not\s+(?:be\s+)?delayed|no\s+delay|isn't\s+delayed|won't\s+be\s+(?:late|delayed)|no\s+change|unchanged|remains?\s+(?:on|unchanged)|"
                      r"still\s+(?:on\s+(?:schedule|track|time)|arriving|due|expected|coming)|on\s+schedule|on\s+track|as\s+planned|as\s+scheduled|as\s+agreed|"
                      r"on\s+time|no\s+impact)\b", re.I)
CONFIRM = re.compile(r"\b(confirm(?:ing|ed|s)?|we\s+can\s+confirm|this\s+is\s+to\s+confirm)\b", re.I)
REQUEST = re.compile(r"(\b(can|could|would|will)\s+you\b|\bplease\s+(?:confirm|advise|send|let|share|provide)|\bkindly\b|\?\s*$)", re.I)
HEDGE = re.compile(r"\b(might|possibly|potential(?:ly)?|risk|likely|unsure|not\s+sure|may\s+(?:be|slip|arrive|need|run|not|have|shift|come|take|get)|"
                   r"could\s+(?:be|slip|arrive|run|shift|take)|to\s+be\s+confirmed|tbc|tba|not\s+yet\s+confirmed|no\s+firm\s+date|"
                   r"(?:will|to)\s+(?:confirm|advise)\s+(?:a\s+|the\s+)?(?:firm|new|revised|final)?\s*(?:date|eta|delivery\s+date)|to\s+follow|heads\s+up|expect\s+to\s+confirm)\b", re.I)
PARTIAL = re.compile(r"\b(partial(?:ly)?|split|in\s+(?:two|three|four|2|3|4)\s+(?:parts|lots|shipments|batches|deliveries|loads)|remaining|the\s+rest|balance|"
                     r"first\s+(?:part|batch|lot|shipment|delivery)|second\s+(?:part|batch|lot|shipment|delivery))\b", re.I)
OTHER = re.compile(r"\b(invoice|payment|price\s+list|prices?|address|contact|holiday|closed|newsletter|email\s+has\s+changed|support\s+email|bank\s+details)\b", re.I)
REL_SHIFT = re.compile(rf"\b(?:by\s+|for\s+)?(?:about\s+|around\s+|roughly\s+)?{_NUMW}\s+(business\s+days?|working\s+days?|days?|weeks?)\b", re.I)
REL_CONTEXT = re.compile(r"\b(late|later|delay|delayed|behind|slip|slipped|slipping|pushed|push|back|postpone|extra|longer)\b", re.I)


@dataclass
class DateMention:
    start: int
    end: int
    value: str
    raw: str
    kind: str = "absolute"   # absolute | weekday | dayonly | relative
    role: str = "neutral"    # old | new | neutral
    qty: int | None = None


@dataclass
class Reading:
    type: str = "other"
    po: str | None = None
    new_date: str | None = None
    split: list | None = None
    confidence: float = 0.97
    reasons: list = field(default_factory=list)

    def penal(self, amount: float, why: str) -> None:
        self.confidence = round(max(0.05, self.confidence - amount), 2)
        self.reasons.append(f"{why} (confidence -{int(round(amount * 100))})")


def _year_for(month: int, day: int, today: date) -> date | None:
    for y in (today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            return None
        if d >= today - timedelta(days=60):
            return d
    return None


def find_dates(text: str, today: date, month_hint: int | None = None) -> list[DateMention]:
    found: list[DateMention] = []

    def add(m, d: date | None, kind="absolute"):
        if d:
            found.append(DateMention(m.start(), m.end(), d.isoformat(), m.group(0), kind))

    for m in re.finditer(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b", text):
        try:
            add(m, date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", text):
        d, mo = int(m.group(1)), int(m.group(2))  # day first
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        if m.group(3):
            y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
            try:
                add(m, date(y, mo, d))
            except ValueError:
                pass
        else:
            add(m, _year_for(mo, d, today))
    for m in re.finditer(rf"\b(\d{{1,2}}){_ORD}\s+(?:of\s+)?{_MON}\b\.?(?:,?\s+(20\d\d))?", text, re.I):
        mo = MONTHS[m.group(2).lower()[:3] if m.group(2).lower()[:3] != "sep" else "sep"]
        if m.group(2).lower() == "may" and not re.match(r"\s*(?:,?\s*20\d\d|\b)", text[m.end():]):
            continue
        y = int(m.group(3)) if m.group(3) else None
        try:
            add(m, date(y, mo, int(m.group(1))) if y else _year_for(mo, int(m.group(1)), today))
        except ValueError:
            pass
    for m in re.finditer(rf"\b{_MON}\.?\s+(\d{{1,2}}){_ORD}\b(?:,?\s+(20\d\d))?", text, re.I):
        word = m.group(1).lower()
        if word == "may" and not re.match(r"\s*\d", text[m.start() + 3:]):
            continue
        mo = MONTHS[word[:3]]
        y = int(m.group(3)) if m.group(3) else None
        try:
            add(m, date(y, mo, int(m.group(2))) if y else _year_for(mo, int(m.group(2)), today))
        except ValueError:
            pass
    # "the 20th" with no month: borrow the month from context
    for m in re.finditer(r"\bthe\s+(\d{1,2})(st|nd|rd|th)\b(?!\s+(?:of\s+)?" + _MON + r")", text, re.I):
        mo = month_hint or today.month
        add(m, _year_for(mo, int(m.group(1)), today), "dayonly")
    # weekday alone, e.g. "on Friday" (a weekday followed by a date is covered above)
    for m in re.finditer(rf"\b(?:(next|this)\s+)?{_DOW}\b(?!\s*,?\s*\d)(?!\s+(?:the\s+)?\d)", text, re.I):
        wd = WEEKDAYS[m.group(2).lower()]
        ahead = (wd - today.weekday()) % 7 or 7
        if (m.group(1) or "").lower() == "next" and ahead < 7 and (today + timedelta(days=ahead)).isocalendar()[1] == today.isocalendar()[1]:
            ahead += 7
        add(m, today + timedelta(days=ahead), "weekday")
    for m in re.finditer(r"\btomorrow\b", text, re.I):
        add(m, today + timedelta(days=1), "relative")
    # drop overlaps, keep the longest match
    found.sort(key=lambda x: (x.start, -(x.end - x.start)))
    out: list[DateMention] = []
    for f in found:
        if out and f.start < out[-1].end:
            continue
        out.append(f)
    return out


def _sentences(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in re.finditer(r"[.!?](?=\s|$)|\n\s*\n", text):
        # do not split on "P.O." or decimals
        if text[max(0, m.start() - 2): m.start() + 1].lower() in ("p.o", ".o."):
            continue
        spans.append((start, m.end()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return [s for s in spans if text[s[0]:s[1]].strip()]


def _add_business_days(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _strip_quoted(text: str) -> str:
    """Drop quoted earlier messages ("> ..." lines and "On ... wrote:" blocks)."""
    lines, out = text.splitlines(), []
    for ln in lines:
        if re.match(r"\s*On .+wrote:\s*$", ln) or re.match(r"\s*-{2,}\s*Original Message", ln, re.I):
            break
        if not ln.lstrip().startswith(">"):
            out.append(ln)
    return "\n".join(out)


def read_email(text: str, today: str | int, pos: dict[str, str] | None = None, subject: str = "") -> dict:
    """Read an email.

    text      the email (subject may be included)
    today     ISO date, or a year (older callers)
    pos       {po_number: current arrival date} from the ERP, used to anchor relative shifts
    """
    if isinstance(today, int):
        today_d = date(today, 10, 26)
    else:
        today_d = date.fromisoformat(today)
    pos = pos or {}
    body = _strip_quoted(text)
    r = Reading()
    low = body.lower()

    # ---------- PO ----------
    po_nums = []
    for m in RE_PO.finditer(body):
        n = "PO-" + m.group(1)
        if n not in po_nums:
            po_nums.append(n)
    if len(po_nums) == 1:
        r.po = po_nums[0]
        r.reasons.append(f"Found one purchase order: {r.po}")
    elif len(po_nums) > 1:
        known = [p for p in po_nums if p in pos]
        r.po = (known or po_nums)[0]
        r.penal(0.4, f"Found {len(po_nums)} purchase orders ({', '.join(po_nums)}); picked {r.po}")
    anchor = pos.get(r.po) if r.po else None
    anchor_d = date.fromisoformat(anchor) if anchor else None

    # ---------- dates and their roles ----------
    hint = None
    abs_months = [int(d.value[5:7]) for d in find_dates(body, today_d) if d.kind == "absolute"]
    if abs_months:
        hint = abs_months[0]
    elif anchor_d:
        hint = anchor_d.month
    mentions = find_dates(body, today_d, hint)
    sents = _sentences(body)
    for d in mentions:
        s0 = next((a for a, b in sents if a <= d.start < b), 0)
        before, after = body[s0:d.start], body[d.end:d.end + 40]
        if re.search(r"\bfrom\s*$", before, re.I) and re.match(r"\s*(?:to|until)\b", after, re.I):
            d.role = "old"
        elif OLD_AFTER.search(after):
            d.role = "old"
        else:
            win = before[-45:]
            o, n = _closest(OLD_KW, win), _closest(NEW_KW, win)
            if o >= 0 and o >= n:
                d.role = "old"
            elif n >= 0:
                d.role = "new"
        sent_text = body[s0:next((b for a, b in sents if a <= d.start < b), len(body))]
        if META_SENT.search(sent_text) and not ARRIVAL_VERB.search(sent_text):
            d.role = "meta"  # a date about the next email, not about the delivery
        # quantity just before the date, e.g. "400 insulated boxes on 4 Nov"
        win = RE_PO.sub("the PO", body[max(0, d.start - 60):d.start])  # a PO number is not a quantity
        q = re.search(r"(?<![\w#-])(\d[\d,]*)\s+(?:[A-Za-z]+\s+){0,2}(?:on|by|for|follows?(?:\s+on)?|(?:arriv|ship|deliver|land|reach)\w*(?:\s+on)?|will\s+arrive(?:\s+on)?)\s*(?:[A-Za-z]+day\s+)?$", win, re.I)
        if not q:  # "ship 900 of the 1,200 rolls on 5 November": the part is the first number
            q = re.search(r"(?<![\w#-])(\d[\d,]*)\s+of\s+(?:the\s+)?[\d,]+\b[^.]*$", win, re.I)
        if q:
            try:
                d.qty = int(q.group(1).replace(",", ""))
            except ValueError:
                pass
    if mentions:
        r.reasons.append("Dates found: " + "; ".join(f'"{d.raw.strip()}" = {d.value} ({d.role})' for d in mentions))

    # relative shifts ("one week later", "3 days late", "delayed by 5 business days", "slipped a week")
    shift_days, shift_text = None, None
    for s0, s1 in sents:
        sent = body[s0:s1]
        if not REL_CONTEXT.search(sent):
            continue
        m = REL_SHIFT.search(sent)
        if not m:
            m2 = re.search(r"\b(slipped|slip|pushed\s+back|delayed|late)\s+(?:by\s+)?(a|one)\s+(week|day)\b", sent, re.I)
            if m2:
                shift_days, shift_text = (7 if m2.group(3).lower() == "week" else 1), m2.group(0)
            continue
        num = m.group(1).lower()
        n = int(num) if num.isdigit() else NUMBERS.get(num, 1)
        unit = m.group(2).lower()
        explicit = next((d for d in mentions if d.role == "old" and s0 <= d.start < s1), None)
        base = date.fromisoformat(explicit.value) if explicit else anchor_d
        if not base:
            r.reasons.append(f'Found a relative shift "{m.group(0)}" but no date to count from')
            shift_text = m.group(0)
            continue
        if "business" in unit or "working" in unit:
            shift_days = (_add_business_days(base, n) - base).days
        else:
            shift_days = n * 7 if "week" in unit else n
        shift_text = m.group(0)
        if explicit:
            anchor_d = base
        break

    # ---------- what kind of email ----------
    has_delay = bool(DELAY.search(body))
    no_delay = bool(NO_DELAY.search(body))
    hedge = bool(HEDGE.search(body))
    partial_word = bool(PARTIAL.search(body))
    declarative_confirm = any(CONFIRM.search(body[a:b]) and not REQUEST.search(body[a:b]) for a, b in sents)
    statements = [body[a:b] for a, b in sents if not REQUEST.search(body[a:b])]
    has_request = any(REQUEST.search(body[a:b]) for a, b in sents)
    only_requests = has_request and not any(DELAY.search(s) or NO_DELAY.search(s) or CONFIRM.search(s) or ARRIVAL_VERB.search(s) for s in statements)
    other_topic = bool(OTHER.search(body))

    new_dates = [d for d in mentions if d.role == "new"]
    neutral_dates = [d for d in mentions if d.role == "neutral"]
    if any(d.role == "meta" for d in mentions):
        r.reasons.append("Ignored dates that are about the next message, not the delivery: " + ", ".join(d.value for d in mentions if d.role == "meta"))
    old_dates = [d for d in mentions if d.role == "old"]
    qty_dates = [d for d in mentions if d.qty and d.role not in ("old", "meta")]

    if not r.po and not [d for d in mentions if d.role != "meta"] and not RE_PO.search(subject or ""):
        r.type = "other"
        r.reasons.append("No purchase order and no delivery date in the email")
    elif only_requests and not has_delay:
        r.type = "other"
        r.reasons.append("The email asks a question or makes a request; it does not report a delivery change")
    elif partial_word and len(qty_dates) >= 2:
        r.type = "partial"
        r.split = [{"qty": d.qty, "date": d.value} for d in sorted(qty_dates, key=lambda x: x.value)]
        r.new_date = r.split[-1]["date"]
        r.reasons.append("Split delivery: " + ", ".join(f"{s['qty']} on {s['date']}" for s in r.split))
    elif no_delay and not (has_delay and new_dates and anchor and any(d.value != anchor for d in new_dates) and not re.search(r"\bnot\s+(?:be\s+)?delayed|no\s+change", low)):
        r.type = "confirmation"
        r.reasons.append("Says the date is unchanged (" + NO_DELAY.search(body).group(0) + ")")
    elif other_topic and not has_delay and not no_delay and not declarative_confirm:
        r.type = "other"
        r.reasons.append("Admin message (" + OTHER.search(body).group(0) + "); no delivery change reported")
    elif has_delay or shift_days or (new_dates and r.po):
        r.type = "delay"
        pick = new_dates or neutral_dates
        if pick:
            vals = sorted({d.value for d in pick})
            if len(vals) > 1 and new_dates:
                last = max(new_dates, key=lambda d: d.start)
                r.new_date = last.value
                r.penal(0.15, f"Several new dates mentioned ({', '.join(vals)}); used the last one stated, {last.value}")
            else:
                r.new_date = vals[-1] if not new_dates else new_dates[-1].value
            if any(d.kind in ("weekday", "dayonly") for d in pick if d.value == r.new_date):
                r.penal(0.04, "The new date was given without a full date, so the month or week was inferred")
        elif shift_days is not None and anchor_d:
            r.new_date = (anchor_d + timedelta(days=shift_days)).isoformat()
            r.reasons.append(f'Worked out the new date from "{shift_text}": {anchor_d.isoformat()} + {shift_days} days = {r.new_date}')
        if not has_delay and not shift_days and r.new_date and anchor and r.new_date == anchor:
            r.type = "confirmation"
            r.new_date = None
            r.reasons.append(f"The date given ({anchor}) is the date already in the ERP and no delay is mentioned, so this is a confirmation")
        elif declarative_confirm and not has_delay and r.new_date and anchor and r.new_date != anchor:
            r.penal(0.25, f"Worded as a confirmation, but the date {r.new_date} differs from the ERP ({anchor})")
        if r.type == "delay" and not r.new_date:
            r.type = "unclear"
            r.reasons.append("Reports a delay but gives no firm new date")
        elif r.type == "delay":
            r.reasons.append("Reports a change to the delivery date" + (" (earlier than planned)" if anchor and r.new_date < anchor else ""))
    elif declarative_confirm:
        r.type = "confirmation"
        r.reasons.append("Confirms the order")
        if new_dates and anchor and new_dates[-1].value != anchor:
            r.type = "delay"
            r.new_date = new_dates[-1].value
            r.penal(0.25, f"Worded as a confirmation, but the date {r.new_date} differs from the ERP ({anchor})")
    else:
        r.type = "other"
        r.reasons.append("No delivery change, confirmation or warning found" + (" (looks like admin: " + OTHER.search(body).group(0) + ")" if other_topic else ""))

    if hedge and r.type in ("delay", "partial", "confirmation"):
        if not r.new_date or r.type == "confirmation" and not no_delay:
            r.type, r.new_date, r.split = "unclear", None, None
            r.reasons.append("Warns of a possible change without a firm date")
        else:
            r.penal(0.35, "The wording is uncertain (" + HEDGE.search(body).group(0) + "), so the date may not be final")
    if r.type == "unclear" and not any("possible change" in x or "no firm new date" in x for x in r.reasons):
        r.reasons.append("Warns of a possible change without a firm date")

    # ---------- final confidence ----------
    if r.type in ("delay", "partial", "confirmation", "unclear") and not r.po:
        r.penal(0.5, "No purchase order number found")
    if r.po and pos and r.po not in pos:
        r.penal(0.3, f"{r.po} is not an open PO in the ERP")
    if r.type == "unclear":
        r.confidence = min(r.confidence, 0.4)
    if r.type == "partial" and r.split and r.po in pos and len(r.split) < 2:
        r.penal(0.3, "Only one part of the split had a quantity and a date")
    if r.type == "other":
        r.confidence = min(r.confidence, 0.9)
    if old_dates and r.type == "delay":
        r.reasons.append("Ignored old dates: " + ", ".join(d.value for d in old_dates))

    from .engine import fmt_date

    summary = {"delay": f"{r.po or 'The order'} now arrives {fmt_date(r.new_date)}." if r.new_date else "Reports a delay.",
               "partial": f"{r.po} arrives in {len(r.split or [])} parts, the last on {fmt_date(r.new_date)}.",
               "confirmation": f"{r.po or 'The order'} keeps its current date.",
               "unclear": f"{r.po or 'An order'} may change, but no firm date is given.",
               "other": "Not about a delivery date."}[r.type]
    return {"type": r.type, "po": r.po, "new_date": r.new_date, "split": r.split, "confidence": r.confidence,
            "summary": summary, "reasons": r.reasons, "reader": "rules"}
