import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def normalize_email(value: str) -> str:
    return value.strip().lower()


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class UserRead(BaseModel):
    role: Literal["user", "admin"] = "user"
    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class AccessTokenResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: str = "bearer"


class TokenResponse(AccessTokenResponse):
    refresh_token: str = Field(repr=False)
    refresh_expires_at: datetime = Field(exclude=True)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)
