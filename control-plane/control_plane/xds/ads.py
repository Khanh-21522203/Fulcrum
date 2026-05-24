from __future__ import annotations

import logging

from fulcrum_grpc_api.envoy.service.discovery.v3 import ads_pb2, ads_pb2_grpc

from control_plane.snapshot import Snapshot, SnapshotCache
from control_plane.xds.types import SUPPORTED_TYPE_URLS

logger = logging.getLogger(__name__)


class AggregatedDiscoveryServicer(
    ads_pb2_grpc.AggregatedDiscoveryServiceServicer
):
    """Minimal xDS v3 ADS service backed by versioned snapshots."""

    def __init__(
        self,
        cache: SnapshotCache | None = None,
        *,
        default_node_group: str = "default",
        control_plane_id: str = "fulcrum-control-plane",
    ) -> None:
        self._cache = cache or SnapshotCache()
        self._default_node_group = default_node_group
        self._control_plane_id = control_plane_id

    def StreamAggregatedResources(self, request_iterator, context):
        node_group = self._default_node_group
        for request in request_iterator:
            if request.node.cluster:
                node_group = request.node.cluster

            if request.error_detail.code:
                logger.warning(
                    "Envoy NACKed xDS response: type_url=%s version=%s nonce=%s error=%s",
                    request.type_url,
                    request.version_info,
                    request.response_nonce,
                    request.error_detail.message,
                )
                continue

            snapshot = self._snapshot_for(node_group)
            if self._is_ack(request, snapshot):
                logger.debug(
                    "Envoy ACKed xDS response: type_url=%s version=%s nonce=%s",
                    request.type_url,
                    request.version_info,
                    request.response_nonce,
                )
                continue

            if request.type_url not in SUPPORTED_TYPE_URLS:
                logger.info("Ignoring unsupported xDS type_url=%s", request.type_url)
                continue

            yield ads_pb2.DiscoveryResponse(
                version_info=snapshot.version,
                resources=snapshot.resources_for(request.type_url),
                type_url=request.type_url,
                nonce=self._nonce_for(snapshot, request.type_url),
                control_plane=ads_pb2.ControlPlane(
                    identifier=self._control_plane_id
                ),
            )

    def _snapshot_for(self, node_group: str) -> Snapshot:
        return self._cache.get(node_group) or Snapshot(
            node_group=node_group,
            version="0",
        )

    @staticmethod
    def _is_ack(
        request: ads_pb2.DiscoveryRequest,
        snapshot: Snapshot,
    ) -> bool:
        return bool(
            request.response_nonce
            and request.version_info == snapshot.version
        )

    @staticmethod
    def _nonce_for(snapshot: Snapshot, type_url: str) -> str:
        return f"{snapshot.node_group}:{snapshot.version}:{type_url}"
