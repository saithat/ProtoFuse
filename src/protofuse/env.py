"""Load repository `.env` and normalize partner credentials for CLI/scripts."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


def load_repo_env(*, override: bool = False) -> None:
    """Load `.env` from the repo root into the current process.

    Modal: ``MODAL_TOKEN_ID`` / ``MODAL_TOKEN_SECRET`` from `.env` take precedence
    over ``~/.modal.toml`` when set (Modal SDK reads these env vars directly).
    ``MODAL_ENVIRONMENT`` selects the proto-tools deployment namespace (often ``main``).
    """

    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=override)

    # Normalize common copy/paste mistakes (spaces, quotes).
    for key in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "MODAL_ENVIRONMENT"):
        raw = os.environ.get(key)
        if raw is None:
            continue
        cleaned = raw.strip().strip('"').strip("'")
        if cleaned != raw:
            os.environ[key] = cleaned

    # When unset, proto-tools defaults to proto-env; keep MODAL_ENVIRONMENT explicit.
    if os.environ.get("MODAL_ACTIVE", "").lower() in ("1", "true", "yes"):
        os.environ.setdefault("MODAL_ENVIRONMENT", "main")


def modal_configured() -> bool:
    """Return True when Modal credentials are available from env or ~/.modal.toml."""

    load_repo_env()
    if os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET"):
        return True
    return (Path.home() / ".modal.toml").is_file()
