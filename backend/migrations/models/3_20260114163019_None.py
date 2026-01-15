from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "users" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "username" VARCHAR(50) NOT NULL UNIQUE,
    "password" VARCHAR(128) NOT NULL,
    "nickname" VARCHAR(50),
    "email" VARCHAR(255),
    "is_approved" BOOL NOT NULL DEFAULT True,
    "permissions" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "network_devices" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "device_name" VARCHAR(255) NOT NULL,
    "ipv4" VARCHAR(50),
    "ipv6" VARCHAR(50),
    "mac" VARCHAR(50),
    "device_type" VARCHAR(50),
    "user_name" VARCHAR(50),
    "password" VARCHAR(128),
    "ssh_port" INT NOT NULL DEFAULT 22,
    "online_status" BOOL NOT NULL DEFAULT False,
    "is_active" BOOL NOT NULL DEFAULT True,
    "vendor" VARCHAR(255),
    "model" VARCHAR(255),
    "serial_number" VARCHAR(255),
    "description" TEXT,
    "telnet_port" INT,
    "last_seen" TIMESTAMPTZ,
    "last_backup" TIMESTAMPTZ,
    "created_by" VARCHAR(50),
    "updated_by" VARCHAR(50),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS "location_nodes" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "parent_id" BIGINT,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "code" VARCHAR(255) UNIQUE,
    "manager_dept" TEXT,
    "manager" TEXT,
    "phone" TEXT,
    "capacity" INT,
    "area" DOUBLE PRECISION,
    "address" TEXT,
    "description" TEXT,
    "status" BOOL NOT NULL DEFAULT True,
    "sort_order" INT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "location_node_devices" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "node_id" BIGINT NOT NULL,
    "device_id" INT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS "location_node_roles" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "node_id" BIGINT NOT NULL,
    "role_id" BIGINT NOT NULL,
    CONSTRAINT "uid_location_no_node_id_95f6cc" UNIQUE ("node_id", "role_id")
);
CREATE TABLE IF NOT EXISTS "location_node_users" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "node_id" BIGINT NOT NULL,
    "user_id" BIGINT NOT NULL,
    CONSTRAINT "uid_location_no_node_id_273038" UNIQUE ("node_id", "user_id")
);
CREATE TABLE IF NOT EXISTS "permissions" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "code" VARCHAR(100) NOT NULL UNIQUE,
    "description" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "roles" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "code" VARCHAR(50) NOT NULL UNIQUE,
    "description" TEXT,
    "is_default" BOOL NOT NULL DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "role_permissions" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "role_id" INT NOT NULL,
    "permission_id" INT NOT NULL,
    CONSTRAINT "uid_role_permis_role_id_6a25fe" UNIQUE ("role_id", "permission_id")
);
CREATE TABLE IF NOT EXISTS "user_roles" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "user_id" INT NOT NULL,
    "role_id" INT NOT NULL,
    CONSTRAINT "uid_user_roles_user_id_63f1a8" UNIQUE ("user_id", "role_id")
);
CREATE TABLE IF NOT EXISTS "order_logs" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "order_id" INT NOT NULL,
    "operator_id" INT NOT NULL,
    "action" VARCHAR(50) NOT NULL,
    "from_status" VARCHAR(50),
    "to_status" VARCHAR(50),
    "remark" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "order_reviews" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "order_id" INT NOT NULL,
    "rating" INT NOT NULL,
    "comment" TEXT,
    "response_time_rating" INT,
    "service_quality_rating" INT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "repair_orders" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "submitter_id" INT NOT NULL,
    "device_id" INT,
    "location_id" BIGINT,
    "assignee_id" INT,
    "priority" VARCHAR(50) NOT NULL DEFAULT 'normal',
    "status" VARCHAR(50) NOT NULL DEFAULT 'pending',
    "actual_completion_time" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "work_logs" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "order_id" INT NOT NULL,
    "operator_id" INT NOT NULL,
    "content" TEXT NOT NULL,
    "images" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "8ut/jo/pmg=="
)
