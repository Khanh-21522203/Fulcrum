import logging
from concurrent import futures

import grpc

from auth_sidecar.handler import AuthorizationServicer
from fulcrum_grpc_api.envoy.service.auth.v3.external_auth_pb2_grpc import (
    add_AuthorizationServicer_to_server,
)


logger = logging.getLogger(__name__)


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_AuthorizationServicer_to_server(AuthorizationServicer(), server)
    server.add_insecure_port("[::]:9191")
    server.start()
    logger.info("Auth gRPC server listening on :9191")
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
