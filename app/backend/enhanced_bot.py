#!/usr/bin/env python3
"""
增强版Telegram消息转发机器人 - 修复实时监听问题
"""
import asyncio
import logging
import signal
import sys
from typing import Dict, Any
from pathlib import Path

from telegram_client_manager import MultiClientManager, multi_client_manager
from config import Config, validate_config
from database import init_database
from utils import setup_logging

class EnhancedTelegramBot:
    """
    增强版Telegram机器人
    
    核心修复:
    1. 独立事件循环: 每个Telegram客户端运行在独立的线程和事件循环中
    2. 直接使用run_until_disconnected: 不包装在任务中，让其自然管理事件循环
    3. 装饰器事件处理: 使用@client.on(events.NewMessage)替代add_event_handler
    4. 异步任务隔离: 消息转发处理在独立任务中进行，避免阻塞事件监听
    """
    
    def __init__(self):
        from log_manager import get_logger
        self.logger = get_logger('enhanced_bot', 'enhanced_bot.log')
        self.multi_client_manager = multi_client_manager
        self.running = False
        
        # 状态回调
        self.status_callbacks = []
        
        
    def add_status_callback(self, callback):
        """添加状态变化回调"""
        self.status_callbacks.append(callback)
    
    def _notify_status_change(self, client_id: str, status: str, data: Dict[str, Any]):
        """处理客户端状态变化"""
        self.logger.info(f"客户端 {client_id} 状态变化: {status}")
        
        # 通知所有回调
        for callback in self.status_callbacks:
            try:
                callback(client_id, status, data)
            except Exception as e:
                self.logger.error(f"状态回调执行失败: {e}")
    
    async def _auto_start_clients(self):
        """自动启动设置了auto_start=True的客户端"""
        try:
            from models import TelegramClient
            from database import get_db
            from sqlalchemy import select
            
            async for db in get_db():
                # 查询所有启用自动启动的客户端
                result = await db.execute(
                    select(TelegramClient).where(
                        TelegramClient.auto_start == True,
                        TelegramClient.is_active == True
                    )
                )
                auto_start_clients = result.scalars().all()
                
                if auto_start_clients:
                    self.logger.info(f"🔄 发现 {len(auto_start_clients)} 个需要自动启动的客户端")
                    
                    for db_client in auto_start_clients:
                        try:
                            self.logger.info(f"🔍 准备自动启动客户端: {db_client.client_id} ({db_client.client_type})")
                            self.logger.info(f"   - DB API ID: {db_client.api_id}")
                            self.logger.info(f"   - DB API Hash: {'***' if db_client.api_hash else None}")
                            self.logger.info(f"   - DB Phone: {db_client.phone}")
                            
                            # 准备配置数据
                            config_data = {}
                            if db_client.client_type == 'bot':
                                config_data = {
                                    'bot_token': db_client.bot_token,
                                    'admin_user_id': db_client.admin_user_id
                                }
                            elif db_client.client_type == 'user':
                                # 使用数据库中的配置，如果为空则使用全局配置
                                config_data = {
                                    'api_id': db_client.api_id or Config.API_ID,
                                    'api_hash': db_client.api_hash or Config.API_HASH,
                                    'phone': db_client.phone or Config.PHONE_NUMBER
                                }
                            
                            self.logger.info(f"   - Config data: api_id={config_data.get('api_id', 'N/A')}, has_hash={bool(config_data.get('api_hash'))}")
                            
                            # 添加到运行时管理器
                            client = self.multi_client_manager.add_client_with_config(
                                db_client.client_id,
                                db_client.client_type,
                                config_data=config_data
                            )
                            client.add_status_callback(self._notify_status_change)
                            
                            # 启动客户端
                            client.start()
                            self.logger.info(f"✅ 自动启动客户端: {db_client.client_id} ({db_client.client_type})")
                            
                        except Exception as client_error:
                            self.logger.error(f"❌ 自动启动客户端 {db_client.client_id} 失败: {client_error}")
                else:
                    self.logger.info("💡 没有设置自动启动的客户端")
                break
                
        except Exception as e:
            self.logger.error(f"❌ 自动启动客户端失败: {e}")
    
    # 【已移除】传统客户端自动迁移功能
    # 所有客户端现在都应该通过 Web UI 手动创建
    # 这样可以避免意外创建不需要的客户端（如 main_user, main_bot）
    async def _auto_fix_database_records(self):
        """检查数据库记录完整性（不自动创建客户端）"""
        try:
            from database import get_db
            from models import TelegramClient
            from sqlalchemy import select
            
            async for db in get_db():
                self.logger.info("🔧 检查数据库记录...")
                
                # 仅查询现有客户端数量，不做任何修改
                result = await db.execute(select(TelegramClient))
                clients = result.scalars().all()
                
                if clients:
                    self.logger.info(f"📊 数据库中存在 {len(clients)} 个客户端配置")
                    for client in clients:
                        self.logger.debug(f"   - {client.client_id} ({client.client_type})")
                else:
                    self.logger.info("💡 数据库中暂无客户端配置，请通过 Web 界面添加")
                
                self.logger.info("✅ 数据库记录检查完成")
                break
                
        except Exception as fix_error:
            self.logger.error(f"❌ 数据库检查失败: {fix_error}")
            self.logger.info("💡 建议手动检查数据库或运行: python reset_database.py")
    
    async def _verify_and_fix_database(self):
        """验证数据库完整性（仅记录现有客户端）"""
        try:
            from sqlalchemy import select
            from database import get_db
            from models import TelegramClient
            
            async for db in get_db():
                # 仅记录现有客户端，不做任何自动创建或修复
                result = await db.execute(select(TelegramClient))
                clients = result.scalars().all()
                
                if clients:
                    client_list = [f"{c.client_id} ({c.client_type})" for c in clients]
                    self.logger.info(f"📊 数据库中存在 {len(clients)} 个客户端: {', '.join(client_list)}")
                else:
                    self.logger.info("📝 数据库中暂无客户端配置，请通过 Web 界面添加")
                
                break
                
        except Exception as e:
            self.logger.warning(f"⚠️ 数据库完整性验证失败: {e}")
    
    async def start(self, web_mode: bool = False, skip_config_validation: bool = False):
        """启动机器人"""
        try:
            self.logger.info("🚀 启动增强版Telegram消息转发机器人")
            
            # 验证配置（Web模式下可以跳过）
            if not skip_config_validation:
                try:
                    validate_config()
                    self.logger.info("✅ 配置验证通过")
                except ValueError as config_error:
                    if web_mode:
                        self.logger.warning(f"⚠️ 配置未完整，将以Web-only模式启动: {config_error}")
                        self.logger.info("🌐 启动Web界面进行配置...")
                        return  # 跳过Telegram客户端启动，仅启动Web服务
                    else:
                        raise  # 非Web模式时仍然抛出配置错误
            else:
                self.logger.info("⏭️ 跳过配置验证（Web-only模式）")
            
            # 创建目录
            Config.create_directories()
            
            # 初始化数据库
            await init_database()
            self.logger.info("✅ 数据库初始化完成")
            
            # 验证数据完整性并自动修复
            await self._verify_and_fix_database()
            
            # 自动启动设置了auto_start=True的客户端
            await self._auto_start_clients()
            
            # 客户端启动完全由自动启动逻辑控制
            # 不再无条件启动客户端，避免绕过auto_start设置
            self.logger.info("✅ 客户端启动已由自动启动逻辑控制")
            
            self.running = True
            
            if web_mode:
                self.logger.info("🌐 Web模式启动完成，客户端将在后台运行")
                return True
            else:
                # 等待信号
                await self._wait_for_signal()
                
        except Exception as e:
            self.logger.error(f"启动失败: {e}")
            raise
    
    async def stop(self):
        """停止机器人"""
        self.logger.info("🛑 停止机器人...")
        
        self.running = False
        
        # 停止所有客户端
        self.multi_client_manager.stop_all()
        
        self.logger.info("✅ 机器人已停止")
    
    async def _wait_for_signal(self):
        """等待停止信号"""
        def signal_handler(signum, frame):
            self.logger.info(f"收到信号 {signum}，准备停止...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await self.stop()
    
    def get_client_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有客户端状态"""
        return self.multi_client_manager.get_all_status()
    
    def refresh_monitored_chats(self):
        """刷新所有客户端的监听聊天列表"""
        for client_id, client in self.multi_client_manager.clients.items():
            try:
                asyncio.create_task(client.refresh_monitored_chats())
            except Exception as e:
                self.logger.error(f"刷新客户端 {client_id} 监听聊天失败: {e}")
    
    def get_login_status(self) -> Dict[str, Any]:
        """获取登录状态（兼容原有接口）"""
        user_client = self.multi_client_manager.get_client("main_user")
        if not user_client:
            return {
                "success": False,
                "logged_in": False,
                "message": "用户客户端不存在"
            }
        
        status = user_client.get_status()
        return {
            "success": status["running"],
            "logged_in": status["connected"],
            "message": "已连接" if status["connected"] else "未连接",
            "user": status["user_info"]
        }
    
    def cache_chat_list_for_web_sync(self) -> Dict[str, Any]:
        """缓存聊天列表（兼容原有接口）"""
        try:
            # 这里可以实现聊天列表缓存逻辑
            return {
                "success": True,
                "message": "聊天列表缓存成功"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"缓存失败: {str(e)}"
            }
    
    def get_chat_list_sync(self):
        """同步获取聊天列表（兼容原有接口）"""
        # 这里可以实现获取聊天列表的逻辑
        return []
    
async def main():
    """主函数"""
    bot = EnhancedTelegramBot()
    
    try:
        await bot.start(web_mode=False)
    except KeyboardInterrupt:
        await bot.stop()
    except Exception as e:
        logging.error(f"程序运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 设置日志 - 使用统一的日志轮转机制
    from log_manager import get_logger
    main_logger = get_logger('main', 'enhanced_bot.log')
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已停止")
    except Exception as e:
        print(f"程序启动失败: {e}")
        sys.exit(1)
