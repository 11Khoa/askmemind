import uuid
from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.user import UserCreate

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class AdminUserCreate(UserCreate):
    role: Literal["user", "admin"] = "user"


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if self.role is None and self.is_active is None:
            raise ValueError("Choose a role or account state")
        return self


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: uuid.UUID | None
    actor_email: str | None = None
    target_user_id: uuid.UUID | None
    target_email: str | None = None
    action: str
    resource_id: uuid.UUID | None
    outcome: str
    request_id: str | None
    details: dict | None
    created_at: datetime
