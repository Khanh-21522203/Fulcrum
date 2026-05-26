# Provider Boundary

Fulcrum's core should stay cloud-neutral. Broker, worker, and control-plane code depend on ports from `fulcrum_shared.ports`; provider-specific code implements those ports.

## Current Default

The local MVP uses Postgres for both durable service-instance state and the worker task outbox:

- broker writes `ServiceInstance` rows and `ProvisioningTask` rows through `InstanceStore`
- worker claims and completes tasks through `ProvisioningTaskQueue`
- control-plane reads ready instances through `SnapshotInstanceSource`

This works locally, in Docker Compose, and in any cloud that can run Postgres.

## Provider Ports

- `InstanceStore`: broker-facing lifecycle write path.
- `ProvisioningTaskQueue`: worker-facing durable task queue.
- `SnapshotInstanceSource`: control-plane read path for routable instances.
- `DnsProvider`: DNS record management for worker side effects.
- `CertificateProvider`: certificate material lifecycle.
- `SecretStore`: runtime secret storage.
- `ObjectStore`: template and artifact storage.

## Ownership Rule

Broker should only validate lifecycle requests and enqueue tasks. Control-plane should only read desired routable state and publish xDS snapshots. Worker owns provider side effects such as DNS, certificates, secrets, and cleanup.

Azure, AWS, GCP, Kubernetes, or filesystem implementations should be added as adapters behind these ports, not as assumptions in the core packages.
