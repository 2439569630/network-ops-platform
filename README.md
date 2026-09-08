# 网络设备运维管理平台

一个面向企业网络设备运维场景的 Web 管理平台。通过 SSH 自动采集设备运行状态，把「逐台登录交换机敲命令」的高频操作收敛为页面点选，并提供批量配置下发、定时巡检告警、权限管控与操作审计能力。

> 本科毕业设计作品，前后端均由一人独立完成。

---

## 一、要解决的问题

| 运维痛点 | 本平台的做法 |
| --- | --- |
| 设备分散，查看状态要逐台 SSH 登录敲命令，效率低 | 后端通过 SSH 统一采集，前端页面点选查询，高频操作从约 30 秒缩短到 2 秒 |
| 改了什么、谁改的，事后查不出来 | 所有关键命令写入审计日志，记录执行人、目标设备、命令内容与时间 |
| 批量变更靠人工逐台执行，容易漏、容易错 | 提供批量配置下发任务，WebSocket 实时回传每台设备的执行进度与结果 |
| 设备宕机没人第一时间知道 | 后台巡检进程定时探测，离线触发告警并推送通知 |
| 谁能执行什么命令，缺少约束 | RBAC 角色 + 细粒度权限码，在接口层做鉴权 |

---

## 二、核心功能

**设备与状态**
- 设备台账管理（增删改查、分组、位置）
- 经 SSH 自动采集版本、接口、VLAN 等信息
- 设备详情页实时展示运行状态

**命令与配置**
- 单设备命令执行，异常统一捕获并提示
- 多设备批量配置下发，任务可创建、查询、取消
- WebSocket 实时回传下发进度

**监控与告警**
- 后台巡检进程定时同步设备状态
- 离线判定与告警触发
- 站内消息与邮件通知

**权限与审计**
- JWT 双令牌（Access / Refresh）+ bcrypt 加盐存储
- RBAC 角色权限模型，接口层依赖注入鉴权
- 会话版本控制：改密或权限变更即时生效
- 三类审计日志：设备变更、SSH 命令、管理员操作

**工单**
- 报修工单全流程：提交 → 派单 → 接单 → 完成 → 评价

---

## 三、技术栈

**后端**
- FastAPI 0.135（Python 3.10）
- Tortoise ORM + PostgreSQL 16（asyncpg 异步驱动）
- Redis 7（会话版本、状态快照、发布订阅）
- Netmiko / Paramiko（SSH 设备接入）
- python-jose（JWT）+ passlib/bcrypt（密码哈希）
- WebSockets（实时推送）
- aiosmtplib（邮件通知）
- 异步任务采用 asyncio worker + Redis 发布订阅，未引入 Celery

**前端**
- Vue 3 + Vite
- Element Plus / Vuetify（UI 组件）
- Pinia（状态管理）+ Vue Router（路由与权限元信息）
- Axios（请求封装）
- ECharts（数据可视化）

**部署**
- Docker Compose 编排 PostgreSQL / Redis / Backend 三容器
- Nginx 反向代理
- 后端三进程总控：API 服务、监控巡检 worker、配置下发 worker

**代码规模**
- 后端：144 个 Python 文件，约 2.97 万行
- 前端：67 个文件，约 2.69 万行

---

## 四、目录结构

```text
network-ops-platform/
├── backend/                    # FastAPI 后端
│   ├── asgi.py                 # FastAPI 启动与生命周期入口
│   ├── supervisor.py           # 三进程总控（API / 监控 / 配置下发）
│   ├── app/
│   │   ├── api/v1/endpoints/   # 路由层：auth、devices、rbac、repair、system……
│   │   ├── core/               # 配置、安全、数据库、Redis、日志
│   │   ├── drivers/            # SSH / Netmiko 驱动与命令解析
│   │   ├── models/orm/         # Tortoise ORM 模型
│   │   ├── schemas/            # Pydantic 数据结构
│   │   ├── services/           # 业务服务层
│   │   ├── utils/              # 通用工具
│   │   └── workers/            # 监控巡检、配置下发 worker
│   ├── migrations/             # 数据库迁移
│   ├── scripts/                # 初始化与运维脚本
│   └── tests/                  # 后端测试
├── frontend/                   # Vue 3 前端
│   └── src/
│       ├── api/                # 接口封装
│       ├── components/         # 业务页面组件
│       ├── router/             # 路由与权限元信息
│       └── stores/             # Pinia 状态模块
├── deploy/nginx/               # Nginx 配置
├── docker-compose.yml
└── .env.example
```

---

## 五、快速开始

### 环境要求

- Docker 与 Docker Compose
- Node.js 18+（仅前端本地开发需要）

### 1. 准备环境变量

```bash
cp .env.example .env
```

修改 `.env` 中的以下项（**务必替换默认值**）：

```bash
DB_PASSWORD=你的数据库密码
REDISPASSWORD=你的 Redis 密码
JWT_SECRET_KEY=随机长字符串
JWT_REFRESH_SECRET_KEY=另一个随机长字符串
BACKEND_CORS_ORIGINS=["http://localhost:5173"]
```

### 2. 启动后端与依赖服务

```bash
docker compose up -d
```

服务启动后：

- 后端 API：`http://localhost:8000`
- 接口文档：`http://localhost:8000/docs`
- PostgreSQL：宿主机 `54322` 端口
- Redis：宿主机 `63790` 端口

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务默认运行在 `http://localhost:5173`。

---

## 六、关键实现说明

**SSH 设备接入**
`backend/app/drivers/base.py` 使用 Netmiko 的 `ConnectHandler` 建立连接，通过 `run_in_executor` 放入线程池执行，避免 SSH 阻塞 FastAPI 事件循环；连接超时、认证失败等异常统一捕获并压缩为可读提示，配合重试策略。

**权限模型**
`backend/app/models/orm/rbac.py` 定义 `roles` / `permissions` / `user_roles` / `role_permissions` 四张表，权限以权限码（code）表达。接口层通过 `RoleChecker` 与 `PermissionChecker` 依赖注入校验；Redis 中维护 `auth_ver` 与 `perm_ver` 版本号，实现改密踢人下线、权限变更即时生效。

**审计留痕**
`backend/app/models/orm/audit.py` 定义三类日志表，其中 `SshCommandAuditLog` 记录 `device_id`、`device_ip`、`command`、`executed_by`、`executed_at`，在命令执行与配置下发的关键路径写入。

**实时推送**
配置下发任务创建后返回任务 ID，前端通过 WebSocket 订阅该 ID，后端 worker 逐设备执行并回传进度与结果。

---

## 七、已知不足与后续规划

如实记录，便于后续改进：

- 设备 SSH 凭据当前为数据库明文存储，计划改用 Fernet 对称加密，密钥通过环境变量注入，不入库、不进版本库
- 尚未实现命令白名单机制，后续将增加只读/配置类命令的分级管控
- 数据库迁移治理不统一，计划形成可回滚、可追溯的迁移流程
- 前端部分高风险操作的权限闸门需与后端进一步对齐
- 计划补充架构图、监控时序图、工单状态机图与 ER 图

---

## 八、说明

- 本项目为本科毕业设计，非生产环境部署
- 设备连接信息、密钥等敏感配置均通过 `.env` 管理，不纳入版本库
- 欢迎交流：`issues`
