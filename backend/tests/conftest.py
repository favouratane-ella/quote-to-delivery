import os

os.environ["Q2D_SKIP_DOTENV"] = "1"
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["AGENT_STEP_DELAY_MS"] = "0"
os.environ["REPLY_DELAY_MS"] = "0"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FRONTEND_DIST"] = str(Path(_tmp) / "no-frontend")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.seed import create_world  # noqa: E402

init_db()


@pytest.fixture()
def db():
    s = SessionLocal()
    create_world(s, "main")
    yield s
    s.close()
