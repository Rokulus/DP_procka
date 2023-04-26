import os
import json
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Query, File, UploadFile, WebSocket, WebSocketDisconnect, WebSocketException, status
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

@router.get("/model-info", include_in_schema=False)
async def show_model_info(
    request: Request,
):
    path = "static/assets/models_xml"
    files = os.listdir(path)
    return templates.TemplateResponse("info.html", {
        "request": request,
        "files": json.dumps(files)
    })

@router.get("/model/{modelName}", include_in_schema=False)
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
        raise HTTPException(status_code=400, detail="Model does not exist")
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
async def download_model(modelName: str):
    if (os.path.isfile(f"static/assets/models/{modelName}/{modelName}.js") == False):
        return {"Model does not exist"}
    if (os.path.isfile(f"static/assets/models/{modelName}.zip") == True):
        file_path = f"static/assets/models/{modelName}.zip"
    else:
        shutil.make_archive(f'static/assets/models/{modelName}', 'zip', 'static/assets/models', f'{modelName}')
        file_path = f"static/assets/models/{modelName}.zip"

    return FileResponse(path=file_path, filename=modelName + ".zip", media_type="multipart/form-data")

@router.post("/upload-download-fmu")
async def upload_and_download_fmu(
    uploaded_fmu: UploadFile = File(...)
):
    file_extension = uploaded_fmu.filename[-4:]
    if file_extension not in [".fmu"]:
        raise HTTPException(status_code=400, detail="Invalid file type, please upload files with .fmu")

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_name = uploaded_fmu.filename[:-4]
    if(os.path.isdir(f"{PROJECT_DIR}/static/assets/models/{file_name}") == True):
        raise HTTPException(status_code=400, detail="Model with same name already exist. Please change name of uploaded model or just download it from the site of models")
    file_location = f"{PROJECT_DIR}/Bodylight.js-FMU-Compiler/input/{uploaded_fmu.filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(uploaded_fmu.file.read())
    file_path = f"{PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip"
    timeout = 10   # [seconds]
    timeout_start = time.time()
    while time.time() < timeout_start + timeout:
        if os.path.isfile(file_path):
            break
        time.sleep(1)
    if(os.path.isfile(file_path)):
        os.system(f"unzip {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip -d {PROJECT_DIR}/static/assets/models/{file_name}")
        os.system(f"cp -R {PROJECT_DIR}/static/assets/models/{file_name}/{file_name}.xml {PROJECT_DIR}/static/assets/models_xml")
        return FileResponse(path=file_path, filename=file_name + ".zip", media_type="multipart/form-data")
    else:
        raise HTTPException(status_code=400, detail=f"File was not uploaded and downloaded or is taking longer than {timeout} seconds to convert file")

@router.post("/upload-model")
async def upload_fmu(
    uploaded_fmu: UploadFile = File(...)
):
    file_extension = uploaded_fmu.filename[-4:]
    if file_extension not in [".fmu"]:
        raise HTTPException(status_code=400, detail="Invalid file type, please upload files with .fmu")

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_name = uploaded_fmu.filename[:-4]
    if(os.path.isdir(f"{PROJECT_DIR}/static/assets/models/{file_name}") == True):
        raise HTTPException(status_code=400, detail="Model with same name already exist. Please change name of uploaded model or just download it from the site of models")
    file_location = f"{PROJECT_DIR}/Bodylight.js-FMU-Compiler/input/{uploaded_fmu.filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(uploaded_fmu.file.read())
    file_path = f"{PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip"
    timeout = 10   # [seconds]
    timeout_start = time.time()
    while time.time() < timeout_start + timeout:
        if os.path.isfile(file_path):
            break
        time.sleep(1)
    if(os.path.isfile(file_path)):
        os.system(f"unzip {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip -d {PROJECT_DIR}/static/assets/models/{file_name}")
        os.system(f"cp -R {PROJECT_DIR}/static/assets/models/{file_name}/{file_name}.xml {PROJECT_DIR}/static/assets/models_xml")
        return {"Success of uploading FMU file"}
    else:
        raise HTTPException(status_code=400, detail=f"File was not uploaded or is taking longer than {timeout} seconds to upload")

@router.delete("/model-remove/{modelName}")
async def remove_model(
    modelName: str,
):

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if (os.path.isfile(f"{PROJECT_DIR}/static/assets/models/{modelName}/{modelName}.js") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")

    os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{modelName}.log")
    if(os.path.isfile(f"{PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{modelName}.log")):
        raise HTTPException(status_code=400, detail="Failed deleting log file in output file of compiler")

    os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{modelName}.zip")
    if(os.path.isfile(f"{PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{modelName}.zip")):
        raise HTTPException(status_code=400, detail="Failed deleting zip file in output directory of compiler")

    if(os.path.isfile(f"{PROJECT_DIR}/static/assets/models/{modelName}.zip")):
        os.remove(f"{PROJECT_DIR}/static/assets/models/{modelName}.zip")

    shutil.rmtree(f"{PROJECT_DIR}/static/assets/models/{modelName}")
    if(os.path.isdir(f"{PROJECT_DIR}/static/assets/models/{modelName}")):
        raise HTTPException(status_code=400, detail="Failed deleting directory of model")

    os.remove(f"{PROJECT_DIR}/static/assets/models_xml/{modelName}.xml")
    if(os.path.isfile(f"{PROJECT_DIR}/static/assets/models/{modelName}")):
        raise HTTPException(status_code=400, detail="Failed deleting xml of model")

    return {"Success of deleting FMU model": True}
