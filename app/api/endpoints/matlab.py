import os
import json
import shutil
import matlab.engine
import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Request, Query, File, UploadFile
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

@router.get("/")
def get_matlab():
    engs = matlab.engine.find_matlab()
    if not engs:
       eng = matlab.engine.start_matlab()
    else:
       eng = matlab.engine.connect_matlab(engs[0])

    b = 6
    eng.workspace['b'] = b
    c = eng.eval('a+b')
    return {"matlab" : c}

@router.put("/{number}")
def put_matlab(number: int):
    engs = matlab.engine.find_matlab()
    if not engs:
       eng = matlab.engine.start_matlab()
    else:
       eng = matlab.engine.connect_matlab(engs[0])

    eng.workspace['x'] = number
    y = 2
    eng.workspace['y'] = y
    z = eng.eval('x-y')
    return {"matlab_put" : z}

@router.put("/model/{number}")
async def put_matlab_model(
   number: int,
   uploaded_model: UploadFile = File(...)
):
    engs = matlab.engine.find_matlab()
    if not engs:
       eng = matlab.engine.start_matlab()
    else:
       eng = matlab.engine.connect_matlab(engs[0])

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_location = f"{PROJECT_DIR}/uploaded_matlab_files/{uploaded_model.filename}"
    FILE_EXIST = Path(file_location)
    if not FILE_EXIST.is_file():
        with open(file_location, "wb+") as file_object:
            file_object.write(uploaded_model.file.read())

    eng.open_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{uploaded_model.filename}', nargout=0)
    model_name = uploaded_model.filename[:-4]
    eng.set_param(f'{model_name}/Gain','Gain', str(number), nargout=0)
    eng.sim(f'{model_name}')
    eng.eval('x = out.data;',nargout=0)
    eng.eval('t = out.tout;',nargout=0)
    x = eng.workspace['x']
    t = eng.workspace['t']
    eng.quit()

    data = np.array(x)
    data_time = np.array(t)
    key = "data"
    final_result = []
    for value in data:
        temp_dict = {}
        temp_dict.update({key: value[0]})
        final_result.append(temp_dict)

    key = "time"
    for i, value in enumerate(data_time):
        final_result[i].update({key: value[0]})


    return final_result


