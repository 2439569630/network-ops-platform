from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE IF EXISTS "device_configs"
        ADD COLUMN IF NOT EXISTS "interfaces_sync_interval" DOUBLE PRECISION NOT NULL DEFAULT 3600.0;

        ALTER TABLE IF EXISTS "device_configs"
        ADD COLUMN IF NOT EXISTS "routes_sync_interval" DOUBLE PRECISION NOT NULL DEFAULT 3600.0;

        ALTER TABLE IF EXISTS "device_configs"
        ADD COLUMN IF NOT EXISTS "vlans_sync_interval" DOUBLE PRECISION NOT NULL DEFAULT 3600.0;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE IF EXISTS "device_configs" DROP COLUMN IF EXISTS "interfaces_sync_interval";
        ALTER TABLE IF EXISTS "device_configs" DROP COLUMN IF EXISTS "routes_sync_interval";
        ALTER TABLE IF EXISTS "device_configs" DROP COLUMN IF EXISTS "vlans_sync_interval";
    """


MODELS_STATE = (
    "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"
    "8ut/jo/pmg=="
)

