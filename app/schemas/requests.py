from pydantic import BaseModel, EmailStr
from dataclasses import dataclass
from fastapi import Query

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

class UploadFMURequest(BaseRequest):
    startTime: float
    stopTime: float
    stepSize: float
    solver: str
    relative_tolerance: float
    startValues: str
    outputInterval: int
    outputValues: str

@dataclass
class Model:
    startTime: float = Query(None, description="describes A")
    stopTime: float = Query(None, description="describes A")
    stepSize: float = None
    solver: str = Query("CVode", description="describes solver")
    relative_tolerance: float = Query(None, description="describes A")
    startValues: str = None
    outputInterval: int = None
    outputValues: str = Query(None, description="Must be in format: variable1,variable2")

