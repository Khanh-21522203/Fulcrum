import asyncio
import logging

import grpc
import uvicorn
from fastapi import FastAPI
from control_plane.api.ops import router as ops_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Fulcrum Control Plane")
app.include_router(ops_router)


async def _serve_grpc() -> None:
    server = grpc.aio.server()
    # TODO: register AggregatedDiscoveryServicer once protos are compiled:
    #   from control_plane.xds.ads import AggregatedDiscoveryServicer
    #   add_AggregatedDiscoveryServiceServicer_to_server(AggregatedDiscoveryServicer(), server)
    server.add_insecure_port("[::]:18000")
    await server.start()
    logger.info("gRPC ADS server listening on :18000")
    await server.wait_for_termination()


async def _serve_http() -> None:
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    await asyncio.gather(_serve_grpc(), _serve_http())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
