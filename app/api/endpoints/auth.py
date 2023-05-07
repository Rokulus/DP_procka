import time

import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core import config, security
from app.models import User
from app.schemas.requests import RefreshTokenRequest
from app.schemas.responses import AccessTokenResponse

from typing import List
from typing import Optional

router = APIRouter()

templates = Jinja2Templates(directory="static/templates")

class LoginForm:
    def __init__(self, request: Request):
        self.request: Request = request
        self.errors: List = []
        self.username: Optional[str] = None
        self.password: Optional[str] = None

    async def load_data(self):
        form = await self.request.form()
        self.username = form.get("email")
        self.password = form.get("password")

@router.get("/login", include_in_schema=False)
async def show_model_info(
    request: Request,
):
    return templates.TemplateResponse("login.html", {
        "request": request,
    })

@router.post("/login", include_in_schema=False)
async def show_model_info(
    request: Request,
    session: AsyncSession = Depends(deps.get_session),
):
    form = LoginForm(request)
    await form.load_data()

    result = await session.execute(select(User).where(User.email == form.username))
    user = result.scalars().first()

    if user is None:
        form.__dict__.update(msg="")
        raise HTTPException(status_code=400, detail="Incorrect email")

    if not security.verify_password(form.password, user.hashed_password):
        form.__dict__.update(msg="")
        raise HTTPException(status_code=400, detail="Incorrect password")

    form.__dict__.update(msg="You are logged in")
    response = templates.TemplateResponse("login.html", form.__dict__)
    response.set_cookie(
        "Authorization",
        value=f"{security.generate_access_token(str(user.id))}",
        max_age=1800,
        expires=1800,
    )
    response.set_cookie(
        "UserId",
        value=f"{str(user.id)}",
        max_age=1800,
        expires=1800,
    )
    return response

@router.post("/access-token", response_model=AccessTokenResponse)
async def login_access_token(
    session: AsyncSession = Depends(deps.get_session),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """OAuth2 compatible token, get an access token for future requests using username and password"""

    result = await session.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()

    if user is None:
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    if not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    return security.generate_access_token_response(str(user.id))


@router.post("/refresh-token", response_model=AccessTokenResponse)
async def refresh_token(
    input: RefreshTokenRequest,
    session: AsyncSession = Depends(deps.get_session),
):
    """OAuth2 compatible token, get an access token for future requests using refresh token"""
    try:
        payload = jwt.decode(
            input.refresh_token,
            config.settings.SECRET_KEY,
            algorithms=[security.JWT_ALGORITHM],
        )
    except (jwt.DecodeError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials, unknown error",
        )

    # JWT guarantees payload will be unchanged (and thus valid), no errors here
    token_data = security.JWTTokenPayload(**payload)

    if not token_data.refresh:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials, cannot use access token",
        )
    now = int(time.time())
    if now < token_data.issued_at or now > token_data.expires_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials, token expired or not yet valid",
        )

    result = await session.execute(select(User).where(User.id == token_data.sub))
    user = result.scalars().first()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return security.generate_access_token_response(str(user.id))
