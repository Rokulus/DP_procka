import os
import shutil

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import get_password_hash
from app.models import User

from pathlib import Path

router = APIRouter()

@router.get("/")
async def get_error_log(
    current_user: User = Depends(deps.get_current_user),
):
    """Get error logs"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_location = f"{PROJECT_DIR}/error.log"

    return FileResponse(path=file_location, filename="error.log", media_type="multipart/form-data")
