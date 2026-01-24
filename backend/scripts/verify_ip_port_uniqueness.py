import asyncio
import random
from tortoise import Tortoise
from app.core.config import settings
from app.services.device_service import device_service
from app.schemas.device import DeviceCreate


async def verify():
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={"models": [
            "app.models.orm.user",
            "app.models.orm.device",
            "app.models.orm.audit",
            "app.models.orm.location",
            "app.models.orm.config",
        ]},
    )
    print("Tortoise initialized.")

    base_ip = f"192.168.{random.randint(1, 250)}.{random.randint(1, 250)}"
    port_a = 2200
    port_b = 2201

    print(f"Creating device A: {base_ip}:{port_a}")
    dev_a = DeviceCreate(
        device_name=f"Dev-A-{base_ip}",
        ipv4=base_ip,
        type="linux",
        ssh_port=port_a,
        user_name="root",
        password="pwdA",
    )
    await device_service.add_device(dev_a, user_id=1)
    print("Device A created.")

    print(f"Creating device B (same IP, diff port): {base_ip}:{port_b}")
    dev_b = DeviceCreate(
        device_name=f"Dev-B-{base_ip}",
        ipv4=base_ip,
        type="linux",
        ssh_port=port_b,
        user_name="root",
        password="pwdB",
    )
    await device_service.add_device(dev_b, user_id=1)
    print("Device B created.")

    print(f"Creating device C (same IP+port as A): {base_ip}:{port_a}")
    dev_c = DeviceCreate(
        device_name=f"Dev-C-{base_ip}",
        ipv4=base_ip,
        type="linux",
        ssh_port=port_a,
        user_name="root",
        password="pwdC",
    )
    try:
        await device_service.add_device(dev_c, user_id=1)
        print("ERROR: Device C should have failed but succeeded")
    except Exception as e:
        print(f"Expected failure: {str(e).splitlines()[0]}")

    await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(verify())

