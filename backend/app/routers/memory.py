"""Inventory, preferences and rejections (T16). Both routes speak UserContext, so the UI and the
agent need no extra types: GET /memory reads it, PUT /memory replaces it and returns what was saved."""

from functools import cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.contracts.parts import PARTS_DIR, load_library
from backend.contracts.spec import UserContext
from backend.memory.store import MemoryStore

router = APIRouter()


@cache
def get_store() -> MemoryStore:
    return MemoryStore()


Store = Annotated[MemoryStore, Depends(get_store)]


@router.get("/memory")
def get_memory(store: Store) -> UserContext:
    return store.load()


@router.put("/memory")
def put_memory(user: UserContext, store: Store) -> UserContext:
    lib, problems = load_library(), []
    unknown = sorted(pid for pid in user.owned if pid not in lib)
    if unknown:
        problems.append(f"unknown part ids in owned: {', '.join(unknown)}")
    negative = sorted(pid for pid, qty in user.owned.items() if qty < 0)
    if negative:
        problems.append(f"negative quantities in owned: {', '.join(negative)}")
    if user.budget_usd is not None and user.budget_usd < 0:
        problems.append("budget_usd must be 0 or more")
    printers = sorted(p.stem for p in (PARTS_DIR / "printers").glob("*.yaml"))
    if user.printer is not None and user.printer not in printers:
        problems.append(
            f"unknown printer {user.printer!r}; known: {', '.join(printers)}"
        )
    if problems:
        raise HTTPException(422, "; ".join(problems))
    return store.save(user)
