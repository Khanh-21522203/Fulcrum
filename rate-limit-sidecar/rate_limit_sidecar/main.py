import logging
from concurrent import futures

import grpc
from rate_limit_sidecar.service import RateLimitServicer
from fulcrum_grpc_api.envoy.service.ratelimit.v3.rls_pb2_grpc import (
    add_RateLimitServiceServicer_to_server,
)

logger = logging.getLogger(__name__)


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_RateLimitServiceServicer_to_server(RateLimitServicer(), server)
    server.add_insecure_port("[::]:8081")
    server.start()
    logger.info("Rate limit gRPC server listening on :8081")
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
