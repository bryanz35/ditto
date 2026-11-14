"""Run files API: GET /runs/{id}/spec and GET /runs/{id}/files/{path} (paths stay inside the run)."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.contracts.runner import run_dir_for
from backend.runtime.runs import RUN_ID

router = APIRouter()


def existing_run_dir(run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id) or not run_dir_for(run_id).is_dir():
        raise HTTPException(404, f"No run {run_id!r}")
    return run_dir_for(run_id)


@router.get("/runs/{run_id}/spec")
def get_spec(run_id: str) -> FileResponse:
    return get_file(run_id, "spec.json")


@router.get("/runs/{run_id}/files/{path:path}")
def get_file(run_id: str, path: str) -> FileResponse:
    run_dir = existing_run_dir(run_id).resolve()
    file = (run_dir / path).resolve()
    if not file.is_relative_to(run_dir) or not file.is_file():
        raise HTTPException(404, f"No file {path!r} in run {run_id}")
    return FileResponse(file)
