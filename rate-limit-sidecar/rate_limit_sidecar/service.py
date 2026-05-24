# Rate Limit Service contract:
#
# Proto: envoy.service.ratelimit.v3.RateLimitService
# Method: ShouldRateLimit (unary RPC)
#
# Proto compilation required before real implementation:
#   pip install grpcio-tools
#   python -m grpc_tools.protoc -I<envoy-api-root> --python_out=. --grpc_python_out=. \
#       envoy/service/ratelimit/v3/rls.proto
#   → generates rls_pb2.py / rls_pb2_grpc.py
#
# Replace the base class below with the generated RateLimitServiceServicer.
#
# Descriptor examples Envoy sends:
#   [{"key": "service_id", "value": "my-service"},
#    {"key": "remote_address", "value": "203.0.113.5"}]
#
# Expected response: overall_code = OVER_LIMIT (2) or OK (1).


class RateLimitServicer:
    """Envoy rate limit gRPC servicer stub."""

    def ShouldRateLimit(self, request, context):
        # TODO: compile envoy protos, implement per-service token-bucket / leaky-bucket logic
        raise NotImplementedError
