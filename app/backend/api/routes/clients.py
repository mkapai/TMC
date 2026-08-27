#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram客户端管理API路由

管理多个Telegram客户端的添加、删除、启动、停止
"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from log_manager import get_logger
from api.dependencies import get_enhanced_bot

logger = get_logger('api.clients', 'api.log')

router = APIRouter()


async def _load_runtime_client(enhanced_bot, client_id: str):
    """Load a configured client into the runtime manager without starting it."""
    if client_id in enhanced_bot.multi_client_manager.clients:
        return enhanced_bot.multi_client_manager.clients[client_id]

    from config import Config
    from database import get_db
    from models import TelegramClient
    from sqlalchemy import select

    async for db in get_db():
        result = await db.execute(
            select(TelegramClient).where(TelegramClient.client_id == client_id)
        )
        db_client = result.scalar_one_or_none()
        if not db_client:
            return None

        if db_client.client_type == 'bot':
            config_data = {
                'bot_token': db_client.bot_token,
                'admin_user_id': db_client.admin_user_id,
                'api_id': db_client.api_id,
                'api_hash': db_client.api_hash,
            }
        else:
            config_data = {
                'api_id': db_client.api_id or Config.API_ID,
                'api_hash': db_client.api_hash or Config.API_HASH,
                'phone': db_client.phone or Config.PHONE_NUMBER,
            }

        client = enhanced_bot.multi_client_manager.add_client_with_config(
            db_client.client_id,
            db_client.client_type,
            config_data=config_data,
        )
        client.add_status_callback(enhanced_bot._notify_status_change)
        logger.info(f"✅ 从数据库加载客户端配置: {client_id}")
        return client

    return None


@router.get("")
async def list_clients():
    """
    获取所有客户端状态
    
    返回所有客户端的运行状态和配置信息
    """
    try:
        enhanced_bot = get_enhanced_bot()
        clients_status = {}
        
        if enhanced_bot:
            # 获取运行时客户端状态
            runtime_clients = enhanced_bot.get_client_status()
            clients_status.update(runtime_clients)
        
        # 从数据库获取所有配置的客户端
        try:
            from models import TelegramClient
            from database import get_db
            from sqlalchemy import select
            
            async for db in get_db():
                result = await db.execute(select(TelegramClient))
                db_clients = result.scalars().all()
                
                # 为每个数据库客户端创建状态信息
                for db_client in db_clients:
                    if db_client.client_id in clients_status:
                        # 运行时客户端已存在，只添加auto_start信息
                        clients_status[db_client.client_id]['auto_start'] = db_client.auto_start
                    else:
                        # 运行时客户端不存在，创建基础状态信息
                        clients_status[db_client.client_id] = {
                            "client_id": db_client.client_id,
                            "client_type": db_client.client_type,
                            "running": False,
                            "connected": False,
                            "login_state": "idle",
                            "user_info": None,
                            "monitored_chats": [],
                            "thread_alive": False,
                            "auto_start": db_client.auto_start
                        }
                break
                        
        except Exception as db_error:
            logger.warning(f"获取数据库客户端信息失败: {db_error}")
            # 如果数据库查询失败，给运行时客户端设置默认auto_start值
            for client_id, client_info in clients_status.items():
                if 'auto_start' not in client_info:
                    client_info['auto_start'] = False
        
        return JSONResponse(content={
            "success": True,
            "clients": clients_status
        })
    except Exception as e:
        logger.error(f"获取客户端状态失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"获取客户端状态失败: {str(e)}"
        }, status_code=500)


@router.post("")
async def add_client(request: Request):
    """
    添加新客户端
    
    支持用户客户端和机器人客户端
    """
    try:
        data = await request.json()
        client_id = data.get('client_id')
        client_type = data.get('client_type')
        
        if not client_id or not client_type:
            return JSONResponse(content={
                "success": False,
                "message": "客户端ID和类型不能为空"
            }, status_code=400)
        
        if client_type not in ['user', 'bot']:
            return JSONResponse(content={
                "success": False,
                "message": "客户端类型必须是 user 或 bot"
            }, status_code=400)
        
        # 验证机器人客户端必需字段
        if client_type == 'bot':
            bot_token = data.get('bot_token')
            admin_user_id = data.get('admin_user_id')
            
            if not bot_token:
                return JSONResponse(content={
                    "success": False,
                    "message": "机器人客户端必须提供Bot Token"
                }, status_code=400)
            
            if not admin_user_id:
                return JSONResponse(content={
                    "success": False,
                    "message": "机器人客户端必须提供管理员用户ID"
                }, status_code=400)
            
            # Bot 客户端的 API_ID 和 API_HASH 是可选的（可以使用全局配置）
            # 但如果提供了，必须同时提供
            api_id = data.get('api_id')
            api_hash = data.get('api_hash')
            if (api_id and not api_hash) or (api_hash and not api_id):
                return JSONResponse(content={
                    "success": False,
                    "message": "API ID 和 API Hash 必须同时提供或同时留空"
                }, status_code=400)
        
        # 验证用户客户端必需字段
        elif client_type == 'user':
            api_id = data.get('api_id')
            api_hash = data.get('api_hash')
            phone = data.get('phone')
            
            if not api_id:
                return JSONResponse(content={
                    "success": False,
                    "message": "用户客户端必须提供API ID"
                }, status_code=400)
            
            if not api_hash:
                return JSONResponse(content={
                    "success": False,
                    "message": "用户客户端必须提供API Hash"
                }, status_code=400)
            
            if not phone:
                return JSONResponse(content={
                    "success": False,
                    "message": "用户客户端必须提供手机号"
                }, status_code=400)
        
        enhanced_bot = get_enhanced_bot()
        if enhanced_bot:
            # 传递配置参数给客户端管理器
            client = enhanced_bot.multi_client_manager.add_client_with_config(
                client_id, 
                client_type,
                config_data=data  # 传递完整的配置数据
            )
            
            # 保存客户端到数据库
            try:
                from models import TelegramClient
                from database import get_db
                from sqlalchemy import select
                
                logger.info(f"🔍 准备保存客户端到数据库:")
                logger.info(f"   - client_id: {client_id}")
                logger.info(f"   - client_type: {client_type}")
                logger.info(f"   - api_id: {data.get('api_id')}")
                logger.info(f"   - api_hash: {'***' if data.get('api_hash') else None}")
                logger.info(f"   - phone: {data.get('phone')}")
                
                async for db in get_db():
                    # 检查是否已存在
                    result = await db.execute(
                        select(TelegramClient).where(TelegramClient.client_id == client_id)
                    )
                    db_client = result.scalar_one_or_none()
                    
                    if not db_client:
                        # 创建新记录
                        db_client = TelegramClient(
                            client_id=client_id,
                            client_type=client_type,
                            api_id=data.get('api_id'),  # 用户和Bot客户端都可以有api_id
                            api_hash=data.get('api_hash'),  # 用户和Bot客户端都可以有api_hash
                            phone=data.get('phone') if client_type == 'user' else None,
                            bot_token=data.get('bot_token') if client_type == 'bot' else None,
                            admin_user_id=data.get('admin_user_id') if client_type == 'bot' else None,
                            auto_start=False  # 默认不自动启动
                        )
                        db.add(db_client)
                        await db.commit()
                        logger.info(f"✅ 客户端 {client_id} 已保存到数据库")
                    else:
                        logger.info(f"💡 客户端 {client_id} 已存在，跳过保存")
                    break
            except Exception as db_error:
                logger.error(f"❌ 保存客户端到数据库失败: {db_error}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 如果是用户客户端，需要验证码登录流程
            if client_type == 'user':
                return JSONResponse(content={
                    "success": True,
                    "message": f"用户客户端 {client_id} 添加成功，请准备接收验证码",
                    "need_verification": True,
                    "client_id": client_id
                })
            else:
                return JSONResponse(content={
                    "success": True,
                    "message": f"机器人客户端 {client_id} 添加成功"
                })
        else:
            return JSONResponse(content={
                "success": False,
                "message": "增强版客户端管理器不可用"
            }, status_code=400)
    except Exception as e:
        logger.error(f"添加客户端失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"添加客户端失败: {str(e)}"
        }, status_code=500)


@router.post("/{client_id}/start")
async def start_client(client_id: str):
    """启动客户端"""
    try:
        enhanced_bot = get_enhanced_bot()
        if not enhanced_bot:
            return JSONResponse(content={
                "success": False,
                "message": "增强版客户端管理器不可用"
            }, status_code=400)
        
        # 如果客户端不在内存中，先从数据库加载
        if client_id not in enhanced_bot.multi_client_manager.clients:
            logger.info(f"客户端 {client_id} 不在内存中，尝试从数据库加载...")
            try:
                client = await _load_runtime_client(enhanced_bot, client_id)
                if not client:
                    return JSONResponse(content={
                        "success": False,
                        "message": f"客户端 {client_id} 不存在"
                    }, status_code=404)
            except Exception as load_error:
                logger.error(f"从数据库加载客户端失败: {load_error}")
                return JSONResponse(content={
                    "success": False,
                    "message": f"加载客户端配置失败: {str(load_error)}"
                }, status_code=500)
        
        # 启动前关闭未完成的临时登录连接，避免两个事件循环争用 session。
        client = enhanced_bot.multi_client_manager.get_client(client_id)
        if client and client.login_state in {'waiting_code', 'waiting_password'}:
            await client._reset_login_state()

        # 启动客户端
        success = enhanced_bot.multi_client_manager.start_client(client_id)
        if success:
            return JSONResponse(content={
                "success": True,
                "message": f"客户端 {client_id} 启动成功"
            })
        else:
            # 获取更详细的错误信息
            client = enhanced_bot.multi_client_manager.get_client(client_id)
            if client and hasattr(client, 'last_error'):
                error_msg = client.last_error
            else:
                error_msg = "启动失败，请查看日志获取详细信息"
            
            return JSONResponse(content={
                "success": False,
                "message": f"客户端 {client_id} 启动失败: {error_msg}"
            }, status_code=400)
            
    except Exception as e:
        logger.error(f"启动客户端失败: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content={
            "success": False,
            "message": f"启动客户端失败: {str(e)}"
        }, status_code=500)


@router.post("/{client_id}/stop")
async def stop_client(client_id: str):
    """停止客户端"""
    try:
        enhanced_bot = get_enhanced_bot()
        if enhanced_bot:
            success = enhanced_bot.multi_client_manager.stop_client(client_id)
            if success:
                return JSONResponse(content={
                    "success": True,
                    "message": f"客户端 {client_id} 停止成功"
                })
            else:
                return JSONResponse(content={
                    "success": False,
                    "message": f"客户端 {client_id} 不存在或已停止"
                }, status_code=400)
        else:
            return JSONResponse(content={
                "success": False,
                "message": "增强版客户端管理器不可用"
            }, status_code=400)
    except Exception as e:
        logger.error(f"停止客户端失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"停止客户端失败: {str(e)}"
        }, status_code=500)


@router.delete("/{client_id}")
async def remove_client(client_id: str):
    """删除客户端（包括 session 文件）"""
    try:
        enhanced_bot = get_enhanced_bot()
        if not enhanced_bot:
            return JSONResponse(content={
                "success": False,
                "message": "增强版客户端管理器不可用"
            }, status_code=400)
        
        # 获取客户端类型（用于删除 session 文件）
        client_type = None
        try:
            from models import TelegramClient
            from database import get_db
            from sqlalchemy import select
            
            async for db in get_db():
                result = await db.execute(
                    select(TelegramClient).where(TelegramClient.client_id == client_id)
                )
                db_client = result.scalar_one_or_none()
                
                if db_client:
                    client_type = db_client.client_type
                break
        except Exception as e:
            logger.warning(f"查询客户端类型失败: {e}")
        
        # 从内存中移除客户端（会自动删除 session 文件）
        # 如果客户端不在内存中，force_delete_session=True 会强制删除 session 文件
        memory_removed = enhanced_bot.multi_client_manager.remove_client(
            client_id, 
            force_delete_session=True  # 删除时始终清理 session 文件
        )
        
        # 从数据库删除
        db_deleted = False
        try:
            from models import TelegramClient
            from database import get_db
            from sqlalchemy import select
            
            async for db in get_db():
                result = await db.execute(
                    select(TelegramClient).where(TelegramClient.client_id == client_id)
                )
                db_client = result.scalar_one_or_none()
                
                if db_client:
                    await db.delete(db_client)
                    await db.commit()
                    logger.info(f"✅ 从数据库删除客户端: {client_id}")
                    db_deleted = True
                break
        except Exception as db_error:
            logger.warning(f"从数据库删除客户端失败（可能不存在）: {db_error}")
        
        if memory_removed or db_deleted:
            return JSONResponse(content={
                "success": True,
                "message": f"客户端 {client_id} 删除成功（包括 session 文件）"
            })
        else:
            return JSONResponse(content={
                "success": False,
                "message": f"客户端 {client_id} 不存在"
            }, status_code=404)
            
    except Exception as e:
        logger.error(f"删除客户端失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"删除客户端失败: {str(e)}"
        }, status_code=500)


@router.post("/{client_id}/auto-start")
async def toggle_auto_start(client_id: str, request: Request):
    """
    切换客户端自动启动状态
    
    保存到数据库，下次启动时自动加载
    """
    try:
        data = await request.json()
        auto_start = data.get('auto_start', False)
        
        # 更新数据库
        from models import TelegramClient
        from database import get_db
        from sqlalchemy import select
        from config import Config
        
        async for db in get_db():
            result = await db.execute(
                select(TelegramClient).where(TelegramClient.client_id == client_id)
            )
            db_client = result.scalar_one_or_none()
            
            if not db_client:
                # 如果客户端不存在，创建默认记录
                logger.info(f"💡 客户端 {client_id} 不存在，创建默认记录")
                
                # 获取客户端类型和配置
                enhanced_bot = get_enhanced_bot()
                client_type = 'user'  # 默认类型
                api_id = None
                api_hash = None
                phone = None
                bot_token = None
                admin_user_id = None
                
                if enhanced_bot and enhanced_bot.multi_client_manager:
                    if client_id in enhanced_bot.multi_client_manager.clients:
                        client_wrapper = enhanced_bot.multi_client_manager.clients[client_id]
                        client_type = client_wrapper.client_type
                        
                        # 从运行时客户端获取实际配置
                        if client_type == 'user':
                            api_id = client_wrapper.api_id or Config.API_ID
                            api_hash = client_wrapper.api_hash or Config.API_HASH
                            phone = client_wrapper.phone or Config.PHONE_NUMBER
                        elif client_type == 'bot':
                            bot_token = client_wrapper.bot_token or Config.BOT_TOKEN
                            admin_user_id = client_wrapper.admin_user_id
                
                db_client = TelegramClient(
                    client_id=client_id,
                    client_type=client_type,
                    api_id=api_id,
                    api_hash=api_hash,
                    phone=phone,
                    bot_token=bot_token,
                    admin_user_id=admin_user_id,
                    auto_start=auto_start
                )
                db.add(db_client)
            else:
                # 更新现有记录
                db_client.auto_start = auto_start
            
            await db.commit()
            break
        
        logger.info(f"✅ 客户端 {client_id} 自动启动状态已更新: {auto_start}")
        
        return JSONResponse(content={
            "success": True,
            "message": f"客户端 {client_id} 自动启动已{'开启' if auto_start else '关闭'}",
            "auto_start": auto_start
        })
        
    except Exception as e:
        logger.error(f"切换自动启动状态失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"切换自动启动状态失败: {str(e)}"
        }, status_code=500)


@router.post("/{client_id}/login")
async def login_client(client_id: str, request: Request):
    """
    用户客户端登录
    
    支持完整的登录流程：
    - step: 'send_code' - 发送验证码
    - step: 'submit_code' - 提交验证码
    - step: 'submit_password' - 提交二步验证密码
    """
    try:
        data = await request.json()
        step = data.get('step')
        code = data.get('code')
        password = data.get('password')
        
        enhanced_bot = get_enhanced_bot()
        if not enhanced_bot:
            return JSONResponse(content={
                "success": False,
                "message": "增强版客户端管理器不可用"
            }, status_code=400)
        
        # 重启后未自动启动的客户端也必须能直接进入登录流程。
        client_wrapper = await _load_runtime_client(enhanced_bot, client_id)
        if not client_wrapper:
            return JSONResponse(content={
                "success": False,
                "message": f"客户端 {client_id} 不存在"
            }, status_code=404)
        
        try:
            await asyncio.wait_for(client_wrapper.login_lock.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            return JSONResponse(content={
                "success": False,
                "message": "登录操作正在进行，请勿重复提交",
                "error_type": "login_in_progress",
            }, status_code=409)

        try:
            if step == 'send_code':
                result = await client_wrapper.send_verification_code()
                return JSONResponse(content=result)

            if step == 'submit_code':
                if not code:
                    return JSONResponse(content={
                        "success": False,
                        "message": "请提供验证码"
                    }, status_code=400)

                result = await client_wrapper.submit_verification_code(code)
                return JSONResponse(content=result)

            if step == 'submit_password':
                if not password:
                    return JSONResponse(content={
                        "success": False,
                        "message": "请提供密码"
                    }, status_code=400)

                result = await client_wrapper.submit_password(password)
                return JSONResponse(content=result)

            return JSONResponse(content={
                "success": False,
                "message": "无效的登录步骤"
            }, status_code=400)
        finally:
            client_wrapper.login_lock.release()
        
    except Exception as e:
        logger.error(f"客户端登录失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"登录失败: {str(e)}"
        }, status_code=500)


"""
✅ 所有7个端点已完成!

- GET /api/clients - 获取所有客户端状态
- POST /api/clients - 添加新客户端
- POST /api/clients/{client_id}/start - 启动客户端
- POST /api/clients/{client_id}/stop - 停止客户端
- DELETE /api/clients/{client_id} - 删除客户端
- POST /api/clients/{client_id}/auto-start - 切换自动启动
- POST /api/clients/{client_id}/login - 客户端登录
"""
