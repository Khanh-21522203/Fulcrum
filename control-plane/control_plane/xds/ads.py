# Aggregated Discovery Service (ADS) — xDS v3
#
# Supported type URLs:
#   LDS  type.googleapis.com/envoy.config.listener.v3.Listener
#   RDS  type.googleapis.com/envoy.config.route.v3.RouteConfiguration
#   CDS  type.googleapis.com/envoy.config.cluster.v3.Cluster
#   EDS  type.googleapis.com/envoy.config.endpoint.v3.ClusterLoadAssignment
#
# Proto compilation required before real implementation:
#   pip install grpcio-tools
#   python -m grpc_tools.protoc -I<envoy-api-root> --python_out=. --grpc_python_out=. \
#       envoy/service/discovery/v3/ads.proto
#   → generates discovery_pb2.py / discovery_pb2_grpc.py
#
# Replace the base class below with the generated AggregatedDiscoveryServiceServicer.


class AggregatedDiscoveryServicer:
    """xDS v3 ADS gRPC servicer stub."""

    def StreamAggregatedResources(self, request_iterator, context):
        # Bidirectional stream:
        #   Receives DiscoveryRequest messages (one per resource type) from Envoy nodes.
        #   Yields DiscoveryResponse messages for LDS / RDS / CDS / EDS.
        #   Envoy ACKs or NACKs each response with version_info.
        raise NotImplementedError
