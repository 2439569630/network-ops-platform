from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "repair_images" (
            "id" BIGSERIAL NOT NULL PRIMARY KEY,
            "order_id" INT,
            "work_log_id" BIGINT,
            "uploader_id" INT NOT NULL,
            "storage_provider" VARCHAR(32) NOT NULL DEFAULT 'local',
            "object_key" VARCHAR(512) NOT NULL,
            "url" TEXT,
            "mime_type" VARCHAR(128),
            "size" INT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS "idx_repair_images_order_id" ON "repair_images" ("order_id");
        CREATE INDEX IF NOT EXISTS "idx_repair_images_work_log_id" ON "repair_images" ("work_log_id");
        CREATE INDEX IF NOT EXISTS "idx_repair_images_uploader_id" ON "repair_images" ("uploader_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "repair_images";
    """


MODELS_STATE = (
    "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"
    "3XIhNs/Et1zUdiND8y2ynWb6fv8/luzdcg=="
)
