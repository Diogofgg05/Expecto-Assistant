"""Backwards-compatible API request models."""
from pydantic import BaseModel, Field


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=8)
    session_id: str = Field(default="", max_length=64)


class VoiceText(BaseModel):
    text: str = Field(min_length=1, max_length=240)
