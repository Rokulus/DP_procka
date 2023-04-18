import os
import json
import shutil
import matlab.engine
import numpy as np
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Query, File, UploadFile, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse

from typing import Union, List, Annotated

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import get_password_hash
from app.models import User, MatlabInstances
from app.schemas.requests import UserCreateRequest, UserUpdatePasswordRequest
from app.schemas.responses import UserResponse

from pathlib import Path

router = APIRouter()

templates = Jinja2Templates(directory="static/templates")

async def get_free_matlab_instance(session):
    engs = matlab.engine.find_matlab()

    matlab_instances_db = await session.execute(select(MatlabInstances).where(MatlabInstances.matlab_instance.in_(engs)))
    matlab_instances = matlab_instances_db.scalars().all()

    # get a set of existing instances from the  matlab_instances in the database
    existing_instances = set(instance.matlab_instance for instance in matlab_instances)

    for eng in engs:
        if eng not in existing_instances:
            matlab_instance = MatlabInstances(
                matlab_instance = eng,
                user_email = None
            )
            session.add(matlab_instance)
            await session.commit()

    #free instance in database if some instance was not freed due to failure of API or Matlab
    now = int(time.time())
    for instance in matlab_instances:
        if instance.expires_at is not None and now > instance.expires_at:
            instance.expires_at = None
            instance.user_email = None
            await session.commit()

    matlab_free_instance_database = await session.execute(select(MatlabInstances).where(MatlabInstances.user_email == None))
    free_instance = matlab_free_instance_database.scalars().first()
    if free_instance is None:
        raise HTTPException(status_code=400, detail="None of the Matlab Instance is free right now")

    return free_instance

@router.put("/model-run")
async def run_matlab_model(
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
    uploaded_model: UploadFile = File(...)
):
    """Run Matlab model"""
    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_location = f"{PROJECT_DIR}/uploaded_matlab_files/{uploaded_model.filename}"
    FILE_EXIST = Path(file_location)
    if not FILE_EXIST.is_file():
        with open(file_location, "wb+") as file_object:
            file_object.write(uploaded_model.file.read())

    try:
        #eng.open_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{uploaded_model.filename}', nargout=0) # -> with GUI
        eng.load_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{uploaded_model.filename}', nargout=0) # -> without GUI
        model_name = uploaded_model.filename[:-4]
        eng.set_param(f'{model_name}','SimulationCommand', 'start', nargout=0)
        #ten while je kvoli tomu aby stihol vytvorit out.data lebo ked to tu nie je tak ten kkt prejde dalej aj ked este neskoncila simulacia
        while float(eng.get_param(f'{model_name}','SimulationTime')) <= float(eng.get_param(f'{model_name}','StopTime')) and eng.get_param(f'{model_name}', 'SimulationStatus') != 'stopped':
            time.sleep(1)
        eng.eval(f"workspace_name = get_param('{model_name}/To Workspace','VariableName')",nargout=0)
        workspace_variableName = eng.workspace['workspace_name']
        eng.eval(f'x = out.{workspace_variableName};',nargout=0)
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
    except matlab.engine.MatlabExecutionError as e:
        return {e.args[0]}
    except Exception as e:
        return {"Error message: ": e}
    finally:
        free_instance.user_email = None
        free_instance.expires_at = None
        await session.commit()

    return final_result

@router.get("/websocket", include_in_schema=False)
async def get(request: Request):
    return templates.TemplateResponse("websocket.html", {
        "request": request,
    })

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Annotated[str, Depends(deps.get_current_websocket)],
    email: str,
    session: AsyncSession = Depends(deps.get_session),
):
    await websocket.accept()

    free_instance = await get_free_matlab_instance(session=session)
    result = await session.execute(select(User).where(User.email == email))
    if result.scalars().first() is None:
        raise WebSocketException(
            code=status.HTTP_404_NOT_FOUND,
            reason="Use your email-adress.",
        )
    free_instance.user_email = email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    while True:
        try:
            modelName = await websocket.receive_text()
            block = await websocket.receive_text()
            file = await websocket.receive_bytes()

            PROJECT_DIR = Path(__file__).parent.parent.parent.parent
            file_location = f"{PROJECT_DIR}/uploaded_matlab_files/{modelName}.slx"
            FILE_EXIST = Path(file_location)
            if not FILE_EXIST.is_file():
                with open(file_location, "wb+") as file_object:
                    file_object.write(file)

            #eng.open_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{modelName}', nargout=0) # -> with GUI
            eng.load_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{modelName}', nargout=0) # -> without GUI
            eng.set_param(f'{modelName}', 'EnablePacing', 'on', nargout=0) # -> slow simulation for testing
            eng.set_param(f'{modelName}','SimulationCommand', 'start', nargout=0)
            while float(eng.get_param(f'{modelName}','SimulationTime')) <= float(eng.get_param(f'{modelName}','StopTime')) and eng.get_param(f'{modelName}', 'SimulationStatus') != 'stopped':
                eng.eval(f'get_param("{modelName}","SimulationTime")', nargout=0)
                eng.eval(f'rto = get_param("{modelName}/{block}", "RuntimeObject")', nargout=0)
                eng.eval('real_time_data = rto.OutputPort(1).Data', nargout=0)
                real_time_data = eng.workspace['real_time_data']
                await push_data(websocket, real_time_data)
        except WebSocketException as e:
            return {'Exception websocket ERROR: ':  e}
        except matlab.engine.MatlabExecutionError as e:
            return {e.args[0]}
        except WebSocketDisconnect:
            free_instance.user_email = None
            free_instance.expires_at = None
            await session.commit()

@asyncio.coroutine
def push_data(websocket, data):
        yield from websocket.send_text(f"Data: {data}")
        yield from asyncio.sleep(0)

@router.put("/model-list-blocks")
async def get_list_of_blocks(
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
    uploaded_model: UploadFile = File(...),
):
    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_location = f"{PROJECT_DIR}/uploaded_matlab_files/{uploaded_model.filename}"
    FILE_EXIST = Path(file_location)
    if not FILE_EXIST.is_file():
        with open(file_location, "wb+") as file_object:
            file_object.write(uploaded_model.file.read())

    try:
        eng.load_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{uploaded_model.filename}', nargout=0)
        model_name = uploaded_model.filename[:-4]
        eng.eval(f'bl = getfullname(Simulink.findBlocks("{model_name}"))', nargout=0)
        bl = eng.workspace['bl']
        eng.quit()
    except matlab.engine.MatlabExecutionError as e:
        return {e.args[0]}
    except Exception as e:
        return {"Error message: ": e}
    finally:
        free_instance.user_email = None
        free_instance.expires_at = None
        await session.commit()

    return bl

@router.put("/block-object-param-names/{block}")
async def get_block_params_names(
    block: str,
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

    eng.load_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{uploaded_model.filename}', nargout=0)
    model_name = uploaded_model.filename[:-4]
    eng.eval(f'param_names = fieldnames(get_param("{model_name}/{block}","ObjectParameters"))', nargout=0)
    param_names = eng.workspace['param_names']
    eng.quit()

    return param_names

@router.put("/block-param/{block}/{param}")
async def get_block_param(
    block: str,
    param: str,
    uploaded_model: UploadFile = File(...)
):
    parameter = ""
    try:
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

        eng.load_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{uploaded_model.filename}', nargout=0)
        model_name = uploaded_model.filename[:-4]
        eng.eval(f'param = get_param("{model_name}/{block}","{param}")', nargout=0)
        parameter = eng.workspace['param']
        eng.quit()
        return {param :str(parameter)}
    except matlab.engine.MatlabExecutionError as e:
        return {e.args[0]}

@router.put("/block-DialogParams/{block}")
async def get_block_dialog_params(
    block: str,
    uploaded_model: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_location = f"{PROJECT_DIR}/uploaded_matlab_files/{uploaded_model.filename}"
    FILE_EXIST = Path(file_location)
    if not FILE_EXIST.is_file():
        with open(file_location, "wb+") as file_object:
            file_object.write(uploaded_model.file.read())

    try:
        eng.load_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{uploaded_model.filename}', nargout=0) # -> without GUI
        model_name = uploaded_model.filename[:-4]
        eng.eval(f"""
                output = '';
                params = fieldnames(get_param('{model_name}/{block}', 'DialogParameters'));
                for i = 1:numel(params)
                    param = params{{i}};
                    value = mat2str(get_param('{model_name}/{block}', param));
                    output = [output, sprintf('%s = %s\\n', param, value)];
                end
                """, nargout=0)

        output = eng.workspace['output']
        lines = output.split('\n')
        output_dict = {}
        for line in lines:
            if line == '':
                break
            parts = line.split('=')
            key = parts[0].strip()
            value = parts[1].strip()
            output_dict[key] = value
        eng.quit()
        return output_dict

    except matlab.engine.MatlabExecutionError as e:
        return {e.args[0]}

    except Exception as e:
        return {"Error message: ": e}

    finally:
        free_instance.user_email = None
        free_instance.expires_at = None
        await session.commit()

@router.put("/set-block-param/{block}/{param}")
async def get_list_of_blocks(
    block: str,
    param: str,
    new_param: str,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
    uploaded_model: UploadFile = File(...),
):
    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_location = f"{PROJECT_DIR}/uploaded_matlab_files/{uploaded_model.filename}"
    FILE_EXIST = Path(file_location)
    if not FILE_EXIST.is_file():
        with open(file_location, "wb+") as file_object:
            file_object.write(uploaded_model.file.read())

    try:
        eng.load_system(f'{PROJECT_DIR}\\uploaded_matlab_files\\{uploaded_model.filename}', nargout=0)
        model_name = uploaded_model.filename[:-4]
        eng.eval(f"set_param('{model_name}/{block}', '{param}', '{new_param}')", nargout=0)
        #eng.set_param(f"'{model_name}/{block}', '{param}', '{new_param}'", nargout=0)
        eng.eval(f"result_of_change = get_param('{model_name}/{block}','{param}')", nargout=0)
        #result = eng.get_param(f"'{model_name}/{block}','{param}'", nargout=0)
        result = eng.workspace['result_of_change']
        eng.quit()
    except matlab.engine.MatlabExecutionError as e:
        return {e.args[0]}
    except Exception as e:
        return {"Error message: ": e}
    finally:
        free_instance.user_email = None
        free_instance.expires_at = None
        await session.commit()

    return {f"Change of {block} was success" :result}