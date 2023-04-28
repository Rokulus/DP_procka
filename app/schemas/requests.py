from pydantic import BaseModel, EmailStr
from dataclasses import dataclass
from fastapi import Query
from typing import Any, Dict

class BaseRequest(BaseModel):
    # may define additional fields or config shared across requests
    pass


class RefreshTokenRequest(BaseRequest):
    refresh_token: str


class UserUpdatePasswordRequest(BaseRequest):
    password: str

class UserChangeEmailRequest(BaseRequest):
    email: EmailStr

class UserCreateRequest(BaseRequest):
    email: EmailStr
    password: str

class RunFMUModelRequest(BaseRequest):
    startTime: float = None
    stopTime: float = 5
    stepSize: float = None
    solver: str = "CVode"
    relative_tolerance: float = None
    startValues: Dict[str, Any] = {}
    outputInterval: float = None
    outputValues: str = ""


