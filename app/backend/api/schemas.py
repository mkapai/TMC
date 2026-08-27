"""Shared API response and request schemas."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error: Optional[str] = None
    code: Optional[str] = None


class PaginatedResponse(BaseModel):
    success: bool = True
    data: list[Any]
    total: int
    page: int
    page_size: int


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)


class LoginResponse(BaseModel):
    success: bool = True
    message: str
    token: str
    user: dict[str, Any]
    expires_in: int


class HealthCheckResponse(BaseModel):
    status: str
    bot_running: bool
    timestamp: Optional[datetime] = None
    version: Optional[str] = None


class ForwardRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_chat_id: str
    source_chat_name: Optional[str] = None
    client_id: str = "main_user"
    client_type: Literal["user", "bot"] = "user"
    delivery_mode: Literal["auto", "manual"] = "auto"
    destination_ids: list[int] = Field(min_length=1)
    is_active: bool = True


class ForwardRuleResponse(BaseModel):
    id: int
    name: str
    source_chat_id: str
    client_id: str
    delivery_mode: Literal["auto", "manual"]
    destination_ids: list[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime
