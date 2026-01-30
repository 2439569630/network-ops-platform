from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "config_push_jobs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL,
    "creator_id" INT NOT NULL,
    "status" VARCHAR(32) NOT NULL DEFAULT 'pending',
    "command_list" JSONB NOT NULL,
    "device_count" INT NOT NULL DEFAULT 0,
    "success_count" INT NOT NULL DEFAULT 0,
    "fail_count" INT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMPTZ
);
        CREATE TABLE IF NOT EXISTS "config_push_job_items" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "device_id" INT NOT NULL,
    "device_name" VARCHAR(255) NOT NULL,
    "device_ip" VARCHAR(50) NOT NULL,
    "status" VARCHAR(32) NOT NULL DEFAULT 'pending',
    "error_message" TEXT,
    "started_at" TIMESTAMPTZ,
    "finished_at" TIMESTAMPTZ,
    "job_id" INT NOT NULL REFERENCES "config_push_jobs" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_config_push_job_id_126d07" UNIQUE ("job_id", "device_id")
);
        CREATE TABLE IF NOT EXISTS "config_push_logs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "job_id" INT NOT NULL,
    "type" VARCHAR(50) NOT NULL,
    "subject" VARCHAR(255),
    "content" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
        ALTER TABLE "device_configs" ADD "offline_retry_silent_min_interval_seconds" DOUBLE PRECISION;
        ALTER TABLE "device_configs" ADD "offline_retry_silent_after_attempts" INT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "device_configs" DROP COLUMN "offline_retry_silent_min_interval_seconds";
        ALTER TABLE "device_configs" DROP COLUMN "offline_retry_silent_after_attempts";
        DROP TABLE IF EXISTS "config_push_jobs";
        DROP TABLE IF EXISTS "config_push_job_items";
        DROP TABLE IF EXISTS "config_push_logs";"""


MODELS_STATE = (
    "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"
    "9/8DmBtuEw=="
)
