
import asyncio
from tortoise import Tortoise
from app.services.device_service import device_service
from app.core.config import settings

async def verify():
    # Initialize Tortoise
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={"models": ["app.models.orm.user", "app.models.orm.device", "app.models.orm.audit"]},
    )
    
    print("Tortoise initialized.")
    
    try:
        print("Calling device_service.get_device_list(0)...")
        devices = await device_service.get_device_list(0)
        print(f"Success! Retrieved {len(devices)} devices.")
        for d in devices[:3]: # Print first 3
            print(f"Device: {d['device_name']} (ID: {d['id']}), Created By: {d['created_by_name']}")
    except Exception as e:
        print(f"Error calling get_device_list: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await Tortoise.close_connections()

if __name__ == "__main__":
    asyncio.run(verify())
