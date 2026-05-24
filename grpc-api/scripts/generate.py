from __future__ import annotations

from pathlib import Path

from grpc_tools import protoc


ROOT = Path(__file__).resolve().parents[1]

PROTOS = [
    "fulcrum_grpc_api/envoy/type/v3/ratelimit_unit.proto",
    "fulcrum_grpc_api/envoy/config/core/v3/base.proto",
    "fulcrum_grpc_api/envoy/extensions/common/ratelimit/v3/ratelimit.proto",
    "fulcrum_grpc_api/envoy/service/ratelimit/v3/rls.proto",
]


def main() -> int:
    return protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{ROOT}",
            f"--python_out={ROOT}",
            f"--grpc_python_out={ROOT}",
            *(str(ROOT / proto) for proto in PROTOS),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
