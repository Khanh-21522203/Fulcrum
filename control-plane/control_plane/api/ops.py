from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    raise HTTPException(501, "not implemented")


@router.get("/snapshots")
async def list_snapshots() -> dict:
    raise HTTPException(501, "not implemented")


@router.post("/snapshots/invalidate", status_code=202)
async def invalidate_snapshots() -> dict:
    raise HTTPException(501, "not implemented")


@router.get("/snapshots/{node_group}/diff")
async def snapshot_diff(node_group: str) -> dict:
    raise HTTPException(501, "not implemented")
