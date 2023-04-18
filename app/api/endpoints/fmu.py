import zipfile

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import get_password_hash
from app.models import User
from app.schemas.requests import UploadFMURequest, Model
from app.schemas.responses import UserResponse

from fmpy import *
from fmpy.util import *

from pathlib import Path

router = APIRouter()

@router.post("/modelInfo")
async def fmu_model_info(
    current_user: User = Depends(deps.get_current_user),
    uploaded_fmu: UploadFile = File(...),
):
    """Get info about FMU model"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_location = f"{PROJECT_DIR}/uploaded_fmu_files/{uploaded_fmu.filename}"
    FILE_EXIST = Path(file_location)
    if not FILE_EXIST.is_file():
        with open(file_location, "wb+") as file_object:
            file_object.write(uploaded_fmu.file.read())

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

@router.post("/fmu/modelRun")
async def fmu_model_run(
    current_user: User = Depends(deps.get_current_user),
    model: Model = Depends(),
    uploaded_fmu: UploadFile = File(...)
):
    """Run FMU model"""
    PROJECT_DIR = Path(__file__).parent.parent.parent.parent

    file_location = f"{PROJECT_DIR}/uploaded_fmu_files/{uploaded_fmu.filename}"
    FILE_EXIST = Path(file_location)
    if not FILE_EXIST.is_file():
        with open(file_location, "wb+") as file_object:
            file_object.write(uploaded_fmu.file.read())

    outputValues = None
    if model.outputValues != None:
        outputValues = model.outputValues.split(",")
        for i, value in enumerate(outputValues): #if somebody writes values with whitespace after ","
            outputValues[i] = ''.join(value.split())

    startValues_dict = {}
    if model.startValues != None:
        startValues = model.startValues.split(",")
        for i, value in enumerate(startValues): #if somebody writes values with whitespace
            startValues[i] = ''.join(value.split())
            values = startValues[i].split("=")
            startValues_dict.update({values[0]: values[1]})

    try:
        result = simulate_fmu(file_location, output=outputValues, start_values=startValues_dict , start_time=model.startTime, stop_time=model.stopTime, step_size=model.stepSize, solver=model.solver, relative_tolerance=model.relative_tolerance)
    except Exception as e:
        return {"Error from simulate_fmu:": e}
    fmu_result = np.array(result) # je to treba zmenit z numpy na str aby sa to dalo poslat
    keys = fmu_result.dtype.names

    final_result = []
    for value in fmu_result:
        temp_dict = {}
        for i, key in enumerate(keys):
            temp_dict.update({key: value[i]})
        final_result.append(temp_dict)

    return final_result




