
import asyncio
from tortoise import Tortoise
from app.core.config import settings
from app.workers.monitor.manager import MonitorManager
from app.models.orm.device import NetworkDevice
from app.core.redis import redis_manager

async def verify():
    # Initialize Redis
    try:
        await redis_manager.init()
        print("Redis initialized.")
    except Exception as e:
        print(f"Redis init failed: {e}")

    # Initialize Tortoise
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={"models": [
            "app.models.orm.user", 
            "app.models.orm.device", 
            "app.models.orm.audit",
            "app.models.orm.notification",
            "app.models.orm.repair",
            "app.models.orm.rbac",
            "app.models.orm.location",
            "app.models.orm.config"
        ]},
    )
    print("Tortoise initialized.")
    
    # Create dummy device if none
    if not await NetworkDevice.all().exists():
        await NetworkDevice.create(
            device_name="TestDevice",
            ipv4="127.0.0.1",
            device_type="linux",
            is_active=True,
            created_by="0" # Ensure created_by is string as per model
        )
        print("Created dummy device.")

    manager = MonitorManager()
    
    print("Loading devices...")
    try:
        await manager.load_devices()
        print(f"Loaded {len(manager.devices)} devices.")
        for did, dev in manager.devices.items():
            print(f"Device: {did}, IP: {dev.ip}, Interval: {dev.interval}")
    except Exception as e:
        print(f"Error loading devices: {e}")
        import traceback
        traceback.print_exc()
        
    await Tortoise.close_connections()
    await redis_manager.close()

if __name__ == "__main__":
    asyncio.run(verify())
