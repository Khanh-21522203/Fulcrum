import unittest
from concurrent import futures

import grpc

from auth_sidecar.handler import AuthorizationServicer, StaticBearerTokenAuthorizer
from fulcrum_grpc_api.envoy.service.auth.v3 import external_auth_pb2
from fulcrum_grpc_api.envoy.service.auth.v3 import external_auth_pb2_grpc


def check_request(authorization: str | None = None):
    request = external_auth_pb2.CheckRequest()
    http = request.attributes.request.http
    http.method = "GET"
    http.path = "/v1/messages"
    http.host = "api.fulcrum.local"
    if authorization is not None:
        http.headers["authorization"] = authorization
    return request


def servicer():
    return AuthorizationServicer(
        StaticBearerTokenAuthorizer(
            expected_token="secret-token",
            principal_id="user_123",
            tenant_id="tenant_456",
        )
    )


class AuthorizationServicerTest(unittest.TestCase):
    def test_allows_valid_bearer_token(self):
        response = servicer().Check(
            check_request("Bearer secret-token"),
            None,
        )

        headers = {
            option.header.key: option.header.value
            for option in response.ok_response.headers
        }
        self.assertEqual(response.status.code, 0)
        self.assertEqual(headers["x-fulcrum-principal-id"], "user_123")
        self.assertEqual(headers["x-fulcrum-tenant-id"], "tenant_456")
        self.assertEqual(headers["x-fulcrum-authenticated"], "true")

    def test_denies_missing_authorization(self):
        response = servicer().Check(check_request(), None)

        self.assertEqual(response.status.code, 16)
        self.assertEqual(
            response.denied_response.status.code,
            external_auth_pb2.HttpStatus.Unauthorized,
        )
        self.assertEqual(response.denied_response.body, '{"error":"missing_authorization"}')

    def test_denies_invalid_bearer_token(self):
        response = servicer().Check(
            check_request("Bearer wrong-token"),
            None,
        )

        self.assertEqual(response.status.code, 16)
        self.assertEqual(
            response.denied_response.status.code,
            external_auth_pb2.HttpStatus.Unauthorized,
        )
        self.assertEqual(response.denied_response.body, '{"error":"invalid_token"}')

    def test_grpc_service_returns_check_response(self):
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        external_auth_pb2_grpc.add_AuthorizationServicer_to_server(servicer(), server)
        port = server.add_insecure_port("[::]:0")
        server.start()
        self.addCleanup(server.stop, 0)

        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = external_auth_pb2_grpc.AuthorizationStub(channel)
            response = stub.Check(
                check_request("Bearer secret-token"),
                timeout=2,
            )

        self.assertEqual(response.status.code, 0)


if __name__ == "__main__":
    unittest.main()
