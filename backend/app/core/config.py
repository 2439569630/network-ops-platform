
import logging
from typing import Any, Dict, Optional, Union
from pydantic import PostgresDsn, RedisDsn, Field
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
    
    # Security
    SECRET_KEY: str = Field(default="dev-secret", alias="JWT_SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    ALGORITHM: str = "HS256"
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    
    # Monitor
    # 监控轮询间隔（秒）
    MONITOR_INTERVAL: int = 60
    # 在线状态检查间隔（秒）
    ONLINE_CHECK_INTERVAL: int = 10
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
