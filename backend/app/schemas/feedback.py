"""Schemas for user feedback and bug reporting."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

FeedbackCategory = Literal[
    "bug",
    "feature_request",
    "confusing_ui",
    "data_issue",
    "other",
]


class FeedbackCreate(BaseModel):
    category: FeedbackCategory = Field(
        ...,
        description="Type of feedback: bug, feature_request, confusing_ui, data_issue, or other",
    )
    page_or_feature: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name of the page or feature where the issue or suggestion applies",
    )
    message: str = Field(
        ...,
        min_length=3,
        max_length=10000,
        description="Detailed description from the user",
    )
    contact_method: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional contact method (email, telegram username, phone)",
    )
    screenshot: Optional[str] = Field(
        default=None,
        description="Optional base64/data URL screenshot",
    )
    user_agent: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Browser client user agent string",
    )


class FeedbackResponse(BaseModel):
    success: bool
    id: str
    message: str
    received_at: datetime
