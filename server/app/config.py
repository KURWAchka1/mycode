from __future__ import annotations

import os
import base64
import json
from dataclasses import dataclass
from pathlib import Path

from .auto_reply import DEFAULT_AUTO_REPLY_TEXT


def playerok_identity_from_token(token: str) -> tuple[str, str]:
    """Read stable account claims without a fragile Playerok APQ profile call."""
    try:
        payload = token.split(".", 2)[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        user_id = str(claims.get("sub", "") or "").strip()
        identity = str(claims.get("identity", "") or "").strip()
        return user_id, identity
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return "", ""


def _read_secret(env_name: str, file_env_name: str) -> str:
    direct = os.getenv(env_name, "").strip()
    if direct:
        return direct
    path = os.getenv(file_env_name, "").strip()
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return ""


def _read_text(env_name: str, file_env_name: str, default: str) -> str:
    path = os.getenv(file_env_name, "").strip()
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    value = os.getenv(env_name)
    return value if value is not None else default


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "да"}


@dataclass(frozen=True)
class Settings:
    playerok_token: str
    playerok_user_agent: str
    api_token: str
    poll_host: str
    poll_port: int
    auto_reply_enabled: bool
    auto_reply_text: str
    data_dir: Path
    retry_interval_seconds: int
    log_level: str

    @property
    def database_path(self) -> Path:
        return self.data_dir / "orders.sqlite3"

    @classmethod
    def load(cls) -> "Settings":
        s = cls(
            playerok_token=_read_secret("PLAYEROK_TOKEN", "PLAYEROK_TOKEN_FILE"),
            playerok_user_agent=os.getenv(
                "PLAYEROK_USER_AGENT",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            ),
            api_token=_read_secret("API_TOKEN", "API_TOKEN_FILE"),
            poll_host=os.getenv("POLL_HOST", "127.0.0.1").strip(),
            poll_port=int(os.getenv("POLL_PORT", "8765")),
            auto_reply_enabled=_as_bool(os.getenv("AUTO_REPLY_ENABLED"), True),
            auto_reply_text=_read_text(
                "AUTO_REPLY_TEXT",
                "AUTO_REPLY_TEXT_FILE",
                DEFAULT_AUTO_REPLY_TEXT,
            ),
            data_dir=Path(os.getenv("DATA_DIR", "/var/lib/playerok-monitor")),
            retry_interval_seconds=max(10, int(os.getenv("RETRY_INTERVAL_SECONDS", "30"))),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
        s.validate()
        s.data_dir.mkdir(parents=True, exist_ok=True)
        return s

    def validate(self) -> None:
        missing: list[str] = []
        if not self.playerok_token:
            missing.append("PLAYEROK_TOKEN / PLAYEROK_TOKEN_FILE")
        if not self.api_token:
            missing.append("API_TOKEN / API_TOKEN_FILE")
        if not self.poll_host:
            missing.append("POLL_HOST")
        if not 1 <= self.poll_port <= 65535:
            missing.append("POLL_PORT 1..65535")
        if missing:
            raise RuntimeError("Missing/invalid configuration: " + "; ".join(missing))
