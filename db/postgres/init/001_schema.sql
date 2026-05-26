CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    CREATE TYPE instance_status AS ENUM (
        'pending',
        'provisioning',
        'ready',
        'failed',
        'deprovisioning',
        'deleted'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE operation_type AS ENUM (
        'provision',
        'deprovision',
        'update'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE operation_state AS ENUM (
        'in_progress',
        'succeeded',
        'failed'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE task_status AS ENUM (
        'pending',
        'processing',
        'succeeded',
        'failed'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS service_instances (
    id uuid PRIMARY KEY,
    service_id text NOT NULL,
    plan_id text NOT NULL,
    organization_id text NOT NULL,
    space_id text NOT NULL,
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    status instance_status NOT NULL DEFAULT 'pending',
    last_operation_type operation_type,
    last_operation_state operation_state,
    last_operation_description text NOT NULL DEFAULT '',
    last_operation_updated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT service_instances_parameters_object
        CHECK (jsonb_typeof(parameters) = 'object'),
    CONSTRAINT service_instances_last_operation_complete
        CHECK (
            (
                last_operation_type IS NULL
                AND last_operation_state IS NULL
                AND last_operation_updated_at IS NULL
            )
            OR (
                last_operation_type IS NOT NULL
                AND last_operation_state IS NOT NULL
                AND last_operation_updated_at IS NOT NULL
            )
        )
);

CREATE TABLE IF NOT EXISTS provisioning_tasks (
    task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id uuid NOT NULL REFERENCES service_instances(id),
    task_type operation_type NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status task_status NOT NULL DEFAULT 'pending',
    attempt integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    locked_by text,
    last_error text,
    enqueued_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT provisioning_tasks_payload_object
        CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT provisioning_tasks_attempt_non_negative
        CHECK (attempt >= 0)
);

CREATE INDEX IF NOT EXISTS idx_service_instances_status
    ON service_instances(status);

CREATE INDEX IF NOT EXISTS idx_service_instances_ready_node_group
    ON service_instances ((parameters->>'node_group'))
    WHERE status = 'ready';

CREATE INDEX IF NOT EXISTS idx_service_instances_domains
    ON service_instances USING gin ((parameters->'domains'))
    WHERE status IN ('provisioning', 'ready');

CREATE INDEX IF NOT EXISTS idx_provisioning_tasks_claim
    ON provisioning_tasks(status, available_at, enqueued_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_provisioning_tasks_instance
    ON provisioning_tasks(instance_id, enqueued_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_service_instances_updated_at ON service_instances;
CREATE TRIGGER trg_service_instances_updated_at
BEFORE UPDATE ON service_instances
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
