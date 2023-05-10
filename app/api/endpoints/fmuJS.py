import os
import json
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Query, File, UploadFile, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, RedirectResponse

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

# Site endpoints

@router.get("/model-info", include_in_schema=False)
async def show_model_info(
    request: Request,
):
    cookie_authorization: str = request.cookies.get("Authorization")
    if cookie_authorization == None:
        return RedirectResponse("https://apis.iolab.sk/auth/login")
    result = await deps.check_access_token(token=cookie_authorization)

    cookie_userId: str = request.cookies.get("UserId")

    path = "static/assets/models_xml/" + cookie_userId
    files = os.listdir(path)
    return templates.TemplateResponse("info.html", {
        "request": request,
        "files": json.dumps(files),
        "userId": cookie_userId
    })

@router.get("/model/{model_name}", include_in_schema=False)
async def show_model(
    request: Request,
    model_name: str,
    modelMode: Union[str, None] = "continuous",
    stopTime: float = 10,
    dataSets: List[str] = Query([]),
    stepSize: float = 0.1,
    interval: float = 30
):
    cookie_authorization: str = request.cookies.get("Authorization")
    if cookie_authorization == None:
        return RedirectResponse("https://apis.iolab.sk/auth/login")
    result = await deps.check_access_token(token=cookie_authorization)

    cookie_userId: str = request.cookies.get("UserId")

    if(os.path.isdir(f"static/assets/models/{cookie_userId}/{model_name}") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")
    f = open(f'static/assets/models/{cookie_userId}/{model_name}/{model_name}.js', 'r')
    content = f.read()
    f.close()
    return templates.TemplateResponse("model.html", {
        "request": request,
        "userId": cookie_userId,
        "model_name": model_name,
        "modelMode": modelMode,
        "stopTime": stopTime,
        "dataSets": json.dumps(dataSets),
        "stepSize": stepSize,
        "interval": interval,
        "contentOfJS": content
    })

@router.get("/download-model-site/{model_name}", include_in_schema=False)
async def download_model_site(
    request: Request,
    model_name: str
):
    cookie_authorization: str = request.cookies.get("Authorization")
    if cookie_authorization == None:
        return RedirectResponse("https://apis.iolab.sk/auth/login")
    result = await deps.check_access_token(token=cookie_authorization)

    cookie_userId: str = request.cookies.get("UserId")

    if (os.path.isfile(f"static/assets/models/{cookie_userId}/{model_name}/{model_name}.js") == False):
        return {"Model does not exist"}
    if (os.path.isfile(f"static/assets/models/{cookie_userId}/{model_name}.zip") == True):
        file_path = f"static/assets/models/{cookie_userId}/{model_name}.zip"
    else:
        shutil.make_archive(f'static/assets/models/{cookie_userId}/{model_name}', 'zip', f'static/assets/models/{cookie_userId}', f'{model_name}')
        file_path = f"static/assets/models/{cookie_userId}/{model_name}.zip"

    return FileResponse(path=file_path, filename=model_name + ".zip", media_type="multipart/form-data")

@router.post("/upload-download-fmu-site", include_in_schema=False)
async def upload_and_download_fmu_site(
    request: Request,
    uploaded_fmu: UploadFile = File(...)
):
    """Uploaded FMU file will be converted to Javascript and XML and returned to user for download. It will also be uplaoded on server."""
    cookie_authorization: str = request.cookies.get("Authorization")
    if cookie_authorization == None:
        return RedirectResponse("https://apis.iolab.sk/auth/login")
    result = await deps.check_access_token(token=cookie_authorization)

    cookie_userId: str = request.cookies.get("UserId")

    file_extension = uploaded_fmu.filename[-4:]
    if file_extension not in [".fmu"]:
        raise HTTPException(status_code=400, detail="Invalid file type, please upload files with .fmu")
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_name = uploaded_fmu.filename[:-4]
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
        os.system(f"unzip {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip -d {PROJECT_DIR}/static/assets/models/{cookie_userId}/{file_name}")
        os.system(f"cp -R {PROJECT_DIR}/static/assets/models/{cookie_userId}/{file_name}/{file_name}.xml {PROJECT_DIR}/static/assets/models_xml/{cookie_userId}")

        os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.log")
        os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip")

        shutil.make_archive(f'static/assets/models/{cookie_userId}/{file_name}', 'zip', f'static/assets/models/{cookie_userId}', f'{file_name}')
        file_path_download = file_path = f"static/assets/models/{cookie_userId}/{file_name}.zip"

        return FileResponse(path=file_path_download, filename=file_name + ".zip", media_type="multipart/form-data")
    else:
        raise HTTPException(status_code=400, detail=f"File was not uploaded and downloaded or is taking longer than {timeout} seconds to convert file")

@router.post("/upload-fmu-site", include_in_schema=False)
async def upload_fmu_site(
    request: Request,
    uploaded_fmu: UploadFile = File(...)
):
    """Upload FMU file."""
    cookie_authorization: str = request.cookies.get("Authorization")
    if cookie_authorization == None:
        return RedirectResponse("https://apis.iolab.sk/auth/login")
    result = await deps.check_access_token(token=cookie_authorization)

    cookie_userId: str = request.cookies.get("UserId")

    file_extension = uploaded_fmu.filename[-4:]
    if file_extension not in [".fmu"]:
        raise HTTPException(status_code=400, detail="Invalid file type, please upload files with .fmu")
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_name = uploaded_fmu.filename[:-4]
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
        os.system(f"unzip {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip -d {PROJECT_DIR}/static/assets/models/{cookie_userId}/{file_name}")
        os.system(f"cp -R {PROJECT_DIR}/static/assets/models/{cookie_userId}/{file_name}/{file_name}.xml {PROJECT_DIR}/static/assets/models_xml/{cookie_userId}")

        os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.log")
        os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip")

        return {"Success of uploading FMU file"}
    else:
        raise HTTPException(status_code=400, detail=f"File was not uploaded or is taking longer than {timeout} seconds to upload")

@router.get("/model-remove/{model_name}", include_in_schema=False)
async def remove_model(
    request: Request,
    model_name: str,
):
    cookie_authorization: str = request.cookies.get("Authorization")
    if cookie_authorization == None:
        return RedirectResponse("https://apis.iolab.sk/auth/login")
    result = await deps.check_access_token(token=cookie_authorization)

    cookie_userId: str = request.cookies.get("UserId")

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if (os.path.isfile(f"{PROJECT_DIR}/static/assets/models/{cookie_userId}/{model_name}/{model_name}.js") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")

    if(os.path.isfile(f"{PROJECT_DIR}/static/assets/models/{cookie_userId}/{model_name}.zip")):
        os.remove(f"{PROJECT_DIR}/static/assets/models/{cookie_userId}/{model_name}.zip")

    shutil.rmtree(f"{PROJECT_DIR}/static/assets/models/{cookie_userId}/{model_name}")
    if(os.path.isdir(f"{PROJECT_DIR}/static/assets/models/{cookie_userId}/{model_name}")):
        raise HTTPException(status_code=400, detail="Failed deleting directory of model")

    os.remove(f"{PROJECT_DIR}/static/assets/models_xml/{cookie_userId}/{model_name}.xml")
    if(os.path.isfile(f"{PROJECT_DIR}/static/assets/models_xml/{cookie_userId}/{model_name}.xml")):
        raise HTTPException(status_code=400, detail="Failed deleting xml of model")

    return {"Success of deleting FMU model": True}

# Only Endpoints

@router.get("/{model_name}")
async def download_model(
    model_name: str,
    current_user: User = Depends(deps.get_current_user)
):
    """Download ZIP file of Javascript and XML version of model."""
    if (os.path.isfile(f"static/assets/models/{current_user.id}/{model_name}/{model_name}.js") == False):
        return {"Model does not exist"}
    if (os.path.isfile(f"static/assets/models/{current_user.id}/{model_name}.zip") == True):
        file_path = f"static/assets/models/{current_user.id}/{model_name}.zip"
    else:
        shutil.make_archive(f'static/assets/models/{current_user.id}/{model_name}', 'zip', f'static/assets/models/{current_user.id}', f'{model_name}')
        file_path = f"static/assets/models/{current_user.id}/{model_name}.zip"

    return FileResponse(path=file_path, filename=model_name + ".zip", media_type="multipart/form-data")

@router.post("/upload-download-fmu")
async def upload_and_download_fmu(
    uploaded_fmu: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_user)
):
    """Uploaded FMU file will be converted to Javascript and XML and returned to user for download. It will also be uplaoded on server. If you upload file with same name, the old one will be updated."""
    file_extension = uploaded_fmu.filename[-4:]
    if file_extension not in [".fmu"]:
        raise HTTPException(status_code=400, detail="Invalid file type, please upload files with .fmu")
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_name = uploaded_fmu.filename[:-4]
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
        os.system(f"unzip {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip -d {PROJECT_DIR}/static/assets/models/{current_user.id}/{file_name}")
        os.system(f"cp -R {PROJECT_DIR}/static/assets/models/{current_user.id}/{file_name}/{file_name}.xml {PROJECT_DIR}/static/assets/models_xml/{current_user.id}")

        os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.log")
        os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip")

        shutil.make_archive(f'static/assets/models/{current_user.id}/{file_name}', 'zip', f'static/assets/models/{current_user.id}', f'{file_name}')
        file_path_download = file_path = f"static/assets/models/{current_user.id}/{file_name}.zip"

        return FileResponse(path=file_path_download, filename=file_name + ".zip", media_type="multipart/form-data")
    else:
        raise HTTPException(status_code=400, detail=f"File was not uploaded and downloaded or is taking longer than {timeout} seconds to convert file")

@router.post("")
async def upload_fmu(
    uploaded_fmu: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_user)
):
    """Upload FMU file. If you upload file with same name, the old one will be updated."""
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
        os.system(f"unzip {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip -d {PROJECT_DIR}/static/assets/models/{current_user.id}/{file_name}")
        os.system(f"cp -R {PROJECT_DIR}/static/assets/models/{current_user.id}/{file_name}/{file_name}.xml {PROJECT_DIR}/static/assets/models_xml/{current_user.id}")

        os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.log")
        os.system(f"rm -f {PROJECT_DIR}/Bodylight.js-FMU-Compiler/output/{file_name}.zip")

        return {"Success of uploading FMU file"}
    else:
        raise HTTPException(status_code=400, detail=f"File was not uploaded or is taking longer than {timeout} seconds to upload")

@router.delete("/{model_name}")
async def remove_model(
    model_name: str,
    current_user: User = Depends(deps.get_current_user)
):

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if (os.path.isfile(f"{PROJECT_DIR}/static/assets/models/{current_user.id}/{model_name}/{model_name}.js") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")

    if(os.path.isfile(f"{PROJECT_DIR}/static/assets/models/{current_user.id}/{model_name}.zip")):
        os.remove(f"{PROJECT_DIR}/static/assets/models/{current_user.id}/{model_name}.zip")

    shutil.rmtree(f"{PROJECT_DIR}/static/assets/models/{current_user.id}/{model_name}")
    if(os.path.isdir(f"{PROJECT_DIR}/static/assets/models/{current_user.id}/{model_name}")):
        raise HTTPException(status_code=400, detail="Failed deleting directory of model")

    os.remove(f"{PROJECT_DIR}/static/assets/models_xml/{current_user.id}/{model_name}.xml")
    if(os.path.isfile(f"{PROJECT_DIR}/static/assets/models_xml/{current_user.id}/{model_name}.xml")):
        raise HTTPException(status_code=400, detail="Failed deleting xml of model")

    return {"Success of deleting FMU model": True}

