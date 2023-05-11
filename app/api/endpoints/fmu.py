import zipfile

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import get_password_hash
from app.models import User
from app.schemas.requests import RunFMUModelRequest
from app.schemas.responses import UserResponse

from fmpy import *
from fmpy.util import *

from pathlib import Path

router = APIRouter()

@router.post("")
async def upload_fmu_model(
    current_user: User = Depends(deps.get_current_user),
    uploaded_model: UploadFile = File(...),
):
    """Upload FMU model, only upload files with .fmu extension. If you upload file with same name, the old one will be updated."""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_extension = uploaded_model.filename[-4:]
    if file_extension not in [".fmu"]:
        raise HTTPException(status_code=400, detail="Invalid file type, please upload files with .fmu")

    file_location = f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{uploaded_model.filename}"
    FILE_EXIST = Path(file_location)

    with open(file_location, "wb+") as file_object:
        file_object.write(uploaded_model.file.read())
    return {"FMU model was successfully uploaded ": uploaded_model.filename}

@router.get("/get-uploaded-models")
async def get_uploaded_models(
    current_user: User = Depends(deps.get_current_user),
):
    """Return array of uploaded FMU models"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    path = f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}"
    files = os.listdir(path)
    files_arr = []
    for f in files:
        files_arr.append(f)
    return files_arr

@router.get("/{model_name}")
async def download_fmu_model(
    model_name: str,
    current_user: User = Depends(deps.get_current_user),
):
    """Download FMU model, please state name of desired model without .fmu"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if(os.path.isfile(f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")

    file_location = f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu"

    return FileResponse(path=file_location, filename=model_name + ".fmu", media_type="multipart/form-data")

@router.get("/model-info/{model_name}")
async def fmu_model_info(
    model_name: str,
    current_user: User = Depends(deps.get_current_user),
):
    """Get info about FMU model, please provide name of the model without .fmu extension"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if(os.path.isfile(f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")

    file_location = f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu"

    md = read_model_description(file_location, validate=False)
    platforms = supported_platforms(file_location)

    fmi_types = []
    if md.modelExchange is not None:
        fmi_types.append('Model Exchange')
    if md.coSimulation is not None:
        fmi_types.append('Co-Simulation')

    ex = md.defaultExperiment

    variables = []
    for v in md.modelVariables:
        start = str(v.start) if v.start is not None else ''
        unit = v.declaredType.unit if v.declaredType else v.unit
        variables.append({
            "Name": v.name,
            "Causality": v.causality,
            "Start": start,
            "Unit": unit,
            "Description": v.description
        })

    model_info = {
        "Model Info": {
            "FMI Version": md.fmiVersion,
            "FMI Type": ', '.join(fmi_types),
            "Model Name": md.modelName,
            "Description": md.description,
            "Platforms": ', '.join(platforms),
            "Continuous States": md.numberOfContinuousStates,
            "Event Indicators": md.numberOfEventIndicators,
            "Number of variables": len(md.modelVariables),
            "Generation Tool": md.generationTool,
            "Generation Date": md.generationDateAndTime
        },
        "Default Experiment": {
            "Start Time": ex.startTime,
            "Stop Time": ex.stopTime,
            "Tolerance": ex.tolerance,
            "Step Size": ex.stepSize
        },
        "Variables": variables
    }
    return {"model": model_info}

@router.post("/model-run/{model_name}")
async def fmu_model_run(
    model_name: str,
    model: RunFMUModelRequest,
    current_user: User = Depends(deps.get_current_user),
):
    """Run uploaded FMU model, please provide name of the model without .fmu extension. startValues must be in format {"h": 2, "v": 3}"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if(os.path.isfile(f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")

    file_location = f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu"

    outputValues = model.outputValues
    if model.outputValues == "":
        outputValues = None

    try:
        result = simulate_fmu(file_location, output=outputValues, start_values=model.startValues , start_time=model.startTime, stop_time=model.stopTime, step_size=model.stepSize, solver=model.solver, relative_tolerance=model.relative_tolerance)
    except Exception as e:
        return {"There was and error while simulating FMU. Please check if support platform of your FMU file is linux64."}
    fmu_result = np.array(result) # je to treba zmenit z numpy na str aby sa to dalo poslat
    keys = fmu_result.dtype.names

    final_result = []
    for value in fmu_result:
        temp_dict = {}
        for i, key in enumerate(keys):
            temp_dict.update({key: value[i]})
        final_result.append(temp_dict)

    return final_result

@router.delete("/{model_name}")
async def delete_uploaded_model(
    model_name: str,
    current_user: User = Depends(deps.get_current_user),
):
    """Delete model that is already uploaded, please provide name of the model without .fmu"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    if(os.path.isfile(f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu") == False):
        raise HTTPException(status_code=400, detail="Model does not exist")

    os.remove(f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu")

    if (os.path.isfile(f"{PROJECT_DIR}/uploaded_fmu_files/{current_user.id}/{model_name}.fmu") == True):
        raise HTTPException(status_code=400, detail="FMU model was not deleted")
    else:
        return {f"FMU model {model_name} was deleted successfully"}






