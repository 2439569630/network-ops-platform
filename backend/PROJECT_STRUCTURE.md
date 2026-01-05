# 后端项目结构文档

本文档描述了重构后的后端项目（Server）目录结构及其职责。

## 根目录 (`Server/`)

| 目录/文件 | 说明 |
| :--- | :--- |
| **`app/`** | **核心应用代码**，包含所有业务逻辑。 |
| **`scripts/`** | **运维脚本**，包含独立运行的服务脚本。 |
| **`Legacy_Backup/`** | **归档目录**，存放重构前的旧代码（Config, DataBase, Routers 等）。 |
| **`logs/`** | **日志目录**，存放应用和驱动的运行日志。 |
| `main.py` | **程序入口**，FastAPI 应用启动文件。 |
| `requirements.txt` | Python 项目依赖列表。 |

## 核心应用目录 (`app/`)

采用分层架构设计：

### 1. 接口层 (`app/api/`)
负责处理 HTTP 请求、路由分发和依赖注入。
- `v1/endpoints/`: 具体业务路由模块。
  - `auth.py`: 认证（登录、Token）。
  - `users.py`: 用户管理。
  - `devices.py`: 设备管理。
  - `system.py`: 系统全局配置。
  - `automation.py`: 自动化任务（如 SNMP 自动配置）。
  - `trap.py`: Trap 服务管理。
  - `notifications.py`: 通知配置与历史。
  - `ssh.py`: Web SSH WebSocket 连接。

### 2. 核心基础设施 (`app/core/`)
提供全局通用的基础服务。
- `config.py`: 静态环境配置（加载 `.env`）。
- `system_config.py`: 数据库动态配置（Singleton）。
- `database.py`: 异步 PostgreSQL 数据库连接池。
- `redis.py`: 异步 Redis 连接池。
- `security.py`: JWT 令牌生成与验证、密码哈希。
- `logger.py`: 统一日志配置中心。

### 3. 业务逻辑层 (`app/services/`)
封装复杂的业务规则，供接口层调用。
- `device_service.py`: 设备增删改查、状态管理。
- `user_service.py`: 用户权限、角色管理。
- `trap_service.py`: Trap 服务的启停控制与日志读取。
- `notification_service.py`: 通知的生成、路由与发送逻辑。
- `ssh_service.py`: SSH 会话管理。

### 4. 驱动层 (`app/drivers/`)
负责与底层设备或协议交互，屏蔽差异。
- `base.py`: 驱动抽象基类。
- `factory.py`: 驱动工厂模式，根据设备类型创建驱动实例。
- `netmiko_driver.py`: 通用 SSH/Telnet 驱动（基于 Netmiko）。
- `snmp_driver.py`: SNMP 协议驱动（用于自动化配置）。
- `linux_driver.py`: Linux 服务器专用驱动。

### 5. 数据模型 (`app/schemas/`)
Pydantic 模型，用于请求验证和响应序列化。
- `user.py`: 用户相关模型。
- `device.py`: 设备相关模型。
- `notification.py`: 通知配置模型。

### 6. 后台工作进程 (`app/workers/`)
运行在后台的长期任务或监听服务。
- `monitor/manager.py`: 设备状态监控管理器（轮询、心跳）。
- `trap/listener.py`: SNMP Trap 监听服务实现。

### 7. 工具类 (`app/utils/`)
- `notification_sender.py`: 具体发送邮件、Webhook 的实现。

## 运维脚本 (`scripts/`)
- `run_trap_service.py`: 独立启动 Trap 监听服务的脚本（负责 PID 文件生命周期管理）。
