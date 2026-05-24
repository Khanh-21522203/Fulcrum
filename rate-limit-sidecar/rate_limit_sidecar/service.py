from fulcrum_grpc_api.envoy.service.ratelimit.v3 import rls_pb2_grpc


class RateLimitServicer(rls_pb2_grpc.RateLimitServiceServicer):
    """Envoy rate limit gRPC servicer stub."""

    def ShouldRateLimit(self, request, context):
        # TODO: implement per-service token-bucket / leaky-bucket logic
        raise NotImplementedError
