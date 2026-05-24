# Envoy Fleet

## Purpose

The data plane. A fleet of Envoy proxy instances running on Azure VM Scale Sets (VMSS) across multiple regions. Handles TLS termination, request routing, and delegates authentication and rate limiting to local sidecar processes. Receives all routing configuration dynamically from the control plane via the xDS ADS API — no proxy restarts required for config changes.

---

## Azure Infrastructure

### Resources Per Region

| Resource | Azure Type | Purpose |
|---|---|---|
| Virtual Network | VNet | Isolated network per region |
| Proxy Subnet | Subnet | Envoy VMSS placement |
| Network Security Group | NSG | Ingress 443/80 from Front Door only. Egress to upstreams. |
| VM Scale Set | VMSS | Auto-scales Envoy node count on CPU / connection metrics |
| Azure Load Balancer | Standard LB (L4) | Distributes inbound connections across VMSS instances |
| Azure Front Door | Global | DDoS protection, CDN, anycast ingress before the LB |
| Azure Compute Gallery | Image gallery | Stores versioned custom Envoy VM images |
| Managed Identity | MSI | Grants VMSS nodes access to Key Vault and Cosmos DB without credentials |
| Azure DNS Zone | Public DNS | Customer-facing domains (updated by the worker) |
| Azure Key Vault | KV | TLS certificates and secrets fetched at node boot |

### Network Topology

```mermaid
flowchart TD
    Internet["Internet"]
    FD["Azure Front Door\n(DDoS + CDN + Anycast)"]
    LB["Azure Load Balancer\n(L4, Standard)"]
    NSG["NSG\n(allow 443/80 from Front Door only)"]
    VMSS["VMSS — Envoy nodes\n(auto-scale)"]
    Backend["Backend Services\n(internal)"]
    CP["Control Plane\n(xDS gRPC)"]

    Internet --> FD --> LB --> NSG --> VMSS
    VMSS -- "xDS gRPC (port 18000)" --> CP
    VMSS -- "HTTP / gRPC" --> Backend
```

---

## VM Image Build Pipeline

Custom images are built with Packer and published to Azure Compute Gallery. VMSS references a specific image version. Rolling image updates trigger a VMSS rolling upgrade.

```mermaid
flowchart LR
    Repo["Config Repo\n(Ansible / Salt)"]
    Packer["Packer\n(azure-arm provisioner)"]
    TempVM["Temp Azure VM\n(build agent)"]
    Provision["Provision step\n- Install Envoy\n- Install sidecars\n- Harden OS\n- Tune network stack\n- Install OTel + Azure Monitor agent"]
    Gallery["Azure Compute Gallery\n(versioned image)"]
    VMSS["VMSS rolling upgrade"]

    Repo --> Packer --> TempVM --> Provision --> Gallery --> VMSS
```

### Image Contents

| Component | Purpose |
|---|---|
| Envoy proxy binary | Data plane — handles all inbound traffic |
| Auth sidecar (Rust) | ext_authz over localhost — authenticates requests |
| Rate limit sidecar (Go) | Implements Envoy rate limit gRPC API over localhost |
| Azure Monitor agent | Ships metrics and logs to Azure Monitor / Log Analytics |
| OpenTelemetry collector | Distributed tracing (forwards to Azure Application Insights or Jaeger) |
| OS hardening | CIS benchmark, disabled unused services, minimal packages |
| Network tuning | TCP buffer sizes, `somaxconn`, `net.core.rmem_max`, connection tracking limits |

---

## Node Bootstrap Sequence

When a VMSS instance starts:

```mermaid
sequenceDiagram
    participant VM as VMSS Node (boot)
    participant MSI as Managed Identity
    participant KV as Key Vault
    participant CP as Control Plane
    participant Auth as Auth Sidecar
    participant RL as Rate Limit Sidecar

    VM->>MSI: Acquire token (no credentials needed)
    VM->>KV: Fetch control plane address + mTLS cert + secret
    VM->>Auth: Start auth sidecar process (localhost:9191)
    VM->>RL: Start rate limit sidecar process (localhost:8081)
    VM->>CP: Open ADS gRPC stream (mTLS)
    CP-->>VM: Initial snapshot (listeners, routes, clusters, endpoints)
    Note over VM: Envoy marks itself ready, LB health check passes
    Note over VM: Node begins accepting traffic
```

---

## Sidecar Model

Sidecars run as separate processes on each node (not containers). Envoy communicates with them over localhost only.

```
┌─────────────────────────────────────────────────────┐
│  Envoy node                                         │
│                                                     │
│  ┌─────────────────┐     ext_authz HTTP             │
│  │  HTTP filter    │──── localhost:9191 ────►  Auth Sidecar (Rust)
│  │  ext_authz      │                               │
│  └─────────────────┘                               │
│                                                     │
│  ┌─────────────────┐     ratelimit gRPC             │
│  │  HTTP filter    │──── localhost:8081 ────► Rate Limit Sidecar (Go)
│  │  ratelimit      │                               │
│  └─────────────────┘                               │
└─────────────────────────────────────────────────────┘
```

### Auth Sidecar

- Protocol: `envoy.service.auth.v3.Authorization` (HTTP ext_authz)
- Receives a `CheckRequest` with full request headers.
- Returns `CheckResponse`: allowed or denied with status code and headers to inject.
- Connects to the control plane on startup to receive dynamic auth policy configuration.

### Rate Limit Sidecar

- Protocol: `envoy.service.ratelimit.v3.RateLimitService` (gRPC)
- Receives rate limit descriptors from Envoy (e.g. service ID, client IP).
- Returns `OVER_LIMIT` or `OK`.
- Per-service limits are configured dynamically via the control plane.

---

## Configuration Flow Summary

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Broker as Service Broker
    participant Worker as Provisioning Worker
    participant DB as Cosmos DB
    participant CP as Control Plane
    participant Envoy as Envoy Fleet

    Dev->>Broker: PUT /v2/service_instances/{id}
    Broker->>DB: Write instance (status=pending)
    Worker->>DB: Write instance (status=ready) after provisioning DNS + cert
    CP->>DB: Poll — detects new instance
    CP->>CP: Re-render snapshot (new virtual host + cluster)
    Envoy->>CP: DiscoveryRequest (stale version)
    CP-->>Envoy: DiscoveryResponse (new routes + clusters)
    Note over Envoy: Begins routing traffic to new service — no restart
```
