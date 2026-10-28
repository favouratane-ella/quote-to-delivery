# How the simulated CRM, ERP and mailboxes work

The app does not connect to a real CRM or ERP. It ships with **simulated versions** of them so anyone can test the agent end to end. They are ordinary database tables, filled with made-up sample data, behind the same connector interface a real system would use.

## The three pieces

```
seed.py  ──fills──▶  database tables  ◀──reads/writes──  SimulatedSystems  ◀──calls──  Agent
(sample data)        (SQLite or Postgres)                 (connectors/simulated.py)      (agent.py)
                            ▲
                            └── the ERP, CRM, Mailbox and Outbox screens read the same tables through the API
```

### 1. The tables (`backend/app/models.py`)

| System | Table | What a row is |
| --- | --- | --- |
| CRM | `customers` | A customer account: name, tier (A/B/C), yearly value, renewal date, contact name and email, account owner, carrier lane |
| CRM | `quotes` | A quote a sales rep wants to send: customer, item, quantity, requested date, status |
| CRM | `crm_notes` | A note on a customer's record. The agent adds one after every customer update and quote decision |
| ERP | `items` | A stock item (SKU) and how many are on hand |
| ERP | `purchase_orders` | An order to a supplier, with its delivery schedule, e.g. `[{"qty": 280, "date": "2026-11-02"}]`, and the original schedule |
| ERP | `sales_orders` | A customer order: how much comes from stock, how much waits on which PO, and the promised date |
| ERP | `suppliers`, `lanes` | Supplier contact emails; carrier transit days per lane (Local 1, Regional 2, National 3) |
| Mailbox | `emails` | The shared supply inbox, including attachments as structured rows |
| Outbox | `outbox` | What customers actually received, after a person approved it |

Every row has a `world_id`. The main world is `main`. Each test scenario makes its own throwaway world, so tests never touch the data people are working with.

### 2. The sample data (`backend/app/seed.py`)

Plain Python lists at the top of the file: 5 items, 4 suppliers, 6 purchase orders, 10 customers, 10 sales orders, 4 quotes and 5 supplier emails. The numbers are chosen so the story works: for example, a 5-day slip on PO-8841 makes three orders late and leaves Kestrel Hotels on time.

`create_world()` writes that data into the tables. It runs on first start, and again when you press **Reset the world** in Settings or run `python -m app.cli reset`.

**To change the sample data:** edit the lists in `seed.py`, then reset the world. Every company, person and figure is made up.

### 3. The connector (`backend/app/connectors/`)

`base.py` defines four interfaces, the only way the agent touches business systems:

| Interface | Methods the agent uses |
| --- | --- |
| `ERPConnector` | `snapshot()`, `get_po()`, `list_pos()`, `update_po_deliveries()` |
| `CRMConnector` | `get_customer()`, `add_note()`, `get_quote()`, `update_quote()` |
| `MailboxConnector` | `get_email()`, `set_status()` |
| `OutboxConnector` | `send()` |

`simulated.py` implements all four with simple database reads and writes. That is the whole "makeshift CRM": about 100 lines.

## Changing data while you test

You can play every outside party from the screens:

- **Supplier mailbox:** write a supplier email from a template or from scratch. With auto-run on, the agent wakes up as soon as it arrives.
- **ERP:** change a PO's arrival date (the agent re-checks every order on it), change stock on hand, or add a sales order (free stock is used first, then the earliest PO with room).
- **Quote desk:** create a quote; the agent checks it.
- **Approvals and checks:** act as the planner and the ops manager.
- **Customer outbox:** see exactly what each customer received.

## Replacing a simulated system with a real one

1. Write a class that implements the interface in `base.py`, for example `SalesforceCRM(CRMConnector)` calling the Salesforce API, or `SapERP(ERPConnector)`.
2. Have `snapshot()` return the same plain shape (`Snapshot` in `engine.py`): items, purchase orders with delivery schedules, customers, lanes and sales orders.
3. Pass your class where `SimulatedSystems` is created in `agent.py` (`self.sys = ...`).

The agent, guardrails, maths, templates, traces and screens do not change. In a first client pilot it is common to replace only the mailbox (real supply inbox) and keep a nightly export of the ERP and CRM in these tables.
