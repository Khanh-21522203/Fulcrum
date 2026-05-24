from __future__ import annotations

import os
from dataclasses import dataclass, field

from google.rpc import status_pb2

from fulcrum_grpc_api.envoy.config.core.v3 import base_pb2
from fulcrum_grpc_api.envoy.service.auth.v3 import external_auth_pb2
from fulcrum_grpc_api.envoy.service.auth.v3 import external_auth_pb2_grpc
from fulcrum_grpc_api.envoy.type.v3 import http_status_pb2


OK = 0
PERMISSION_DENIED = 7
UNAUTHENTICATED = 16


@dataclass(frozen=True)
class AuthCheck:
    method: str
    path: str
    host: str
    headers: dict[str, str]
    token: str | None
    client_principal: str | None


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    status_code: int
    grpc_code: int
    reason: str
    principal_id: str | None = None
    tenant_id: str | None = None
    headers_to_add: dict[str, str] = field(default_factory=dict)


class StaticBearerTokenAuthorizer:
    """Development authorizer backed by one configured bearer token."""

    def __init__(
        self,
        expected_token: str | None = None,
        principal_id: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        self._expected_token = expected_token or os.getenv(
            "FULCRUM_AUTH_BEARER_TOKEN",
            "dev-token",
        )
        self._principal_id = principal_id or os.getenv(
            "FULCRUM_AUTH_PRINCIPAL_ID",
            "dev-principal",
        )
        self._tenant_id = tenant_id or os.getenv("FULCRUM_AUTH_TENANT_ID")

    def authorize(self, check: AuthCheck) -> AuthDecision:
        if check.token is None:
            return AuthDecision(
                allowed=False,
                status_code=401,
                grpc_code=UNAUTHENTICATED,
                reason="missing_authorization",
            )

        if check.token != self._expected_token:
            return AuthDecision(
                allowed=False,
                status_code=401,
                grpc_code=UNAUTHENTICATED,
                reason="invalid_token",
            )

        headers = {
            "x-fulcrum-principal-id": self._principal_id,
            "x-fulcrum-authenticated": "true",
        }
        if self._tenant_id is not None:
            headers["x-fulcrum-tenant-id"] = self._tenant_id

        return AuthDecision(
            allowed=True,
            status_code=200,
            grpc_code=OK,
            reason="ok",
            principal_id=self._principal_id,
            tenant_id=self._tenant_id,
            headers_to_add=headers,
        )


class AuthorizationServicer(external_auth_pb2_grpc.AuthorizationServicer):
    """Envoy external authorization gRPC servicer."""

    def __init__(self, authorizer: StaticBearerTokenAuthorizer | None = None) -> None:
        self._authorizer = authorizer or StaticBearerTokenAuthorizer()

    def Check(self, request, context):
        check = self._parse_check(request)
        decision = self._authorizer.authorize(check)
        return self._response_for_decision(decision)

    def _parse_check(self, request) -> AuthCheck:
        http = request.attributes.request.http
        headers = {key.lower(): value for key, value in http.headers.items()}
        token = self._bearer_token(headers.get("authorization"))

        return AuthCheck(
            method=http.method,
            path=http.path,
            host=http.host,
            headers=headers,
            token=token,
            client_principal=request.attributes.source.principal or None,
        )

    def _bearer_token(self, authorization: str | None) -> str | None:
        if authorization is None:
            return None

        scheme, separator, token = authorization.partition(" ")
        if separator == "" or scheme.lower() != "bearer" or token.strip() == "":
            return None
        return token.strip()

    def _response_for_decision(self, decision: AuthDecision):
        if decision.allowed:
            return external_auth_pb2.CheckResponse(
                status=status_pb2.Status(code=OK, message=decision.reason),
                ok_response=external_auth_pb2.OkHttpResponse(
                    headers=[
                        self._header_option(key, value)
                        for key, value in decision.headers_to_add.items()
                    ]
                ),
            )

        return external_auth_pb2.CheckResponse(
            status=status_pb2.Status(code=decision.grpc_code, message=decision.reason),
            denied_response=external_auth_pb2.DeniedHttpResponse(
                status=http_status_pb2.HttpStatus(
                    code=self._http_status_code(decision.status_code)
                ),
                headers=[
                    self._header_option("content-type", "application/json"),
                ],
                body=f'{{"error":"{decision.reason}"}}',
            ),
        )

    def _header_option(self, key: str, value: str):
        return base_pb2.HeaderValueOption(
            header=base_pb2.HeaderValue(key=key, value=value)
        )

    def _http_status_code(self, status_code: int):
        if status_code == 403:
            return http_status_pb2.HttpStatus.Forbidden
        if status_code == 401:
            return http_status_pb2.HttpStatus.Unauthorized
        return http_status_pb2.HttpStatus.Forbidden
