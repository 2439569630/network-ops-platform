
import asyncio
from tortoise import Tortoise
from app.services.device_service import device_service
from app.schemas.device import DeviceCreate
from app.core.config import settings

async def verify_add():
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={"models": ["app.models.orm.user", "app.models.orm.device", "app.models.orm.audit"]},
    )
    
    print("Tortoise initialized.")
    
    # Randomize IP to avoid conflict
    import random
    ip = f"192.168.200.{random.randint(1, 254)}"
    
    device_in = DeviceCreate(
        device_name=f"TestDevice-{ip}",
        ipv4=ip,
        type="linux",
        ssh_port=22,
        user_name="root",
        password="password"
    )
    
    try:
        print(f"Adding device {ip}...")
        await device_service.add_device(device_in, user_id=123456) # Assuming 123456 exists or just as ID
        print("Device added successfully.")
        
        # Verify fetch
        devices = await device_service.get_device_list(0, search_query=ip)
        if devices and devices[0]['ipv4'] == ip:
            print("Device found in list.")
            print(f"Device ID: {devices[0]['id']}")
            
            # Verify delete
            print("Deleting device...")
            await device_service.delete_device(device_id=devices[0]['id'], deleted_by="123456")
            print("Device deleted.")
            
            # Verify deleted list
            deleted = await device_service.get_deleted_devices()
            deleted_device = next((d for d in deleted if d['ipv4'] == ip), None)
            if deleted_device:
                 print("Device found in deleted list.")
                 
                 # Purge
                 print("Purging device...")
                 await device_service.purge_device(deleted_device['id'])
                 print("Device purged.")
            else:
                 print("Device NOT found in deleted list!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await Tortoise.close_connections()

if __name__ == "__main__":
    asyncio.run(verify_add())
