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
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

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

    # add new instances
    for eng in engs:
        if eng not in existing_instances:
            matlab_instance = MatlabInstances(
                matlab_instance = eng,
                user_email = None
            )
            session.add(matlab_instance)
            await session.commit()

    # delete old instances
    await session.execute(delete(MatlabInstances).where(MatlabInstances.matlab_instance.notin_(engs)))
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
        raise HTTPException(status_code=400, detail="None of the Matlab Instances are free right now")

    return free_instance

@router.get("/get-matlab-instances")
async def get_matlab_instances(
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Return free Matlab instances"""
    free_instance = await get_free_matlab_instance(session=session)
    result = await session.execute(select(MatlabInstances))
    return result.scalars().all()

@router.post("")
async def upload_matlab_model(
    current_user: User = Depends(deps.get_current_user),
    uploaded_model: UploadFile = File(...),
):
    """Upload Matlab model, please only upload files with .slx or .mdl extension. If you upload file with same name, the old one will be updated. """
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_extension = uploaded_model.filename[-4:]
    if file_extension not in [".slx", ".mdl"]:
        raise HTTPException(status_code=400, detail="Invalid file type, please upload files with .slx or .mdl")

    file_location = f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{uploaded_model.filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(uploaded_model.file.read())
    return {"Matlab model was successfully uploaded ": uploaded_model.filename}


@router.get("/get-uploaded-models")
async def get_uploaded_models(
    current_user: User = Depends(deps.get_current_user),
):
    """Return uploaded Matlab models"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    path = f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}"
    files = os.listdir(path)
    files_arr = []
    for f in files:
        files_arr.append(f)
    return files_arr

@router.get("/model-list-blocks/{model_name}")
async def get_list_of_blocks(
    model_name: str,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Return list of blocks in model, please provide name of the model with extension .slx or .mdl based on the model you want to use."""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent
    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}") == False):
        raise HTTPException(status_code=400, detail="Matlab model does not exist")

    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    try:
        eng.load_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0)
        name = model_name[:-4]
        eng.eval(f'bl = getfullname(Simulink.findBlocks("{name}"))', nargout=0)
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

@router.get("/block-DialogParams/{model_name}/{block}")
async def get_block_dialog_params(
    model_name: str,
    block: str,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Return Dialog Parameter of desired block, please provide name of the model with extension .slx or .mdl based on the model you want to use."""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent
    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}") == False):
        raise HTTPException(status_code=400, detail="Matlab model does not exist")

    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    try:
        eng.load_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0) # -> without GUI
        name = model_name[:-4]
        eng.eval(f"""
                output = '';
                params = fieldnames(get_param('{name}/{block}', 'DialogParameters'));
                for i = 1:numel(params)
                    param = params{{i}};
                    value = mat2str(get_param('{name}/{block}', param));
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
        eng.close_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0)
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

@router.get("/block-param-info/{model_name}/{block}/{param}")
async def get_block_param_info(
    model_name: str,
    block: str,
    param: str,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Return parameter of desired block, please provide name of the model with extension .slx or .mdl based on the model you want to use."""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent
    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}") == False):
        raise HTTPException(status_code=400, detail="Matlab model does not exist")

    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    parameter = ""
    try:
        eng.load_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0)
        name = model_name[:-4]
        eng.eval(f'param = get_param("{name}/{block}","{param}")', nargout=0)
        parameter = eng.workspace['param']
        eng.close_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0)
        eng.quit()
        return {param :str(parameter)}
    except matlab.engine.MatlabExecutionError as e:
        return {e.args[0]}
    finally:
        free_instance.user_email = None
        free_instance.expires_at = None
        await session.commit()

@router.get("/{model_name}")
async def download_matlab_model(
    model_name: str,
    current_user: User = Depends(deps.get_current_user),
):
    """Download Matlab model, please provide name of the model with .slx or .mdl"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if(os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")

    file_location = f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}"

    return FileResponse(path=file_location, filename=model_name, media_type="multipart/form-data")

@router.post("/model-run/{model_name}")
async def run_matlab_model(
    model_name: str,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Run Matlab model, please provide name of the model with extension .slx or .mdl based on the model you want to run."""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent
    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}") == False):
        raise HTTPException(status_code=400, detail="Matlab model does not exist")

    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)


    try:
        #eng.open_system(f'{PROJECT_DIR}/uploaded_matlab_files/{uploaded_model.filename}', nargout=0) # -> with GUI
        eng.load_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0) # -> without GUI
        name = model_name[:-4]
        eng.set_param(f'{name}','SimulationCommand', 'start', nargout=0)
        while float(eng.get_param(f'{name}','SimulationTime')) <= float(eng.get_param(f'{name}','StopTime')) and eng.get_param(f'{name}', 'SimulationStatus') != 'stopped':
            time.sleep(1)
        eng.eval(f"workspace_name = get_param('{name}/To Workspace','VariableName')",nargout=0)
        workspace_variableName = eng.workspace['workspace_name']
        eng.eval(f'x = out.{workspace_variableName};',nargout=0)
        eng.eval('t = out.tout;',nargout=0)
        x = eng.workspace['x']
        t = eng.workspace['t']
        eng.close_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0)
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

@router.put("/{model_name}/{block}/{param}")
async def set_block_param(
    model_name: str,
    block: str,
    param: str,
    new_value: str,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    """Set block parameter, please provide name of the model with extension .slx or .mdl based on the model you want to use."""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent
    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}") == False):
        raise HTTPException(status_code=400, detail="Matlab model does not exist")

    free_instance = await get_free_matlab_instance(session=session)
    free_instance.user_email = current_user.email
    issued_at = int(time.time()) + 2 * 60 # -> 2 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    try:
        eng.load_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0)
        name = model_name[:-4]
        eng.eval(f"set_param('{name}/{block}', '{param}', '{new_value}')", nargout=0)
        eng.eval(f"result_of_change = get_param('{name}/{block}','{param}')", nargout=0)
        result = eng.workspace['result_of_change']
        eng.save_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0)
        eng.close_system(f'{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}', nargout=0)
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


@router.delete("/{model_name}")
async def delete_uploaded_model(
    model_name: str,
    current_user: User = Depends(deps.get_current_user),
):
    """Delete model that is already uploaded, please provide name of the model with .slx or .mdl"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}") == False):
        raise HTTPException(status_code=400, detail="Matlab model does not exist")

    os.remove(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}")

    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}.original") == True):
        os.remove(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}.original")

    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}.autosave") == True):
        os.remove(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}.autosave")

    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{current_user.id}/{model_name}") == True):
        raise HTTPException(status_code=400, detail="Matlab model was not deleted")
    else:
        return {f"Matlab model {model_name} was deleted successfully"}

@router.get("/websocket/site", include_in_schema=False)
async def get(
    request: Request
):
    cookie_authorization: str = request.cookies.get("Authorization")
    if cookie_authorization == None:
        return RedirectResponse("https://apis.iolab.sk/auth/login")
    result = await deps.check_access_token(token=cookie_authorization)

    return templates.TemplateResponse("websocket.html", {
        "request": request,
    })

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    email: str,
    session: AsyncSession = Depends(deps.get_session),
):
    await websocket.accept()

    free_instance = await get_free_matlab_instance(session=session)
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if user is None or free_instance is None:
        raise WebSocketException(
            code=status.HTTP_404_NOT_FOUND,
            reason="Bad email adress or none of the free_instane is free.",
        )
    free_instance.user_email = email
    issued_at = int(time.time()) + 5 * 60 # -> 5 minutes from now
    free_instance.expires_at = issued_at
    await session.commit()
    eng = matlab.engine.connect_matlab(free_instance.matlab_instance)

    try:
        modelName = await websocket.receive_text()
        blocks = await websocket.receive_text()

        blocks = blocks.split(",")

        PROJECT_DIR = Path(__file__).parent.parent.parent.parent
        if (os.path.isfile(f"{PROJECT_DIR}/uploaded_matlab_files/{user.id}/{modelName}") == False):
            raise WebSocketException(status_code=400, detail="Matlab model does not exist")

        #eng.open_system(f'{PROJECT_DIR}/uploaded_matlab_files/{user.id}/{modelName}', nargout=0) # -> with GUI
        eng.load_system(f'{PROJECT_DIR}/uploaded_matlab_files/{user.id}/{modelName}', nargout=0) # -> without GUI
        name = modelName[:-4]
        #eng.set_param(f'{name}', 'EnablePacing', 'on', nargout=0) # -> slow simulation for testing
        eng.set_param(f'{name}','SimulationCommand', 'start', nargout=0)
        while float(eng.get_param(f'{name}','SimulationTime')) <= float(eng.get_param(f'{name}','StopTime')) and eng.get_param(f'{name}', 'SimulationStatus') != 'stopped':
            eng.eval(f'get_param("{name}","SimulationTime")', nargout=0)
            for block in blocks:
                eng.eval(f'rto = get_param("{name}/{block}", "RuntimeObject")', nargout=0)
                eng.eval('real_time_data = rto.OutputPort(1).Data', nargout=0)
                real_time_data = eng.workspace['real_time_data']
                await push_data(websocket, block ,real_time_data)
    except WebSocketException as e:
        return {'Exception websocket ERROR: ':  e}
    except matlab.engine.MatlabExecutionError as e:
        return {e.args[0]}
    finally:
        eng.close_system(f'{PROJECT_DIR}/uploaded_matlab_files/{user.id}/{modelName}', nargout=0)
        eng.quit()
        free_instance.user_email = None
        free_instance.expires_at = None
        await session.commit()

@asyncio.coroutine
def push_data(websocket, block, data):
        yield from websocket.send_text(f"{block}: {data}")
        yield from asyncio.sleep(0)
