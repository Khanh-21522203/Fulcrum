LDS_TYPE_URL = "type.googleapis.com/envoy.config.listener.v3.Listener"
RDS_TYPE_URL = "type.googleapis.com/envoy.config.route.v3.RouteConfiguration"
CDS_TYPE_URL = "type.googleapis.com/envoy.config.cluster.v3.Cluster"
EDS_TYPE_URL = "type.googleapis.com/envoy.config.endpoint.v3.ClusterLoadAssignment"
SDS_TYPE_URL = "type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret"
RTDS_TYPE_URL = "type.googleapis.com/envoy.service.runtime.v3.Runtime"

SUPPORTED_TYPE_URLS = frozenset(
    {
        LDS_TYPE_URL,
        RDS_TYPE_URL,
        CDS_TYPE_URL,
        EDS_TYPE_URL,
        SDS_TYPE_URL,
        RTDS_TYPE_URL,
    }
)
