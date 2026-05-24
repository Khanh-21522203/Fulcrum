from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import time_ns
from typing import Protocol, Sequence
from uuid import UUID

from google.protobuf.any_pb2 import Any
from google.protobuf.duration_pb2 import Duration
from google.protobuf.struct_pb2 import Struct

from fulcrum_grpc_api.envoy.config.core.v3 import config_source_pb2, grpc_service_pb2
from fulcrum_grpc_api.envoy.config.cluster.v3 import cluster_pb2
from fulcrum_grpc_api.envoy.config.endpoint.v3 import endpoint_pb2
from fulcrum_grpc_api.envoy.config.listener.v3 import listener_pb2
from fulcrum_grpc_api.envoy.config.ratelimit.v3 import rls_pb2 as rls_config_pb2
from fulcrum_grpc_api.envoy.config.route.v3 import route_pb2
from fulcrum_grpc_api.envoy.extensions.filters.http.ext_authz.v3 import (
    ext_authz_pb2,
)
from fulcrum_grpc_api.envoy.extensions.filters.http.ratelimit.v3 import (
    rate_limit_pb2,
)
from fulcrum_grpc_api.envoy.extensions.filters.http.router.v3 import router_pb2
from fulcrum_grpc_api.envoy.extensions.filters.network.http_connection_manager.v3 import (
    http_connection_manager_pb2,
)
from fulcrum_grpc_api.envoy.extensions.transport_sockets.tls.v3 import secret_pb2
from fulcrum_grpc_api.envoy.service.runtime.v3 import runtime_pb2
from fulcrum_shared.models import InstanceStatus, ServiceInstance

from control_plane.xds.types import (
    CDS_TYPE_URL,
    EDS_TYPE_URL,
    LDS_TYPE_URL,
    RDS_TYPE_URL,
    RTDS_TYPE_URL,
    SDS_TYPE_URL,
)

DEFAULT_LISTENER_NAME = "fulcrum_http"
DEFAULT_ROUTE_CONFIGURATION_NAME = "fulcrum_routes"
DEFAULT_RUNTIME_NAME = "fulcrum_runtime"
DEFAULT_NODE_GROUP = "default"
DEFAULT_LISTENER_ADDRESS = "0.0.0.0"
DEFAULT_LISTENER_PORT = 8080
DEFAULT_ROUTE_PREFIX = "/"
DEFAULT_TIMEOUT_SECONDS = 30
AUTH_SIDECAR_CLUSTER = "auth_sidecar"
RATE_LIMIT_SIDECAR_CLUSTER = "ratelimit_sidecar"
RATE_LIMIT_DOMAIN = "fulcrum"


@dataclass
class Snapshot:
    node_group: str
    version: str
    listeners: list[Any] = field(default_factory=list)
    routes: list[Any] = field(default_factory=list)
    clusters: list[Any] = field(default_factory=list)
    endpoints: list[Any] = field(default_factory=list)
    secrets: list[Any] = field(default_factory=list)
    runtime: list[Any] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def resources_for(self, type_url: str) -> list[Any]:
        resources_by_type = {
            LDS_TYPE_URL: self.listeners,
            RDS_TYPE_URL: self.routes,
            CDS_TYPE_URL: self.clusters,
            EDS_TYPE_URL: self.endpoints,
            SDS_TYPE_URL: self.secrets,
            RTDS_TYPE_URL: self.runtime,
        }
        return list(resources_by_type.get(type_url, ()))

    def resource_counts(self) -> dict[str, int]:
        return {
            "listeners": len(self.listeners),
            "routes": len(self.routes),
            "clusters": len(self.clusters),
            "endpoints": len(self.endpoints),
            "secrets": len(self.secrets),
            "runtime": len(self.runtime),
        }


class SnapshotCache:
    """In-memory versioned snapshot store, keyed by node_group."""

    def __init__(self) -> None:
        self._store: dict[str, Snapshot] = {}
        self._previous: dict[str, Snapshot] = {}

    def get(self, node_group: str) -> Snapshot | None:
        return self._store.get(node_group)

    def set(self, snapshot: Snapshot) -> None:
        current = self._store.get(snapshot.node_group)
        if current is not None:
            self._previous[snapshot.node_group] = current
        self._store[snapshot.node_group] = snapshot

    def previous(self, node_group: str) -> Snapshot | None:
        return self._previous.get(node_group)

    def all(self) -> dict[str, Snapshot]:
        return dict(self._store)

    def clear(self) -> None:
        self._store.clear()
        self._previous.clear()


class ServiceInstanceSource(Protocol):
    async def list_ready(self, node_group: str) -> Sequence[ServiceInstance]:
        ...


class EmptyServiceInstanceSource:
    async def list_ready(self, node_group: str) -> Sequence[ServiceInstance]:
        return ()


class StaticServiceInstanceSource:
    def __init__(self, instances: Sequence[ServiceInstance]) -> None:
        self._instances = list(instances)

    async def list_ready(self, node_group: str) -> Sequence[ServiceInstance]:
        return [
            instance
            for instance in self._instances
            if instance.status == InstanceStatus.READY
            and _instance_node_group(instance) == node_group
        ]


class SnapshotBuilder:
    """Reads active ServiceInstances + Jinja2 templates; renders Envoy resources."""

    def __init__(
        self,
        source: ServiceInstanceSource | None = None,
        *,
        listener_address: str = DEFAULT_LISTENER_ADDRESS,
        listener_port: int = DEFAULT_LISTENER_PORT,
    ) -> None:
        self._source = source or EmptyServiceInstanceSource()
        self._listener_address = listener_address
        self._listener_port = listener_port

    async def build(self, node_group: str = "default") -> Snapshot:
        instances = list(await self._source.list_ready(node_group))
        resources = [_ServiceResource.from_instance(instance) for instance in instances]

        # TODO: fetch Jinja2 templates from Blob Storage
        return Snapshot(
            node_group=node_group,
            version=str(time_ns()),
            listeners=[
                _pack(
                    _listener(
                        self._listener_address,
                        self._listener_port,
                    )
                )
            ],
            routes=[_pack(_route_configuration(resources))],
            clusters=[_pack(_cluster(resource)) for resource in resources],
            endpoints=[_pack(_endpoint_assignment(resource)) for resource in resources],
            secrets=[
                _pack(secret_pb2.Secret(name=resource.secret_name))
                for resource in resources
                if resource.secret_name
            ],
            runtime=[_pack(_runtime(resources))],
        )


@dataclass(frozen=True)
class _ServiceResource:
    instance_id: UUID
    domains: tuple[str, ...]
    upstream_host: str
    upstream_port: int
    timeout_seconds: int
    route_prefix: str = DEFAULT_ROUTE_PREFIX
    tls_enabled: bool = False

    @classmethod
    def from_instance(cls, instance: ServiceInstance) -> "_ServiceResource":
        params = instance.parameters
        domains = tuple(params.get("domains") or ())
        upstream_host = str(params.get("upstream_host") or "")
        upstream_port = int(params.get("upstream_port") or 0)
        timeout_seconds = int(params.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
        route_prefix = str(params.get("path_prefix") or DEFAULT_ROUTE_PREFIX)

        if not domains:
            raise ValueError(f"ServiceInstance {instance.id} has no domains")
        if not upstream_host:
            raise ValueError(f"ServiceInstance {instance.id} has no upstream_host")
        if upstream_port <= 0:
            raise ValueError(f"ServiceInstance {instance.id} has invalid upstream_port")
        if not route_prefix.startswith("/"):
            raise ValueError(f"ServiceInstance {instance.id} has invalid path_prefix")

        return cls(
            instance_id=instance.id,
            domains=domains,
            upstream_host=upstream_host,
            upstream_port=upstream_port,
            timeout_seconds=timeout_seconds,
            route_prefix=route_prefix,
            tls_enabled=bool(params.get("tls", False)),
        )

    @property
    def cluster_name(self) -> str:
        return f"svc_{self.instance_id.hex}"

    @property
    def virtual_host_name(self) -> str:
        return f"vh_{self.instance_id.hex}"

    @property
    def secret_name(self) -> str | None:
        if not self.tls_enabled:
            return None
        return f"tls_{self.instance_id.hex}"


def _instance_node_group(instance: ServiceInstance) -> str:
    return str(instance.parameters.get("node_group") or DEFAULT_NODE_GROUP)


def _pack(message) -> Any:
    resource = Any()
    resource.Pack(message)
    return resource


def _listener(address: str, port: int) -> listener_pb2.Listener:
    return listener_pb2.Listener(
        name=DEFAULT_LISTENER_NAME,
        address=listener_pb2.Address(
            socket_address=listener_pb2.SocketAddress(
                address=address,
                port_value=port,
            )
        ),
        filter_chains=[
            listener_pb2.FilterChain(
                filters=[
                    listener_pb2.Filter(
                        name="envoy.filters.network.http_connection_manager",
                        typed_config=_pack(_http_connection_manager()),
                    )
                ]
            )
        ],
    )


def _http_connection_manager() -> http_connection_manager_pb2.HttpConnectionManager:
    return http_connection_manager_pb2.HttpConnectionManager(
        codec_type=http_connection_manager_pb2.HttpConnectionManager.AUTO,
        stat_prefix="fulcrum_edge",
        rds=http_connection_manager_pb2.Rds(
            config_source=config_source_pb2.ConfigSource(
                ads=config_source_pb2.AggregatedConfigSource()
            ),
            route_config_name=DEFAULT_ROUTE_CONFIGURATION_NAME,
        ),
        http_filters=[
            http_connection_manager_pb2.HttpFilter(
                name="envoy.filters.http.ext_authz",
                typed_config=_pack(
                    ext_authz_pb2.ExtAuthz(
                        grpc_service=_grpc_service(AUTH_SIDECAR_CLUSTER),
                        failure_mode_allow=False,
                    )
                ),
            ),
            http_connection_manager_pb2.HttpFilter(
                name="envoy.filters.http.ratelimit",
                typed_config=_pack(
                    rate_limit_pb2.RateLimit(
                        domain=RATE_LIMIT_DOMAIN,
                        timeout=Duration(seconds=1),
                        failure_mode_deny=False,
                        rate_limit_service=rls_config_pb2.RateLimitServiceConfig(
                            grpc_service=_grpc_service(RATE_LIMIT_SIDECAR_CLUSTER)
                        ),
                    )
                ),
            ),
            http_connection_manager_pb2.HttpFilter(
                name="envoy.filters.http.router",
                typed_config=_pack(router_pb2.Router()),
            ),
        ],
    )


def _grpc_service(cluster_name: str) -> grpc_service_pb2.GrpcService:
    return grpc_service_pb2.GrpcService(
        envoy_grpc=grpc_service_pb2.GrpcService.EnvoyGrpc(
            cluster_name=cluster_name,
        ),
        timeout=Duration(seconds=1),
    )


def _route_configuration(
    resources: Sequence[_ServiceResource],
) -> route_pb2.RouteConfiguration:
    return route_pb2.RouteConfiguration(
        name=DEFAULT_ROUTE_CONFIGURATION_NAME,
        virtual_hosts=[
            route_pb2.VirtualHost(
                name=resource.virtual_host_name,
                domains=list(resource.domains),
                routes=[
                    route_pb2.Route(
                        match=route_pb2.RouteMatch(prefix=resource.route_prefix),
                        route=route_pb2.RouteAction(
                            cluster=resource.cluster_name,
                            timeout=Duration(seconds=resource.timeout_seconds),
                            rate_limits=[
                                route_pb2.RateLimit(
                                    actions=[
                                        route_pb2.RateLimit.Action(
                                            generic_key=route_pb2.RateLimit.Action.GenericKey(
                                                descriptor_key="service_id",
                                                descriptor_value=resource.cluster_name,
                                            )
                                        )
                                    ]
                                )
                            ],
                        ),
                    )
                ],
            )
            for resource in resources
        ],
    )


def _cluster(resource: _ServiceResource) -> cluster_pb2.Cluster:
    return cluster_pb2.Cluster(
        name=resource.cluster_name,
        type=cluster_pb2.Cluster.STRICT_DNS,
        lb_policy=cluster_pb2.Cluster.ROUND_ROBIN,
        load_assignment=cluster_pb2.ClusterLoadAssignment(
            cluster_name=resource.cluster_name,
            endpoints=[
                cluster_pb2.LocalityLbEndpoints(
                    lb_endpoints=[
                        cluster_pb2.LbEndpoint(
                            endpoint=cluster_pb2.Endpoint(
                                address=cluster_pb2.Address(
                                    socket_address=cluster_pb2.SocketAddress(
                                        address=resource.upstream_host,
                                        port_value=resource.upstream_port,
                                    )
                                )
                            )
                        )
                    ]
                )
            ],
        ),
    )


def _endpoint_assignment(resource: _ServiceResource) -> endpoint_pb2.ClusterLoadAssignment:
    return endpoint_pb2.ClusterLoadAssignment(
        cluster_name=resource.cluster_name,
        endpoints=[
            endpoint_pb2.LocalityLbEndpoints(
                lb_endpoints=[
                    endpoint_pb2.LbEndpoint(
                        endpoint=endpoint_pb2.Endpoint(
                            address=endpoint_pb2.Address(
                                socket_address=endpoint_pb2.SocketAddress(
                                    address=resource.upstream_host,
                                    port_value=resource.upstream_port,
                                )
                            )
                        )
                    )
                ]
            )
        ],
    )


def _runtime(resources: Sequence[_ServiceResource]) -> runtime_pb2.Runtime:
    layer = Struct()
    layer.update(
        {
            "generated_by": "fulcrum-control-plane",
            "active_services": len(resources),
        }
    )
    return runtime_pb2.Runtime(
        name=DEFAULT_RUNTIME_NAME,
        layer=layer,
    )
