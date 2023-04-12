import os
import json
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse

from typing import Union, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import get_password_hash
from app.models import User
from app.schemas.requests import UserCreateRequest, UserUpdatePasswordRequest
from app.schemas.responses import UserResponse

from pathlib import Path

router = APIRouter()

templates = Jinja2Templates(directory="static/templates")

@router.get("/model-info")
async def show_model_info(
    request: Request,
):
    path = "static/assets/models_xml"
    files = os.listdir(path)
    return templates.TemplateResponse("info.html", {
        "request": request,
        "files": json.dumps(files)
    })

@router.get("/model/{modelName}")
def show_model(
    request: Request,
    modelName: str,
    modelMode: Union[str, None] = "continuous",
    stopTime: float = 10,
    dataSets: List[str] = Query([]),
    stepSize: float = 0.1,
    interval: float = 30
):
    if(os.path.isdir(f"static/assets/models/{modelName}") == False):
        return {"Model does not exist"}
    f = open(f'static/assets/models/{modelName}/{modelName}.js', 'r')
    content = f.read()
    f.close()
    return templates.TemplateResponse("model.html", {
        "request": request,
        "modelName": modelName,
        "modelMode": modelMode,
        "stopTime": stopTime,
        "dataSets": json.dumps(dataSets),
        "stepSize": stepSize,
        "interval": interval,
        "contentOfJS": content
    })

@router.get("/download-model/{modelName}")
async def returnFile(modelName: str):
    if (os.path.isfile(f"static/assets/models/{modelName}/{modelName}.js") == False):
        return {"Model does not exist"}
    if (os.path.isfile(f"static/assets/models/{modelName}.zip") == True):
        file_path = f"static/assets/models/{modelName}.zip"
    else:
        shutil.make_archive(f'static/assets/models/{modelName}', 'zip', 'static/assets/models', f'{modelName}')
        file_path = f"static/assets/models/{modelName}.zip"

    return FileResponse(path=file_path, filename=modelName + ".zip", media_type="multipart/form-data")

@router.get("/model-remove/{modelName}")
async def remove_model(modelName: str):
    if (os.path.isfile(f"static/assets/models/{modelName}/{modelName}.js") == False):
        return {"Model does not exist"}

    # os.system(f"rm -f /var/www/fastapi/Bodylight.js-FMU-Compiler/output/{modelName}.log")
    # if(os.path.isfile(f"/var/www/fastapi/Bodylight.js-FMU-Compiler/output/{modelName}.log")):
    #     return {"Failed deleting log file in output file of compiler"}
    # os.system(f"rm -f /var/www/fastapi/Bodylight.js-FMU-Compiler/output/{modelName}.zip")
    # if(os.path.isfile(f"/var/www/fastapi/Bodylight.js-FMU-Compiler/output/{modelName}.zip")):
    #     return {"Failed deleting zip file in output directory of compiler"}

    if(os.path.isfile(f"static/assets/models/{modelName}.zip")):
        os.remove(f"static/assets/models/{modelName}.zip")

    shutil.rmtree(f"static/assets/models/{modelName}")
    if(os.path.isdir(f"static/assets/models/{modelName}")):
        return {"Failed deleting directory of model"}

    os.remove(f"static/assets/models_xml/{modelName}.xml")
    if(os.path.isfile(f"static/assets/models/{modelName}")):
        return {"Failed deleting xml of model"}

    return {"Success": True}
