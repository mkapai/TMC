#!/usr/bin/env python3
"""
Telegram Message Forwarder - FastAPI Application
FastAPI Web API入口文件
"""
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os
from pathlib import Path

# 导入API路由
from api.routes import (
    auth, chats, clients, dashboard, delivery_targets, messages,
    public_resources, rules, settings, system, users,
)

# 导入核心业务逻辑
from enhanced_bot import EnhancedTelegramBot
from database import init_database
from log_manager import get_logger
from config import Config
from middleware import AuthenticationMiddleware

# 初始化日志
logger = get_logger('fastapi', 'web_api.log')

# 全局bot实例
enhanced_bot_instance = None


def get_enhanced_bot():
    """获取全局bot实例"""
    return enhanced_bot_instance


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global enhanced_bot_instance
    
    # 启动时
    logger.info("🚀 启动FastAPI应用...")
    
    try:
        # 检查并应用数据库迁移
        # 默认开启自动迁移；仅当显式设置为 false/0/no 时关闭
        auto_migrate_env = os.getenv("AUTO_MIGRATE", "true").lower()
        auto_migrate = auto_migrate_env not in ("false", "0", "no")
        if auto_migrate:
            logger.info("🔍 检查数据库迁移...")
            from services.migration_manager import check_and_migrate
            migration_success = check_and_migrate(auto_migrate=True, backup_first=True)
            if not migration_success:
                raise RuntimeError("数据库迁移失败，应用拒绝使用不兼容的数据库结构启动")
        
        # 初始化数据库
        await init_database()
        logger.info("✅ 数据库初始化完成")
        
        # 初始化EnhancedBot
        enhanced_bot_instance = EnhancedTelegramBot()
        await enhanced_bot_instance.start(web_mode=True, skip_config_validation=True)
        logger.info("✅ EnhancedBot启动完成")

        from services.delivery_worker import get_delivery_worker
        await get_delivery_worker().start()
        logger.info("✅ 消息投递 worker 启动完成")
        
        yield
        
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}")
        raise
    finally:
        # 关闭时
        logger.info("🛑 关闭FastAPI应用...")
        
        try:
            from services.delivery_worker import get_delivery_worker
            await get_delivery_worker().stop()
        except Exception as e:
            logger.error(f"停止投递 worker 失败: {e}")
        
        if enhanced_bot_instance:
            await enhanced_bot_instance.stop()
            logger.info("✅ EnhancedBot已停止")


# 创建FastAPI应用
app = FastAPI(
    title="Telegram Message Central API",
    description="""
## 📱 Telegram消息转发和管理中心

一个将 Telegram 实时消息过滤、审核并投递到多个目标的管理平台。

### 🌟 主要功能

* **消息队列**: 实时消息经过过滤、替换和去重后持久化
* **多目标投递**: 支持 Telegram 复制发送和签名 Webhook
* **客户端管理**: 多账号管理，支持会话持久化
* **规则引擎**: 灵活的转发规则配置
* **人工审核**: 支持编辑、批准、拒绝和失败重试

### 🔐 认证说明

大部分API需要JWT Token认证：

1. 使用 `/api/auth/login` 登录获取token
2. 在请求头中添加: `Authorization: Bearer <your-token>`
3. Token默认有效期24小时

### 📚 API文档

* **Swagger UI**: [/docs](/docs) - 交互式API测试
* **ReDoc**: [/redoc](/redoc) - 美观的文档阅读
* **OpenAPI Spec**: [/openapi.json](/openapi.json) - API规范

### 🔗 相关链接

* [GitHub仓库](https://github.com/yourusername/telegram-message-central)
* [使用文档](https://github.com/yourusername/telegram-message-central/wiki)
* [问题反馈](https://github.com/yourusername/telegram-message-central/issues)
    """,
    version=Config.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "认证",
            "description": "用户认证和授权管理，包括登录、登出、Token刷新等操作"
        },
        {
            "name": "用户管理",
            "description": "用户账号管理，包括创建、修改、删除用户等操作"
        },
        {
            "name": "系统管理",
            "description": "系统配置和管理，包括系统信息、运行状态等"
        },
        {
            "name": "转发规则",
            "description": "消息转发规则的增删改查，支持关键词过滤、黑白名单等"
        },
        {
            "name": "聊天管理",
            "description": "Telegram聊天会话管理，包括频道、群组、私聊等"
        },
        {
            "name": "客户端管理",
            "description": "Telegram客户端（账号）管理，支持多账号操作"
        },
        {
            "name": "系统设置",
            "description": "系统全局设置，包括代理、通知、备份等配置"
        },
        {
            "name": "仪表板",
            "description": "数据统计和可视化，展示系统运行状态和统计信息"
        },
        {
            "name": "消息队列",
            "description": "过滤和去重后的消息审核、缓存与投递状态"
        },
        {
            "name": "发送目标",
            "description": "Telegram 和 Webhook 多目标配置"
        }
    ],
    contact={
        "name": "TMC Team",
        "email": "support@tmc.example.com"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    }
)

# 认证中间件 - 保护所有API路由（必须在CORS之前添加，因为中间件执行顺序是倒序）
app.add_middleware(AuthenticationMiddleware)

# CORS配置（最后添加，最先执行）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # API 使用 Bearer Token，不依赖跨域 Cookie
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(auth.router, prefix="/api", tags=["认证"])  # 认证路由（不需要auth前缀，因为router已经有了）
app.include_router(users.router, prefix="/api/users", tags=["用户管理"])
app.include_router(system.router, prefix="/api/system", tags=["系统管理"])
app.include_router(rules.router, prefix="/api/rules", tags=["转发规则"])
app.include_router(chats.router, prefix="/api/chats", tags=["聊天管理"])
app.include_router(clients.router, prefix="/api/clients", tags=["客户端管理"])
app.include_router(settings.router, prefix="/api/settings", tags=["系统设置"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["仪表板"])
app.include_router(messages.router, prefix="/api/messages", tags=["消息队列"])
app.include_router(delivery_targets.router, prefix="/api/delivery-targets", tags=["发送目标"])
app.include_router(public_resources.router, prefix="/public/resources", tags=["公开资源"])


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "bot_running": enhanced_bot_instance is not None and enhanced_bot_instance.running if enhanced_bot_instance else False
    }


@app.get("/api")
async def api_root():
    """API根路径信息"""
    return {
        "name": "Telegram Message Forwarder API",
        "version": Config.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/api/health")
async def api_health_check():
    """API健康检查（兼容原有路径）"""
    return await health_check()


# 错误处理
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """404错误处理"""
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": "资源未找到"}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """500错误处理"""
    logger.error(f"服务器内部错误: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "服务器内部错误"}
    )


# 静态文件服务（如果需要）
# 可以用来服务前端构建的文件
# 静态文件服务 - 前端SPA应用
frontend_dist = Path(__file__).parent / "frontend" / "dist"
logger.info(f"🔍 检查前端目录: {frontend_dist}")

if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    logger.info(f"✅ 前端目录存在，挂载静态文件服务")
    
    # 挂载静态资源目录
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """服务前端SPA应用"""
        # 排除API路由、文档、健康检查
        if (full_path.startswith("api") or 
            full_path.startswith("docs") or 
            full_path.startswith("redoc") or 
            full_path.startswith("openapi.json") or 
            full_path == "health"):
            # 这些路由不存在，返回404
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "资源未找到"}
            )
        
        # 检查是否是静态文件
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        
        # 否则返回index.html（支持SPA前端路由）
        return FileResponse(frontend_dist / "index.html")
else:
    logger.warning(f"⚠️  前端目录不存在或缺少index.html: {frontend_dist}")


if __name__ == "__main__":
    import uvicorn
    
    # 开发环境配置
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9393,
        reload=True,  # 开发模式自动重载
        log_level="info"
    )
