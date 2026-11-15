"""FastAPI app. Every router lives in its own module, so later tasks add routes without editing this file."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.routers import files, memory, runs
from backend.runtime.runs import end_interrupted_runs


@asynccontextmanager
async def lifespan(_: FastAPI):
    end_interrupted_runs()  # runs a previous process left half done
    yield


app = FastAPI(title="Prompt-to-Device", lifespan=lifespan)
for module in (runs, files, memory):
    app.include_router(module.router)
