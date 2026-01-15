
from app.core.config import settings

TORTOISE_ORM = {
    "connections": {"default": settings.DATABASE_URL},
    "apps": {
        "models": {
            "models": [
                "app.models.orm.user",
                "app.models.orm.device",
                "app.models.orm.audit",
                "app.models.orm.notification",
                "app.models.orm.repair",
                "app.models.orm.rbac",
                "app.models.orm.location",
                "app.models.orm.config",
                "aerich.models",
            ],
            "default_connection": "default",
        },
    },
}
