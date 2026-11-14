"""FastAPI app. Every router lives in its own module, so later tasks add routes without editing this file."""

from fastapi import FastAPI

from backend.app.routers import device, files, memory, runs

app = FastAPI(title="Prompt-to-Device")
for module in (runs, files, memory, device):
    app.include_router(module.router)
