"""Background job: a simulated customer "thinks" for a moment, then answers, and the agent reads the answer."""
from __future__ import annotations

import time

from . import models as m
from .agent import Agent, utcnow
from .config import settings
from .db import SessionLocal

W = "main"


def reply_bg(so: str, stage: str = "notice", proposal_id: int | None = None) -> None:
    if settings.REPLY_DELAY_MS:
        time.sleep(settings.REPLY_DELAY_MS / 1000)
    db = SessionLocal()
    try:
        agent = Agent(db, W)
        rid = agent.sim_followup(so, stage, proposal_id)
        if rid and agent.cfg.auto_run:
            agent.run_reply(rid)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        db.add(m.ActivityLog(world_id=W, at=utcnow(), actor="System", system="Customer", text=f"Simulated reply for {so} failed: {e}"))
        db.commit()
    finally:
        db.close()
