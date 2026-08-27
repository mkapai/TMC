#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移完整性检查脚本

检查数据库表结构是否与模型定义一致
"""

import sys
from sqlalchemy import inspect, create_engine
from sqlalchemy.engine import reflection
from models import (
    DeliveryJob, DeliveryTarget, ForwardRule, MessageResource,
    QueuedMessage, TelegramClient, User,
)
from database import DATABASE_URL

def check_table_columns(engine, table_name, model_class):
    """检查表的列是否与模型一致"""
    inspector = inspect(engine)
    
    # 获取数据库中的列
    db_columns = {col['name']: col for col in inspector.get_columns(table_name)}
    
    # 获取模型中的列
    model_columns = {col.name: col for col in model_class.__table__.columns}
    
    issues = []
    
    # 检查缺失的列
    missing_columns = set(model_columns.keys()) - set(db_columns.keys())
    if missing_columns:
        issues.append(f"  ❌ 缺失列: {', '.join(missing_columns)}")
    
    # 检查多余的列
    extra_columns = set(db_columns.keys()) - set(model_columns.keys())
    if extra_columns:
        issues.append(f"  ⚠️  多余列: {', '.join(extra_columns)}")
    
    return issues

def check_indexes(engine, table_name):
    """检查表的索引"""
    inspector = inspect(engine)
    indexes = inspector.get_indexes(table_name)
    
    if indexes:
        print(f"  ✅ 索引: {len(indexes)} 个")
        for idx in indexes:
            print(f"     - {idx['name']}: {idx['column_names']}")
    else:
        print(f"  ℹ️  无索引")

def check_foreign_keys(engine, table_name):
    """检查表的外键"""
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys(table_name)
    
    if fks:
        print(f"  ✅ 外键: {len(fks)} 个")
        for fk in fks:
            print(f"     - {fk['name']}: {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
    else:
        print(f"  ℹ️  无外键")

def main():
    """主函数"""
    print("🔍 开始检查数据库迁移完整性...\n")
    
    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)
        
        # 要检查的表和模型映射
        tables_to_check = {
            'forward_rules': ForwardRule,
            'telegram_clients': TelegramClient,
            'users': User,
            'delivery_targets': DeliveryTarget,
            'queued_messages': QueuedMessage,
            'message_resources': MessageResource,
            'delivery_jobs': DeliveryJob,
        }
        
        all_issues = []
        
        for table_name, model_class in tables_to_check.items():
            print(f"📋 检查表: {table_name}")
            
            # 检查表是否存在
            if table_name not in inspector.get_table_names():
                print(f"  ❌ 表不存在！\n")
                all_issues.append(f"{table_name}: 表不存在")
                continue
            
            # 检查列
            issues = check_table_columns(engine, table_name, model_class)
            if issues:
                all_issues.extend([f"{table_name}: {issue}" for issue in issues])
                for issue in issues:
                    print(issue)
            else:
                print(f"  ✅ 所有列匹配")
            
            # 检查索引
            check_indexes(engine, table_name)
            
            # 检查外键
            check_foreign_keys(engine, table_name)
            
            print()
        
        # 总结
        print("=" * 60)
        if all_issues:
            print(f"❌ 发现 {len(all_issues)} 个问题：")
            for issue in all_issues:
                print(f"  - {issue}")
            sys.exit(1)
        else:
            print("✅ 所有表结构检查通过！")
            sys.exit(0)
            
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()

