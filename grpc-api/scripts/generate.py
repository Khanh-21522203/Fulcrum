from __future__ import annotations

import site
from pathlib import Path

from grpc_tools import protoc


ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = [path for path in site.getsitepackages() if Path(path).exists()]

PROTOS = [
    "fulcrum_grpc_api/envoy/config/core/v3/config_source.proto",
    "fulcrum_grpc_api/envoy/config/core/v3/grpc_service.proto",
    "fulcrum_grpc_api/envoy/config/ratelimit/v3/rls.proto",
    "fulcrum_grpc_api/envoy/config/listener/v3/listener.proto",
    "fulcrum_grpc_api/envoy/config/route/v3/route.proto",
    "fulcrum_grpc_api/envoy/config/cluster/v3/cluster.proto",
    "fulcrum_grpc_api/envoy/config/endpoint/v3/endpoint.proto",
    "fulcrum_grpc_api/envoy/extensions/transport_sockets/tls/v3/secret.proto",
    "fulcrum_grpc_api/envoy/extensions/filters/http/ext_authz/v3/ext_authz.proto",
    "fulcrum_grpc_api/envoy/extensions/filters/http/ratelimit/v3/rate_limit.proto",
    "fulcrum_grpc_api/envoy/extensions/filters/http/router/v3/router.proto",
    "fulcrum_grpc_api/envoy/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto",
    "fulcrum_grpc_api/envoy/service/discovery/v3/ads.proto",
    "fulcrum_grpc_api/envoy/service/auth/v3/external_auth.proto",
    "fulcrum_grpc_api/envoy/service/ratelimit/v3/rls.proto",
    "fulcrum_grpc_api/envoy/service/runtime/v3/runtime.proto",
]


def main() -> int:
    return protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{ROOT}",
            *(f"-I{path}" for path in INCLUDE_DIRS),
            f"--python_out={ROOT}",
            f"--grpc_python_out={ROOT}",
            *(str(ROOT / proto) for proto in PROTOS),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
