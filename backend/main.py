# -*- coding: utf-8 -*-
#
# FastAPI 应用程序入口点
#
# 此文件是整个应用程序的启动入口。
# 实际上，它主要负责导入在 asgi.py 中初始化的 FastAPI 应用实例 `app`。
# 这种分离（main.py vs asgi.py）通常用于区分 "应用定义" 和 "应用运行/入口"。
# 在生产环境中，通常使用 uvicorn 或 gunicorn 指向此模块中的 app 对象来启动服务。
# 例如：uvicorn FastAPIProject.main:app --host 0.0.0.0 --port 8000
#

# 从 asgi 模块导入已经配置好的 FastAPI 应用实例
# asgi.py 中包含了数据库连接、Redis连接、中间件配置、路由注册等所有核心逻辑
from asgi import app

