import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import get_password_hash
from app.models import User
from app.schemas.requests import UserCreateRequest, UserUpdatePasswordRequest, UserChangeEmailRequest
from app.schemas.responses import UserResponse

from pathlib import Path

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(deps.get_current_user),
):
    """Get current user"""
    return current_user

@router.delete("/me", status_code=204)
async def delete_current_user(
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Delete current user"""
    await session.execute(delete(User).where(User.id == current_user.id))
    await session.commit()

@router.post("/change-email")
async def update_current_user_email(
    new_email: UserChangeEmailRequest,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Update current user email"""
    result = await session.execute(select(User).where(User.email == new_email.email))
    if result.scalars().first() is not None:
        raise HTTPException(status_code=400, detail="Cannot use this email address")
    current_user.email = new_email.email
    session.add(current_user)
    await session.commit()
    return current_user


@router.post("/reset-password", response_model=UserResponse)
async def reset_current_user_password(
    user_update_password: UserUpdatePasswordRequest,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """Update current user password"""
    current_user.hashed_password = get_password_hash(user_update_password.password)
    session.add(current_user)
    await session.commit()
    return current_user


@router.post("/register", response_model=UserResponse)
async def register_new_user(
    new_user: UserCreateRequest,
    session: AsyncSession = Depends(deps.get_session),
):
    """Create new user"""
    result = await session.execute(select(User).where(User.email == new_user.email))
    if result.scalars().first() is not None:
        raise HTTPException(status_code=400, detail="Cannot use this email address")
    user = User(
        email=new_user.email,
        hashed_password=get_password_hash(new_user.password),
        is_superuser=False
    )
    session.add(user)
    await session.commit()

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent
    name_of_user_directory = user.id
    path = f"{PROJECT_DIR}/uploaded_fmu_files/{name_of_user_directory}"
    os.mkdir(path)

    path = f"{PROJECT_DIR}/uploaded_matlab_files/{name_of_user_directory}"
    os.mkdir(path)

    path = f"{PROJECT_DIR}/static/assets/models/{name_of_user_directory}"
    os.mkdir(path)

    path = f"{PROJECT_DIR}/static/assets/models_xml/{name_of_user_directory}"
    os.mkdir(path)

    return user

@router.get("/all-users", response_model=list[UserResponse])
async def show_all_users(
    current_user: User = Depends(deps.get_current_user), #musi tam by toto ak to chcem mat autorizovane
    session: AsyncSession = Depends(deps.get_session),
):
    """Get all users if authorized user is super user"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    result = await session.execute(select(User))
    return result.scalars().all()

@router.delete("/delete-user")
async def delete_current_user(
    user_email: str,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Delete specified user if authorized user is super user"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    await session.execute(delete(User).where(User.email == user_email))
    await session.commit()
    return {"Success"}