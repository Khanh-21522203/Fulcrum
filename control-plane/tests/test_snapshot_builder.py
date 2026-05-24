import unittest
import uuid

from fulcrum_grpc_api.envoy.config.cluster.v3 import cluster_pb2
from fulcrum_grpc_api.envoy.config.endpoint.v3 import endpoint_pb2
from fulcrum_grpc_api.envoy.config.listener.v3 import listener_pb2
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

from control_plane.snapshot import SnapshotBuilder, StaticServiceInstanceSource


def instance(
    *,
    instance_id: uuid.UUID,
    node_group: str = "region-eastus",
    status: InstanceStatus = InstanceStatus.READY,
    tls: bool = False,
) -> ServiceInstance:
    return ServiceInstance(
        id=instance_id,
        service_id="load-balancer",
        plan_id="standard",
        organization_id="org-001",
        space_id="space-001",
        status=status,
        parameters={
            "domains": ["api.example.com"],
            "upstream_host": "api.internal",
            "upstream_port": 8080,
            "timeout_seconds": 15,
            "node_group": node_group,
            "tls": tls,
        },
    )


class SnapshotBuilderTest(unittest.IsolatedAsyncioTestCase):
    async def test_builds_typed_xds_resources_from_ready_instances(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        builder = SnapshotBuilder(
            StaticServiceInstanceSource(
                [
                    instance(instance_id=instance_id, tls=True),
                    instance(
                        instance_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                        status=InstanceStatus.PENDING,
                    ),
                ]
            )
        )

        snapshot = await builder.build("region-eastus")

        self.assertEqual(snapshot.node_group, "region-eastus")
        self.assertEqual(snapshot.resource_counts(), {
            "listeners": 1,
            "routes": 1,
            "clusters": 1,
            "endpoints": 1,
            "secrets": 1,
            "runtime": 1,
        })

        listener = listener_pb2.Listener()
        self.assertTrue(snapshot.listeners[0].Unpack(listener))
        self.assertEqual(listener.name, "fulcrum_http")
        self.assertEqual(listener.address.socket_address.port_value, 8080)
        network_filter = listener.filter_chains[0].filters[0]
        self.assertEqual(
            network_filter.name,
            "envoy.filters.network.http_connection_manager",
        )

        hcm = http_connection_manager_pb2.HttpConnectionManager()
        self.assertTrue(network_filter.typed_config.Unpack(hcm))
        self.assertEqual(hcm.rds.route_config_name, "fulcrum_routes")
        self.assertTrue(hcm.rds.config_source.HasField("ads"))
        self.assertEqual(
            [http_filter.name for http_filter in hcm.http_filters],
            [
                "envoy.filters.http.ext_authz",
                "envoy.filters.http.ratelimit",
                "envoy.filters.http.router",
            ],
        )

        ext_authz = ext_authz_pb2.ExtAuthz()
        self.assertTrue(hcm.http_filters[0].typed_config.Unpack(ext_authz))
        self.assertEqual(
            ext_authz.grpc_service.envoy_grpc.cluster_name,
            "auth_sidecar",
        )
        self.assertFalse(ext_authz.failure_mode_allow)

        rate_limit = rate_limit_pb2.RateLimit()
        self.assertTrue(hcm.http_filters[1].typed_config.Unpack(rate_limit))
        self.assertEqual(rate_limit.domain, "fulcrum")
        self.assertEqual(
            rate_limit.rate_limit_service.grpc_service.envoy_grpc.cluster_name,
            "ratelimit_sidecar",
        )

        router = router_pb2.Router()
        self.assertTrue(hcm.http_filters[2].typed_config.Unpack(router))

        routes = route_pb2.RouteConfiguration()
        self.assertTrue(snapshot.routes[0].Unpack(routes))
        self.assertEqual(routes.virtual_hosts[0].domains, ["api.example.com"])
        self.assertEqual(
            routes.virtual_hosts[0].routes[0].route.cluster,
            "svc_11111111111111111111111111111111",
        )
        self.assertEqual(routes.virtual_hosts[0].routes[0].route.timeout.seconds, 15)
        descriptor = (
            routes.virtual_hosts[0]
            .routes[0]
            .route.rate_limits[0]
            .actions[0]
            .generic_key
        )
        self.assertEqual(descriptor.descriptor_key, "service_id")
        self.assertEqual(
            descriptor.descriptor_value,
            "svc_11111111111111111111111111111111",
        )

        cluster = cluster_pb2.Cluster()
        self.assertTrue(snapshot.clusters[0].Unpack(cluster))
        self.assertEqual(cluster.name, "svc_11111111111111111111111111111111")
        self.assertEqual(cluster.type, cluster_pb2.Cluster.STRICT_DNS)
        self.assertEqual(
            cluster.load_assignment.endpoints[0]
            .lb_endpoints[0]
            .endpoint.address.socket_address.address,
            "api.internal",
        )

        endpoint = endpoint_pb2.ClusterLoadAssignment()
        self.assertTrue(snapshot.endpoints[0].Unpack(endpoint))
        self.assertEqual(endpoint.cluster_name, cluster.name)
        self.assertEqual(
            endpoint.endpoints[0]
            .lb_endpoints[0]
            .endpoint.address.socket_address.port_value,
            8080,
        )

        secret = secret_pb2.Secret()
        self.assertTrue(snapshot.secrets[0].Unpack(secret))
        self.assertEqual(secret.name, "tls_11111111111111111111111111111111")

        runtime = runtime_pb2.Runtime()
        self.assertTrue(snapshot.runtime[0].Unpack(runtime))
        self.assertEqual(runtime.layer["active_services"], 1)

    async def test_filters_instances_by_node_group(self):
        builder = SnapshotBuilder(
            StaticServiceInstanceSource(
                [
                    instance(
                        instance_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                        node_group="region-eastus",
                    ),
                    instance(
                        instance_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                        node_group="region-westus",
                    ),
                ]
            )
        )

        snapshot = await builder.build("region-westus")

        routes = route_pb2.RouteConfiguration()
        self.assertTrue(snapshot.routes[0].Unpack(routes))
        self.assertEqual(len(routes.virtual_hosts), 1)
        self.assertEqual(
            routes.virtual_hosts[0].name,
            "vh_22222222222222222222222222222222",
        )

    async def test_rejects_invalid_ready_instance(self):
        broken = instance(
            instance_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        )
        broken.parameters.pop("upstream_host")
        builder = SnapshotBuilder(StaticServiceInstanceSource([broken]))

        with self.assertRaisesRegex(ValueError, "upstream_host"):
            await builder.build("region-eastus")


if __name__ == "__main__":
    unittest.main()
