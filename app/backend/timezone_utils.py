#!/usr/bin/env python3
"""
统一的时区处理工具模块 - 简化设计
核心原则：所有时间比较都在用户配置的时区进行，避免反复转换
"""
import os
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def get_user_timezone():
    """获取用户配置的时区对象"""
    try:
        import pytz
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
        logger.warning("pytz 不可用，使用 UTC")
        return timezone.utc

def get_user_now():
    """获取用户时区的当前时间"""
    user_tz = get_user_timezone()
    return datetime.now(user_tz)

def get_user_timestamp():
    """获取用户时区当前时间的Unix时间戳（秒）"""
    return get_user_now().timestamp()

def telegram_time_to_user_time(telegram_dt):
    """
    将Telegram消息时间（UTC）转换为用户时区时间
    这是唯一需要转换的地方
    """
    if telegram_dt is None:
        return None
    
    user_tz = get_user_timezone()
    
    # Telegram消息时间通常是UTC，如果没有时区信息就假设是UTC
    if telegram_dt.tzinfo is None:
        telegram_dt = telegram_dt.replace(tzinfo=timezone.utc)
    
    # 转换到用户时区
    return telegram_dt.astimezone(user_tz)

def rule_time_to_database_time(value):
    """Normalize a rule time to naive UTC for database storage."""
    if isinstance(value, str):
        normalized = value.replace('Z', '+00:00')
        normalized = re.sub(r'(\.\d{6})\d*', r'\1', normalized)
        value = datetime.fromisoformat(normalized)

    if not isinstance(value, datetime):
        return value

    if value.tzinfo is None:
        user_tz = get_user_timezone()
        localize = getattr(user_tz, 'localize', None)
        value = localize(value) if localize else value.replace(tzinfo=user_tz)

    return value.astimezone(timezone.utc).replace(tzinfo=None)

def database_time_to_user_time(db_dt):
    """
    将数据库时间转换为用户时区时间
    数据库时间可能没有时区信息，需要根据存储方式处理
    """
    if db_dt is None:
        return None
    
    if db_dt.tzinfo is None:
        db_dt = db_dt.replace(tzinfo=timezone.utc)

    return db_dt.astimezone(get_user_timezone())

def database_time_to_utc_isoformat(db_dt):
    """Serialize a stored rule time with an explicit UTC offset."""
    if db_dt is None:
        return None
    if db_dt.tzinfo is None:
        db_dt = db_dt.replace(tzinfo=timezone.utc)
    return db_dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

# 向后兼容的别名
get_configured_timezone = get_user_timezone
get_current_time = get_user_now
get_local_now = get_user_now
to_configured_timezone = telegram_time_to_user_time
ensure_timezone = database_time_to_user_time
