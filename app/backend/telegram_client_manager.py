#!/usr/bin/env python3
"""
Telegram客户端管理器 - 解决事件循环冲突的核心模块
"""
import asyncio
import threading
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserPrivacyRestrictedError
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from config import Config
from database import db_manager, get_db
from models import ForwardRule, get_local_now
from filters import KeywordFilter, RegexReplacer
from proxy_utils import get_proxy_manager
from log_manager import get_logger

logger = logging.getLogger(__name__)


class LoginErrorHandler:
    """统一处理 Telegram 登录错误"""
    
    @staticmethod
    def handle_error(error: Exception) -> Dict[str, Any]:
        """
        统一处理 Telegram 错误，返回友好的错误信息
        
        Args:
            error: Telegram 异常
            
        Returns:
            包含 success, message, error_type 的字典
        """
        try:
            from telethon.errors import (
                SessionPasswordNeededError,
                PhoneCodeInvalidError,
                PhoneCodeExpiredError,
                FloodWaitError,
                PhoneNumberInvalidError,
                PhoneNumberBannedError,
                PhoneNumberUnoccupiedError
            )
            
            if isinstance(error, SessionPasswordNeededError):
                return {
                    "success": True,  # 需要密码不算失败
                    "message": "需要输入二步验证密码",
                    "step": "waiting_password",
                    "error_type": "need_password"
                }
            elif isinstance(error, PhoneCodeInvalidError):
                return {
                    "success": False,
                    "message": "验证码错误，请检查后重新输入",
                    "error_type": "invalid_code"
                }
            elif isinstance(error, PhoneCodeExpiredError):
                return {
                    "success": False,
                    "message": "验证码已过期，请重新发送",
                    "error_type": "code_expired",
                    "should_resend": True
                }
            elif isinstance(error, FloodWaitError):
                wait_seconds = getattr(error, 'seconds', 60)
                wait_minutes = wait_seconds // 60
                if wait_minutes > 0:
                    time_text = f"{wait_minutes} 分钟"
                else:
                    time_text = f"{wait_seconds} 秒"
                return {
                    "success": False,
                    "message": f"操作过于频繁，请等待 {time_text} 后重试",
                    "error_type": "flood_wait",
                    "wait_seconds": wait_seconds
                }
            elif isinstance(error, PhoneNumberInvalidError):
                return {
                    "success": False,
                    "message": "手机号码格式错误，请使用国际格式（如：+8613800138000）",
                    "error_type": "invalid_phone"
                }
            elif isinstance(error, PhoneNumberBannedError):
                return {
                    "success": False,
                    "message": "该手机号码已被 Telegram 封禁，无法使用",
                    "error_type": "phone_banned"
                }
            elif isinstance(error, PhoneNumberUnoccupiedError):
                return {
                    "success": False,
                    "message": "该手机号码未注册 Telegram，请先注册",
                    "error_type": "phone_unregistered"
                }
            else:
                # 未知错误，返回原始错误信息
                error_msg = str(error)
                # 尝试从错误信息中提取有用信息
                if "timeout" in error_msg.lower():
                    return {
                        "success": False,
                        "message": "连接超时，请检查网络或代理设置",
                        "error_type": "timeout"
                    }
                elif "connection" in error_msg.lower():
                    return {
                        "success": False,
                        "message": "网络连接失败，请检查网络或代理设置",
                        "error_type": "connection_error"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"登录失败: {error_msg}",
                        "error_type": "unknown"
                    }
        except Exception as e:
            # 处理错误的过程中出错，返回最基本的错误信息
            return {
                "success": False,
                "message": f"发生未知错误: {str(error)}",
                "error_type": "unknown"
            }


def get_configured_timezone():
    """获取配置的时区对象"""
    try:
        import pytz
        import os
        tz_name = os.environ.get('TZ', 'Asia/Shanghai')
        
        if tz_name == 'UTC':
            return pytz.UTC
        else:
            try:
                return pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                logger.warning(f"未知时区 {tz_name}，使用 Asia/Shanghai")
                return pytz.timezone('Asia/Shanghai')
    except ImportError:
        logger.warning("pytz 不可用，使用 UTC 时区")
        return timezone.utc

def get_current_time():
    """获取当前配置时区的时间"""
    try:
        import pytz
        import os
        tz_name = os.environ.get('TZ', 'Asia/Shanghai')
        
        if tz_name == 'UTC':
            return datetime.now(pytz.UTC)
        else:
            try:
                tz = pytz.timezone(tz_name)
                return datetime.now(tz)
            except pytz.UnknownTimeZoneError:
                logger.warning(f"未知时区 {tz_name}，使用 Asia/Shanghai")
                tz = pytz.timezone('Asia/Shanghai')
                return datetime.now(tz)
    except ImportError:
        logger.warning("pytz 不可用，使用系统本地时间")
        return datetime.now()

def ensure_timezone(dt):
    """确保datetime对象有时区信息"""
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # 如果没有时区信息，假设是配置的时区
        configured_tz = get_configured_timezone()
        return configured_tz.localize(dt)
    
    return dt

class TelegramClientManager:
    """
    Telegram客户端管理器
    
    核心修复:
    1. 每个客户端运行在独立线程中
    2. 使用装饰器事件处理避免add_event_handler
    3. 直接使用run_until_disconnected，不包装在任务中
    4. 异步任务隔离，避免阻塞事件监听
    """
    
    def __init__(self, client_id: str, client_type: str = "user"):
        self.client_id = client_id
        self.client_type = client_type  # "user" or "bot"
        self.client: Optional[TelegramClient] = None
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.running = False
        self.connected = False
        self.user_info = None
        
        # 客户端配置
        # 机器人客户端配置
        self.bot_token: Optional[str] = None
        self.admin_user_id: Optional[str] = None
        
        # 用户客户端配置
        self.api_id: Optional[str] = None
        self.api_hash: Optional[str] = None
        self.phone: Optional[str] = None
        
        # 注意：bot 客户端也可以有独立的 api_id 和 api_hash
        # 如果 bot 客户端没有配置，则使用全局配置
        
        # 消息处理
        self.keyword_filter = KeywordFilter()
        self.regex_replacer = RegexReplacer()
        self.monitored_chats = set()
        self.history_backfills = set()
        
        # 状态回调
        self.status_callbacks: List[Callable] = []
        
        # 错误信息（供 API 使用）
        self.last_error: Optional[str] = None
        
        # 登录流程状态
        self.login_session = None
        self.login_state = "idle"  # idle, waiting_code, waiting_password, completed
        self.login_lock = asyncio.Lock()
        self.last_code_sent_time = None  # 上次发送验证码的时间
        self.code_cooldown_seconds = 60   # 验证码发送冷却时间（秒）
        
        # 日志队列 - 用于备份失败的日志记录（在运行时初始化）
        self.failed_log_queue = None
        self.log_retry_task = None
        
        # 日志 - 使用统一的日志管理器，消息转发日志会写入 enhanced_bot.log
        self.logger = get_logger(f"client.{client_id}", "enhanced_bot.log")
    
    def add_status_callback(self, callback: Callable):
        """添加状态变化回调"""
        self.status_callbacks.append(callback)
    
    async def _dispose_login_client(self):
        """Close the temporary login client and release its SQLite session."""
        client = self.client
        self.client = None
        if not client:
            return

        try:
            await client.disconnect()
        except Exception as e:
            self.logger.warning(f"断开登录客户端失败: {e}")

        try:
            session = getattr(client, 'session', None)
            if session:
                session.close()
        except Exception as e:
            self.logger.warning(f"关闭登录 session 失败: {e}")

        self.connected = False

    async def _reset_login_state(self):
        """
        重置登录状态
        
        在登录失败或取消登录时调用，确保状态完全清理
        """
        self.login_state = "idle"
        self.login_session = None
        
        if not self.running:
            await self._dispose_login_client()
    
    def _notify_status_change(self, status: str, data: Dict[str, Any] = None):
        """通知状态变化"""
        for callback in self.status_callbacks:
            try:
                callback(self.client_id, status, data or {})
            except Exception as e:
                self.logger.error(f"状态回调执行失败: {e}")
    
    def start(self) -> bool:
        """启动客户端（在独立线程中）"""
        if self.running:
            self.logger.warning("客户端已在运行中")
            return True
        
        try:
            self.thread = threading.Thread(
                target=self._run_client_thread,
                name=f"TelegramClient-{self.client_id}",
                daemon=True
            )
            self.thread.start()
            
            # 等待启动完成
            max_wait = 30  # 30秒超时
            start_time = time.time()
            while not self.running and (time.time() - start_time) < max_wait:
                time.sleep(0.1)
            
            if self.running:
                self.logger.info(f"✅ 客户端 {self.client_id} 启动成功")
                return True
            else:
                self.logger.error(f"❌ 客户端 {self.client_id} 启动超时")
                return False
                
        except Exception as e:
            self.logger.error(f"启动客户端失败: {e}")
            return False
    
    def stop(self):
        """停止客户端"""
        if not self.running:
            return
        
        self.running = False
        
        if self.loop and self.client:
            # 在客户端的事件循环中执行断开连接
            try:
                # 创建一个异步函数来断开连接
                async def disconnect_client():
                    if self.client.is_connected():
                        await self.client.disconnect()
                
                future = asyncio.run_coroutine_threadsafe(
                    disconnect_client(), 
                    self.loop
                )
                future.result(timeout=5)  # 等待最多5秒
            except Exception as e:
                self.logger.warning(f"停止客户端时出错: {e}")
        
        if self.thread:
            self.thread.join(timeout=10)
        
        self.logger.info(f"✅ 客户端 {self.client_id} 已停止")
    
    def _run_client_thread(self):
        """在独立线程中运行客户端"""
        try:
            # 创建独立的事件循环
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # 运行客户端
            self.loop.run_until_complete(self._run_client())
            
        except Exception as e:
            self.logger.error(f"客户端线程运行失败: {e}")
            self._notify_status_change("error", {"error": str(e)})
        finally:
            if self.loop:
                self.loop.close()
            self.running = False
            self.connected = False
    
    async def _run_client(self):
        """运行客户端主逻辑"""
        try:
            # 初始化日志队列（在事件循环中）
            self.failed_log_queue = asyncio.Queue(maxsize=1000)
            
            # 丢弃上一次失败后残留的临时 client，避免重复打开 session。
            if self.client and not self.running:
                await self._dispose_login_client()

            await self._create_client()
            
            if not self.client:
                raise Exception("客户端创建失败")
            
            # 启动客户端
            try:
                if self.client_type == "bot":
                    bot_token = self.bot_token or Config.BOT_TOKEN
                    await self.client.start(bot_token=bot_token)
                else:
                    # 【优化】用户客户端启动逻辑：
                    # - 如果已有 session 且已授权，可以正常启动
                    # - 如果没有 session 或未授权，阻止命令行登录，引导使用 Web 界面
                    self.logger.info(f"📞 正在连接到 Telegram 服务器...")
                    
                    # 先连接（不登录）
                    await self.client.connect()
                    
                    # 检查是否已授权
                    if not await self.client.is_user_authorized():
                        self.logger.error("❌ 用户客户端未登录，请通过 Web 界面完成登录")
                        await self.client.disconnect()
                        raise Exception("用户客户端需要通过 Web 界面登录，不能在命令行环境中启动")
                    
                    # 已授权，正常启动（不会触发命令行输入）
                    self.logger.info(f"✅ 用户客户端已授权，使用现有 session 启动")
            except Exception as start_error:
                error_msg = str(start_error)
                if "database is locked" in error_msg:
                    self.logger.warning(f"⚠️ Session 文件被锁定，尝试自动修复...")
                    
                    # 尝试自动修复：清理锁定的 session 文件
                    try:
                        import sqlite3
                        import time
                        import gc
                        session_path = Path(Config.SESSIONS_DIR) / f"{self.client_type}_{self.client_id}.session"
                        
                        if session_path.exists():
                            self.logger.info("   ├─ 📂 Session文件存在，开始清理锁定...")
                            
                            # 第1步：断开当前连接（如果有）
                            if hasattr(self, 'client') and self.client:
                                try:
                                    await self.client.disconnect()
                                    self.client = None
                                    self.logger.info("   ├─ 🔌 已断开旧连接")
                                except Exception as e:
                                    self.logger.debug(f"   ├─ 断开连接异常: {e}")
                            
                            # 等待连接完全释放
                            await asyncio.sleep(0.5)
                            gc.collect()  # 强制垃圾回收
                            
                            # 第2步：强制删除 WAL 和 SHM 文件
                            wal_file = session_path.with_suffix('.session-wal')
                            shm_file = session_path.with_suffix('.session-shm')
                            
                            for file, name in [(wal_file, 'WAL'), (shm_file, 'SHM')]:
                                if file.exists():
                                    try:
                                        file.unlink()
                                        self.logger.info(f"   ├─ 🗑️ 删除 {name} 文件")
                                    except Exception as e:
                                        self.logger.warning(f"   ├─ ⚠️ 删除{name}失败: {e}")
                            
                            # 第3步：尝试打开数据库并清除WAL模式
                            try:
                                conn = sqlite3.connect(str(session_path), timeout=10.0, check_same_thread=False)
                                conn.execute("PRAGMA journal_mode=DELETE")
                                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                                conn.commit()
                                conn.close()
                                self.logger.info("   ├─ ✅ Session 文件锁定已清除")
                            except Exception as db_error:
                                self.logger.warning(f"   ├─ ⚠️ 无法清除数据库锁: {db_error}")
                                # 如果还是锁定，尝试最后一招：复制session文件
                                try:
                                    import shutil
                                    backup_path = session_path.with_suffix('.session.backup')
                                    temp_path = session_path.with_suffix('.session.tmp')
                                    
                                    # 复制到临时文件
                                    shutil.copy2(session_path, temp_path)
                                    # 删除原文件
                                    session_path.unlink()
                                    # 重命名回来
                                    temp_path.rename(session_path)
                                    self.logger.info("   ├─ ✅ 使用复制方式清除锁定")
                                except Exception as copy_error:
                                    self.logger.error(f"   ├─ ❌ 复制方式也失败: {copy_error}")
                            
                            # 等待文件系统同步
                            await asyncio.sleep(1.0)
                            
                            # 第4步：重新创建客户端
                            self.logger.info("   ├─ 🔄 重新创建客户端...")
                            await self._create_client()
                            
                            # 第5步：重试启动
                            self.logger.info("   └─ 🔄 重试启动客户端...")
                            await self.client.start()
                            self.logger.info("   └─ ✅ 客户端启动成功（锁定已修复）")
                    except Exception as fix_error:
                        fix_error_msg = str(fix_error)
                        self.logger.error(f"❌ 自动修复失败: {fix_error}")
                        
                        # 如果还是锁定错误，说明无法自动修复
                        if "database is locked" in fix_error_msg:
                            self.logger.error("💡 Session 文件持续被锁定，建议手动解决:")
                            self.logger.error("   1. 停止所有使用此 session 的进程")
                            self.logger.error("   2. 重启 Docker 容器")
                            self.logger.error("   3. 如果问题持续，删除 session 文件并重新登录")
                            # 不抛出异常，让客户端保持"已停止"状态，用户可以手动重试
                            return
                        else:
                            raise Exception(f"Session 文件被锁定且无法自动修复: {error_msg}")
                elif "Server closed the connection" in error_msg or "0 bytes read" in error_msg:
                    self.logger.error(f"❌ Telegram 服务器连接失败: {error_msg}")
                    self.logger.error("💡 可能的解决方案:")
                    self.logger.error("   1. 检查网络连接是否正常")
                    self.logger.error("   2. 检查系统设置中的代理配置是否正确（如果需要代理）")
                    self.logger.error("   3. 尝试删除 session 文件后重新登录")
                    self.logger.error("   4. 稍后再试，可能是 Telegram 服务器暂时不可用")
                    raise Exception(f"Telegram 服务器连接失败，请检查网络和代理设置: {error_msg}")
                else:
                    raise
            
            # 获取用户信息
            self.user_info = await self.client.get_me()
            self.connected = True
            self.running = True
            
            self.logger.info(f"✅ {self.client_type} 客户端已连接: {getattr(self.user_info, 'username', '') or getattr(self.user_info, 'first_name', 'Unknown')}")
            self._notify_status_change("connected", {
                "user_info": {
                    "id": self.user_info.id,
                    "username": getattr(self.user_info, 'username', ''),
                    "first_name": getattr(self.user_info, 'first_name', ''),
                    "phone": getattr(self.user_info, 'phone', '')
                }
            })
            
            # 保存客户端配置到数据库（包含连接时间）
            await self._save_client_config()
            
            # 注册事件处理器（使用装饰器方式）
            self._register_event_handlers()
            
            # 更新监听聊天列表
            await self._update_monitored_chats()
            asyncio.create_task(self._backfill_time_filtered_rules())
            
            # 关键修复：直接使用run_until_disconnected，不包装在任务中
            self.logger.info(f"🎯 开始监听消息...")
            await self.client.run_until_disconnected()
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"客户端运行失败: {error_msg}")
            
            # 保存错误信息供 API 使用
            self.last_error = error_msg
            
            self._notify_status_change("error", {"error": error_msg})
            raise
        finally:
            self.running = False
            self.connected = False
            self._notify_status_change("disconnected", {})
    
    async def _update_last_connected(self):
        """更新数据库中的最后连接时间"""
        try:
            from models import TelegramClient
            from database import get_db
            from sqlalchemy import select
            from datetime import datetime
            
            async for db in get_db():
                result = await db.execute(
                    select(TelegramClient).where(TelegramClient.client_id == self.client_id)
                )
                db_client = result.scalar_one_or_none()
                
                if db_client:
                    db_client.last_connected = datetime.now()
                    await db.commit()
                    self.logger.debug(f"✅ 已更新客户端 {self.client_id} 的最后连接时间")
                break
        except Exception as e:
            self.logger.warning(f"更新最后连接时间失败（不影响运行）: {e}")
    
    async def _save_client_config(self):
        """保存或更新客户端配置到数据库"""
        try:
            from models import TelegramClient
            from database import get_db
            from sqlalchemy import select
            from datetime import datetime
            
            async for db in get_db():
                result = await db.execute(
                    select(TelegramClient).where(TelegramClient.client_id == self.client_id)
                )
                db_client = result.scalar_one_or_none()
                
                if db_client:
                    # 更新现有记录
                    if self.client_type == 'user':
                        if self.api_id:
                            db_client.api_id = str(self.api_id)
                        if self.api_hash:
                            db_client.api_hash = self.api_hash
                        if self.phone:
                            db_client.phone = self.phone
                    elif self.client_type == 'bot':
                        if self.bot_token:
                            db_client.bot_token = self.bot_token
                        if self.admin_user_id:
                            db_client.admin_user_id = self.admin_user_id
                    
                    db_client.last_connected = datetime.now()
                    await db.commit()
                    self.logger.info(f"✅ 已更新客户端 {self.client_id} 的配置到数据库")
                else:
                    # 创建新记录
                    new_client = TelegramClient(
                        client_id=self.client_id,
                        client_type=self.client_type,
                        api_id=str(self.api_id) if self.api_id and self.client_type == 'user' else None,
                        api_hash=self.api_hash if self.api_hash and self.client_type == 'user' else None,
                        phone=self.phone if self.phone and self.client_type == 'user' else None,
                        bot_token=self.bot_token if self.bot_token and self.client_type == 'bot' else None,
                        admin_user_id=self.admin_user_id if self.admin_user_id and self.client_type == 'bot' else None,
                        last_connected=datetime.now(),
                        auto_start=False
                    )
                    db.add(new_client)
                    await db.commit()
                    self.logger.info(f"✅ 已保存客户端 {self.client_id} 的配置到数据库")
                break
        except Exception as e:
            self.logger.warning(f"保存客户端配置失败（不影响运行）: {e}")
    
    async def _create_client(self):
        """创建Telegram客户端"""
        try:
            # 获取代理配置
            proxy_manager = get_proxy_manager()
            proxy_config = proxy_manager.get_telethon_proxy()
            proxy_info = proxy_manager.get_proxy_info()
            if proxy_config:
                self.logger.info(
                    f"🌐 Telethon 使用代理: {proxy_info['type']}://"
                    f"{proxy_info['host']}:{proxy_info['port']}"
                )
            else:
                self.logger.info("🌐 Telethon 使用直连")
            
            # 会话文件路径
            session_name = f"{Config.SESSIONS_DIR}/{self.client_type}_{self.client_id}"
            session_file = f"{session_name}.session"
            
            # 检查session文件是否存在
            import os
            session_exists = os.path.exists(session_file)
            
            # 预防性清理：删除可能存在的 WAL 和 SHM 锁定文件
            if session_exists:
                wal_file = f"{session_file}-wal"
                shm_file = f"{session_file}-shm"
                
                if os.path.exists(wal_file):
                    try:
                        os.remove(wal_file)
                        self.logger.debug(f"🗑️ 清理旧 WAL 文件")
                    except Exception as e:
                        self.logger.warning(f"⚠️ 无法删除 WAL 文件: {e}")
                
                if os.path.exists(shm_file):
                    try:
                        os.remove(shm_file)
                        self.logger.debug(f"🗑️ 清理旧 SHM 文件")
                    except Exception as e:
                        self.logger.warning(f"⚠️ 无法删除 SHM 文件: {e}")
            
            self.logger.info(f"🔍 客户端 {self.client_id} 配置检查:")
            self.logger.info(f"   - Session路径: {session_file}")
            self.logger.info(f"   - Session存在: {session_exists}")
            self.logger.info(f"   - 客户端API ID: {self.api_id}")
            self.logger.info(f"   - 客户端API Hash: {'***' if self.api_hash else None}")
            self.logger.info(f"   - 全局API ID: {Config.API_ID}")
            self.logger.info(f"   - 全局API Hash: {'***' if Config.API_HASH else None}")
            
            # 根据客户端类型使用不同的配置
            if self.client_type == "bot":
                # 机器人客户端使用bot_token
                bot_token = self.bot_token or Config.BOT_TOKEN
                if not bot_token:
                    raise ValueError(f"机器人客户端 {self.client_id} 缺少Bot Token")
                
                # Bot 客户端的 API 配置：优先使用客户端配置，否则使用全局配置
                api_id = int(self.api_id) if self.api_id else None
                api_hash = self.api_hash or None
                
                # 如果没有客户端特定配置，使用全局配置
                if not api_id or not api_hash:
                    if session_exists:
                        # Session文件存在，使用全局配置
                        api_id = Config.API_ID
                        api_hash = Config.API_HASH
                        self.logger.info(f"💡 Bot客户端 {self.client_id} 使用session文件和全局API配置")
                    else:
                        # 新Bot客户端，必须有全局配置
                        api_id = Config.API_ID
                        api_hash = Config.API_HASH
                        if not api_id or not api_hash:
                            raise ValueError(f"Bot客户端 {self.client_id} 缺少API ID或API Hash（客户端配置和全局配置都为空）")
                        self.logger.info(f"💡 Bot客户端 {self.client_id} 使用全局API配置")
                else:
                    self.logger.info(f"✅ Bot客户端 {self.client_id} 使用客户端专属API配置")
                
                self.client = TelegramClient(
                    session_name,
                    api_id,
                    api_hash,
                    proxy=proxy_config,
                    connection_retries=5,
                    retry_delay=2,
                    timeout=30,
                    auto_reconnect=True
                )
            else:
                # 用户客户端：优先使用客户端配置，如果session存在则可以使用全局配置
                api_id = int(self.api_id) if self.api_id else None
                api_hash = self.api_hash or None
                
                # 如果没有客户端特定配置，检查是否有session文件
                if not api_id or not api_hash:
                    if session_exists:
                        # Session文件存在，使用全局配置
                        api_id = Config.API_ID
                        api_hash = Config.API_HASH
                        self.logger.info(f"💡 客户端 {self.client_id} 使用session文件和全局API配置")
                    else:
                        raise ValueError(f"用户客户端 {self.client_id} 缺少API ID或API Hash，且没有session文件（路径：{session_file}）")
                
                if not api_id or not api_hash:
                    raise ValueError(f"用户客户端 {self.client_id} 缺少API ID或API Hash（全局配置也为空）")
                
                self.client = TelegramClient(
                    session_name,
                    api_id,
                    api_hash,
                    proxy=proxy_config,
                    connection_retries=5,
                    retry_delay=2,
                    timeout=30,
                    auto_reconnect=True
                )
            
            if session_exists:
                self.logger.info(f"📱 {self.client_type} 客户端已创建（使用现有session）")
            else:
                self.logger.info(f"📱 {self.client_type} 客户端已创建（新session）")
            
        except Exception as e:
            self.logger.error(f"创建客户端失败: {e}")
            raise
    
    def _register_event_handlers(self):
        """注册事件处理器（使用装饰器方式）"""
        if not self.client:
            return
        
        # 核心修复：使用装饰器事件处理替代add_event_handler
        @self.client.on(events.NewMessage())
        async def handle_new_message(event):
            """处理新消息事件"""
            try:
                if getattr(event.message, "grouped_id", None):
                    return
                # 异步任务隔离：在独立任务中处理，避免阻塞事件监听
                asyncio.create_task(self._process_message(event))
            except Exception as e:
                self.logger.error(f"消息处理任务创建失败: {e}")

        @self.client.on(events.Album())
        async def handle_album(event):
            """将 Telegram 相册作为一条多资源消息处理。"""
            try:
                asyncio.create_task(self._process_message(event, media_messages=list(event.messages)))
            except Exception as e:
                self.logger.error(f"相册消息处理任务创建失败: {e}")
        
        @self.client.on(events.MessageEdited())
        async def handle_message_edited(event):
            """处理消息编辑事件"""
            try:
                asyncio.create_task(self._process_message(event, is_edited=True))
            except Exception as e:
                self.logger.error(f"消息编辑处理任务创建失败: {e}")
        
        self.logger.info("✅ 事件处理器已注册（装饰器方式）")
    
    async def _safe_send_message(self, chat_id: int, text: str, **kwargs):
        """
        安全地发送消息（跨事件循环调用）
        
        用于 MessageContext 调用，自动处理事件循环切换
        """
        if not self.client or not self.loop:
            raise Exception("客户端未连接")
        
        async def _send():
            return await self.client.send_message(chat_id, text, **kwargs)
        
        # 使用 run_coroutine_threadsafe 在客户端事件循环中执行
        future = asyncio.run_coroutine_threadsafe(_send(), self.loop)
        return future.result(timeout=30)  # 30秒超时
    
    async def _safe_download_media(self, message, file_path: str):
        """
        安全地下载媒体（跨事件循环调用）
        
        用于 MessageContext 调用，自动处理事件循环切换
        """
        if not self.client or not self.loop:
            raise Exception("客户端未连接")
        
        async def _download():
            return await self.client.download_media(message, file=file_path)
        
        # 使用 run_coroutine_threadsafe 在客户端事件循环中执行
        future = asyncio.run_coroutine_threadsafe(_download(), self.loop)
        return future.result(timeout=300)  # 5分钟超时
    
    @staticmethod
    def _select_primary_message(messages):
        return next(
            (
                message for message in messages
                if getattr(message, "text", None) or getattr(message, "message", None)
            ),
            messages[0],
        )

    async def _load_album_messages(self, message):
        grouped_id = getattr(message, "grouped_id", None)
        if not grouped_id:
            return [message]
        try:
            message_ids = range(max(1, int(message.id) - 9), int(message.id) + 10)
            candidates = await self.client.get_messages(message.peer_id, ids=list(message_ids))
            return sorted(
                [candidate for candidate in candidates if candidate and candidate.grouped_id == grouped_id],
                key=lambda candidate: candidate.id,
            ) or [message]
        except Exception as e:
            self.logger.warning(f"加载编辑后的相册消息失败: message={message.id}, error={e}")
            return [message]

    async def _process_message(self, event, is_edited: bool = False, media_messages=None):
        """处理消息（在独立任务中运行）- 优化版"""
        start_time = time.time()
        try:
            if media_messages is None and is_edited and getattr(event.message, "grouped_id", None):
                media_messages = await self._load_album_messages(event.message)
            media_messages = list(media_messages or [event.message])
            message = self._select_primary_message(media_messages)
            
            # 性能优化：提前检查消息有效性
            if not message or not hasattr(message, 'peer_id'):
                return
            
            # 过滤服务消息（如置顶、加入群组等系统消息）
            from telethon.tl.types import MessageService
            if isinstance(message, MessageService):
                self.logger.debug(f"⏭️ 跳过服务消息: {message.id} (类型: {type(message.action).__name__})")
                return
                
            # 修复聊天ID转换问题 - 更准确的转换逻辑
            from telethon.tl.types import PeerChannel, PeerChat, PeerUser
            
            if isinstance(message.peer_id, PeerChannel):
                # 超级群组/频道：转换为 -100xxxxxxxxx 格式
                raw_chat_id = message.peer_id.channel_id
                chat_id = -1000000000000 - raw_chat_id
            elif isinstance(message.peer_id, PeerChat):
                # 普通群组：转换为负数
                raw_chat_id = message.peer_id.chat_id
                chat_id = -raw_chat_id
            else:
                # 私聊用户：保持正数
                raw_chat_id = message.peer_id.user_id
                chat_id = raw_chat_id
            
            # 先检查是否需要监听此聊天，只有监听的才记录INFO级别日志
            if chat_id not in self.monitored_chats:
                # 不在监听列表，使用DEBUG级别
                self.logger.debug(f"收到消息但不在监听列表: 原始ID={raw_chat_id}, 转换ID={chat_id}, 消息ID={message.id}")
                return
            
            # 在监听列表中，记录INFO级别日志
            self.logger.info(f"📨 收到监控消息: 聊天ID={chat_id}, 消息ID={message.id}")
            self.logger.debug(f"处理监听消息: 聊天ID={chat_id}, 消息ID={message.id}")
            
            # 1. 处理转发规则
            rules = await self._get_applicable_rules(chat_id)
            
            if rules:
                # 并发处理多个规则（如果有多个）
                if len(rules) > 1:
                    tasks = []
                    for rule in rules:
                        task = asyncio.create_task(self._process_rule_safe(
                            rule, message, event, is_edited, media_messages
                        ))
                        tasks.append(task)
                    await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    # 单个规则直接处理
                    await self._process_rule_safe(
                        rules[0], message, event, is_edited, media_messages
                    )
            else:
                self.logger.debug(f"聊天ID {chat_id} 没有适用的转发规则")
            
            # 性能监控
            processing_time = (time.time() - start_time) * 1000
            if processing_time > 1000:  # 超过1秒记录警告
                self.logger.warning(f"消息处理耗时: {processing_time:.2f}ms")
                    
        except Exception as e:
            self.logger.error(f"消息处理失败: {e}")
    
    async def _get_applicable_rules(self, chat_id: int) -> List[ForwardRule]:
        """获取适用的转发规则"""
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            async with db_manager.async_session() as db:
                stmt = select(ForwardRule).options(
                    selectinload(ForwardRule.keywords),
                    selectinload(ForwardRule.replace_rules),
                    selectinload(ForwardRule.delivery_targets),
                ).where(
                    ForwardRule.source_chat_id == chat_id,
                    ForwardRule.is_active == True,
                    ForwardRule.client_id == self.client_id,
                )

                result = await db.execute(stmt)
                return list(result.scalars().all())
                
        except Exception as e:
            self.logger.error(f"获取转发规则失败: {e}")
            return []
    
    async def _process_rule_safe(
        self, rule: ForwardRule, message, event, is_edited: bool = False, media_messages=None
    ):
        """安全的规则处理包装器"""
        try:
            await self._process_rule(rule, message, event, is_edited, media_messages)
        except Exception as e:
            self.logger.error(f"处理规则 {rule.id}({rule.name}) 失败: {e}")

    async def _reject_filtered_edit(
        self, rule: ForwardRule, message, is_edited: bool, media_messages=None
    ) -> None:
        if not is_edited:
            return
        from services.message_queue_service import get_message_queue_service
        source_message_id = max(
            int(getattr(media_message, "id", message.id))
            for media_message in (media_messages or [message])
        )
        rejected = await get_message_queue_service().reject_edited_message(rule, source_message_id)
        if rejected:
            self.logger.info(f"编辑后的消息不再满足规则，已拒绝: message={message.id}, rule={rule.name}")
    
    async def _process_rule(
        self, rule: ForwardRule, message, event, is_edited: bool = False, media_messages=None
    ):
        """处理单个转发规则"""
        try:
            # 消息类型检查
            if not self._check_message_type(rule, message):
                await self._reject_filtered_edit(rule, message, is_edited, media_messages)
                return
            
            # 时间过滤检查
            if not self._check_time_filter(rule, message):
                await self._reject_filtered_edit(rule, message, is_edited, media_messages)
                return
            
            # 【新功能】发送者过滤检查
            if getattr(rule, 'enable_sender_filter', False):
                from utils.sender_filter import SenderFilter
                sender_info = SenderFilter.get_sender_info(message)
                is_allowed = SenderFilter.is_sender_allowed(
                    sender_info['id'],
                    sender_info['username'],
                    getattr(rule, 'sender_filter_mode', 'whitelist'),
                    getattr(rule, 'sender_whitelist', None),
                    getattr(rule, 'sender_blacklist', None)
                )
                if not is_allowed:
                    self.logger.info(f"⏭️ 发送者 {sender_info['username'] or sender_info['id']} 被过滤器阻止")
                    await self._reject_filtered_edit(rule, message, is_edited, media_messages)
                    return
            
            # 获取消息文本（对于媒体消息使用caption）
            message_text = message.text or message.message or ""
            
            # 关键词过滤
            if rule.enable_keyword_filter and rule.keywords:
                if not self.keyword_filter.should_forward(message_text, rule.keywords):
                    await self._reject_filtered_edit(rule, message, is_edited, media_messages)
                    return
            
            # 文本替换
            text_to_forward = message_text
            if rule.enable_regex_replace and rule.replace_rules:
                text_to_forward = self.regex_replacer.apply_replacements(text_to_forward, rule.replace_rules)
            
            from services.message_queue_service import get_message_queue_service
            queue_id = await get_message_queue_service().enqueue(
                rule, message, text_to_forward, self.client, media_messages=media_messages
            )
            if queue_id:
                action = "更新" if is_edited else "入队"
                self.logger.info(f"✅ 消息已{action}: queue_id={queue_id}, rule={rule.name}")
            return queue_id
            
        except Exception as e:
            self.logger.error(f"规则处理失败: {e}", exc_info=True)
    
    def _check_message_type(self, rule: ForwardRule, message) -> bool:
        """检查消息类型是否符合规则"""
        try:
            from telethon.tl.types import (
                MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
                MessageMediaGeo, MessageMediaVenue, MessageMediaContact,
                MessageMediaGame, MessageMediaInvoice, MessageMediaGeoLive,
                MessageMediaPoll, MessageMediaDice, MessageMediaStory
            )
            
            # 检查是否为纯文本消息（无媒体）
            if not message.media:
                # 纯文本消息检查
                if message.text and not getattr(rule, 'enable_text', True):
                    self.logger.debug(f"📝 文本消息被规则禁用: {rule.name}")
                    return False
                return True
            
            # 有媒体的消息 - 检查具体媒体类型
            media = message.media
            
            # 图片
            if isinstance(media, MessageMediaPhoto):
                enable_photo = getattr(rule, 'enable_photo', True)
                self.logger.info(f"🖼️ 检测到图片消息 - 规则 '{rule.name}' enable_photo={enable_photo}")
                if not enable_photo:
                    self.logger.debug(f"🖼️ 图片消息被规则禁用: {rule.name}")
                    return False
                self.logger.info(f"✅ 图片消息通过类型检查")
                return True
            
            # 文档（包括视频、音频、文档等）
            if isinstance(media, MessageMediaDocument):
                document = media.document
                if hasattr(document, 'mime_type') and document.mime_type:
                    mime_type = document.mime_type.lower()
                    
                    # 视频
                    if mime_type.startswith('video/'):
                        if not getattr(rule, 'enable_video', True):
                            self.logger.debug(f"🎥 视频消息被规则禁用: {rule.name}")
                            return False
                        return True
                    
                    # 音频
                    if mime_type.startswith('audio/'):
                        if not getattr(rule, 'enable_audio', True):
                            self.logger.debug(f"🎵 音频消息被规则禁用: {rule.name}")
                            return False
                        return True
                    
                    # 文档/其他文件
                    if not getattr(rule, 'enable_document', True):
                        self.logger.debug(f"📄 文档消息被规则禁用: {rule.name}")
                        return False
                    return True
                
                # 检查是否为特殊类型（语音、贴纸、动图等）
                if hasattr(document, 'attributes'):
                    for attr in document.attributes:
                        attr_type = type(attr).__name__
                        
                        # 语音消息
                        if 'Voice' in attr_type:
                            if not getattr(rule, 'enable_voice', True):
                                self.logger.debug(f"🎤 语音消息被规则禁用: {rule.name}")
                                return False
                            return True
                        
                        # 贴纸
                        if 'Sticker' in attr_type:
                            if not getattr(rule, 'enable_sticker', False):  # 默认禁用贴纸
                                self.logger.debug(f"😀 贴纸消息被规则禁用: {rule.name}")
                                return False
                            return True
                        
                        # 动图
                        if 'Animated' in attr_type or 'Video' in attr_type:
                            if not getattr(rule, 'enable_animation', True):
                                self.logger.debug(f"🎞️ 动图消息被规则禁用: {rule.name}")
                                return False
                            return True
            
            # 网页预览
            if isinstance(media, MessageMediaWebPage):
                if not getattr(rule, 'enable_webpage', True):
                    self.logger.debug(f"🌐 网页预览被规则禁用: {rule.name}")
                    return False
                return True
            
            # 其他媒体类型（地理位置、联系人、游戏等）
            # 默认允许，除非有特定的禁用设置
            self.logger.debug(f"🔍 未知媒体类型，默认允许: {type(media).__name__}")
            return True
            
        except Exception as e:
            self.logger.error(f"消息类型检查失败: {e}")
            # 出错时默认允许转发
            return True
    
    def _check_time_filter(self, rule: ForwardRule, message) -> bool:
        """检查时间过滤条件 - 统一在用户时区进行比较"""
        from timezone_utils import get_user_now, telegram_time_to_user_time, database_time_to_user_time
        
        if not hasattr(rule, 'time_filter_type'):
            return True
        
        # 核心：将Telegram消息时间转换为用户时区，后续所有比较都在用户时区进行
        message_time = telegram_time_to_user_time(message.date)
        current_time = get_user_now()
        
        if rule.time_filter_type == "after_start":
            # 启动后的消息都转发（实时消息处理）
            return True
        elif rule.time_filter_type == "today_only":
            # 仅转发当天消息
            today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            return message_time >= today_start
        elif rule.time_filter_type == "from_time":
            # 从指定时间开始 - 数据库时间转为用户时区
            if hasattr(rule, 'start_time') and rule.start_time:
                start_time = database_time_to_user_time(rule.start_time)
                return message_time >= start_time
            else:
                # 未设置开始时间，默认允许所有实时消息
                self.logger.warning(f"⚠️ 规则 '{rule.name}' 设置为from_time但未配置start_time，默认允许实时消息")
                return True
        elif rule.time_filter_type == "time_range":
            # 指定时间段内 - 数据库时间转为用户时区
            if hasattr(rule, 'start_time') and hasattr(rule, 'end_time'):
                if rule.start_time and rule.end_time:
                    start_time = database_time_to_user_time(rule.start_time)
                    end_time = database_time_to_user_time(rule.end_time)
                    return start_time <= message_time <= end_time
                else:
                    # 时间配置不完整，默认允许所有实时消息
                    self.logger.warning(f"⚠️ 规则 '{rule.name}' 设置为time_range但时间配置不完整，默认允许实时消息")
                    return True
            else:
                # 缺少时间属性，默认允许所有实时消息
                self.logger.warning(f"⚠️ 规则 '{rule.name}' 设置为time_range但缺少时间属性，默认允许实时消息")
                return True
        elif rule.time_filter_type == "all_messages":
            # 转发所有消息（无时间限制）
            return True
        
        return True

    @staticmethod
    def _utc_time(value):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def _backfill_rule_history(self, rule_id: int, force_full: bool = False) -> None:
        if rule_id in self.history_backfills:
            return
        self.history_backfills.add(rule_id)
        try:
            from sqlalchemy import func, select
            from telethon.tl.types import MessageService
            from services.business_services import ForwardRuleService
            from models import QueuedMessage

            rule = await ForwardRuleService.get_rule_by_id(rule_id)
            if (
                not rule
                or not rule.is_active
                or rule.client_id != self.client_id
                or rule.time_filter_type not in {"from_time", "time_range"}
                or not rule.start_time
            ):
                return

            iterator_options = {"reverse": True}
            if not force_full:
                async with db_manager.async_session() as db:
                    last_message_id = await db.scalar(select(func.max(QueuedMessage.source_message_id)).where(
                        QueuedMessage.rule_id == rule.id,
                        QueuedMessage.client_id == rule.client_id,
                        QueuedMessage.source_chat_id == str(rule.source_chat_id),
                    ))
                if last_message_id:
                    iterator_options["min_id"] = int(last_message_id)

            if "min_id" not in iterator_options:
                start_time = self._utc_time(rule.start_time)
                iterator_options["offset_date"] = start_time - timedelta(microseconds=1)

            end_time = self._utc_time(rule.end_time) if rule.time_filter_type == "time_range" else None
            chat_id = int(rule.source_chat_id)
            scanned = 0
            matched = 0
            self.logger.info(
                f"🔄 开始回填历史消息: rule={rule.name}, chat={chat_id}, "
                f"start={self._utc_time(rule.start_time)}, end={end_time or 'now'}"
            )
            album_messages = []
            album_id = None

            async def flush_album():
                nonlocal album_messages, album_id, matched
                if not album_messages:
                    return
                primary = self._select_primary_message(album_messages)
                if await self._process_rule(
                    rule, primary, event=None, media_messages=album_messages
                ):
                    matched += 1
                album_messages = []
                album_id = None

            async for message in self.client.iter_messages(chat_id, **iterator_options):
                message_time = self._utc_time(getattr(message, "date", None))
                if end_time and message_time and message_time > end_time:
                    await flush_album()
                    break
                if isinstance(message, MessageService):
                    continue
                scanned += 1
                grouped_id = getattr(message, "grouped_id", None)
                if grouped_id:
                    if album_id is not None and grouped_id != album_id:
                        await flush_album()
                    album_id = grouped_id
                    album_messages.append(message)
                    continue

                await flush_album()
                if await self._process_rule(
                    rule, message, event=None, media_messages=[message]
                ):
                    matched += 1
            await flush_album()

            self.logger.info(
                f"✅ 历史消息回填完成: rule={rule.name}, scanned={scanned}, matched={matched}"
            )
        except Exception as e:
            self.logger.error(f"历史消息回填失败: rule_id={rule_id}, error={e}", exc_info=True)
        finally:
            self.history_backfills.discard(rule_id)

    async def _backfill_time_filtered_rules(self) -> None:
        try:
            from sqlalchemy import select

            async with db_manager.async_session() as db:
                rule_ids = list((await db.scalars(select(ForwardRule.id).where(
                    ForwardRule.is_active == True,
                    ForwardRule.client_id == self.client_id,
                    ForwardRule.time_filter_type.in_(["from_time", "time_range"]),
                    ForwardRule.start_time.is_not(None),
                ))).all())
            for rule_id in rule_ids:
                await self._backfill_rule_history(rule_id)
        except Exception as e:
            self.logger.error(f"加载历史回填规则失败: {e}", exc_info=True)

    def schedule_history_backfill(self, rule_id: int, force_full: bool = True) -> bool:
        if not self.loop or not self.running or not self.connected:
            return False
        asyncio.run_coroutine_threadsafe(
            self._backfill_rule_history(rule_id, force_full=force_full),
            self.loop,
        )
        return True
    
    async def _update_monitored_chats(self):
        """更新当前客户端启用规则的实时消息监听列表。"""
        try:
            async for db in get_db():
                from sqlalchemy import select, distinct

                stmt = select(distinct(ForwardRule.source_chat_id)).where(
                    ForwardRule.is_active == True,
                    ForwardRule.client_id == self.client_id,
                )
                result = await db.execute(stmt)
                forward_chat_ids = result.scalars().all()
                self.monitored_chats = {int(chat_id) for chat_id in forward_chat_ids}
                self.logger.info(
                    f"🎯 更新实时消息监听列表 ({len(self.monitored_chats)} 个聊天): "
                    f"{list(self.monitored_chats)}"
                )
                break
                
        except Exception as e:
            self.logger.error(f"更新监听聊天列表失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def send_verification_code(self) -> Dict[str, Any]:
        """发送验证码"""
        try:
            if self.client_type != 'user':
                return {"success": False, "message": "只有用户客户端支持验证码登录"}
            
            if not self.phone:
                return {"success": False, "message": "手机号未设置"}
            
            # 【优化】检查验证码发送冷却时间
            if self.last_code_sent_time:
                elapsed = time.time() - self.last_code_sent_time
                remaining = self.code_cooldown_seconds - int(elapsed)
                if remaining > 0:
                    return {
                        "success": False,
                        "message": f"发送过于频繁，请等待 {remaining} 秒后重试",
                        "error_type": "rate_limit",
                        "remaining_seconds": remaining
                    }
            
            # 创建客户端
            await self._create_client()
            
            if not self.client:
                return {"success": False, "message": "客户端创建失败"}
            
            # 先连接客户端（不进行完整登录）
            await self.client.connect()
            
            if not self.client.is_connected():
                return {"success": False, "message": "客户端连接失败"}
            
            # 【优化】检查是否已经登录（Session 预加载）
            try:
                if await self.client.is_user_authorized():
                    # 已经登录，获取用户信息
                    me = await self.client.get_me()
                    self.user_info = me
                    self.login_state = "completed"
                    self.connected = True
                    
                    self.logger.info(f"✅ Session 已存在，无需重复登录: {getattr(me, 'username', '') or getattr(me, 'first_name', 'Unknown')}")
                    
                    # 保存客户端配置到数据库
                    await self._save_client_config()
                    
                    # 登录 API 与监听线程使用不同事件循环，不能共享同一个
                    # Telethon client。先释放临时连接，再由“启动”动作创建监听连接。
                    await self._dispose_login_client()
                    return {
                        "success": True,
                        "message": "用户已登录，可以启动客户端了",
                        "step": "completed",
                        "auto_started": False,
                        "auto_start_ready": True,
                        "user_info": {
                            "id": me.id,
                            "username": getattr(me, 'username', ''),
                            "first_name": getattr(me, 'first_name', ''),
                            "phone": getattr(me, 'phone', '')
                        }
                    }
            except Exception as auth_check_error:
                # 检查失败不影响后续流程，继续发送验证码
                self.logger.warning(f"检查登录状态失败: {auth_check_error}")
            
            # 发送验证码
            result = await self.client.send_code_request(self.phone)
            self.login_session = result
            self.login_state = "waiting_code"
            
            # 【优化】记录发送时间，用于冷却计算
            self.last_code_sent_time = time.time()
            
            self.logger.info(f"✅ 验证码已发送到 {self.phone}")
            return {
                "success": True,
                "message": f"验证码已发送到 {self.phone}",
                "step": "waiting_code",
                "cooldown_seconds": self.code_cooldown_seconds  # 前端可用于倒计时显示
            }
            
        except Exception as e:
            self.logger.error(f"发送验证码失败: {e}")
            await self._reset_login_state()
            # 使用统一的错误处理器
            error_response = LoginErrorHandler.handle_error(e)
            return error_response
    
    async def submit_verification_code(self, code: str) -> Dict[str, Any]:
        """提交验证码"""
        try:
            if self.login_state != "waiting_code":
                return {"success": False, "message": "当前不在等待验证码状态"}
            
            if not self.login_session:
                return {"success": False, "message": "登录会话无效，请重新发送验证码"}
            
            # 【优化】自动重连机制
            if not self.client:
                return {"success": False, "message": "客户端未初始化，请重新发送验证码"}
            
            if not self.client.is_connected():
                self.logger.warning("⚠️ 客户端已断开连接，尝试自动重连...")
                try:
                    await self.client.connect()
                    if not self.client.is_connected():
                        return {
                            "success": False,
                            "message": "客户端重连失败，请重新发送验证码",
                            "should_resend": True
                        }
                    self.logger.info("✅ 客户端自动重连成功")
                except Exception as reconnect_error:
                    self.logger.error(f"❌ 客户端重连失败: {reconnect_error}")
                    return {
                        "success": False,
                        "message": "客户端连接已过期，请重新发送验证码",
                        "should_resend": True
                    }
            
            # 提交验证码
            try:
                # 导入 Telethon 专用异常
                from telethon.errors import SessionPasswordNeededError
                
                result = await self.client.sign_in(phone=self.phone, code=code)
                
                # 登录成功
                self.user_info = result
                self.login_state = "completed"
                # 注意：不设置 self.connected = True，登录流程和启动流程分离
                
                self.logger.info(f"✅ 用户客户端登录成功: {getattr(result, 'username', '') or getattr(result, 'first_name', 'Unknown')}")
                
                # 保存客户端配置到数据库
                await self._save_client_config()
                
                # 【关键修复】登录完成后断开连接，释放 session 文件锁
                # 这样用户点击启动时不会遇到 "database is locked" 错误
                try:
                    if self.client and self.client.is_connected():
                        await self.client.disconnect()
                        self.logger.info("🔌 登录完成，已断开临时连接（session 已保存）")
                except Exception as disc_error:
                    self.logger.warning(f"断开登录连接失败: {disc_error}")
                
                return {
                    "success": True,
                    "message": "登录成功，可以启动客户端了",
                    "step": "completed",
                    "auto_start_ready": True,  # 提示前端可以自动启动
                    "user_info": {
                        "id": result.id,
                        "username": getattr(result, 'username', ''),
                        "first_name": getattr(result, 'first_name', ''),
                        "phone": getattr(result, 'phone', '')
                    }
                }
                
            except SessionPasswordNeededError:
                # 【修复】使用 Telethon 专用异常，更准确
                self.login_state = "waiting_password"
                self.logger.info("🔐 检测到需要二步验证密码")
                return {
                    "success": True,
                    "message": "需要输入二步验证密码",
                    "step": "waiting_password"
                }
            except Exception as e:
                # 其他错误
                self.login_state = "idle"
                raise e
            
        except Exception as e:
            self.logger.error(f"提交验证码失败: {e}")
            # 【优化】使用统一的状态清理方法
            await self._reset_login_state()
            # 使用统一的错误处理器
            error_response = LoginErrorHandler.handle_error(e)
            return error_response
    
    async def submit_password(self, password: str) -> Dict[str, Any]:
        """提交二步验证密码"""
        try:
            if self.login_state != "waiting_password":
                return {"success": False, "message": "当前不在等待密码状态"}
            
            # 【优化】自动重连机制
            if not self.client:
                return {"success": False, "message": "客户端未初始化，请重新发送验证码"}
            
            if not self.client.is_connected():
                self.logger.warning("⚠️ 客户端已断开连接，尝试自动重连...")
                try:
                    await self.client.connect()
                    if not self.client.is_connected():
                        return {
                            "success": False,
                            "message": "客户端重连失败，请重新发送验证码",
                            "should_resend": True
                        }
                    self.logger.info("✅ 客户端自动重连成功")
                except Exception as reconnect_error:
                    self.logger.error(f"❌ 客户端重连失败: {reconnect_error}")
                    return {
                        "success": False,
                        "message": "客户端连接已过期，请重新发送验证码",
                        "should_resend": True
                    }
            
            # 提交密码
            result = await self.client.sign_in(password=password)
            
            # 登录成功
            self.user_info = result
            self.login_state = "completed"
            # 注意：不设置 self.connected = True，登录流程和启动流程分离
            
            self.logger.info(f"✅ 用户客户端二步验证成功: {getattr(result, 'username', '') or getattr(result, 'first_name', 'Unknown')}")
            
            # 保存客户端配置到数据库
            await self._save_client_config()
            
            # 【关键修复】登录完成后断开连接，释放 session 文件锁
            try:
                if self.client and self.client.is_connected():
                    await self.client.disconnect()
                    self.logger.info("🔌 登录完成，已断开临时连接（session 已保存）")
            except Exception as disc_error:
                self.logger.warning(f"断开登录连接失败: {disc_error}")
            
            return {
                "success": True,
                "message": "登录成功，可以启动客户端了",
                "step": "completed",
                "auto_start_ready": True,  # 提示前端可以自动启动
                "user_info": {
                    "id": result.id,
                    "username": getattr(result, 'username', ''),
                    "first_name": getattr(result, 'first_name', ''),
                    "phone": getattr(result, 'phone', '')
                }
            }
            
        except Exception as e:
            self.logger.error(f"二步验证失败: {e}")
            # 【优化】使用统一的状态清理方法
            await self._reset_login_state()
            # 使用统一的错误处理器
            error_response = LoginErrorHandler.handle_error(e)
            # 对于密码错误，特别处理
            if error_response.get("error_type") == "unknown":
                error_msg = str(e).lower()
                if "password" in error_msg or "invalid" in error_msg:
                    error_response["message"] = "密码错误，请检查后重新输入"
                    error_response["error_type"] = "invalid_password"
            return error_response
    
    def get_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        # 安全地序列化用户信息
        user_info_safe = None
        if self.user_info:
            try:
                user_info_safe = {
                    "id": getattr(self.user_info, 'id', None),
                    "username": getattr(self.user_info, 'username', None),
                    "first_name": getattr(self.user_info, 'first_name', None),
                    "last_name": getattr(self.user_info, 'last_name', None),
                    "phone": getattr(self.user_info, 'phone', None),
                    "bot": getattr(self.user_info, 'bot', None)
                }
            except Exception as e:
                self.logger.warning(f"序列化用户信息失败: {e}")
                user_info_safe = {"error": "序列化失败"}
        
        return {
            "client_id": self.client_id,
            "client_type": self.client_type,
            "running": self.running,
            "connected": self.connected,
            "login_state": getattr(self, 'login_state', 'idle'),
            "user_info": user_info_safe,
            "monitored_chats": list(self.monitored_chats),
            "thread_alive": self.thread.is_alive() if self.thread else False
        }
    
    def get_chats_sync(self) -> List[Dict[str, Any]]:
        """同步获取聊天列表（线程安全）"""
        if not self.loop or not self.running or not self.connected:
            return []
        
        try:
            # 使用 run_coroutine_threadsafe 在客户端的事件循环中执行
            future = asyncio.run_coroutine_threadsafe(
                self._get_chats_async(),
                self.loop
            )
            # 等待结果，超时时间10秒
            return future.result(timeout=10)
        except Exception as e:
            self.logger.warning(f"获取聊天列表失败: {e}")
            return []
    
    def get_chat_title_sync(self, chat_id: str) -> str:
        """同步获取特定聊天的标题（线程安全）"""
        if not self.loop or not self.running or not self.connected:
            return f"聊天 {chat_id}"
        
        try:
            # 使用 run_coroutine_threadsafe 在客户端的事件循环中执行
            future = asyncio.run_coroutine_threadsafe(
                self._get_chat_title_async(chat_id),
                self.loop
            )
            # 等待结果，超时时间5秒
            return future.result(timeout=5)
        except Exception as e:
            self.logger.warning(f"获取聊天 {chat_id} 标题失败: {e}")
            return f"聊天 {chat_id}"
    
    async def _get_chat_title_async(self, chat_id: str) -> str:
        """在客户端事件循环中异步获取特定聊天标题"""
        try:
            if not self.client or not self.client.is_connected():
                return f"聊天 {chat_id}"
            
            # 转换聊天ID
            try:
                chat_id_int = int(chat_id)
            except ValueError:
                chat_id_int = chat_id
            
            # 获取聊天实体
            entity = await self.client.get_entity(chat_id_int)
            
            # 提取标题
            if hasattr(entity, 'title') and entity.title:
                title = entity.title
            elif hasattr(entity, 'username') and entity.username:
                title = f"@{entity.username}"
            elif hasattr(entity, 'first_name'):
                first_name = getattr(entity, 'first_name', '')
                last_name = getattr(entity, 'last_name', '')
                title = f"{first_name} {last_name}".strip()
            else:
                title = f"聊天 {chat_id}"
            
            self.logger.info(f"✅ 获取聊天 {chat_id} 标题: {title}")
            return title
            
        except Exception as e:
            self.logger.warning(f"⚠️ 无法获取聊天 {chat_id} 标题: {e}")
            return f"聊天 {chat_id}"
    
    async def _get_chats_async(self) -> List[Dict[str, Any]]:
        """在客户端事件循环中异步获取聊天列表"""
        try:
            if not self.client or not self.client.is_connected():
                return []
            
            # 不限制聊天数量，获取所有聊天
            dialogs = await self.client.get_dialogs()
            chats = []
            
            # 获取客户端用户信息用于显示
            client_display_name = "未知客户端"
            if self.user_info:
                if self.client_type == "bot":
                    client_display_name = f"机器人: {getattr(self.user_info, 'first_name', self.client_id)}"
                else:
                    first_name = getattr(self.user_info, 'first_name', '') or ''
                    last_name = getattr(self.user_info, 'last_name', '') or ''
                    username = getattr(self.user_info, 'username', '') or ''
                    
                    # 构建全名（只包含非空部分）
                    name_parts = [first_name, last_name]
                    full_name = ' '.join(part for part in name_parts if part).strip()
                    
                    if username:
                        client_display_name = f"用户: {full_name} (@{username})".strip()
                    else:
                        client_display_name = f"用户: {full_name}".strip()
                    
                    if not client_display_name.replace("用户: ", "").strip():
                        client_display_name = f"用户: {self.client_id}"
            
            for dialog in dialogs:
                try:
                    # 获取更详细的聊天信息
                    entity = dialog.entity
                    chat_type = "user"
                    if dialog.is_group:
                        chat_type = "group"
                    elif dialog.is_channel:
                        chat_type = "channel"
                    
                    # 获取聊天标题
                    title = dialog.title or dialog.name
                    if not title and hasattr(entity, 'first_name'):
                        # 对于私聊用户，组合姓名
                        first_name = getattr(entity, 'first_name', '')
                        last_name = getattr(entity, 'last_name', '')
                        title = f"{first_name} {last_name}".strip()
                    if not title:
                        title = "未知聊天"
                    
                    chat_data = {
                        "id": str(dialog.id),
                        "title": title,
                        "type": chat_type,
                        "username": getattr(entity, 'username', None),
                        "description": getattr(entity, 'about', None),
                        "members_count": getattr(entity, 'participants_count', 0) if hasattr(entity, 'participants_count') else 0,
                        "client_id": self.client_id,
                        "client_type": self.client_type,
                        "client_display_name": client_display_name,
                        "is_verified": getattr(entity, 'verified', False),
                        "is_scam": getattr(entity, 'scam', False),
                        "is_fake": getattr(entity, 'fake', False),
                        "unread_count": dialog.unread_count,
                        "last_message_date": dialog.date.isoformat() if dialog.date else None
                    }
                    chats.append(chat_data)
                except Exception as e:
                    self.logger.warning(f"处理聊天数据失败: {e}")
                    continue
            
            self.logger.info(f"✅ 客户端 {self.client_id} 获取到 {len(chats)} 个聊天")
            return chats
        except Exception as e:
            self.logger.error(f"获取聊天列表失败: {e}")
            return []
    
    async def refresh_monitored_chats(self):
        """刷新监听聊天列表（外部调用）"""
        if self.loop and self.running:
            asyncio.run_coroutine_threadsafe(
                self._update_monitored_chats(),
                self.loop
            )


class MultiClientManager:
    """
    多客户端管理器
    
    管理多个Telegram客户端实例，避免客户端竞争
    """
    
    def __init__(self):
        self.clients: Dict[str, TelegramClientManager] = {}
        self.logger = get_logger("multi_client_manager", "enhanced_bot.log")
    
    def add_client(self, client_id: str, client_type: str = "user") -> TelegramClientManager:
        """添加客户端"""
        if client_id in self.clients:
            self.logger.warning(f"客户端 {client_id} 已存在")
            return self.clients[client_id]
        
        client = TelegramClientManager(client_id, client_type)
        self.clients[client_id] = client
        
        self.logger.info(f"✅ 添加客户端: {client_id} ({client_type})")
        return client

    def add_client_with_config(self, client_id: str, client_type: str = "user", config_data: dict = None) -> TelegramClientManager:
        """添加带配置的客户端"""
        if client_id in self.clients:
            self.logger.warning(f"客户端 {client_id} 已存在")
            return self.clients[client_id]
        
        client = TelegramClientManager(client_id, client_type)
        
        # 存储客户端特定配置
        if config_data:
            if client_type == 'bot':
                client.bot_token = config_data.get('bot_token')
                client.admin_user_id = config_data.get('admin_user_id')
            elif client_type == 'user':
                client.api_id = config_data.get('api_id')
                client.api_hash = config_data.get('api_hash')
                client.phone = config_data.get('phone')
        
        self.clients[client_id] = client
        
        self.logger.info(f"✅ 添加带配置的客户端: {client_id} ({client_type})")
        return client
    
    def remove_client(self, client_id: str, force_delete_session: bool = False) -> bool:
        """
        移除客户端（包括删除 session 文件）
        
        Args:
            client_id: 客户端ID
            force_delete_session: 是否强制删除 session 文件（即使客户端不在内存中）
        
        Returns:
            bool: 是否成功从内存中移除客户端
        """
        if client_id not in self.clients:
            # 客户端不在内存中
            if force_delete_session:
                # 强制删除 session 文件（用于清理数据库中的客户端）
                self._delete_session_file(client_id)
                self.logger.info(f"💡 客户端 {client_id} 不在内存中，但已删除 session 文件")
            else:
                self.logger.debug(f"💡 客户端 {client_id} 不在内存中")
            return False
        
        client = self.clients[client_id]
        
        # 检查客户端是否正在运行
        if client.running:
            self.logger.warning(f"⚠️ 客户端 {client_id} 正在运行，先停止客户端")
            client.stop()
            # 等待客户端完全停止
            import time
            timeout = 5
            for _ in range(timeout * 10):
                if not client.running:
                    break
                time.sleep(0.1)
            
            if client.running:
                self.logger.error(f"❌ 客户端 {client_id} 停止超时，强制移除")
        
        # 删除 session 文件
        self._delete_session_file(client_id, client.client_type)
        
        del self.clients[client_id]
        
        self.logger.info(f"✅ 移除客户端: {client_id}（包括 session 文件）")
        return True
    
    def _delete_session_file(self, client_id: str, client_type: str = None) -> bool:
        """删除客户端的 session 文件"""
        try:
            import os
            from pathlib import Path
            from config import Config
            
            sessions_dir = Path(Config.SESSIONS_DIR)
            
            # 尝试删除可能的 session 文件
            if client_type:
                # 已知类型，直接删除
                session_file = sessions_dir / f"{client_type}_{client_id}.session"
                if session_file.exists():
                    session_file.unlink()
                    self.logger.info(f"🗑️ 删除 session 文件: {session_file}")
                    return True
            else:
                # 未知类型，尝试两种可能
                for ctype in ['user', 'bot']:
                    session_file = sessions_dir / f"{ctype}_{client_id}.session"
                    if session_file.exists():
                        session_file.unlink()
                        self.logger.info(f"🗑️ 删除 session 文件: {session_file}")
                        return True
            
            self.logger.debug(f"💡 未找到客户端 {client_id} 的 session 文件")
            return False
            
        except Exception as e:
            self.logger.error(f"❌ 删除 session 文件失败: {e}")
            return False
    
    def get_client(self, client_id: str) -> Optional[TelegramClientManager]:
        """获取客户端"""
        return self.clients.get(client_id)
    
    def start_client(self, client_id: str) -> bool:
        """启动客户端"""
        client = self.clients.get(client_id)
        if not client:
            return False
        
        return client.start()

    def schedule_history_backfill(self, client_id: str, rule_id: int) -> bool:
        client = self.clients.get(client_id)
        return client.schedule_history_backfill(rule_id) if client else False
    
    def stop_client(self, client_id: str) -> bool:
        """停止客户端"""
        client = self.clients.get(client_id)
        if not client:
            return False
        
        client.stop()
        return True
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有客户端状态"""
        return {
            client_id: client.get_status()
            for client_id, client in self.clients.items()
        }
    
    def stop_all(self):
        """停止所有客户端"""
        for client in self.clients.values():
            client.stop()
        self.clients.clear()
        self.logger.info("✅ 所有客户端已停止")
    
    def update_chat_names_sync(self, rules):
        """同步方式更新聊天名称 - 简化版本"""
        self.logger.info("🔄 开始获取聊天名称（同步方式）...")
        
        if not self.clients:
            self.logger.warning("⚠️ 没有可用的客户端")
            return []
        
        # 获取第一个可用的客户端
        client_manager = next(iter(self.clients.values()))
        if not client_manager or not client_manager.client:
            self.logger.warning("⚠️ 客户端不可用")
            return []
            
        if not client_manager.connected:
            self.logger.warning("⚠️ 客户端未连接")
            return []
        
        updated_rules = []
        
        for rule in rules:
            updated_fields = {}
            
            # 由于聊天名称获取需要在正确的事件循环中执行，
            # 我们在这里只返回占位符信息，真正的获取将在其他地方进行
            if rule.source_chat_id and (not rule.source_chat_name or rule.source_chat_name.startswith('聊天 ')):
                updated_fields['source_chat_name'] = f"聊天 {rule.source_chat_id}"
            
            if updated_fields:
                updated_rules.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "updates": updated_fields
                })
                self.logger.info(f"🔄 准备更新规则 {rule.name}: {updated_fields}")
        
        self.logger.info(f"✅ 获取聊天名称完成: 准备更新 {len(updated_rules)} 个规则")
        return updated_rules

# 全局多客户端管理器实例
multi_client_manager = MultiClientManager()
