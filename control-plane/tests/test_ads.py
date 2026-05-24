import unittest
from concurrent import futures

import grpc
from google.protobuf.any_pb2 import Any
from google.protobuf.wrappers_pb2 import StringValue

from control_plane.snapshot import Snapshot, SnapshotCache
from control_plane.xds.ads import AggregatedDiscoveryServicer
from control_plane.xds.types import (
    CDS_TYPE_URL,
    LDS_TYPE_URL,
    RDS_TYPE_URL,
    RTDS_TYPE_URL,
    SDS_TYPE_URL,
)
from fulcrum_grpc_api.envoy.service.discovery.v3 import ads_pb2, ads_pb2_grpc


def packed_resource(value: str) -> Any:
    resource = Any()
    resource.Pack(StringValue(value=value))
    return resource


def request(type_url: str, *, version: str = "", nonce: str = ""):
    return ads_pb2.DiscoveryRequest(
        version_info=version,
        type_url=type_url,
        response_nonce=nonce,
        node=ads_pb2.Node(cluster="region-eastus"),
    )


def snapshot_cache() -> SnapshotCache:
    cache = SnapshotCache()
    cache.set(
        Snapshot(
            node_group="region-eastus",
            version="v1",
            listeners=[packed_resource("listener")],
            routes=[packed_resource("route")],
            clusters=[packed_resource("cluster")],
            secrets=[packed_resource("secret")],
            runtime=[packed_resource("runtime")],
        )
    )
    return cache


class AggregatedDiscoveryServicerTest(unittest.TestCase):
    def test_returns_resources_for_requested_type_url(self):
        servicer = AggregatedDiscoveryServicer(snapshot_cache())

        responses = list(
            servicer.StreamAggregatedResources(
                iter([request(CDS_TYPE_URL)]),
                None,
            )
        )

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].version_info, "v1")
        self.assertEqual(responses[0].type_url, CDS_TYPE_URL)
        self.assertEqual(len(responses[0].resources), 1)

    def test_supports_sds_and_rtds(self):
        servicer = AggregatedDiscoveryServicer(snapshot_cache())

        responses = list(
            servicer.StreamAggregatedResources(
                iter([request(SDS_TYPE_URL), request(RTDS_TYPE_URL)]),
                None,
            )
        )

        self.assertEqual([response.type_url for response in responses], [
            SDS_TYPE_URL,
            RTDS_TYPE_URL,
        ])
        self.assertEqual([len(response.resources) for response in responses], [1, 1])

    def test_ack_does_not_echo_response(self):
        servicer = AggregatedDiscoveryServicer(snapshot_cache())

        responses = list(
            servicer.StreamAggregatedResources(
                iter([request(RDS_TYPE_URL, version="v1", nonce="nonce-1")]),
                None,
            )
        )

        self.assertEqual(responses, [])

    def test_grpc_stream_returns_discovery_response(self):
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        ads_pb2_grpc.add_AggregatedDiscoveryServiceServicer_to_server(
            AggregatedDiscoveryServicer(snapshot_cache()),
            server,
        )
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        self.addCleanup(server.stop, 0)

        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = ads_pb2_grpc.AggregatedDiscoveryServiceStub(channel)
            responses = list(
                stub.StreamAggregatedResources(
                    iter([request(LDS_TYPE_URL)]),
                    timeout=2,
                )
            )

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].type_url, LDS_TYPE_URL)
        self.assertEqual(responses[0].version_info, "v1")


if __name__ == "__main__":
    unittest.main()
