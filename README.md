# Quote-to-Delivery Accelerator

A JADA accelerator that keeps sales and supply in step on every order. When a supplier delay lands in the inbox, the agent reads it, updates the ERP, finds every customer order that will now be late, ranks the customers, drafts the updates, and routes them to a person for approval. It also checks quotes before a sales rep promises a date.

This repo is a working, deployable MVP. It runs on a **simulated world** (ERP, CRM, supplier mailbox, carrier lanes, customer outbox) filled with made-up sample data, so anyone can test it without connecting real systems. **It needs no API key**: a deterministic rules engine does the reading, writing and routing. Claude can be switched on later.

## Quick start

1. Install **Python 3.11+** ([python.org](https://www.python.org/downloads/); on Windows tick "Add python.exe to PATH") and **Node.js 20+** ([nodejs.org](https://nodejs.org/)).
2. Unzip the folder.
3. Start it:
   - **Windows:** double-click `start.bat`
   - **Mac or Linux:** open a terminal in the folder and run `./start.sh`
4. Your browser opens **http://localhost:8000**. The first start takes a few minutes while it installs; after that it starts in seconds.

To stop it, close the window (Windows) or press Ctrl+C (Mac, Linux). Your data is kept in `backend/q2d.db`; **Settings > Reset the world** puts the sample data back.

More detail: [how the simulated CRM and ERP work](docs/SIMULATED_SYSTEMS.md) · [how the rules engine decides](docs/RULES_ENGINE.md)

## What is in it

| Part | Where | What it does |
| --- | --- | --- |
| Agent | `backend/app/agent.py` | Wakes on a trigger, works through traced steps, stops for people where the rules say so |
| Engine | `backend/app/engine.py` | Delivery dates, affected orders, priority scores, quote checks. Pure code, no AI |
| Rules engine | `backend/app/rules_reader.py`, `chat_rules.py` | Reads supplier emails and answers chat questions with no AI. Explains every decision |
| Claude (optional) | `backend/app/llm.py`, `prompts.py` | With an API key: reads emails, writes updates, open-ended chat |
| Connectors | `backend/app/connectors/` | The only way the agent touches business systems. Simulated today, swappable for real ones |
| Test scenarios | `backend/app/scenarios.py` | 14 situations with expected results, each run in its own throwaway world |
| API | `backend/app/api.py` | FastAPI, under `/api`. Interactive docs at `/docs` |
| Web app | `frontend/` | React + Vite. 13 screens: how it works, agent runs, chat, mailbox, ERP, CRM, outbox, approvals, quote desk, scenarios, test pack, log, settings |

## How the agent decides

Every run is stored step by step, and each step is tagged with who did the work:

| Tag | Meaning |
| --- | --- |
| System event | Something changed: an email arrived, a PO date moved, a quote was submitted |
| Agent reads | Data pulled from a system (the data is stored with the step) |
| Rules engine | The deterministic reader or a template did the work; its reasons are listed |
| AI judgement | Claude read or wrote language (only with an API key). The exact prompt and raw reply are stored |
| Code calculation | Dates, quantities, money and scores, worked out by `engine.py` |
| Guardrail check | Pass or fail checks that decide what happens next |
| Agent writes | A change written to a system |
| Person | A planner, ops manager or sales rep acted |

**Numbers and routing are always code.** Delivery dates, priority scores and who approves what never depend on AI. Reading and writing use the rules engine by default, or Claude if a key is set.

### Guardrails

- The ERP changes only when the email names a PO that exists, comes from that PO's supplier, gives a valid future date within 120 days that differs from the ERP, split quantities add up, and confidence clears the pass mark (default 90%). Otherwise the run stops and a planner checks it.
- No customer message is ever sent by the agent. Drafts go to an approval queue.
- Orders worth the approval limit or more (default $25,000) need the ops manager.
- A wording check confirms each draft states the order number and the new date; if not, it goes to the manager.

## Run it locally (developer setup)

The start scripts above do this for you. To run the pieces yourself:

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY to use Claude; leave empty for rules mode

# backend
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# frontend, in a second terminal
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxies /api to :8000)
```

Or build the frontend once and let the API serve everything on one port:

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --port 8000   # http://localhost:8000
```

The database is SQLite (`backend/q2d.db`) unless `DATABASE_URL` says otherwise. The sample world is created on first start.

## Sign in and try it

Sign in with a demo account (password `demo` for all): `priya@jada-demo.com` (supply planner), `marcus@jada-demo.com` (ops manager), `dana@jada-demo.com` (sales rep), `admin@jada-demo.com` (administrator). Each role sees only what it needs. Sign-in is a demo: accounts live in the browser and are not secure.

1. **Planner (Priya):** open *Supplier emails* and process all 14. Anything uncertain stops for a person.
2. **Manager (Marcus):** open *Approvals* and approve the customer updates. Each customer then replies in character (simulated).
3. **Watch the recovery:** *Customer replies* shows what each reply meant. Open an order such as **SO-5601 Atlas Labs** (critical, hard deadline) or **SO-5532 Northwind** (offered a split) to see the options, the conversation and the timeline. Approve a recovery plan and the order moves back to low risk.
4. **Start over** (sidebar) resets the demo data.

## What happens after the customer is told

Every late order gets a case. The customer's reply is read (accepts, cannot accept, wants part now, wants faster shipping, wants a credit, cancels, asks a question), the options are costed (ship from stock, split, reallocate from lower-priority orders, express shipping, substitute item, new date, credit, chase the supplier) and the best one for that customer is proposed. Customers can have a hard deadline, take part deliveries, or be flexible. A person approves before anything changes. The case closes when the order is back to low risk, or is escalated with fallbacks. Inventory works the same way: warehouse stock notes update stock and replan affected orders, and items at their reorder point get a purchase order proposed.

## Testing

```bash
cd backend
pytest -q                                   # 25 tests: engine, 75-case reader pack, 31 scenarios, replies, recovery, API
python -m app.cli scenarios --mode rules    # 31 of 31 with the rules engine
python -m app.cli scenarios                 # uses Claude instead if ANTHROPIC_API_KEY is set
```

The reader pack's last 25 cases were written after the rules engine was built, as a held-out check (first run 23 of 25, now 25 of 25). It is still JADA's own test set: add a client's real supplier emails before going live.

## Deploy

**Vercel (web app) + Render (API), the setup used for the hosted demo.** The API needs a long-running server (background jobs, saved state), so it runs on Render and the web app on Vercel.

1. Render: New > Blueprint > pick this repo. `render.yaml` creates a free web service named `quote-to-delivery`. Its URL is `https://quote-to-delivery.onrender.com` (if Render gives another name, change the destination in `frontend/vercel.json`). The free plan sleeps when idle and resets its data on restart, which suits the demo.
2. Vercel: Add New > Project > import this repo, set the root directory to `frontend`. `frontend/vercel.json` builds the app and sends `/api/*` to Render.


The `Dockerfile` builds the frontend and serves it from the API in one container.

**Docker Compose (app + Postgres):**
```bash
cp .env.example .env    # set ANTHROPIC_API_KEY
docker compose up --build
```

**Render:** New > Blueprint, point it at this repo. `render.yaml` creates the web service and a Postgres database. Add `ANTHROPIC_API_KEY` in the dashboard.

**Railway, Fly.io, Azure Container Apps, Google Cloud Run:** deploy the Dockerfile, set `DATABASE_URL` to a Postgres database (Supabase and Neon work) and `ANTHROPIC_API_KEY`. The container listens on `$PORT` (default 8000). Health check: `/api/health`.

Without `DATABASE_URL`, the container uses SQLite at `/data/q2d.db`. Mount a volume there if you want data to survive restarts.

### Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | empty | Optional. Enables Claude. Empty means the rules engine does everything |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model used for reading, drafting and chat |
| `DATABASE_URL` | `sqlite:///./q2d.db` | Any SQLAlchemy URL. `postgres://` URLs are accepted |
| `DEMO_TODAY` | `2026-10-26` | The sample data is dated around this day. `live` uses the real date |
| `AGENT_STEP_DELAY_MS` | `300` | Pause between steps so people can watch a run. `0` for none |
| `SEED_ON_START` | `true` | Create the sample world on first start |
| `CORS_ORIGINS` | empty | Comma-separated origins, if the frontend is hosted separately |

Approval limit, pass mark, tone, AI or rules mode, and auto-run are set per client on the *Settings* screen.

## Going live for a client

1. Implement the four interfaces in `backend/app/connectors/base.py` against the client's systems: `ERPConnector` (for example SAP, NetSuite, Dynamics), `CRMConnector` (Salesforce, HubSpot), `MailboxConnector` (Microsoft Graph, Gmail), `OutboxConnector`.
2. Swap `SimulatedSystems` for them where `Agent` is created (`agent.py`).
3. Load 50 or more of the client's past supplier emails as scenarios and check the score before switching auto-run on.
4. Set the client's approval limit, pass mark and tone in Settings.

Everything else (the agent, guardrails, engine, prompts, traces and UI) stays the same. That is the accelerator.

## Project layout

```
backend/
  app/
    agent.py          the agent runner and its traced steps
    engine.py         delivery dates, impact, priority, quote checks
    llm.py            Claude client and tool-use loop
    prompts.py        every prompt sent to Claude
    rules_reader.py   keyword backup reader
    connectors/       base interfaces + simulated systems
    scenarios.py      8 test scenarios with expected results
    chat_tools.py     read-only tools for the chat agent
    api.py, main.py   FastAPI routes; serves the built frontend
    models.py, db.py  SQLAlchemy tables (SQLite or Postgres)
    seed.py           the sample world
    cli.py            seed, reset, run scenarios
  tests/
frontend/
  src/App.tsx         layout, navigation, live status strip
  src/pages/          one file per area
  src/components/Trace.tsx   the run trace and the human checkpoints
Dockerfile, docker-compose.yml, render.yaml, .github/workflows/ci.yml
```

All companies, people, orders and figures in the sample data are made up.
