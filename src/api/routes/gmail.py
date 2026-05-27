"""Gmail routes — stub for Phase 2 plan 02-02 implementation."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def gmail_status() -> dict:
    return {"status": "not_implemented"}
