
import secrets
import sys
from typing import Any, Dict, Optional, Union
from pydantic import PostgresDsn, RedisDsn, Field, model_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """系统配置类"""
    PROJECT_NAME: str = "Network Device Manager"
    API_V1_STR: str = "/api/v1"
    
    # Database
    # 使用 Field(alias="...") 或默认值来适配现有环境
    # 根据 PostgreSQL.py 中的硬编码值设置默认值
    POSTGRES_USER: str = Field(default="lhq", alias="DB_USER")
    POSTGRES_PASSWORD: str = Field(default="isHjPEaxBrwbkQpN", alias="DB_PASSWORD")
    POSTGRES_SERVER: str = Field(default="123.207.72.157", alias="DB_HOST")
    POSTGRES_PORT: int = Field(default=54322, alias="DB_PORT")
    POSTGRES_DB: str = Field(default="lhq", alias="DB_NAME")
    
    # Redis
    REDIS_HOST: str = Field(default="localhost", alias="REDISHOST")
    REDIS_PASSWORD: Optional[str] = Field(default=None, alias="REDISPASSWORD")
    REDIS_PORT: int = Field(default=6379, alias="REDISPORT")
    REDIS_MAX_CONNECTIONS: int = Field(default=20, alias="REDIS_MAX_CONNECTIONS")
    REDIS_PUBSUB_MAX_CONNECTIONS: int = Field(default=200, alias="REDIS_PUBSUB_MAX_CONNECTIONS")
    
    # Security
    ALLOW_EPHEMERAL_JWT_SECRETS: bool = Field(default=False, alias="ALLOW_EPHEMERAL_JWT_SECRETS")
    SECRET_KEY: Optional[str] = Field(default=None, alias="JWT_SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    ALGORITHM: str = "HS256"
    REFRESH_SECRET_KEY: Optional[str] = Field(default=None, alias="JWT_REFRESH_SECRET_KEY")
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days

    @model_validator(mode="after")
    def _validate_jwt_secrets(self):
        placeholders = {"dev-secret", "dev-refresh-secret", "change-me"}
        allow_ephemeral = bool(self.ALLOW_EPHEMERAL_JWT_SECRETS) or ("pytest" in sys.modules or "unittest" in sys.modules)

        secret_key = str(self.SECRET_KEY or "").strip()
        if not secret_key:
            if not allow_ephemeral:
                raise ValueError("JWT_SECRET_KEY 未配置")
            secret_key = secrets.token_urlsafe(48)
        if secret_key in placeholders:
            if not allow_ephemeral:
                raise ValueError("JWT_SECRET_KEY 强度不足")
            secret_key = secrets.token_urlsafe(48)
        if len(secret_key) < 32:
            if not allow_ephemeral:
                raise ValueError("JWT_SECRET_KEY 强度不足")
            secret_key = secrets.token_urlsafe(48)
        self.SECRET_KEY = secret_key

        refresh_secret = str(self.REFRESH_SECRET_KEY or "").strip()
        if not refresh_secret:
            refresh_secret = secret_key
        if refresh_secret in placeholders:
            if not allow_ephemeral:
                raise ValueError("JWT_REFRESH_SECRET_KEY 强度不足")
            refresh_secret = secret_key
        if len(refresh_secret) < 32:
            if not allow_ephemeral:
                raise ValueError("JWT_REFRESH_SECRET_KEY 强度不足")
            refresh_secret = secret_key
        self.REFRESH_SECRET_KEY = refresh_secret
        return self
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    
    # Monitor
    # 监控轮询间隔（秒）
    MONITOR_INTERVAL: int = 60
    # 设备列表热更新轮询间隔（秒），用于兜底同步数据库变更
    DEVICE_LOADER_INTERVAL: int = 300
    # 禁用设备列表热更新轮询（1=禁用）
    DISABLE_DEVICE_LOADER: int = 0
    # 运行态快照在 Redis 的 TTL（秒），0 表示不设置过期
    RUNTIME_SNAPSHOT_TTL_SECONDS: int = 86400
    # 运行态快照超过多少秒视为过期（用于前端展示陈旧状态）
    RUNTIME_SNAPSHOT_STALE_AFTER_SECONDS: int = 0

    ALERT_LOG_RETENTION_DAYS: int = 90
    NOTIFICATION_HISTORY_RETENTION_DAYS: int = 90
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgres://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore" # 忽略 .env 中多余的变量

settings = Settings()
