"""Runtime configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path


def _load_dotenv() -> None:
    """Read KEY=value lines from .env in the repo root (or backend/) without overriding real env vars."""
    root = Path(__file__).resolve().parents[2]
    for f in (root / ".env", root / "backend" / ".env"):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ and v != "":
                os.environ[k] = v


if os.getenv("Q2D_SKIP_DOTENV") != "1":
    _load_dotenv()


def _flag(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./q2d.db")
    # Hosts like Render and Heroku hand out postgres:// URLs; SQLAlchemy needs the driver named.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings:
    DATABASE_URL: str = _database_url()
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    # The sample data is dated around 26 Oct 2026. Set DEMO_TODAY=live to use the real date.
    DEMO_TODAY: str = os.getenv("DEMO_TODAY", "2026-10-26")
    AGENT_STEP_DELAY_MS: int = int(os.getenv("AGENT_STEP_DELAY_MS", "300"))
    SEED_ON_START: bool = _flag("SEED_ON_START", True)
    # How long a simulated customer "thinks" before replying to an update. 0 = immediately.
    REPLY_DELAY_MS: int = int(os.getenv("REPLY_DELAY_MS", "6000"))
    CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    FRONTEND_DIST: Path = Path(os.getenv("FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist")))

    @property
    def today(self) -> str:
        return date.today().isoformat() if self.DEMO_TODAY == "live" else self.DEMO_TODAY


settings = Settings()
