import asyncio
import logging
import os
from concurrent import futures

import grpc
import uvicorn
from fastapi import FastAPI
from control_plane.api.ops import router as ops_router
from control_plane.app_state import snapshot_builder, snapshot_cache
from control_plane.xds.ads import AggregatedDiscoveryServicer
from fulcrum_grpc_api.envoy.service.discovery.v3.ads_pb2_grpc import (
    add_AggregatedDiscoveryServiceServicer_to_server,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Fulcrum Control Plane")
app.include_router(ops_router)


async def _serve_grpc() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_AggregatedDiscoveryServiceServicer_to_server(
        AggregatedDiscoveryServicer(snapshot_cache),
        server,
    )
    server.add_insecure_port("[::]:18000")
    server.start()
    logger.info("gRPC ADS server listening on :18000")
    try:
        await asyncio.Event().wait()
    finally:
        server.stop(grace=None)


async def _serve_http() -> None:
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    await _seed_local_snapshot()
    await asyncio.gather(_serve_grpc(), _serve_http())


async def _seed_local_snapshot() -> None:
    if os.getenv("FULCRUM_DEV_SEED_INSTANCE") != "1":
        return
    snapshot = await snapshot_builder.build("local")
    snapshot_cache.set(snapshot)
    logger.info("Seeded local snapshot version %s", snapshot.version)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
