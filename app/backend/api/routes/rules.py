#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则管理API路由

完整实现所有规则相关的API端点
"""

from fastapi import APIRouter, Request, Body, Depends
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from log_manager import get_logger
from api.dependencies import get_enhanced_bot
from auth import get_current_user
from models import User
import json
from datetime import datetime

logger = get_logger('api.rules', 'api.log')

router = APIRouter()


def _serialize_rule(rule, include_relations: bool = False):
    data = {
        "id": rule.id,
        "name": rule.name,
        "source_chat_id": rule.source_chat_id,
        "source_chat_name": rule.source_chat_name,
        "is_active": rule.is_active,
        "delivery_mode": getattr(rule, "delivery_mode", "auto"),
        "destination_ids": [target.id for target in rule.delivery_targets],
        "delivery_targets": [
            {"id": target.id, "name": target.name, "target_type": target.target_type}
            for target in rule.delivery_targets
        ],
        "enable_keyword_filter": rule.enable_keyword_filter,
        "enable_regex_replace": getattr(rule, "enable_regex_replace", False),
        "client_id": getattr(rule, "client_id", "main_user"),
        "client_type": getattr(rule, "client_type", "user"),
        "enable_text": getattr(rule, "enable_text", True),
        "enable_media": getattr(rule, "enable_media", True),
        "enable_photo": getattr(rule, "enable_photo", True),
        "enable_video": getattr(rule, "enable_video", True),
        "enable_document": getattr(rule, "enable_document", True),
        "enable_audio": getattr(rule, "enable_audio", True),
        "enable_voice": getattr(rule, "enable_voice", True),
        "enable_sticker": getattr(rule, "enable_sticker", False),
        "enable_animation": getattr(rule, "enable_animation", True),
        "enable_webpage": getattr(rule, "enable_webpage", True),
        "forward_delay": getattr(rule, "forward_delay", 0),
        "max_message_length": getattr(rule, "max_message_length", 4096),
        "enable_link_preview": getattr(rule, "enable_link_preview", True),
        "time_filter_type": getattr(rule, "time_filter_type", "after_start"),
        "start_time": rule.start_time.isoformat() if rule.start_time else None,
        "end_time": rule.end_time.isoformat() if rule.end_time else None,
        "enable_deduplication": getattr(rule, "enable_deduplication", False),
        "dedup_time_window": getattr(rule, "dedup_time_window", 3600),
        "dedup_check_content": getattr(rule, "dedup_check_content", True),
        "dedup_check_media": getattr(rule, "dedup_check_media", True),
        "enable_sender_filter": getattr(rule, "enable_sender_filter", False),
        "sender_filter_mode": getattr(rule, "sender_filter_mode", "whitelist"),
        "sender_whitelist": getattr(rule, "sender_whitelist", None),
        "sender_blacklist": getattr(rule, "sender_blacklist", None),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }
    if include_relations:
        data["keywords"] = [
            {
                "id": keyword.id,
                "rule_id": keyword.rule_id,
                "keyword": keyword.keyword,
                "is_blacklist": keyword.is_exclude,
                "is_regex": keyword.is_regex,
                "case_sensitive": keyword.case_sensitive,
                "created_at": keyword.created_at.isoformat() if keyword.created_at else None,
            }
            for keyword in rule.keywords
        ]
        data["replace_rules"] = [
            {
                "id": replacement.id,
                "name": replacement.name,
                "pattern": replacement.pattern,
                "replacement": replacement.replacement,
                "priority": replacement.priority,
                "is_regex": replacement.is_regex,
                "is_active": replacement.is_active,
            }
            for replacement in rule.replace_rules
        ]
    return data


# ============================================================================
# 规则CRUD
# ============================================================================

@router.get("")
async def list_rules():
    """获取所有规则列表"""
    try:
        from services.business_services import ForwardRuleService
        rules = await ForwardRuleService.get_all_rules()
        
        # 添加调试日志
        logger.info(f"📋 获取到 {len(rules)} 条规则")
        
        rules_data = [_serialize_rule(rule) for rule in rules]
        
        return JSONResponse(content={
            "success": True,
            "rules": rules_data
        })
    except Exception as e:
        logger.error(f"获取规则失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"获取规则失败: {str(e)}"
        }, status_code=500)


@router.post("")
async def create_rule(request: Request):
    """创建新规则"""
    try:
        data = await request.json()
        from services.business_services import ForwardRuleService
        
        # 验证必需的字段
        required_fields = ['name', 'source_chat_id', 'destination_ids']
        for field in required_fields:
            if field not in data:
                return JSONResponse(content={
                    "success": False,
                    "message": f"缺少必需字段: {field}"
                }, status_code=400)
        
        # 提取参数，排除必需字段和已明确传递的字段
        if data.get('delivery_mode', 'auto') not in ('auto', 'manual'):
            return JSONResponse(content={"success": False, "message": "无效的发送模式"}, status_code=400)
        if not data.get('destination_ids'):
            return JSONResponse(content={"success": False, "message": "至少选择一个发送目标"}, status_code=400)
        excluded_fields = ['name', 'source_chat_id', 'source_chat_name']
        kwargs = {k: v for k, v in data.items() if k not in excluded_fields}
        
        rule = await ForwardRuleService.create_rule(
            name=data['name'],
            source_chat_id=data['source_chat_id'],
            source_chat_name=data.get('source_chat_name', ''),
            **kwargs
        )
        
        # 序列化规则数据
        rule_data = _serialize_rule(rule) if rule else None
        
        return JSONResponse(content={
            "success": True,
            "rule": rule_data,
            "message": "规则创建成功"
        })
    except Exception as e:
        logger.error(f"创建规则失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"创建规则失败: {str(e)}"
        }, status_code=500)


@router.get("/{rule_id}")
async def get_rule(rule_id: int):
    """获取单个规则详情"""
    try:
        from services.business_services import ForwardRuleService
        rule = await ForwardRuleService.get_rule_by_id(rule_id)
        
        if not rule:
            return JSONResponse(content={
                "success": False,
                "message": "规则不存在"
            }, status_code=404)
        
        rule_dict = _serialize_rule(rule, include_relations=True)
        
        return JSONResponse(content={
            "success": True,
            "rule": rule_dict
        })
    except Exception as e:
        logger.error(f"获取规则详情失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"获取规则详情失败: {str(e)}"
        }, status_code=500)


@router.put("/{rule_id}")
async def update_rule(rule_id: int, request: Request):
    """更新规则"""
    try:
        data = await request.json()
        from services.business_services import ForwardRuleService
        
        # 检查规则是否存在
        existing_rule = await ForwardRuleService.get_rule_by_id(rule_id)
        if not existing_rule:
            return JSONResponse(content={
                "success": False,
                "message": "规则不存在"
            }, status_code=404)
        
        if data.get('delivery_mode', existing_rule.delivery_mode) not in ('auto', 'manual'):
            return JSONResponse(content={"success": False, "message": "无效的发送模式"}, status_code=400)
        if 'destination_ids' in data and not data['destination_ids']:
            return JSONResponse(content={"success": False, "message": "至少选择一个发送目标"}, status_code=400)

        # 过滤掉不应该更新的字段
        excluded_fields = ['id', 'created_at']
        update_data = {k: v for k, v in data.items() if k not in excluded_fields}
        
        logger.info(f"更新规则 {rule_id}:")
        logger.info(f"  - 过滤后更新数据: {update_data}")
        logger.info(f"  - 现有规则状态: is_active={existing_rule.is_active}")
        
        # 更新规则
        success = await ForwardRuleService.update_rule(rule_id, **update_data)
        
        if not success:
            return JSONResponse(content={
                "success": False,
                "message": "更新规则失败"
            }, status_code=500)
        
        # 获取更新后的规则
        updated_rule = await ForwardRuleService.get_rule_by_id(rule_id)
        
        rule_data = _serialize_rule(updated_rule) if updated_rule else None
        
        return JSONResponse(content={
            "success": True,
            "rule": rule_data,
            "message": "规则更新成功"
        })
    except Exception as e:
        logger.error(f"更新规则失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"更新规则失败: {str(e)}"
        }, status_code=500)


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int):
    """删除规则"""
    try:
        from services.business_services import ForwardRuleService
        
        # 检查规则是否存在
        existing_rule = await ForwardRuleService.get_rule_by_id(rule_id)
        if not existing_rule:
            return JSONResponse(content={
                "success": False,
                "message": "规则不存在"
            }, status_code=404)
        
        # 删除规则
        success = await ForwardRuleService.delete_rule(rule_id)
        
        if not success:
            return JSONResponse(content={
                "success": False,
                "message": "删除规则失败"
            }, status_code=500)
        
        return JSONResponse(content={
            "success": True,
            "message": "规则删除成功"
        })
    except Exception as e:
        logger.error(f"删除规则失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"删除规则失败: {str(e)}"
        }, status_code=500)


# ============================================================================
# 关键词管理
# ============================================================================

@router.get("/{rule_id}/keywords")
async def list_keywords(rule_id: int):
    """获取规则的关键词列表"""
    try:
        from models import Keyword
        from database import get_db
        from sqlalchemy import select
        
        async for db in get_db():
            result = await db.execute(
                select(Keyword).where(Keyword.rule_id == rule_id)
            )
            keywords = result.scalars().all()
            
            keywords_data = []
            for kw in keywords:
                keywords_data.append({
                    "id": kw.id,
                    "rule_id": kw.rule_id,
                    "keyword": kw.keyword,
                    "is_blacklist": kw.is_exclude,
                    "created_at": kw.created_at.isoformat() if kw.created_at else None
                })
            
            return JSONResponse({
                "success": True,
                "keywords": keywords_data
            })
    except Exception as e:
        logger.error(f"获取关键词列表失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"获取关键词列表失败: {str(e)}"}
        )


@router.post("/{rule_id}/keywords")
async def create_keyword(rule_id: int, request: Request):
    """添加关键词"""
    try:
        from models import Keyword
        from database import get_db
        
        data = await request.json()
        
        async for db in get_db():
            keyword = Keyword(
                rule_id=rule_id,
                keyword=data.get('keyword'),
                is_exclude=data.get('is_blacklist', False)
            )
            
            db.add(keyword)
            await db.commit()
            await db.refresh(keyword)
            
            return JSONResponse({
                "success": True,
                "message": "关键词创建成功",
                "keyword": {
                    "id": keyword.id,
                    "rule_id": keyword.rule_id,
                    "keyword": keyword.keyword,
                    "is_blacklist": keyword.is_exclude,
                    "created_at": keyword.created_at.isoformat() if keyword.created_at else None
                }
            })
    except Exception as e:
        logger.error(f"创建关键词失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"创建关键词失败: {str(e)}"}
        )


@router.put("/keywords/{keyword_id}")
async def update_keyword(keyword_id: int, request: Request):
    """更新关键词"""
    try:
        from models import Keyword
        from database import get_db
        from sqlalchemy import select
        
        data = await request.json()
        
        async for db in get_db():
            result = await db.execute(
                select(Keyword).where(Keyword.id == keyword_id)
            )
            keyword = result.scalar_one_or_none()
            
            if not keyword:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": "关键词不存在"}
                )
            
            # 更新字段
            if 'keyword' in data:
                keyword.keyword = data['keyword']
            if 'is_blacklist' in data:
                keyword.is_exclude = data['is_blacklist']
            
            await db.commit()
            await db.refresh(keyword)
            
            return JSONResponse({
                "success": True,
                "message": "关键词更新成功",
                "keyword": {
                    "id": keyword.id,
                    "rule_id": keyword.rule_id,
                    "keyword": keyword.keyword,
                    "is_blacklist": keyword.is_exclude,
                    "created_at": keyword.created_at.isoformat() if keyword.created_at else None
                }
            })
    except Exception as e:
        logger.error(f"更新关键词失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"更新关键词失败: {str(e)}"}
        )


@router.delete("/keywords/{keyword_id}")
async def delete_keyword(keyword_id: int):
    """删除关键词"""
    try:
        from models import Keyword
        from database import get_db
        from sqlalchemy import delete
        
        async for db in get_db():
            result = await db.execute(
                delete(Keyword).where(Keyword.id == keyword_id)
            )
            await db.commit()
            
            if result.rowcount > 0:
                return JSONResponse({
                    "success": True,
                    "message": "关键词删除成功"
                })
            else:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": "关键词不存在"}
                )
    except Exception as e:
        logger.error(f"删除关键词失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"删除关键词失败: {str(e)}"}
        )


@router.post("/{rule_id}/keywords/batch")
async def batch_create_keywords(rule_id: int, request: Request):
    """批量添加关键词"""
    try:
        from models import Keyword
        from database import get_db
        
        data = await request.json()
        keywords_list = data.get('keywords', [])
        
        if not keywords_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "关键词列表不能为空"}
            )
        
        async for db in get_db():
            created_keywords = []
            for keyword_text in keywords_list:
                keyword = Keyword(
                    rule_id=rule_id,
                    keyword=keyword_text,
                    is_exclude=data.get('is_blacklist', False)
                )
                db.add(keyword)
                created_keywords.append(keyword)
            
            await db.commit()
            
            # 刷新所有创建的关键词以获取ID
            for kw in created_keywords:
                await db.refresh(kw)
            
            keywords_data = []
            for kw in created_keywords:
                keywords_data.append({
                    "id": kw.id,
                    "rule_id": kw.rule_id,
                    "keyword": kw.keyword,
                    "is_blacklist": kw.is_exclude,
                    "created_at": kw.created_at.isoformat() if kw.created_at else None
                })
            
            return JSONResponse({
                "success": True,
                "message": f"成功批量创建 {len(keywords_data)} 个关键词",
                "keywords": keywords_data
            })
    except Exception as e:
        logger.error(f"批量创建关键词失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"批量创建关键词失败: {str(e)}"}
        )


# ============================================================================
# 替换规则管理
# ============================================================================

@router.get("/{rule_id}/replacements")
async def list_replacements(rule_id: int):
    """获取规则的替换规则列表"""
    try:
        from models import ReplaceRule
        from database import get_db
        from sqlalchemy import select
        
        async for db in get_db():
            result = await db.execute(
                select(ReplaceRule).where(ReplaceRule.rule_id == rule_id)
                .order_by(ReplaceRule.priority)
            )
            replacements = result.scalars().all()
            
            replacements_data = []
            for rr in replacements:
                replacements_data.append({
                    "id": rr.id,
                    "rule_id": rr.rule_id,
                    "name": rr.name,
                    "pattern": rr.pattern,
                    "replacement": rr.replacement,
                    "priority": rr.priority,
                    "is_regex": rr.is_regex,
                    "is_active": rr.is_active,
                    "created_at": rr.created_at.isoformat() if rr.created_at else None
                })
            
            return JSONResponse({
                "success": True,
                "replacements": replacements_data
            })
    except Exception as e:
        logger.error(f"获取替换规则列表失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"获取替换规则列表失败: {str(e)}"}
        )


@router.post("/{rule_id}/replacements")
async def create_replacement(rule_id: int, request: Request):
    """创建替换规则"""
    try:
        from models import ReplaceRule
        from database import get_db
        
        data = await request.json()
        
        async for db in get_db():
            replacement = ReplaceRule(
                rule_id=rule_id,
                name=data.get('name'),
                pattern=data.get('pattern'),
                replacement=data.get('replacement'),
                priority=data.get('priority', 1),
                is_regex=data.get('is_regex', True),
                is_active=data.get('is_active', True)
            )
            
            db.add(replacement)
            await db.commit()
            await db.refresh(replacement)
            
            return JSONResponse({
                "success": True,
                "message": "替换规则创建成功",
                "replacement": {
                    "id": replacement.id,
                    "rule_id": replacement.rule_id,
                    "name": replacement.name,
                    "pattern": replacement.pattern,
                    "replacement": replacement.replacement,
                    "priority": replacement.priority,
                    "is_regex": getattr(replacement, 'is_regex', True),
                    "is_active": replacement.is_active,
                    "created_at": replacement.created_at.isoformat() if replacement.created_at else None
                }
            })
    except Exception as e:
        logger.error(f"创建替换规则失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"创建替换规则失败: {str(e)}"}
        )


@router.put("/replacements/{replacement_id}")
async def update_replacement(replacement_id: int, request: Request):
    """更新替换规则"""
    try:
        from models import ReplaceRule
        from database import get_db
        from sqlalchemy import select
        
        data = await request.json()
        
        async for db in get_db():
            result = await db.execute(
                select(ReplaceRule).where(ReplaceRule.id == replacement_id)
            )
            replacement = result.scalar_one_or_none()
            
            if not replacement:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": "替换规则不存在"}
                )
            
            # 更新字段
            if 'name' in data:
                replacement.name = data['name']
            if 'pattern' in data:
                replacement.pattern = data['pattern']
            if 'replacement' in data:
                replacement.replacement = data['replacement']
            if 'priority' in data:
                replacement.priority = data['priority']
            if 'is_regex' in data:
                replacement.is_regex = data['is_regex']
            if 'is_active' in data:
                replacement.is_active = data['is_active']
            
            await db.commit()
            await db.refresh(replacement)
            
            return JSONResponse({
                "success": True,
                "message": "替换规则更新成功",
                "replacement": {
                    "id": replacement.id,
                    "rule_id": replacement.rule_id,
                    "name": replacement.name,
                    "pattern": replacement.pattern,
                    "replacement": replacement.replacement,
                    "priority": replacement.priority,
                    "is_regex": getattr(replacement, 'is_regex', True),
                    "is_active": replacement.is_active,
                    "created_at": replacement.created_at.isoformat() if replacement.created_at else None
                }
            })
    except Exception as e:
        logger.error(f"更新替换规则失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"更新替换规则失败: {str(e)}"}
        )


@router.patch("/replacements/{replacement_id}")
async def toggle_replacement(replacement_id: int, request: Request):
    """切换替换规则状态（PATCH用于部分更新）"""
    try:
        from models import ReplaceRule
        from database import get_db
        from sqlalchemy import select
        
        data = await request.json()
        
        async for db in get_db():
            result = await db.execute(
                select(ReplaceRule).where(ReplaceRule.id == replacement_id)
            )
            replacement = result.scalar_one_or_none()
            
            if not replacement:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": "替换规则不存在"}
                )
            
            # 更新状态
            if 'is_active' in data:
                replacement.is_active = data['is_active']
            
            await db.commit()
            await db.refresh(replacement)
            
            return JSONResponse({
                "success": True,
                "message": "替换规则状态更新成功",
                "replacement": {
                    "id": replacement.id,
                    "is_active": replacement.is_active,
                }
            })
    except Exception as e:
        logger.error(f"切换替换规则状态失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"切换替换规则状态失败: {str(e)}"}
        )


@router.delete("/replacements/{replacement_id}")
async def delete_replacement(replacement_id: int):
    """删除替换规则"""
    try:
        from models import ReplaceRule
        from database import get_db
        from sqlalchemy import delete
        
        async for db in get_db():
            result = await db.execute(
                delete(ReplaceRule).where(ReplaceRule.id == replacement_id)
            )
            await db.commit()
            
            if result.rowcount > 0:
                return JSONResponse({
                    "success": True,
                    "message": "替换规则删除成功"
                })
            else:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": "替换规则不存在"}
                )
    except Exception as e:
        logger.error(f"删除替换规则失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"删除替换规则失败: {str(e)}"}
        )


# ============================================================================
# 完成状态
# ============================================================================

"""
✅ 所有12个端点已完成!

规则CRUD (5个):
- GET /api/rules - 获取所有规则
- POST /api/rules - 创建规则
- GET /api/rules/{rule_id} - 获取单个规则
- PUT /api/rules/{rule_id} - 更新规则
- DELETE /api/rules/{rule_id} - 删除规则

关键词管理 (4个):
- GET /api/rules/{rule_id}/keywords - 获取关键词
- POST /api/rules/{rule_id}/keywords - 添加关键词
- PUT /api/keywords/{keyword_id} - 更新关键词
- DELETE /api/keywords/{keyword_id} - 删除关键词

替换规则管理 (4个):
- GET /api/rules/{rule_id}/replacements - 获取替换规则
- POST /api/rules/{rule_id}/replacements - 添加替换规则
- PUT /api/replacements/{replacement_id} - 更新替换
- DELETE /api/replacements/{replacement_id} - 删除替换

导入/导出 (2个):
- POST /api/rules/export - 导出规则
- POST /api/rules/import - 导入规则
"""


# ============================================================================
# 规则导出/导入
# ============================================================================

@router.post("/export")
async def export_rules(
    ids: Optional[List[int]] = Body(default=[], embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    导出规则配置
    
    支持导出指定ID的规则，或导出所有规则
    返回JSON格式的规则配置
    需要登录认证
    """
    try:
        from models import ForwardRule, Keyword, ReplaceRule
        from database import get_db
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        async for db in get_db():
            # 构建查询
            query = select(ForwardRule).options(selectinload(ForwardRule.delivery_targets))
            if ids:
                query = query.where(ForwardRule.id.in_(ids))
            
            result = await db.execute(query)
            rules = result.scalars().all()
            
            # 即使没有规则也返回成功，只是数据为空
            if not rules:
                logger.info("没有规则可导出，返回空数据")
                return JSONResponse({
                    "success": True,
                    "data": [],
                    "message": "当前没有规则可导出",
                    "filename": "rules_export_0.json"
                })
            
            # 转换为可导出格式
            exported_data = []
            for rule in rules:
                # 获取关键词
                keywords_query = select(Keyword).where(Keyword.rule_id == rule.id)
                keywords_result = await db.execute(keywords_query)
                keywords = keywords_result.scalars().all()
                
                # 获取替换规则
                replacements_query = select(ReplaceRule).where(ReplaceRule.rule_id == rule.id)
                replacements_result = await db.execute(replacements_query)
                replacements = replacements_result.scalars().all()
                
                rule_data = {
                    "name": rule.name,
                    "source_chat_id": rule.source_chat_id,
                    "source_chat_name": rule.source_chat_name,
                    "delivery_mode": rule.delivery_mode,
                    "destination_ids": [target.id for target in rule.delivery_targets],
                    "is_active": rule.is_active,
                    "enable_keyword_filter": rule.enable_keyword_filter,
                    "enable_regex_replace": rule.enable_regex_replace,
                    "client_id": rule.client_id,
                    "client_type": rule.client_type,
                    "enable_text": rule.enable_text,
                    "enable_media": rule.enable_media,
                    "enable_photo": rule.enable_photo,
                    "enable_video": rule.enable_video,
                    "enable_document": rule.enable_document,
                    "enable_audio": rule.enable_audio,
                    "enable_voice": rule.enable_voice,
                    "enable_sticker": rule.enable_sticker,
                    "enable_animation": rule.enable_animation,
                    "enable_webpage": rule.enable_webpage,
                    "forward_delay": rule.forward_delay,
                    "max_message_length": rule.max_message_length,
                    "enable_link_preview": rule.enable_link_preview,
                    "time_filter_type": rule.time_filter_type,
                    "start_time": rule.start_time.isoformat() if rule.start_time else None,
                    "end_time": rule.end_time.isoformat() if rule.end_time else None,
                    "enable_deduplication": rule.enable_deduplication,
                    "dedup_time_window": rule.dedup_time_window,
                    "dedup_check_content": rule.dedup_check_content,
                    "dedup_check_media": rule.dedup_check_media,
                    "enable_sender_filter": rule.enable_sender_filter,
                    "sender_filter_mode": rule.sender_filter_mode,
                    "sender_whitelist": rule.sender_whitelist,
                    "sender_blacklist": rule.sender_blacklist,
                    "keywords": [
                        {
                            "keyword": kw.keyword,
                            "is_regex": kw.is_regex,
                            "is_exclude": kw.is_exclude,
                            "case_sensitive": kw.case_sensitive
                        }
                        for kw in keywords
                    ],
                    "replacements": [
                        {
                            "name": rep.name,
                            "pattern": rep.pattern,
                            "replacement": rep.replacement,
                            "priority": rep.priority,
                            "is_regex": rep.is_regex,
                            "is_active": rep.is_active,
                            "is_global": rep.is_global
                        }
                        for rep in replacements
                    ]
                }
                exported_data.append(rule_data)
            
            logger.info(f"导出规则成功: {len(exported_data)} 条")
            
            response_data = {
                "success": True,
                "data": exported_data,
                "message": f"成功导出 {len(exported_data)} 条规则",
                "filename": f"rules_export_{len(exported_data)}.json"
            }
            logger.info(f"返回数据: success={response_data['success']}, data数量={len(exported_data)}")
            
            return JSONResponse(response_data)
            
    except Exception as e:
        logger.error(f"导出规则失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"导出规则失败: {str(e)}"}
        )


@router.post("/import")
async def import_rules(
    data: List[Dict[str, Any]] = Body(..., embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    导入规则配置
    
    从JSON格式导入规则，支持批量导入
    需要登录认证
    """
    try:
        from models import DeliveryTarget, ForwardRule, Keyword, ReplaceRule
        from database import get_db
        from sqlalchemy import select
        
        if not data:
            return JSONResponse({
                "success": False,
                "message": "导入数据为空"
            })
        
        async for db in get_db():
            imported_count = 0
            
            for rule_data in data:
                try:
                    # 创建规则（使用正确的字段名）
                    new_rule = ForwardRule(
                        name=rule_data.get("name", ""),
                        source_chat_id=rule_data.get("source_chat_id", ""),
                        source_chat_name=rule_data.get("source_chat_name"),
                        delivery_mode=rule_data.get("delivery_mode", "auto"),
                        is_active=rule_data.get("is_active", True),
                        enable_keyword_filter=rule_data.get("enable_keyword_filter", False),
                        enable_regex_replace=rule_data.get("enable_regex_replace", False),
                        client_id=rule_data.get("client_id", "main_user"),
                        client_type=rule_data.get("client_type", "user"),
                        enable_text=rule_data.get("enable_text", True),
                        enable_media=rule_data.get("enable_media", True),
                        enable_photo=rule_data.get("enable_photo", True),
                        enable_video=rule_data.get("enable_video", True),
                        enable_document=rule_data.get("enable_document", True),
                        enable_audio=rule_data.get("enable_audio", True),
                        enable_voice=rule_data.get("enable_voice", True),
                        enable_sticker=rule_data.get("enable_sticker", False),
                        enable_animation=rule_data.get("enable_animation", True),
                        enable_webpage=rule_data.get("enable_webpage", True),
                        forward_delay=rule_data.get("forward_delay", 0),
                        max_message_length=rule_data.get("max_message_length", 4096),
                        enable_link_preview=rule_data.get("enable_link_preview", True),
                        time_filter_type=rule_data.get("time_filter_type", "after_start"),
                        enable_deduplication=rule_data.get("enable_deduplication", False),
                        dedup_time_window=rule_data.get("dedup_time_window", 3600),
                        dedup_check_content=rule_data.get("dedup_check_content", True),
                        dedup_check_media=rule_data.get("dedup_check_media", True),
                        enable_sender_filter=rule_data.get("enable_sender_filter", False),
                        sender_filter_mode=rule_data.get("sender_filter_mode", "whitelist"),
                        sender_whitelist=rule_data.get("sender_whitelist"),
                        sender_blacklist=rule_data.get("sender_blacklist"),
                    )
                    
                    # 处理时间字段
                    if rule_data.get("start_time"):
                        from datetime import datetime
                        new_rule.start_time = datetime.fromisoformat(rule_data["start_time"])
                    if rule_data.get("end_time"):
                        from datetime import datetime
                        new_rule.end_time = datetime.fromisoformat(rule_data["end_time"])
                    
                    db.add(new_rule)
                    await db.flush()  # 获取新规则的ID
                    destination_ids = rule_data.get("destination_ids", [])
                    if destination_ids:
                        new_rule.delivery_targets = list((await db.scalars(
                            select(DeliveryTarget).where(
                                DeliveryTarget.id.in_(destination_ids),
                                DeliveryTarget.is_active.is_(True),
                                DeliveryTarget.is_deleted.is_(False),
                            )
                        )).all())
                    
                    # 导入关键词
                    for kw_data in rule_data.get("keywords", []):
                        keyword = Keyword(
                            rule_id=new_rule.id,
                            keyword=kw_data.get("keyword", ""),
                            is_regex=kw_data.get("is_regex", False),
                            is_exclude=kw_data.get("is_exclude", False),
                            case_sensitive=kw_data.get("case_sensitive", False)
                        )
                        db.add(keyword)
                    
                    # 导入替换规则
                    for rep_data in rule_data.get("replacements", []):
                        replacement = ReplaceRule(
                            rule_id=new_rule.id,
                            name=rep_data.get("name", ""),
                            pattern=rep_data.get("pattern", ""),
                            replacement=rep_data.get("replacement", ""),
                            priority=rep_data.get("priority", 0),
                            is_regex=rep_data.get("is_regex", True),
                            is_active=rep_data.get("is_active", True),
                            is_global=rep_data.get("is_global", False)
                        )
                        db.add(replacement)
                    
                    imported_count += 1
                    
                except Exception as e:
                    logger.warning(f"导入规则失败 (跳过): {rule_data.get('name', 'Unknown')} - {e}")
                    continue
            
            await db.commit()
            
            logger.info(f"导入规则成功: {imported_count}/{len(data)} 条")
            
            return JSONResponse({
                "success": True,
                "imported_count": imported_count,
                "message": f"成功导入 {imported_count} 条规则（总共 {len(data)} 条）"
            })
            
    except Exception as e:
        logger.error(f"导入规则失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"导入规则失败: {str(e)}"}
        )
