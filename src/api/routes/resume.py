"""Resume routes — stub for Phase 2 plan 02-04 implementation."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def resume_status() -> dict:
    return {"status": "not_implemented"}
