from fastapi import APIRouter

from app.api.endpoints import auth, users, fmuJS, fmu, matlab, logs

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authorization"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(fmuJS.router, prefix="/fmuJS", tags =["FMU Javascript"])
api_router.include_router(fmu.router, prefix="/fmu", tags=["FMU"])
api_router.include_router(matlab.router, prefix="/matlab", tags=["Matlab"])
api_router.include_router(logs.router, prefix="/logs", tags=["Logs"])
