import json
import logging
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"ts": utc_now(), "event": event, **fields}
    logging.getLogger("supportops.agent").log(
        level, json.dumps(payload, ensure_ascii=True)
    )
