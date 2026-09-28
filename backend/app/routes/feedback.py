"""Feedback and bug reporting routes for Beta. Prefix: /feedback (or under api_router)."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ..schemas.feedback import FeedbackCreate, FeedbackResponse
from ..services.telegram_service import (
    DEFAULT_TELEGRAM_CHANNEL_URL,
    DEFAULT_TELEGRAM_GROUP_URL,
    format_feedback_for_telegram,
    send_telegram_message,
)

logger = logging.getLogger("app.routes.feedback")

router = APIRouter(prefix="/feedback", tags=["Feedback"])

FEEDBACK_FILE = Path(os.environ.get("FEEDBACK_STORAGE_PATH", "logs/feedback.jsonl"))


def _ensure_storage_dir():
    try:
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("Could not ensure directory for feedback storage: %s", exc)


def _append_feedback(record: dict[str, Any]):
    _ensure_storage_dir()
    try:
        # Create a lightweight copy without large base64 screenshot if needed,
        # or truncate screenshot in log to prevent huge file bloat
        stored = dict(record)
        if stored.get("screenshot") and len(stored["screenshot"]) > 1000:
            # Keep screenshot but log truncated version to app logs
            pass
        with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(stored, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to write feedback record to file: %s", exc)


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit user feedback or bug report",
)
async def submit_feedback(
    payload: FeedbackCreate,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Submit a bug report, feature request, confusing UI issue, or data issue."""
    now = datetime.now(timezone.utc)
    feedback_id = f"fb_{uuid.uuid4().hex[:12]}"

    client_ip = request.client.host if request.client else "unknown"
    user_agent = payload.user_agent or request.headers.get("user-agent", "unknown")

    record = {
        "id": feedback_id,
        "category": payload.category,
        "page_or_feature": payload.page_or_feature,
        "message": payload.message,
        "contact_method": payload.contact_method,
        "screenshot": payload.screenshot,
        "user_agent": user_agent,
        "client_ip": client_ip,
        "received_at": now.isoformat(),
    }

    # Persist to disk
    _append_feedback(record)
    logger.info(
        "FEEDBACK_RECEIVED | id=%s | category=%s | page=%s | contact=%s",
        feedback_id,
        payload.category,
        payload.page_or_feature,
        payload.contact_method or "none",
    )

    # Dispatch to Telegram asynchronously
    msg_html = format_feedback_for_telegram(record)
    background_tasks.add_task(send_telegram_message, msg_html)

    return FeedbackResponse(
        success=True,
        id=feedback_id,
        message="Thank you! Your feedback has been received and logged.",
        received_at=now,
    )


@router.get(
    "/community-links",
    summary="Get official Telegram community and discussion group links",
)
async def get_community_links():
    """Returns official links to the Telegram channel and linked discussion group."""
    return {
        "channel_url": os.environ.get("TELEGRAM_CHANNEL_URL", DEFAULT_TELEGRAM_CHANNEL_URL),
        "discussion_url": os.environ.get("TELEGRAM_GROUP_URL", DEFAULT_TELEGRAM_GROUP_URL),
        "support_email": os.environ.get("SUPPORT_EMAIL", "support@tradinglabs.com"),
    }


@router.get(
    "",
    summary="List recent feedback items (diagnostics/admin)",
)
async def list_feedback(limit: int = 50):
    """Retrieve recent feedback items from local storage."""
    if not FEEDBACK_FILE.exists():
        return {"items": [], "total": 0}

    items: List[dict] = []
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        # Omit screenshot string from list endpoint to keep response fast & small
                        if "screenshot" in data and data["screenshot"]:
                            data["has_screenshot"] = True
                            del data["screenshot"]
                        items.append(data)
                    except Exception:
                        continue
    except Exception as exc:
        logger.warning("Error reading feedback file: %s", exc)

    items.reverse()  # Newest first
    return {"items": items[:limit], "total": len(items)}
