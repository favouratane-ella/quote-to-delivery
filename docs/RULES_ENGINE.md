# The rules engine: how the agent decides without AI

With no API key, every decision is deterministic: the same email and the same ERP data always give the same result. Each run shows its reasoning step by step.

## 1. Reading a supplier email (`backend/app/rules_reader.py`)

The reader returns `type`, `po`, `new_date`, `split`, `confidence` and a list of `reasons`, which appear on the run under "How it read the email".

| It handles | Examples |
| --- | --- |
| PO references | PO-8841, PO 8841, P.O. 8841, purchase order 8841 |
| Date formats | 7 Nov, 7th of November, November 7, Nov 7th, 2026-11-07, 07/11/2026, 10/11 (day first), Friday, the 20th, tomorrow |
| Relative shifts | one week later, 3 days late, two weeks behind schedule, delayed by 5 business days, slipped a week. Counted from an explicit "from 6 Nov", or else from the PO's arrival in the ERP |
| Old versus new dates | instead of, not, from X to Y, was, originally, previously, ignore our earlier note that said |
| Negation | not delayed, no change, still arriving, as planned, as scheduled |
| Hedging | might, may slip, could slip, risk, to be confirmed, will confirm a new date, heads up |
| Questions | "Can you confirm the address?" is not a confirmation |
| Splits | 400 on 4 Nov and the remaining 200 on 12 Nov; in three lots |
| Admin mail | price lists, invoices, payments, holidays, contact changes |
| Quoted replies | lines starting with ">" and "On ... wrote:" blocks are ignored |

**Types:** `delay` (date changes, later or earlier), `partial` (split delivery), `confirmation` (date unchanged), `unclear` (a possible change with no firm date), `other` (not about a delivery date).

**Confidence** starts at 97% and drops for each uncertainty, with the reason recorded:

| Penalty | When |
| --- | --- |
| 50 | No PO number |
| 40 | More than one PO in the email |
| 35 | Hedged wording with a date ("might slip to 9 Nov") |
| 30 | PO is not open in the ERP |
| 25 | Worded as a confirmation, but the date differs from the ERP |
| 15 | Several different new dates |
| 4 | The date had no month or week ("Friday", "the 20th") |

`unclear` is capped at 40%.

**Accuracy:** the test pack holds 65 supplier messages with known answers. Cases T01 to T40 were used while building the reader. T41 to T65 were written afterwards as a held-out check: the reader got 23 of 25 on its first run, and the two gaps were fixed in general rules, not by special-casing those emails. It now scores 65 of 65. That is still our own test set: before a client goes live, add 50 or more of their real supplier emails.

## 2. Deciding what to do (guardrails, `agent.py`)

The agent changes the ERP on its own only when **every** check passes:

1. The email changes a delivery date (type `delay` or `partial`).
2. The PO exists in the ERP.
3. The sender is the supplier on that PO.
4. The new date is a valid future date.
5. The new date is within 120 days.
6. The new date differs from the ERP.
7. For splits: the quantities add up to the PO total.
8. Confidence is at or above the pass mark (default 90%, set in Settings).

If any check fails, the run stops and a planner confirms, corrects or dismisses it. Confirmations and admin emails are filed with no change.

## 3. Calculating (`engine.py`)

- **Arrival** = the later of today and the supply date, plus carrier transit days for the customer's lane.
- Orders that share a PO take its deliveries in promised-date order, so a split PO can cover the first orders and not the last.
- **Affected** = orders whose arrival moved *and* is now after the promised date.
- **Priority score** (0 to 100) = order value up to 40 (full marks at $50,000) + tier (A 25, B 15, C 5) + 20 if renewal is within 45 days + 3 per day late, up to 15. High is 70+, Medium 45+.
- **Quote check** uses free stock first, then each inbound delivery's quantity not yet promised to another order, in date order. If the date cannot be met it offers the earliest full date and, where stock allows, a split.

## 4. Writing and routing customer updates

- Templates in three tones (Warm and clear, Short and direct, Formal), filled only with facts from the ERP and CRM.
- **Wording check:** the message must name the order and the new date.
- Orders worth the approval limit or more (default $25,000), or failing the wording check, go to the ops manager. Smaller ones go after one check.
- Nothing is sent without a person.

## 5. Ask the agent

Without AI, the chat recognises: late orders, what-if delays ("What if PO-8850 slips 3 days?"), quote checks ("Can we promise 300 CC-210 to Kestrel Hotels by 20 Nov?"), what is waiting for a person, and lookups of an order, PO or customer. Anything else gets a list of what it can answer.

## Switching Claude on later

Set `ANTHROPIC_API_KEY` in `.env`. Claude then reads emails and writes drafts. The same guardrails, maths and routing still apply, and the rules engine remains the fallback if a Claude call fails.
