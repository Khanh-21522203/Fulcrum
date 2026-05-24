from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from control_plane.app_state import snapshot_builder, snapshot_cache
from control_plane.snapshot import Snapshot

router = APIRouter()


class SnapshotInvalidateRequest(BaseModel):
    node_group: str = "default"


def snapshot_summary(snapshot: Snapshot) -> dict:
    return {
        "node_group": snapshot.node_group,
        "version": snapshot.version,
        "updated_at": snapshot.updated_at.isoformat(),
        "resources": snapshot.resource_counts(),
    }


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    snapshots = snapshot_cache.all()
    if not snapshots:
        raise HTTPException(503, "no snapshots loaded")
    return {
        "status": "ready",
        "snapshots": len(snapshots),
    }


@router.get("/snapshots")
async def list_snapshots() -> dict:
    return {
        "snapshots": [
            snapshot_summary(snapshot)
            for snapshot in snapshot_cache.all().values()
        ]
    }


@router.post("/snapshots/invalidate", status_code=202)
async def invalidate_snapshots(body: SnapshotInvalidateRequest) -> dict:
    snapshot = await snapshot_builder.build(body.node_group)
    snapshot_cache.set(snapshot)
    return {
        "status": "rebuilt",
        "snapshot": snapshot_summary(snapshot),
    }


@router.get("/snapshots/{node_group}/diff")
async def snapshot_diff(node_group: str) -> dict:
    current = snapshot_cache.get(node_group)
    if current is None:
        raise HTTPException(404, "snapshot not found")

    previous = snapshot_cache.previous(node_group)
    return {
        "node_group": node_group,
        "previous": snapshot_summary(previous) if previous else None,
        "current": snapshot_summary(current),
    }
