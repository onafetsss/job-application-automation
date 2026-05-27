"""Profile routes — stub for Phase 2 plan 02-06 implementation."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def profile_status() -> dict:
    return {"status": "not_implemented"}
