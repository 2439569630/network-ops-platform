from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_network_devices_ipv4_port
    ON "network_devices" ("ipv4", "ssh_port");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
    DROP INDEX IF EXISTS idx_network_devices_ipv4_port;
    """

