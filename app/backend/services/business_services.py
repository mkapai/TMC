"""
业务逻辑服务层 - 优化版
"""
import asyncio
from datetime import datetime, timedelta
from models import get_local_now
from typing import List, Optional, Dict, Any, Union
from sqlalchemy import select, delete, update, and_, or_, desc, func, text
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
import json
from functools import lru_cache
import time

from database import get_db
from models import DeliveryTarget, ForwardRule, Keyword, ReplaceRule, UserSession, BotSettings, rule_delivery_targets
from filters import KeywordFilter, RegexReplacer, MessageProcessor
from timezone_utils import get_user_now, rule_time_to_database_time

# 性能优化：缓存装饰器
def cache_result(ttl: int = 300):
    """缓存结果装饰器"""
    def decorator(func):
        cache = {}
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            now = time.time()
            
            # 检查缓存
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if now - timestamp < ttl:
                    return result
            
            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            cache[cache_key] = (result, now)
            
            # 清理过期缓存
            expired_keys = [k for k, (_, ts) in cache.items() if now - ts > ttl]
            for k in expired_keys:
                del cache[k]
                
            return result
        return wrapper
    return decorator

class ForwardRuleService:
    """转发规则服务"""
    
    @staticmethod
    async def create_rule(
        name: str,
        source_chat_id: str,
        source_chat_name: str,
        **kwargs
    ) -> ForwardRule:
        """创建转发规则"""
        # 处理时间字段转换（与update_rule保持一致）
        for time_field in ['start_time', 'end_time']:
            if time_field in kwargs and kwargs[time_field] is not None:
                time_value = kwargs[time_field]
                try:
                    kwargs[time_field] = rule_time_to_database_time(time_value)
                except ValueError as e:
                    logger.warning(f"⚠️ 创建规则时时间字段 {time_field} 格式无效: {time_value}, 错误: {e}")
                    kwargs.pop(time_field, None)
        
        destination_ids = kwargs.pop('destination_ids', [])
        async for db in get_db():
            rule = ForwardRule(
                name=name,
                source_chat_id=source_chat_id,
                source_chat_name=source_chat_name,
                **kwargs
            )
            if destination_ids:
                rule.delivery_targets = list((await db.scalars(
                    select(DeliveryTarget).where(
                        DeliveryTarget.id.in_(destination_ids),
                        DeliveryTarget.is_active.is_(True),
                        DeliveryTarget.is_deleted.is_(False),
                    )
                )).all())
            if not rule.delivery_targets:
                raise ValueError("至少选择一个可用的发送目标")
            
            db.add(rule)
            await db.commit()
            await db.refresh(rule, attribute_names=["delivery_targets"])
            
            logger.info(f"✅ 创建转发规则成功: {rule.name}, ID: {rule.id}")
            return rule
    
    @staticmethod
    async def get_rule_by_id(rule_id: int) -> Optional[ForwardRule]:
        """根据ID获取规则"""
        async for db in get_db():
            stmt = select(ForwardRule).where(ForwardRule.id == rule_id).options(
                selectinload(ForwardRule.keywords),
                selectinload(ForwardRule.replace_rules),
                selectinload(ForwardRule.delivery_targets),
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
    
    @staticmethod
    @cache_result(ttl=60)  # 缓存1分钟
    async def get_rules_by_source_chat(source_chat_id: str) -> List[ForwardRule]:
        """根据源聊天ID获取规则 - 优化版"""
        async for db in get_db():
            # 优化：使用joinedload减少查询次数，添加索引提示
            stmt = select(ForwardRule).where(
                and_(
                    ForwardRule.source_chat_id == source_chat_id,
                    ForwardRule.is_active == True
                )
            ).options(
                joinedload(ForwardRule.keywords),
                joinedload(ForwardRule.replace_rules),
                joinedload(ForwardRule.delivery_targets),
            ).order_by(ForwardRule.id)  # 添加排序确保结果稳定
            
            result = await db.execute(stmt)
            rules = result.unique().scalars().all()  # unique()去重joinedload的重复结果
            
            logger.debug(f"获取到 {len(rules)} 条活跃规则，源聊天: {source_chat_id}")
            return rules
    
    @staticmethod
    async def get_all_rules() -> List[ForwardRule]:
        """获取所有规则（包括非活跃的）- 优化版"""
        async for db in get_db():
            stmt = select(ForwardRule).options(
                joinedload(ForwardRule.keywords),
                joinedload(ForwardRule.replace_rules),
                joinedload(ForwardRule.delivery_targets),
            ).order_by(ForwardRule.created_at.desc())  # 按创建时间倒序
            
            result = await db.execute(stmt)
            rules = result.unique().scalars().all()
            
            logger.debug(f"获取到 {len(rules)} 条规则")
            return rules

    @staticmethod
    async def get_all_active_rules() -> List[ForwardRule]:
        """获取所有活跃规则"""
        async for db in get_db():
            stmt = select(ForwardRule).where(ForwardRule.is_active == True).options(
                selectinload(ForwardRule.keywords),
                selectinload(ForwardRule.replace_rules),
                selectinload(ForwardRule.delivery_targets),
            )
            result = await db.execute(stmt)
            return result.scalars().all()
    
    @staticmethod
    async def update_rule(rule_id: int, **kwargs) -> bool:
        """更新规则"""
        from database import db_manager
        
        try:
            # 处理时间字段转换
            for time_field in ['start_time', 'end_time']:
                if time_field in kwargs and kwargs[time_field] is not None:
                    time_value = kwargs[time_field]
                    try:
                        kwargs[time_field] = rule_time_to_database_time(time_value)
                    except ValueError as e:
                        logger.warning(f"⚠️ 时间字段 {time_field} 格式无效: {time_value}, 错误: {e}")
                        kwargs.pop(time_field, None)
            
            destination_ids = kwargs.pop('destination_ids', None)

            # 添加更新时间
            kwargs['updated_at'] = get_user_now()
            
            # 使用数据库会话工厂
            if not db_manager.async_session:
                await db_manager.init_db()
            
            async with db_manager.async_session() as db:
                try:
                    if destination_ids is not None:
                        rule_result = await db.execute(
                            select(ForwardRule)
                            .where(ForwardRule.id == rule_id)
                            .options(selectinload(ForwardRule.delivery_targets))
                        )
                        rule = rule_result.scalar_one_or_none()
                        if not rule:
                            return False
                        rule.delivery_targets = list((await db.scalars(
                            select(DeliveryTarget).where(
                                DeliveryTarget.id.in_(destination_ids or [-1]),
                                DeliveryTarget.is_active.is_(True),
                                DeliveryTarget.is_deleted.is_(False),
                            )
                        )).all())
                        if not rule.delivery_targets:
                            raise ValueError("至少选择一个可用的发送目标")

                    # 更新前查询当前值
                    before_stmt = select(ForwardRule.is_active).where(ForwardRule.id == rule_id)
                    before_result = await db.execute(before_stmt)
                    before_value = before_result.scalar_one_or_none()
                    logger.info(f"🔍 更新前规则状态: rule_id={rule_id}, is_active={before_value}")
                    
                    stmt = update(ForwardRule).where(ForwardRule.id == rule_id).values(**kwargs)
                    result = await db.execute(stmt)
                    await db.commit()
                    
                    # 更新后查询验证
                    after_stmt = select(ForwardRule.is_active).where(ForwardRule.id == rule_id)
                    after_result = await db.execute(after_stmt)
                    after_value = after_result.scalar_one_or_none()
                    logger.info(f"🔍 更新后规则状态: rule_id={rule_id}, is_active={after_value}")
                    
                    if result.rowcount > 0:
                        logger.info(f"✅ 更新转发规则成功: {rule_id}, 更新字段: {list(kwargs.keys())}, 影响行数: {result.rowcount}")
                        logger.info(f"📊 状态变化: {before_value} -> {after_value}")
                        
                        # 数据库更新成功，前端将获取实时数据
                        logger.info("✅ 数据库更新完成，前端将获取实时数据")
                        
                        return True
                    else:
                        logger.warning(f"⚠️ 更新转发规则失败: {rule_id}, 没有行被更新")
                        return False
                        
                except Exception as e:
                    logger.error(f"❌ 更新转发规则异常: {rule_id}, 错误: {e}")
                    await db.rollback()
                    raise
                    
        except Exception as e:
            logger.error(f"❌ 数据库连接异常: {e}")
            return False
    
    @staticmethod
    async def delete_rule(rule_id: int) -> bool:
        """删除规则"""
        from database import db_manager
        
        try:
            # 使用数据库会话工厂
            if not db_manager.async_session:
                await db_manager.init_db()
            
            async with db_manager.async_session() as db:
                try:
                    # 检查规则是否存在
                    check_stmt = select(ForwardRule.id).where(ForwardRule.id == rule_id)
                    check_result = await db.execute(check_stmt)
                    existing_rule = check_result.scalar_one_or_none()
                    
                    if not existing_rule:
                        logger.warning(f"⚠️ 规则不存在: rule_id={rule_id}")
                        return False
                    
                    # SQLite does not enforce ON DELETE CASCADE unless the
                    # connection explicitly enables foreign keys.
                    await db.execute(
                        delete(rule_delivery_targets).where(
                            rule_delivery_targets.c.rule_id == rule_id
                        )
                    )

                    # 删除规则
                    stmt = delete(ForwardRule).where(ForwardRule.id == rule_id)
                    result = await db.execute(stmt)
                    await db.commit()
                    
                    if result.rowcount > 0:
                        logger.info(f"✅ 删除转发规则成功: rule_id={rule_id}, 影响行数: {result.rowcount}")
                        return True
                    else:
                        logger.warning(f"⚠️ 删除规则失败，无影响行数: rule_id={rule_id}")
                        return False
                        
                except Exception as e:
                    logger.error(f"❌ 删除规则数据库操作异常: rule_id={rule_id}, 错误: {e}")
                    await db.rollback()
                    raise
                    
        except Exception as e:
            logger.error(f"❌ 删除规则异常: rule_id={rule_id}, 错误: {e}")
            return False
    
    @staticmethod
    async def copy_rule(source_rule_id: int, target_rule_id: Optional[int] = None) -> Optional[ForwardRule]:
        """复制规则"""
        source_rule = await ForwardRuleService.get_rule_by_id(source_rule_id)
        if not source_rule:
            return None
        
        async for db in get_db():
            if target_rule_id:
                # 更新现有规则
                stmt = update(ForwardRule).where(ForwardRule.id == target_rule_id).values(
                    enable_keyword_filter=source_rule.enable_keyword_filter,
                    enable_regex_replace=source_rule.enable_regex_replace,
                    enable_media=source_rule.enable_media,
                    forward_delay=source_rule.forward_delay,
                    max_message_length=source_rule.max_message_length,
                    enable_link_preview=source_rule.enable_link_preview
                )
                await db.execute(stmt)
                
                # 复制关键词
                await KeywordService.copy_keywords(source_rule_id, target_rule_id)
                # 复制替换规则
                await ReplaceRuleService.copy_replace_rules(source_rule_id, target_rule_id)
                
                await db.commit()
                return await ForwardRuleService.get_rule_by_id(target_rule_id)
            else:
                # 创建新规则
                new_rule = ForwardRule(
                    name=f"{source_rule.name}_copy",
                    source_chat_id=source_rule.source_chat_id,
                    source_chat_name=source_rule.source_chat_name,
                    delivery_mode=source_rule.delivery_mode,
                    enable_keyword_filter=source_rule.enable_keyword_filter,
                    enable_regex_replace=source_rule.enable_regex_replace,
                    enable_media=source_rule.enable_media,
                    forward_delay=source_rule.forward_delay,
                    max_message_length=source_rule.max_message_length,
                    enable_link_preview=source_rule.enable_link_preview
                )
                target_ids = [target.id for target in source_rule.delivery_targets]
                if target_ids:
                    new_rule.delivery_targets = list((await db.scalars(
                        select(DeliveryTarget).where(DeliveryTarget.id.in_(target_ids))
                    )).all())
                
                db.add(new_rule)
                await db.commit()
                await db.refresh(new_rule)
                
                # 复制关键词和替换规则
                await KeywordService.copy_keywords(source_rule_id, new_rule.id)
                await ReplaceRuleService.copy_replace_rules(source_rule_id, new_rule.id)
                
                return new_rule

class KeywordService:
    """关键词服务"""
    
    @staticmethod
    async def add_keyword(rule_id: int, keyword: str, is_regex: bool = False, 
                         is_exclude: bool = False, case_sensitive: bool = False) -> Keyword:
        """添加关键词"""
        async for db in get_db():
            kw = Keyword(
                rule_id=rule_id,
                keyword=keyword,
                is_regex=is_regex,
                is_exclude=is_exclude,
                case_sensitive=case_sensitive
            )
            
            db.add(kw)
            await db.commit()
            await db.refresh(kw)
            
            logger.info(f"添加关键词: {keyword} (规则ID: {rule_id})")
            return kw
    
    @staticmethod
    async def get_keywords_by_rule(rule_id: int) -> List[Keyword]:
        """获取规则的所有关键词"""
        async for db in get_db():
            stmt = select(Keyword).where(Keyword.rule_id == rule_id)
            result = await db.execute(stmt)
            return result.scalars().all()
    
    @staticmethod
    async def delete_keyword(keyword_id: int) -> bool:
        """删除关键词"""
        async for db in get_db():
            stmt = delete(Keyword).where(Keyword.id == keyword_id)
            result = await db.execute(stmt)
            await db.commit()
            
            if result.rowcount > 0:
                logger.info(f"删除关键词: {keyword_id}")
                return True
            return False
    
    @staticmethod
    async def delete_keywords_by_rule(rule_id: int) -> int:
        """删除规则的所有关键词"""
        async for db in get_db():
            stmt = delete(Keyword).where(Keyword.rule_id == rule_id)
            result = await db.execute(stmt)
            await db.commit()
            
            logger.info(f"删除规则 {rule_id} 的所有关键词")
            return result.rowcount
    
    @staticmethod
    async def copy_keywords(source_rule_id: int, target_rule_id: int) -> int:
        """复制关键词"""
        source_keywords = await KeywordService.get_keywords_by_rule(source_rule_id)
        
        async for db in get_db():
            count = 0
            for kw in source_keywords:
                new_kw = Keyword(
                    rule_id=target_rule_id,
                    keyword=kw.keyword,
                    is_regex=kw.is_regex,
                    is_exclude=kw.is_exclude,
                    case_sensitive=kw.case_sensitive
                )
                db.add(new_kw)
                count += 1
            
            await db.commit()
            logger.info(f"复制 {count} 个关键词从规则 {source_rule_id} 到 {target_rule_id}")
            return count

class ReplaceRuleService:
    """替换规则服务"""
    
    @staticmethod
    async def add_replace_rule(rule_id: int, name: str, pattern: str, 
                              replacement: str, priority: int = 0) -> ReplaceRule:
        """添加替换规则"""
        async for db in get_db():
            replace_rule = ReplaceRule(
                rule_id=rule_id,
                name=name,
                pattern=pattern,
                replacement=replacement,
                priority=priority
            )
            
            db.add(replace_rule)
            await db.commit()
            await db.refresh(replace_rule)
            
            logger.info(f"添加替换规则: {name} (规则ID: {rule_id})")
            return replace_rule
    
    @staticmethod
    async def get_replace_rules_by_rule(rule_id: int) -> List[ReplaceRule]:
        """获取规则的所有替换规则"""
        async for db in get_db():
            stmt = select(ReplaceRule).where(
                ReplaceRule.rule_id == rule_id
            ).order_by(ReplaceRule.priority)
            result = await db.execute(stmt)
            return result.scalars().all()
    
    @staticmethod
    async def delete_replace_rule(replace_rule_id: int) -> bool:
        """删除替换规则"""
        async for db in get_db():
            stmt = delete(ReplaceRule).where(ReplaceRule.id == replace_rule_id)
            result = await db.execute(stmt)
            await db.commit()
            
            if result.rowcount > 0:
                logger.info(f"删除替换规则: {replace_rule_id}")
                return True
            return False
    
    @staticmethod
    async def copy_replace_rules(source_rule_id: int, target_rule_id: int) -> int:
        """复制替换规则"""
        source_rules = await ReplaceRuleService.get_replace_rules_by_rule(source_rule_id)
        
        async for db in get_db():
            count = 0
            for rule in source_rules:
                new_rule = ReplaceRule(
                    rule_id=target_rule_id,
                    name=rule.name,
                    pattern=rule.pattern,
                    replacement=rule.replacement,
                    priority=rule.priority,
                    is_active=rule.is_active,
                    is_global=rule.is_global
                )
                db.add(new_rule)
                count += 1
            
            await db.commit()
            logger.info(f"复制 {count} 个替换规则从规则 {source_rule_id} 到 {target_rule_id}")
            return count

class UserSessionService:
    """用户会话服务"""
    
    @staticmethod
    async def create_or_update_session(user_id: int, **kwargs) -> UserSession:
        """创建或更新用户会话"""
        async for db in get_db():
            stmt = select(UserSession).where(UserSession.user_id == user_id)
            result = await db.execute(stmt)
            session = result.scalar_one_or_none()
            
            if session:
                # 更新现有会话
                for key, value in kwargs.items():
                    setattr(session, key, value)
                session.last_activity = get_local_now()
            else:
                # 创建新会话
                session = UserSession(user_id=user_id, **kwargs)
                db.add(session)
            
            await db.commit()
            await db.refresh(session)
            
            return session
    
    @staticmethod
    async def get_session_by_user_id(user_id: int) -> Optional[UserSession]:
        """根据用户ID获取会话"""
        async for db in get_db():
            stmt = select(UserSession).where(UserSession.user_id == user_id)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
    
    @staticmethod
    async def is_admin(user_id: int) -> bool:
        """检查用户是否为管理员"""
        session = await UserSessionService.get_session_by_user_id(user_id)
        return session.is_admin if session else False

class BotSettingsService:
    """机器人设置服务"""
    
    @staticmethod
    async def get_setting(key: str, default_value: str = "") -> str:
        """获取设置值"""
        async for db in get_db():
            stmt = select(BotSettings).where(BotSettings.key == key)
            result = await db.execute(stmt)
            setting = result.scalar_one_or_none()
            
            return setting.value if setting else default_value
    
    @staticmethod
    async def set_setting(key: str, value: str, description: str = "", 
                         data_type: str = "string") -> BotSettings:
        """设置配置值"""
        async for db in get_db():
            stmt = select(BotSettings).where(BotSettings.key == key)
            result = await db.execute(stmt)
            setting = result.scalar_one_or_none()
            
            if setting:
                setting.value = value
                setting.description = description
                setting.data_type = data_type
                setting.updated_at = get_local_now()
            else:
                setting = BotSettings(
                    key=key,
                    value=value,
                    description=description,
                    data_type=data_type
                )
                db.add(setting)
            
            await db.commit()
            await db.refresh(setting)
            
            return setting
    
    @staticmethod
    async def get_all_settings() -> List[BotSettings]:
        """获取所有设置"""
        async for db in get_db():
            stmt = select(BotSettings).order_by(BotSettings.key)
            result = await db.execute(stmt)
            return result.scalars().all()

class MessageProcessingService:
    """消息处理服务"""
    
    def __init__(self):
        self.processor = MessageProcessor()
    
    async def process_message(self, rule: ForwardRule, message_text: str) -> Optional[str]:
        """处理消息"""
        try:
            # 获取关键词和替换规则
            keywords = rule.keywords if rule.enable_keyword_filter else []
            replace_rules = rule.replace_rules if rule.enable_regex_replace else []
            
            # 处理消息
            processed_text = self.processor.process_message(
                message_text, keywords, replace_rules
            )
            
            return processed_text
            
        except Exception as e:
            logger.error(f"消息处理失败: {e}")
            return None
